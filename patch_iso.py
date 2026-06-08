#!/usr/bin/env python3
"""
patch_iso.py - Patches the original PS2 ISO in-place by:
1. Finding the LBA of SLPS_251.96 in the original ISO filesystem
2. Patching only the changed bytes from the modified ELF (same-size file)
3. Writing the full new CDIMAGE.BIN at its original LBA position (may be smaller)

This avoids rebuilding the ISO (which would change file positions and break
hardcoded LBA references in the game's streaming audio/video engine).
"""
import struct, sys, os, shutil, subprocess

ORIGINAL_ISO = "Venus & Braves - Majo to Megami to Horobi no Yogen (Japan).iso"
OUTPUT_ISO   = "venus_braves_translated.iso"
SECTOR_SIZE  = 2048

def find_all_files_in_iso(iso_path):
    """Walk ISO 9660 filesystem and return all (name, lba, size) tuples."""
    with open(iso_path, 'rb') as f:
        f.seek(16 * SECTOR_SIZE)
        pvd = f.read(SECTOR_SIZE)
        root_lba  = struct.unpack_from('<I', pvd, 156 + 2)[0]
        root_size = struct.unpack_from('<I', pvd, 156 + 10)[0]
        return _collect_files(f, root_lba, root_size)

def _collect_files(f, lba, size):
    f.seek(lba * SECTOR_SIZE)
    data = f.read(size)
    results = []
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            pos += 1
            continue
        entry = data[pos:pos+rec_len]
        if len(entry) < 34:
            break
        file_lba  = struct.unpack_from('<I', entry, 2)[0]
        file_size = struct.unpack_from('<I', entry, 10)[0]
        flags     = entry[25]
        name_len  = entry[32]
        name      = entry[33:33+name_len].decode('ascii', errors='replace').split(';')[0]
        if name not in ('\x00', '\x01'):
            results.append((name, file_lba, file_size))
            if flags & 2:
                saved = f.tell()
                results.extend(_collect_files(f, file_lba, file_size))
                f.seek(saved)
        pos += rec_len
    return results

def find_file_in_iso(iso_path, filename):
    """Walk ISO 9660 filesystem to find a file and return (lba, size)."""
    for name, lba, size in find_all_files_in_iso(iso_path):
        if name.upper() == filename.upper():
            return lba, size
    return None, None

def get_max_extent(iso_path, file_lba):
    """Return the max bytes writable at file_lba before hitting the next file."""
    all_files = find_all_files_in_iso(iso_path)
    all_lbas = sorted(set(f[1] for f in all_files if f[1] > file_lba))
    if all_lbas:
        next_lba = all_lbas[0]
        return (next_lba - file_lba) * SECTOR_SIZE
    # No file after — use ISO size
    return os.path.getsize(iso_path) - file_lba * SECTOR_SIZE

def _walk_dir(f, lba, size, target):
    f.seek(lba * SECTOR_SIZE)
    data = f.read(size)
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            pos += 1
            continue
        entry = data[pos:pos+rec_len]
        if len(entry) < 34:
            break
        file_lba  = struct.unpack_from('<I', entry, 2)[0]
        file_size = struct.unpack_from('<I', entry, 10)[0]
        flags     = entry[25]
        name_len  = entry[32]
        name      = entry[33:33+name_len].decode('ascii', errors='replace')
        bare = name.split(';')[0]
        if bare == target:
            return file_lba, file_size
        if (flags & 2) and bare not in ('\x00', '\x01'):
            saved = f.tell()
            result = _walk_dir(f, file_lba, file_size, target)
            f.seek(saved)
            if result[0] is not None:
                return result
        pos += rec_len
    return None, None

def patch_same_size(output_iso, file_lba, original_data, patched_data):
    """Write only the changed bytes (for same-size files like SLPS_251.96)."""
    assert len(original_data) == len(patched_data), "File sizes must match"
    file_offset = file_lba * SECTOR_SIZE
    changes = [(i, patched_data[i]) for i in range(len(original_data))
               if original_data[i] != patched_data[i]]
    print(f"  Patching {len(changes)} changed bytes at ISO offset 0x{file_offset:X} (LBA {file_lba})")
    with open(output_iso, 'r+b') as f:
        for (rel_offset, new_byte) in changes:
            f.seek(file_offset + rel_offset)
            f.write(bytes([new_byte]))
    print(f"  Done.")

def write_file_at_lba(output_iso, file_lba, orig_size, new_data, max_extent=None):
    """
    Write new_data at the given LBA position.
    If new_data is smaller than orig_size, zero-pad the remainder.
    If new_data is larger than max_extent, abort to avoid corrupting adjacent files.
    """
    file_offset = file_lba * SECTOR_SIZE
    if max_extent is not None and len(new_data) > max_extent:
        print(f"  ERROR: New data ({len(new_data):,} bytes) exceeds available space")
        print(f"         before next file ({max_extent:,} bytes).")
        print(f"         Overflow: {len(new_data) - max_extent:,} bytes would corrupt adjacent data.")
        print(f"         Aborting to prevent ISO corruption.")
        return False
    pad = max(0, orig_size - len(new_data))
    delta = len(new_data) - orig_size
    if delta > 0:
        print(f"  NOTE: New data is {delta:,} bytes LARGER than original ISO record.")
        if max_extent is not None:
            print(f"  Slack available before next file: {max_extent - orig_size:,} bytes — OK.")
    print(f"  Writing {len(new_data):,} bytes at ISO offset 0x{file_offset:X} (LBA {file_lba})")
    if pad > 0:
        print(f"  Zero-padding {pad:,} trailing bytes to fill original allocation")
    CHUNK = 8 * 1024 * 1024  # 8MB chunks
    with open(output_iso, 'r+b') as f:
        f.seek(file_offset)
        written = 0
        while written < len(new_data):
            chunk = new_data[written:written+CHUNK]
            f.write(chunk)
            written += len(chunk)
            print(f"\r  Progress: {written/1024/1024:.0f} / {len(new_data)/1024/1024:.0f} MB", end='', flush=True)
        if pad > 0:
            zero_written = 0
            while zero_written < pad:
                to_write = min(CHUNK, pad - zero_written)
                f.write(b'\x00' * to_write)
                zero_written += to_write
    print(f"\n  Done.")
    return True

def main():
    print(f"Source ISO: {ORIGINAL_ISO}")
    print(f"Output ISO: {OUTPUT_ISO}")
    print()

    # 1. Clone original ISO (APFS copy-on-write — instant, minimal disk usage)
    if os.path.exists(OUTPUT_ISO):
        print(f"Output already exists — removing.")
        os.remove(OUTPUT_ISO)
    print(f"Cloning original ISO -> {OUTPUT_ISO} (APFS CoW) ...")
    result = subprocess.run(
        ["cp", "-c", ORIGINAL_ISO, OUTPUT_ISO],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"APFS clone failed ({result.stderr.strip()}), falling back to full copy...")
        shutil.copy2(ORIGINAL_ISO, OUTPUT_ISO)
    print(f"Clone done. Size: {os.path.getsize(OUTPUT_ISO):,} bytes")
    print()

    # 2. Patch SLPS_251.96 (same-size — byte-diff only)
    elf_patched = "extracted_iso/SLPS_251.96"
    elf_orig    = "SLPS_251.96.orig"
    if os.path.exists(elf_patched) and os.path.exists(elf_orig):
        lba, size = find_file_in_iso(ORIGINAL_ISO, "SLPS_251.96")
        if lba is None:
            print("ERROR: Could not find SLPS_251.96 in ISO")
            return 1
        print(f"SLPS_251.96: LBA={lba}, orig_size={size:,}")
        with open(elf_orig, 'rb') as f:
            orig_data = f.read()
        with open(elf_patched, 'rb') as f:
            patch_data = f.read()
        assert len(orig_data) == size, f"ELF orig size mismatch: {len(orig_data)} vs {size}"
        assert len(patch_data) == size, f"ELF patched size mismatch: {len(patch_data)} vs {size}"
        patch_same_size(OUTPUT_ISO, lba, orig_data, patch_data)
    else:
        print("Skipping SLPS_251.96 patch (files not found)")
    print()

    # 3. Write new CDIMAGE.BIN at its original LBA (may be smaller than original)
    cdimage_patched = "extracted_iso/IMAGE/CDIMAGE.BIN"
    cdimage_orig    = "CDIMAGE.BIN.orig"
    if os.path.exists(cdimage_patched) and os.path.exists(cdimage_orig):
        lba, size = find_file_in_iso(ORIGINAL_ISO, "CDIMAGE.BIN")
        if lba is None:
            print("ERROR: Could not find CDIMAGE.BIN in ISO")
        else:
            print(f"CDIMAGE.BIN: LBA={lba}, orig_size={size:,}")
            with open(cdimage_patched, 'rb') as f:
                new_data = f.read()
            max_extent = get_max_extent(ORIGINAL_ISO, lba)
            delta_kb = (size - len(new_data)) // 1024
            sign = "smaller" if delta_kb >= 0 else "LARGER"
            print(f"  New size: {len(new_data):,} bytes  ({abs(delta_kb)} KB {sign} than original)")
            print(f"  Max writable before next file: {max_extent:,} bytes")
            if not write_file_at_lba(OUTPUT_ISO, lba, size, new_data, max_extent=max_extent):
                print("\nERROR: CDIMAGE.BIN is too large to fit in the ISO allocation.")
                print("The repacked CDIMAGE must be <= the original size to avoid")
                print("corrupting adjacent files (MOVIMAGE.BIN).")
                return 1
    else:
        print(f"Skipping CDIMAGE.BIN (orig={os.path.exists(cdimage_orig)}, patched={os.path.exists(cdimage_patched)})")
    print()

    print("✓ All patches applied. Output ISO ready:")
    print(f"  {OUTPUT_ISO}  ({os.path.getsize(OUTPUT_ISO)/1024/1024/1024:.2f} GB)")
    return 0

if __name__ == '__main__':
    sys.exit(main())
