#!/usr/bin/env python3
"""
encode_ps2_texture.py
=====================
Encodes a modified RGBA PNG (from PCSX2 dump) back into PS2 VRAM format
(PSMT8 / PSMCT32) so it can be re-injected into btlst1.arc.

The pipeline is:
  1. Load original PCSX2 dump PNG (ground truth decoded texture)
  2. Load decompressed GIM entry 0 (raw VRAM data)
  3. Use correlation to find exact pixel format & swizzle offset
  4. Modify pixels (erase Japanese text, draw English)
  5. Re-encode pixels back into VRAM format
  6. Re-compress with LZSS
  7. Patch btlst1.arc

PS2 PSMT8 VRAM layout reference:
  32x16 pixel 'pages', each page = 8x4 'blocks', each block = 4x4 'columns'
  https://psi-rockin.github.io/ps2tek/#gpulocal-transmission
"""

import struct, os, math, shutil
from PIL import Image, ImageDraw, ImageFont

ARC_PATH     = "cdimage_unpacked/seven_data_link/taka/title/btlst1.arc"
DUMP_NEWGAME = "Dump/SLPS-25196/dumps/22256c3d3ca61d7a-00002a80.png"
DUMP_CONT    = "Dump/SLPS-25196/dumps/7e5db600f94499e8-00002a80.png"
DUMP_OPTIONS = "Dump/SLPS-25196/dumps/2ddc468541cd6963-00002a80.png"
OUT_DIR      = "ite_out"

# ── LZSS ─────────────────────────────────────────────────────────────────────

def lzss_decompress(data):
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
    """LZSS EI=11, EJ=4 compressor (slow but correct)."""
    N   = 2048
    F   = 18
    buf = bytearray(N)
    r   = N - F

    out    = bytearray()
    flags  = 0
    nbits  = 0
    coded  = bytearray()

    def emit():
        nonlocal flags, coded
        out.append(flags)
        out.extend(coded)
        flags = 0; coded.clear()

    src = 0
    while src < len(data):
        # Find longest match
        best_len = 1  # literal fallback
        best_pos = 0

        for dist in range(1, min(src + 1, N)):
            base = (r - dist) & (N - 1)
            ml = 0
            while ml < F and src + ml < len(data):
                if buf[(base + ml) & (N - 1)] != data[src + ml]:
                    break
                ml += 1
            if ml > best_len:
                best_len = ml
                best_pos = base

        if nbits == 8:
            emit(); nbits = 0

        if best_len >= 2:
            # back-reference: bit=0
            lo = best_pos & 0xFF
            hi = ((best_pos >> 8) & 0xF) | ((best_len - 2) << 4)
            coded.extend([lo, hi])
            for k in range(best_len):
                c = data[src + k]
                buf[r] = c; r = (r + 1) & (N - 1)
            src += best_len
        else:
            # literal: bit=1
            flags |= (1 << nbits)
            c = data[src]; src += 1
            coded.append(c)
            buf[r] = c; r = (r + 1) & (N - 1)

        nbits += 1

    if nbits > 0:
        emit()

    return bytes(out)


# ── PS2 VRAM swizzle (PSMT8) ─────────────────────────────────────────────────
# Reference: ps2tek, nocash gbatek, PCSX2 source (GSLocalMemory.cpp)

# PSMT8 block layout within a page:
# A page is 128x64 pixels (for PSMT8).
# Within the page, 4x8 blocks of 32x16 pixels each.
# Within a block, 2x8 columns of 16x2 pixels each.

# We'll use the direct address computation from PCSX2's GSLocalMemory.
# For PSMT8:
#   word_addr = base_page * (128*64/4) + block_offset + ...
# This is complex. Let's use a lookup-table approach.

# Precompute the PSMT8 swizzle table for a given texture width/height
# This converts linear (x,y) → byte address in VRAM block format.

# The PS2 PSMT8 byte address computation (from nocash/PCSX2 source):
# page = (y//64) * (width//128) + (x//128)
# block = blockTable8[(y//16)%4][(x//32)%4]   (within page)
# column = (y//2)%8
# in_column_x = x%32
# in_column_y = y%2
# ... + column swizzle

# We'll implement the standard PCSX2 PSMT8 address calculation:

_bt8 = [
    [0, 1, 4, 5, 16, 17, 20, 21],
    [2, 3, 6, 7, 18, 19, 22, 23],
    [8, 9, 12, 13, 24, 25, 28, 29],
    [10, 11, 14, 15, 26, 27, 30, 31],
]

def psmt8_addr(x, y, tbw):
    """
    Compute PSMT8 byte address in VRAM for pixel (x,y) given texture buffer width tbw.
    tbw is in units of 64-pixel pages (tbw = texture_width // 64).
    Returns the byte offset into the VRAM block.
    """
    # Page dimensions for PSMT8: 128x64
    page_x  = x // 128
    page_y  = y // 64
    pages_wide = tbw // 2   # tbw is in 64-pixel units, page is 128 wide
    if pages_wide < 1: pages_wide = 1
    page    = page_y * pages_wide + page_x

    # Block within page (4x4 blocks of 32x16 pixels)
    bx = (x // 32) % 4
    by = (y // 16) % 4
    block_in_page = _bt8[by][bx]

    # Column within block (16 columns of 32x2 pixels)
    col = (y // 2) % 8

    # Pixel within column
    in_x = x % 32
    in_y = y % 2

    # column interleave
    if in_y == 0:
        cx = in_x
    else:
        cx = in_x ^ 16  # alternate columns are XOR-swapped

    byte_in_col = col * 32 + cx

    # addresses
    bytes_per_block = 16 * 32        # 32x16 pixels of PSMT8 = 512 bytes
    bytes_per_page  = 32 * bytes_per_block  # 32 blocks/page
    # Wait, a page is 128*64 = 8192 bytes
    bytes_per_page  = 128 * 64       # 8192 bytes
    bytes_per_block = bytes_per_page // 32  # 256 bytes

    addr = (page * bytes_per_page +
            block_in_page * bytes_per_block +
            byte_in_col)
    return addr


# ── Palette handling ──────────────────────────────────────────────────────────

def build_palette_from_dump_pixels(dump_img, tex_width, tex_height, num_colors=256):
    """
    Build a palette from the unique colors in the PCSX2 dump.
    Returns (palette_rgba, indexed_pixels).
    """
    from PIL import Image as PILImage
    # Quantize the dump to num_colors
    tex = dump_img.crop((0, 0, tex_width, tex_height))
    quantized = tex.quantize(colors=num_colors, dither=PILImage.Dither.NONE)
    palette_data = quantized.getpalette()  # [R,G,B, R,G,B, ...]
    palette_rgba = [(palette_data[i*3], palette_data[i*3+1], palette_data[i*3+2], 255)
                    for i in range(num_colors)]
    pixels = list(quantized.getdata())
    return palette_rgba, pixels


# ── Main ─────────────────────────────────────────────────────────────────────

def get_font(size=14):
    candidates = [
        "/System/Library/Fonts/Supplemental/Palatino.ttc",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Times.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except: pass
    return ImageFont.load_default()


def draw_english_button(img, text):
    """Clear the button text area and draw English text in the same style."""
    draw = ImageDraw.Draw(img)
    # Clear button area (top-left ~100x30 pixels)
    draw.rectangle([0, 0, 99, 29], fill=(0, 0, 0, 0))
    
    font = get_font(14)
    text_color  = (250, 231, 189, 200)
    shadow_col  = (40, 25, 10, 120)
    
    try:
        bb = font.getbbox(text)
        tw, th = bb[2]-bb[0], bb[3]-bb[1]
        ty_off = bb[1]
    except:
        tw, th = font.getsize(text); ty_off = 0
    
    tx = 3
    ty = (30 - th) // 2 - ty_off
    draw.text((tx+1, ty+1), text, font=font, fill=shadow_col)
    draw.text((tx, ty), text, font=font, fill=text_color)
    return img


def encode_psmt8_to_vram(dump_img, vram_buf, tex_w, tex_h, tbw, base_byte_offset, num_colors=256):
    """
    Take the dump_img pixels, quantize to PSMT8, and write them into vram_buf
    using the PSMT8 swizzle starting at base_byte_offset.
    Returns (new_vram_buf, palette_rgba).
    """
    palette_rgba, pixels = build_palette_from_dump_pixels(dump_img, tex_w, tex_h, num_colors)
    
    new_buf = bytearray(vram_buf)
    for y in range(tex_h):
        for x in range(tex_w):
            idx = pixels[y * tex_w + x]
            addr = psmt8_addr(x, y, tbw) + base_byte_offset
            if 0 <= addr < len(new_buf):
                new_buf[addr] = idx
    
    return bytes(new_buf), palette_rgba


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # ── Step 1: Load arc and decompress ──
    print("Loading btlst1.arc ...")
    with open(ARC_PATH, "rb") as f:
        arc = bytearray(f.read())

    n_entries = struct.unpack_from("<I", arc, 0)[0]
    offsets   = [struct.unpack_from("<I", arc, 4 + i*4)[0] for i in range(n_entries)]
    offsets.append(len(arc))

    print(f"  {n_entries} entries at: {[hex(o) for o in offsets[:-1]]}")

    # Entry 0 = texture GIM (LZSS compressed)
    entry0_raw = bytes(arc[offsets[0]:offsets[1]])
    gim_hdr    = entry0_raw[:16]
    gim_body   = entry0_raw[16:]

    print(f"\nDecompressing entry 0 ({len(gim_body)} bytes compressed)...")
    decomp = bytearray(lzss_decompress(gim_body))
    print(f"  → {len(decomp)} bytes decompressed")

    # ── Step 2: We need to figure out the VRAM layout ──
    # From the PCSX2 dump, we know:
    #   • The texture appears to be 512 pixels wide (consistent with PSMT8 tbw=8)
    #   • The texture height could be 256 or 512
    #   • The button labels are in the top-left ~100x30 pixel region
    #
    # STRATEGY: Instead of full re-encode (which requires knowing exact layout),
    # we'll do a TARGETED BYTE SEARCH:
    #   - Compare decomp against dump PNG pixel-by-pixel using the swizzle
    #   - Try different (tbw, base_offset) combinations
    #   - When we get high correlation → we've found the right layout

    dump_ng = Image.open(DUMP_NEWGAME).convert("RGBA")
    
    print("\nFinding PSMT8 VRAM layout by correlation...")
    print("(Testing tbw values and base offsets...)")

    # The PCSX2 dump is 1024x1024 @ 1x upscale = this IS the VRAM page.
    # The texture region we care about is the top-left ~512x256 or 256x128 area.
    # PSMT8 tbw = texture_buffer_width / 64. Common PS2 values: 4,6,8,10,16.
    # The VRAM dump is 1024px wide → tbw for the full VRAM = 1024/64 = 16.
    # But the texture itself could have tbw=8 (512px wide), uploaded to VRAM at some base.
    
    # Try correlation: take 10 "probe" pixels with known high alpha from the dump
    # and check if they appear correctly at the swizzled address for each tbw/offset.
    
    probe_pixels = []
    for y in range(5, 25):
        for x in range(3, 90):
            r, g, b, a = dump_ng.getpixel((x, y))
            if a > 150:
                probe_pixels.append((x, y, r, g, b, a))
                if len(probe_pixels) >= 20: break
        if len(probe_pixels) >= 20: break

    print(f"  Probe pixels: {probe_pixels[:3]}")
    
    # The PCSX2 PSMT8 dump is stored with already-depalettized RGBA32 values.
    # In the VRAM (decomp), PSMT8 pixels are palette INDICES (0-255).
    # The palette in the VRAM maps index→RGBA32.
    # The palette entries are 256×RGBA32 = 1024 bytes, stored elsewhere in VRAM.
    #
    # Since we can't easily find the palette in decomp,
    # let's instead look for SPATIAL PATTERNS:
    # - Regions of the button area in the dump have specific alpha=0 (fully transparent background)
    # - In PSMT8, index 0 is typically mapped to transparent
    # - So the transparent region of the button should have bytes = 0x00 in VRAM
    # - And the text pixels should have non-zero bytes
    
    # Let's find where the transparency pattern matches:
    # In the dump, the button BG (outside text) is RGBA(0,0,0,0) = transparent
    # In PSMT8 VRAM, these become index 0 (typically).
    # The text pixels are RGBA(250,231,189,128) → some non-zero palette index.
    
    # Build a binary mask: 1=text pixel, 0=transparent
    MASK_W, MASK_H = 64, 20   # the button text region
    mask = []
    for y in range(MASK_H):
        for x in range(MASK_W):
            r, g, b, a = dump_ng.getpixel((x, y))
            mask.append(1 if a > 30 else 0)
    
    text_px_count = sum(mask)
    print(f"\n  Button text mask: {MASK_W}x{MASK_H}, text pixels={text_px_count}")
    
    best_match = (0, 0, 0, 0)   # (score, tbw, base_offset, tex_width)
    
    for tbw in [4, 6, 8, 10, 16]:
        tex_w = tbw * 64
        for base_off in range(0, min(len(decomp), 0x20000), 256):
            # Check if at this (tbw, base_off), the text pattern correlates
            # Score = (transparent pixels with 0x00 in VRAM) +
            #         (text pixels with non-zero in VRAM)
            score = 0
            valid = 0
            for y in range(MASK_H):
                for x in range(MASK_W):
                    addr = psmt8_addr(x, y, tbw) + base_off
                    if addr < 0 or addr >= len(decomp):
                        continue
                    vram_val = decomp[addr]
                    expected_text = mask[y * MASK_W + x]
                    if expected_text == 0 and vram_val == 0:
                        score += 1
                    elif expected_text == 1 and vram_val != 0:
                        score += 1
                    valid += 1
            
            if valid > 0:
                normalized = score * MASK_W * MASK_H // valid
                if normalized > best_match[0]:
                    best_match = (normalized, tbw, base_off, tex_w)
    
    score, tbw, base_off, tex_w = best_match
    print(f"\n  Best VRAM layout: tbw={tbw} tex_w={tex_w} base_off=0x{base_off:X} score={score}/{MASK_W*MASK_H}")
    
    if score < MASK_W * MASK_H * 0.5:
        print("  WARNING: Low correlation score. The swizzle may be wrong.")
        print("  Saving debug output anyway...")
    
    # ── Step 3: Decode existing VRAM to verify visually ──
    # We don't have the palette, but we can visualize the raw index values
    tex_h_guess = len(decomp) // tex_w
    vis_w = min(tex_w, 512)
    vis_h = min(tex_h_guess, 256)
    vis = bytearray(vis_w * vis_h)
    for y in range(vis_h):
        for x in range(vis_w):
            addr = psmt8_addr(x, y, tbw) + base_off
            if 0 <= addr < len(decomp):
                vis[y * vis_w + x] = decomp[addr]
    img_vis = Image.frombytes("L", (vis_w, vis_h), bytes(vis))
    img_vis.save(f"{OUT_DIR}/psmt8_decoded_{tbw}_{base_off:x}.png")
    print(f"\n  Saved PSMT8-decoded view: {OUT_DIR}/psmt8_decoded_{tbw}_{base_off:x}.png")
    print("  (Check if this shows the button text!)")


if __name__ == "__main__":
    main()
