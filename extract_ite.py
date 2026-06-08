#!/usr/bin/env python3
"""
extract_ite.py  –  Venus & Braves ITE texture extractor (v3)
=============================================================
ITE entry format (corrected after binary analysis):

  Offset  Size  Description
  ------  ----  -----------
  0x00     4    Magic "ITE\x00"
  0x04     4    Display width  (pixels)
  0x08     4    Display height (pixels)
  0x0C     4    Flags / format hint (usually 0)
  0x10    32    Up to 8 VRAM destination addresses (u32, high-bit = valid flag)
  0x30    ???   Pixel data blocks (GS upload payload, concatenated)

The VRAM addresses at 0x10–0x2C are NOT byte offsets into the payload;
they are the GS VRAM destination for each block (in units that are later
used by the GS DMA engine).  The sub-block sizes are uniform:
  sub-block size = (next_addr – current_addr) * 16  (bytes) roughly,
but practically the easiest approach is to treat the data from 0x30 to the
end of the ITE entry as a single flat payload and try all pixel formats.

The pixel data is stored in PS2 block-interleaved (swizzled) format.
For PSMT8 (8-bit indexed): each 16×8 pixel block = 128 bytes, 
  arranged within a 128×64 pixel page in a specific column-interleaved order.
For PSMT4 (4-bit indexed): each 16×16 pixel block = 128 bytes,
  arranged within a 128×128 pixel page similarly.

This script applies the correct PS2 block deswizzle, tries multiple pixel
formats, and saves PNGs.

Usage:
    python3 extract_ite.py [fhm_file] [out_dir]
    python3 extract_ite.py all [out_dir]   # process all screen FHMs
"""

import struct, sys, os, math
from PIL import Image

SCREEN_DIR = "cdimage_unpacked/seven_data_link/futa/screen"

# ── FHM / ITE parsing ─────────────────────────────────────────────────────────

ITE_HDR = 0x30   # pixel data starts 48 bytes into the ITE entry

def parse_fhm(data):
    num = struct.unpack_from('<I', data, 0)[0]
    if not (1 <= num <= 512):
        raise ValueError(f"Bad num_entries={num}")
    return [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(num)]


def parse_ite(entry):
    """Return (w, h, flags, vram_addrs, pixel_data)."""
    if entry[:4] != b'ITE\x00':
        return None
    w     = struct.unpack_from('<I', entry, 0x04)[0]
    h     = struct.unpack_from('<I', entry, 0x08)[0]
    flags = struct.unpack_from('<I', entry, 0x0C)[0]
    vram  = []
    for k in range(8):
        v = struct.unpack_from('<I', entry, 0x10 + k*4)[0]
        if v:
            vram.append(v & 0x7FFFFFFF)
    pixels = entry[ITE_HDR:]
    return w, h, flags, vram, pixels


# ── PS2 block deswizzle ───────────────────────────────────────────────────────
#
# Reference: PS2TEK  https://psi-rockin.github.io/ps2tek/#vramformats
#
# PSMT8 (8 bpp): page = 128×64 pixels, block = 16×8 pixels, 64 blocks/page
#   Column layout of blocks within a page (8 wide × 8 tall):
#     Even columns (in 64-px wide "column" sense) use one interleave,
#     odd columns the other.  The block indices (0-31) within a page
#     follow this pattern:
#
#       col: 0  1  2  3  4  5  6  7
#     row 0: 0  1  4  5 16 17 20 21
#     row 1: 2  3  6  7 18 19 22 23
#     row 2: 8  9 12 13 24 25 28 29
#     row 3:10 11 14 15 26 27 30 31
#     (rows 4-7 mirror rows 0-3 with +32, but PSMT8 page only has 32 blocks)
#
# Each block is 16×8 pixels = 128 bytes, stored linearly (row-major).

PSMT8_BLOCK_TABLE = [
    [ 0,  1,  4,  5, 16, 17, 20, 21],
    [ 2,  3,  6,  7, 18, 19, 22, 23],
    [ 8,  9, 12, 13, 24, 25, 28, 29],
    [10, 11, 14, 15, 26, 27, 30, 31],
    [32, 33, 36, 37, 48, 49, 52, 53],
    [34, 35, 38, 39, 50, 51, 54, 55],
    [40, 41, 44, 45, 56, 57, 60, 61],
    [42, 43, 46, 47, 58, 59, 62, 63],
]

def deswizzle_psmt8(raw, w, h):
    """Deswizzle PS2 PSMT8 texture data."""
    pw = math.ceil(w / 128)   # pages wide
    ph = math.ceil(h / 64)    # pages tall
    page_size = 8192           # 128*64 bytes
    total = pw * ph * page_size

    src = bytearray(raw[:total])
    if len(src) < total:
        src += bytearray(total - len(src))

    out = bytearray(pw * 128 * ph * 64)

    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = src[page_off:page_off + page_size]

            for block_row in range(8):
                for block_col in range(8):
                    block_idx = PSMT8_BLOCK_TABLE[block_row][block_col]
                    src_off   = block_idx * 128
                    block_data = page[src_off:src_off + 128]

                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 64  + block_row *  8

                    for row in range(8):
                        for col in range(16):
                            sx = dst_x + col
                            sy = dst_y + row
                            si = row * 16 + col
                            di = sy * (pw * 128) + sx
                            if si < len(block_data) and di < len(out):
                                out[di] = block_data[si]

    return bytes(out), pw * 128, ph * 64


# PSMT4 (4 bpp): page = 128×128 pixels, block = 16×16 pixels
PSMT4_BLOCK_TABLE = [
    [ 0,  1,  4,  5, 16, 17, 20, 21],
    [ 2,  3,  6,  7, 18, 19, 22, 23],
    [ 8,  9, 12, 13, 24, 25, 28, 29],
    [10, 11, 14, 15, 26, 27, 30, 31],
]

def deswizzle_psmt4(raw, w, h):
    """Deswizzle PS2 PSMT4 texture data (4 bits/pixel, two pixels/byte)."""
    pw = math.ceil(w / 128)
    ph = math.ceil(h / 128)
    page_size = 8192            # 128*128/2 bytes
    total = pw * ph * page_size

    src = bytearray(raw[:total])
    if len(src) < total:
        src += bytearray(total - len(src))

    # Expanded to 1 byte/pixel before deswizzle
    expanded_out = bytearray(pw * 128 * ph * 128)

    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = src[page_off:page_off + page_size]

            for block_row in range(4):
                for block_col in range(8):
                    block_idx = PSMT4_BLOCK_TABLE[block_row][block_col] if block_row < 4 else 0
                    src_byte_off = block_idx * 128  # 16*16/2 = 128 bytes
                    block_data   = page[src_byte_off:src_byte_off + 128]

                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 128 + block_row * 16

                    for row in range(16):
                        for col in range(16):
                            bi  = (row * 16 + col) // 2
                            nib = (row * 16 + col) % 2
                            if bi < len(block_data):
                                v = (block_data[bi] & 0x0F) if nib == 0 else (block_data[bi] >> 4) & 0x0F
                            else:
                                v = 0
                            di = (dst_y + row) * (pw * 128) + (dst_x + col)
                            if di < len(expanded_out):
                                expanded_out[di] = v

    return bytes(expanded_out), pw * 128, ph * 128


# ── CLUT / palette helpers ────────────────────────────────────────────────────

def ps2_alpha(a): return min(255, a * 2)

def unswizzle_clut(raw, n):
    """Swap pairs within 8-entry banks (CSM2 CLUT swizzle for PSMT8)."""
    c = bytearray(raw[:n*4])
    for bank in range(n // 32):
        b = bank * 32 * 4
        c[b+8*4:b+16*4], c[b+16*4:b+24*4] = \
            bytearray(c[b+16*4:b+24*4]), bytearray(c[b+8*4:b+16*4])
    return bytes(c)

def build_palette(clut_bytes, n, swizzle=False):
    if swizzle:
        clut_bytes = unswizzle_clut(clut_bytes, n)
    pal = []
    for i in range(n):
        b, g, r, a = clut_bytes[i*4:i*4+4]
        pal.extend([r, g, b, ps2_alpha(a)])
    return pal


def apply_palette(index_bytes, w, h, palette, bpp=8):
    if bpp == 4:
        # index_bytes already expanded (1 byte/pixel)
        pix = bytes(min(i, len(palette)//4 - 1) for i in index_bytes[:w*h])
    else:
        pix = (index_bytes + bytes(w*h))[:w*h]
    img = Image.frombytes('P', (w, h), pix)
    img.putpalette(palette, rawmode='RGBA')
    return img.convert('RGBA')


# ── image quality check ───────────────────────────────────────────────────────

def looks_real(img):
    if img.width * img.height == 0:
        return False
    px = list(img.getdata())
    visible = sum(1 for r,g,b,a in px if a > 8)
    if visible / len(px) < 0.005:
        return False
    # Not all one value
    rv = [p[0] for p in px if p[3] > 8]
    if not rv:
        return False
    mn, mx = min(rv), max(rv)
    return mx - mn > 4


# ── main extraction ───────────────────────────────────────────────────────────

def extract_entry(ite_data, w, h, prefix, out_dir, verbose=True):
    """Try all pixel format / deswizzle combinations. Save any readable images."""
    saved = []

    def try_save(img, tag):
        if img is None or not looks_real(img):
            return
        # Crop to declared w×h if image is larger
        if img.width > w or img.height > h:
            img = img.crop((0, 0, w, h))
        path = os.path.join(out_dir, f"{prefix}_{tag}.png")
        img.save(path)
        saved.append(tag)
        if verbose:
            print(f"      ✓ {tag}  → {os.path.basename(path)}")

    # ── PSMT8 with deswizzle ─────────────────────────────────────────────
    sw8, sw_w8, sw_h8 = deswizzle_psmt8(ite_data, w, h)
    # Try 256-colour palette (first 1024 bytes of raw as CLUT)
    if len(ite_data) >= 1024:
        for swz in [False, True]:
            pal = build_palette(ite_data[:1024], 256, swizzle=swz)
            img = apply_palette(sw8, sw_w8, sw_h8, pal, bpp=8)
            try_save(img, f"psmt8_dez_{'sw' if swz else 'lin'}_clut_first1k")

    # Grayscale (no CLUT) - just for structure identification
    if sw8:
        raw_gray = bytes(sw8[:sw_w8 * sw_h8])
        img = Image.frombytes('L', (sw_w8, sw_h8), raw_gray).convert('RGBA')
        try_save(img, f"psmt8_dez_gray")

    # ── PSMT4 with deswizzle ─────────────────────────────────────────────
    sw4, sw_w4, sw_h4 = deswizzle_psmt4(ite_data, w, h)
    if len(ite_data) >= 64:
        pal4 = build_palette(ite_data[:64], 16)
        img = apply_palette(sw4, sw_w4, sw_h4, pal4, bpp=4)
        try_save(img, "psmt4_dez_clut_first64")
    # Grayscale
    if sw4:
        gray4 = bytes(b * 17 for b in sw4[:sw_w4 * sw_h4])
        img = Image.frombytes('L', (sw_w4, sw_h4), gray4).convert('RGBA')
        try_save(img, "psmt4_dez_gray")

    # ── Raw (no deswizzle) grayscale ─────────────────────────────────────
    for test_w in sorted(set([w, 128, 256])):
        if test_w <= 0:
            continue
        for bpp in [1, 0.5]:
            npx = int(len(ite_data) / bpp) if bpp >= 1 else len(ite_data) * 2
            rows = npx // test_w
            if 1 <= rows <= h * 4:
                try:
                    if bpp == 1:
                        raw = (ite_data + bytes(rows*test_w))[:rows*test_w]
                        img = Image.frombytes('L', (test_w, rows), raw).convert('RGBA')
                    else:
                        exp = bytearray(test_w * rows)
                        for idx in range(test_w * rows):
                            bi = idx // 2
                            if bi < len(ite_data):
                                nib = (ite_data[bi] & 0x0F) if idx%2==0 \
                                      else (ite_data[bi] >> 4)
                                exp[idx] = nib * 17
                        img = Image.frombytes('L', (test_w, rows), bytes(exp)).convert('RGBA')
                    try_save(img, f"raw_{test_w}x{rows}_{'8bpp' if bpp==1 else '4bpp'}")
                except Exception:
                    pass

    return saved


def extract_fhm(fhm_path, out_dir, verbose=True):
    os.makedirs(out_dir, exist_ok=True)
    with open(fhm_path, 'rb') as f:
        data = f.read()

    offsets = parse_fhm(data)
    basename = os.path.splitext(os.path.basename(fhm_path))[0]

    if verbose:
        print(f"\n{'='*60}")
        print(f"FHM : {fhm_path}")
        print(f"Size: {len(data):,} bytes  |  Entries: {len(offsets)}")
        print('='*60)

    results = {}
    for i, off in enumerate(offsets):
        if off >= len(data):
            continue
        entry_end = offsets[i+1] if i+1 < len(offsets) else len(data)
        entry = data[off:entry_end]

        parsed = parse_ite(entry)
        if parsed is None:
            if verbose:
                print(f"\n  Entry {i:2d}: [{entry[:4].hex()}] skipped")
            continue

        w, h, flags, vram, pixels = parsed

        if verbose:
            print(f"\n  Entry {i:2d} @ 0x{off:06X}  {w}x{h}  "
                  f"total={len(entry):,}  pixels={len(pixels):,}")
            print(f"    vram_addrs: {[hex(v) for v in vram[:4]]}")

        prefix = f"{basename}_e{i:02d}_{w}x{h}"

        # Save raw pixel bytes
        with open(os.path.join(out_dir, f"{prefix}.raw"), 'wb') as rf:
            rf.write(pixels)

        saved = extract_entry(pixels, w, h, prefix, out_dir, verbose=verbose)
        results[i] = (w, h, saved)

        if not saved and verbose:
            print("      (no readable image — likely GS block-swizzled without CLUT)")

    return results


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'all':
        out = sys.argv[2] if len(sys.argv) > 2 else "ite_out"
        for fname in sorted(os.listdir(SCREEN_DIR)):
            if fname.endswith('.fhm'):
                fhm = os.path.join(SCREEN_DIR, fname)
                subdir = os.path.join(out, os.path.splitext(fname)[0])
                extract_fhm(fhm, subdir, verbose=True)
    else:
        fhm = sys.argv[1] if len(sys.argv) > 1 \
            else "cdimage_unpacked/seven_data_link/futa/screen/predict.fhm"
        out = sys.argv[2] if len(sys.argv) > 2 else "ite_out"
        extract_fhm(fhm, out)
