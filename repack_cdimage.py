#!/usr/bin/env python3
import os
import struct
import sys
from pathlib import Path

ALIGNMENT = 0x800

# Max CDIMAGE size: must not exceed original allocation in the ISO
# (MOVIMAGE.BIN starts immediately after, zero slack)
MAX_CDIMAGE_SIZE = 373_645_312

def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + (alignment - 1)) & ~(alignment - 1)

def parse_index_pairs(data: bytes):
    dword_count = len(data) // 4
    dwords = struct.unpack(f"<{dword_count}I", data[: dword_count * 4])
    name_offsets = list(dwords[0::2])
    sizes = list(dwords[1::2])
    
    entry_count = 1
    for i in range(1, len(name_offsets)):
        if name_offsets[i] < name_offsets[i - 1]:
            break
        entry_count += 1
        
    return name_offsets[:entry_count], sizes[:entry_count]

def parse_filelist_names(filelist_blob: bytes):
    names = []
    for part in filelist_blob.split(b"\x00"):
        if len(part) < 4:
            continue
        try:
            text = part.decode("ascii")
        except UnicodeDecodeError:
            continue
        if "/" in text and "." in text:
            names.append(text)
    return names

def main():
    workspace_dir = "/Users/acr/Develop/venus-braves"
    unpacked_dir = Path(os.path.join(workspace_dir, "cdimage_unpacked"))
    output_path = Path(os.path.join(workspace_dir, "extracted_iso/IMAGE/CDIMAGE.BIN"))
    
    template_path = unpacked_dir / "header_template.bin"
    if not template_path.exists():
        print(f"[!] Error: Header template not found at {template_path}")
        sys.exit(1)
        
    template_data = template_path.read_bytes()
    name_offsets, orig_sizes = parse_index_pairs(template_data)
    entry_count = len(orig_sizes)
    
    # Read filelist.bin to parse filenames
    filelist_path = unpacked_dir / "filelist.bin"
    if not filelist_path.exists():
        print(f"[!] Error: filelist.bin not found at {filelist_path}")
        sys.exit(1)
        
    filelist_blob = filelist_path.read_bytes()
    parsed_names = parse_filelist_names(filelist_blob)
    
    names = ["filelist.bin"]
    expected_paths = max(0, entry_count - 1)
    parsed_names = parsed_names[:expected_paths]
    for i in range(1, entry_count):
        idx = i - 1
        if idx < len(parsed_names):
            names.append(parsed_names[idx])
        else:
            names.append(f"unknown/{i:05d}.bin")
            
    print(f"[+] Found {entry_count} entries to repack.")
    
    # Read file contents and update sizes
    new_sizes = []
    file_contents = []
    
    for i, name in enumerate(names):
        filepath = unpacked_dir / name
        if not filepath.exists():
            print(f"[!] Error: Missing file {filepath}")
            sys.exit(1)
            
        content = filepath.read_bytes()
        new_sizes.append(len(content))
        file_contents.append(content)

    # Calculate projected size
    header_raw_size = entry_count * 8
    header_size = align_up(header_raw_size)
    projected = header_size + sum(align_up(s) for s in new_sizes)
    overflow = projected - MAX_CDIMAGE_SIZE

    if overflow > 0:
        print(f"[!] Projected size {projected:,} exceeds budget by {overflow:,} bytes.")
        print(f"[!] Compressing uncompressed ITE entries in FHM files...")
        overflow = _compress_fhm_entries(names, new_sizes, file_contents, overflow)
        if overflow > 0:
            print(f"[!] ERROR: Still {overflow:,} bytes over budget after compression.")
            print(f"[!] Cannot fit CDIMAGE in the ISO allocation.")
            sys.exit(1)

    # Rebuild index table
    index_bytes = bytearray()
    for i in range(entry_count):
        index_bytes.extend(struct.pack('<2I', name_offsets[i], new_sizes[i]))
        
    # Align header to 0x800 bytes
    padding_size = header_size - len(index_bytes)
    header_bytes = index_bytes + b'\x00' * padding_size
    
    # Output file list repacking info
    print(f"[+] Header size: 0x{header_size:X} bytes (Padding: {padding_size} bytes)")
    
    # Open target CDIMAGE.BIN for writing
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f_out:
        # Write header
        f_out.write(header_bytes)
        
        # Write files
        for i, (name, content) in enumerate(zip(names, file_contents)):
            f_out.write(content)
            # Align payload to 0x800
            aligned_size = align_up(len(content))
            pad_len = aligned_size - len(content)
            if pad_len > 0:
                f_out.write(b'\x00' * pad_len)
                
    print(f"[+] Successfully repacked CDIMAGE.BIN to {output_path}")
    print(f"[+] Final CDIMAGE.BIN size: {output_path.stat().st_size} bytes")

# ── LZSS compressor (EI=11, EJ=4) ────────────────────────────────────────────

def _lzss_compress(data):
    N = 2048; THRESHOLD = 2; MAX_MATCH = 17
    buf = bytearray(N); r = N - 18
    out = bytearray(); flags = 0; nbits = 0; coded = bytearray()
    def emit():
        nonlocal flags, coded
        out.append(flags); out.extend(coded)
        flags = 0; coded.clear()
    src = 0
    while src < len(data):
        best_len = 1; best_pos = 0
        for dist in range(1, min(src + 1, N)):
            base = (r - dist) & (N - 1); ml = 0
            while ml < MAX_MATCH and src + ml < len(data):
                if buf[(base + ml) & (N - 1)] != data[src + ml]: break
                ml += 1
            if ml > best_len: best_len = ml; best_pos = base
        if nbits == 8: emit(); nbits = 0
        if best_len >= THRESHOLD:
            lo = best_pos & 0xFF
            hi = ((best_pos >> 8) & 0xF) | ((best_len - 2) << 4)
            coded.extend([lo, hi])
            for k in range(best_len):
                buf[r] = data[src + k]; r = (r + 1) & (N - 1)
            src += best_len
        else:
            flags |= (1 << nbits)
            buf[r] = data[src]; coded.append(data[src])
            r = (r + 1) & (N - 1); src += 1
        nbits += 1
    if nbits > 0: emit()
    return bytes(out)


def _compress_fhm_entries(names, new_sizes, file_contents, overflow_bytes):
    """
    LZSS-compress uncompressed ITE entries within FHM files to reduce size.
    Only processes entries where the ITE header has GS addresses (bit 31 set)
    indicating uncompressed pixel data.  Converts them to compressed ITE format
    (offsets without bit 31).  Returns remaining overflow (<=0 = success).
    """
    ITE_MAGIC = b'ITE\x00'
    ITE_HDR   = 0x30
    remaining = overflow_bytes

    for fi in range(len(names)):
        if remaining <= 0:
            break
        ext = os.path.splitext(names[fi])[1].lower()
        if ext != '.fhm':
            continue

        fhm = bytearray(file_contents[fi])
        n_entries = struct.unpack_from('<I', fhm, 0)[0]
        if not (1 <= n_entries <= 512):
            continue
        offsets = [struct.unpack_from('<I', fhm, 4 + i * 4)[0]
                   for i in range(n_entries)]
        offsets.append(len(fhm))

        changed = False
        for ei in range(n_entries):
            if remaining <= 0:
                break
            e_start = offsets[ei]
            e_end   = offsets[ei + 1]
            entry   = fhm[e_start:e_end]
            if len(entry) < ITE_HDR + 16 or entry[:4] != ITE_MAGIC:
                continue
            first_addr = struct.unpack_from('<I', entry, 0x10)[0]
            if not (first_addr & 0x80000000):
                continue  # already compressed or not GS-addressed

            # This entry has uncompressed GS data — compress its pixel payload
            raw_pixels = entry[ITE_HDR:]
            compressed = _lzss_compress(raw_pixels)

            # Build new compressed ITE:
            #   header (0x30 bytes) + compressed payload
            #   offset[0] = 0x30 (single section), offset[1..7] = 0
            new_hdr = bytearray(entry[:ITE_HDR])
            struct.pack_into('<I', new_hdr, 0x10, ITE_HDR)  # offset to data
            for k in range(1, 8):
                struct.pack_into('<I', new_hdr, 0x10 + k * 4, 0)
            new_entry = bytes(new_hdr) + compressed

            old_sz = len(entry)
            new_sz = len(new_entry)
            if new_sz >= old_sz:
                continue  # compression didn't help

            # Rebuild FHM with the compressed entry
            parts = []
            cur_offsets = []
            pos = 4 + n_entries * 4  # FHM data starts after header
            for j in range(n_entries):
                cur_offsets.append(pos)
                if j == ei:
                    parts.append(new_entry)
                    pos += new_sz
                else:
                    orig_e = fhm[offsets[j]:offsets[j + 1]]
                    parts.append(orig_e)
                    pos += len(orig_e)

            new_fhm = bytearray()
            new_fhm.extend(struct.pack('<I', n_entries))
            for o in cur_offsets:
                new_fhm.extend(struct.pack('<I', o))
            for p in parts:
                new_fhm.extend(p)

            savings = align_up(len(fhm)) - align_up(len(new_fhm))
            print(f"    Compressed {names[fi]} entry [{ei}]: "
                  f"{old_sz:,} → {new_sz:,} bytes "
                  f"(FHM {len(fhm):,} → {len(new_fhm):,}, "
                  f"saves {savings:,} aligned bytes)")

            fhm = new_fhm
            # Re-parse offsets for subsequent entries
            offsets = [struct.unpack_from('<I', fhm, 4 + i * 4)[0]
                       for i in range(n_entries)]
            offsets.append(len(fhm))
            remaining -= savings
            changed = True

        if changed:
            file_contents[fi] = bytes(fhm)
            new_sizes[fi] = len(fhm)

    if remaining <= 0:
        print(f"[+] Compression recovered enough space "
              f"({overflow_bytes:,} bytes needed).")
    return remaining


if __name__ == '__main__':
    main()
