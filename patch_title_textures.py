#!/usr/bin/env python3
"""
patch_title_textures.py
=======================
Finds the menu button text (はじめから / つづきから / オプション) in the GIM
texture inside btlst1.arc, replaces it with English, and re-injects it.

Strategy:
  1. Decompress GIM from btlst1.arc using LZSS
  2. Cross-correlate the decompressed data with the PCSX2 dump PNG to locate
     the pixel buffer offset and pixel format
  3. Paint English text in the right style
  4. Re-compress with LZSS and write back to the arc / ISO
"""

import struct, os, math
from PIL import Image, ImageDraw, ImageFont

ARC_PATH   = "cdimage_unpacked/seven_data_link/taka/title/btlst1.arc"
DUMP_DIR   = "Dump/SLPS-25196/dumps"
OUT_DIR    = "ite_out"

# ── LZSS ─────────────────────────────────────────────────────────────────────

def lzss_decompress(data):
    """LZSS EI=11 EJ=4 LE offset_bias=0 (confirmed for this game)."""
    N, r = 2048, 2048 - 18
    buf  = bytearray(N)
    out  = bytearray()
    pos  = 0
    while pos < len(data):
        flags = data[pos]; pos += 1
        for b in range(8):
            if pos >= len(data): break
            if (flags >> b) & 1:
                c = data[pos]; pos += 1
                out.append(c); buf[r] = c; r = (r+1) & (N-1)
            else:
                if pos+1 >= len(data): break
                lo = data[pos]; hi = data[pos+1]; pos += 2
                mo = lo | ((hi & 0xF) << 8)
                ml = (hi >> 4) + 2
                for k in range(ml):
                    c = buf[(mo+k) & (N-1)]
                    out.append(c); buf[r] = c; r = (r+1) & (N-1)
    return bytes(out)


def lzss_compress(data):
    """LZSS EI=11 EJ=4 LE offset_bias=0 compressor (matching decompressor)."""
    N = 2048
    F = 18        # max match = 2^4 + 2
    THRESHOLD = 2

    r = N - F
    buf = bytearray(N)   # ring buffer (init = 0)

    out_bits  = bytearray()
    flag_byte = 0
    flag_pos  = 0
    coded     = bytearray()

    def flush():
        nonlocal flag_byte, coded
        out_bits.append(flag_byte)
        out_bits.extend(coded)
        flag_byte = 0
        coded.clear()

    bit_count = 0
    src_pos   = 0
    src       = memoryview(data)

    while src_pos < len(data):
        # Find longest match in ring buffer
        best_len = THRESHOLD - 1
        best_off = 0

        # Brute-force search (up to N-1 positions back)
        for dist in range(1, min(src_pos + 1, N)):
            base = (r - dist) & (N - 1)
            ml = 0
            while ml < F and src_pos + ml < len(data):
                if buf[(base + ml) & (N - 1)] != data[src_pos + ml]:
                    break
                ml += 1
            if ml > best_len:
                best_len = ml
                best_off = base

        if best_len >= THRESHOLD:
            # Back-reference
            if bit_count == 8:
                flush(); bit_count = 0
            # bit = 0 → back-reference
            flag_byte |= 0 << bit_count
            bit_count  += 1
            lo = best_off & 0xFF
            hi = ((best_off >> 8) & 0xF) | ((best_len - THRESHOLD) << 4)
            coded.extend([lo, hi])
            for k in range(best_len):
                c = data[src_pos + k]
                buf[r] = c; r = (r+1) & (N-1)
            src_pos += best_len
        else:
            # Literal
            if bit_count == 8:
                flush(); bit_count = 0
            flag_byte |= 1 << bit_count
            bit_count  += 1
            c = data[src_pos]; src_pos += 1
            coded.append(c)
            buf[r] = c; r = (r+1) & (N-1)

    if bit_count > 0:
        flush()

    return bytes(out_bits)


# ── Load reference PCSX2 dump ─────────────────────────────────────────────────

def load_pcsx2_dump(label):
    """Load the PCSX2 dump PNG for a given button label (New Game / Continue / Options)."""
    label_to_file = {
        "New Game": "22256c3d3ca61d7a-00002a80.png",
        "Continue": "7e5db600f94499e8-00002a80.png",
        "Options":  "2ddc468541cd6963-00002a80.png",
    }
    fname = label_to_file.get(label)
    if not fname:
        return None
    path = os.path.join(DUMP_DIR, fname)
    if not os.path.exists(path):
        print(f"  WARNING: PCSX2 dump not found: {path}")
        return None
    return Image.open(path).convert("RGBA")


# ── Analyse the decompressed GIM vs PCSX2 dump ───────────────────────────────

def find_pixel_format_and_offset(decomp_bytes, dump_img):
    """
    Try to locate where in the decompressed GIM the button texture pixels live,
    by testing different pixel formats (RGBA32, RGBA16, PSMT8) and offsets.
    Returns (offset, format_name, width, height) or None.
    """
    dump_arr = list(dump_img.getdata())  # list of (R,G,B,A) tuples, 1024*1024

    # We know from the dump that the button area (first 100x30 pixels at top-left)
    # has specific RGBA32 values.  Sample a few reference pixels that are clearly
    # non-transparent (the button text itself):
    reference_pixels = []
    for y in range(5, 25):
        for x in range(5, 90):
            r, g, b, a = dump_img.getpixel((x, y))
            if a > 100:   # opaque enough to be a text pixel
                reference_pixels.append((x, y, r, g, b, a))
                if len(reference_pixels) >= 10:
                    break
        if len(reference_pixels) >= 10:
            break

    print(f"  Reference pixels from dump: {reference_pixels[:3]}")

    # The PS2 renders at its own resolution then PCSX2 upscales.
    # With upscale_multiplier=1, the dump IS 1x.  The native resolution for this
    # title-screen texture is likely 512x448 or 640x224 (standard PS2).
    # The GIM contains one page of VRAM.  Try treating the raw bytes as:
    #   RGBA32  = 4 bytes/pixel,  width choices: 512, 256, 640
    #   RGBA16  = 2 bytes/pixel,  width choices: 512, 256, 640, 1024
    #   PSMT8   = 1 byte/pixel  (indexed) — we'd need the palette

    formats = [
        ("RGBA32", 4, [512, 256, 640, 1024]),
        ("RGBA16", 2, [512, 256, 640, 1024]),
    ]

    for fmt_name, bpp, widths in formats:
        for w in widths:
            pix_count = len(decomp_bytes) // bpp
            h = pix_count // w
            if h < 30 or h > 2048:
                continue

            # For each reference pixel (x, y, R, G, B, A) from the dump,
            # check if we find a matching value at offset = y*w*bpp + x*bpp
            matched = 0
            for (px, py, pr, pg, pb, pa) in reference_pixels[:5]:
                offset = py * w * bpp + px * bpp
                if offset + bpp > len(decomp_bytes):
                    continue

                if fmt_name == "RGBA32":
                    # PS2 RGBA32 is actually ABGR in memory (little-endian)
                    # or BGRA depending on GS settings
                    b_val = decomp_bytes[offset]
                    g_val = decomp_bytes[offset+1]
                    r_val = decomp_bytes[offset+2]
                    a_val = decomp_bytes[offset+3]
                    # PS2 alpha is 0-128, not 0-255
                    a_scaled = min(255, a_val * 2)
                    # Check if r,g,b values are in roughly the same ballpark
                    if (abs(r_val - pr) < 30 and abs(g_val - pg) < 30 and
                            abs(b_val - pb) < 30 and abs(a_scaled - pa) < 60):
                        matched += 1

                elif fmt_name == "RGBA16":
                    word = struct.unpack_from('<H', decomp_bytes, offset)[0]
                    r_val = (word & 0x1F) << 3
                    g_val = ((word >> 5) & 0x1F) << 3
                    b_val = ((word >> 10) & 0x1F) << 3
                    a_val = 255 if (word >> 15) else 0
                    if (abs(r_val - pr) < 50 and abs(g_val - pg) < 50 and
                            abs(b_val - pb) < 50):
                        matched += 1

            if matched >= 3:
                print(f"  ★ MATCH: {fmt_name} w={w} h={h} matched={matched}/5")
                return (0, fmt_name, w, h)

    print("  No direct pixel-format match found.")
    return None


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. Load the ARC file
    print("Loading btlst1.arc...")
    with open(ARC_PATH, "rb") as f:
        arc = f.read()

    num_entries = struct.unpack_from("<I", arc, 0)[0]
    offsets = [struct.unpack_from("<I", arc, 4 + i*4)[0] for i in range(num_entries)]
    offsets.append(len(arc))  # sentinel for last entry size

    print(f"  {num_entries} entries: {[hex(o) for o in offsets[:-1]]}")

    # 2. Decompress GIM entry 0 (= first GIM, which is the title/menu texture)
    gim_raw = arc[offsets[0]:offsets[1]]
    gim_header = gim_raw[:16]  # "GIM\x00" + 12 bytes header
    gim_body   = gim_raw[16:]

    print(f"\nDecompressing GIM (entry 0)...")
    print(f"  Compressed size: {len(gim_body)} bytes")
    decomp = lzss_decompress(gim_body)
    print(f"  Decompressed:    {len(decomp)} bytes")

    # Save decompressed as raw for inspection
    with open(f"{OUT_DIR}/gim0_decomp.raw", "wb") as f:
        f.write(decomp)

    # 3. Save the raw decompressed data as various width interpretations to find pixels
    print("\nSaving interpreted views...")
    for bpp, fmt, widths in [
        (4, "RGBA32", [512, 256, 640]),
        (2, "RGBA16", [512, 640, 1024]),
        (1, "PSMT8",  [512, 256, 640]),
    ]:
        for w in widths:
            total_px = len(decomp) // bpp
            h = total_px // w
            if h < 10 or h > 2048:
                continue

            if bpp == 4:  # RGBA32 - try BGRA, RGBA, ABGR orderings
                for order, (ri, gi, bi, ai) in [
                    ("BGRA", (2,1,0,3)),
                    ("RGBA", (0,1,2,3)),
                    ("ABGR", (3,2,1,0)),
                ]:
                    px = bytearray(w * h * 4)
                    for i in range(w * h):
                        base = i * 4
                        if base + 3 < len(decomp):
                            px[i*4+0] = decomp[base+ri]
                            px[i*4+1] = decomp[base+gi]
                            px[i*4+2] = decomp[base+bi]
                            px[i*4+3] = min(255, decomp[base+ai] * 2)
                    img = Image.frombytes("RGBA", (w, h), bytes(px))
                    # Only save if the top 100x30 area has content
                    crop = img.crop((0, 0, 100, 30))
                    pix = list(crop.getdata())
                    non_empty = sum(1 for p in pix if p[3] > 30)
                    if non_empty > 5:
                        fname = f"{OUT_DIR}/gim0_{fmt}_{order}_{w}x{h}.png"
                        img.save(fname)
                        print(f"  SAVED (non-empty): {fname} ({non_empty} visible px)")

            elif bpp == 2:  # RGBA16
                px = bytearray(w * h * 4)
                for i in range(w * h):
                    base = i * 2
                    if base + 1 < len(decomp):
                        word = struct.unpack_from('<H', decomp, base)[0]
                        px[i*4+0] = (word & 0x1F) << 3
                        px[i*4+1] = ((word >> 5) & 0x1F) << 3
                        px[i*4+2] = ((word >> 10) & 0x1F) << 3
                        px[i*4+3] = 255 if (word >> 15) else 0
                img = Image.frombytes("RGBA", (w, h), bytes(px))
                crop = img.crop((0, 0, 100, 30))
                pix = list(crop.getdata())
                non_empty = sum(1 for p in pix if p[3] > 30)
                if non_empty > 5:
                    fname = f"{OUT_DIR}/gim0_{fmt}_{w}x{h}.png"
                    img.save(fname)
                    print(f"  SAVED (non-empty): {fname} ({non_empty} visible px)")

            elif bpp == 1:  # PSMT8 (grayscale for now)
                raw = decomp[:w*h]
                img = Image.frombytes("L", (w, h), raw)
                fname = f"{OUT_DIR}/gim0_{fmt}_{w}x{h}.png"
                img.save(fname)

    print("\nDone! Check ite_out/ for the interpreted GIM views.")
    print("Next: find which view shows the menu button text, then we can edit and re-inject.")


if __name__ == "__main__":
    main()
