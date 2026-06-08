#!/usr/bin/env python3
"""
patch_title_fa.py
=================
Patches the menu button textures in title.fa (Venus & Braves PS2).

The title.fa file (tsuyoshi/pic_obj/title.fa) stores GIM image entries with:
  - 32-byte header: "GIM\x00" + metadata (width at 0x1C, height at 0x1E)
  - Raw RGBA32 pixel data (R, G, B, A per pixel, PS2 alpha range 0-128)

Button entries (normal/selected pairs):
  Entry  4 / 5  : はじめから  (100x30)  → New Game
  Entry  6 / 7  : つづきから  (100x31)  → Continue
  Entry  8 / 9  : クロニクルモード (154x29) → Chronicle Mode
  Entry 10 / 11 : オプション  (102x31)  → Options
  Entry 12 / 13 : ネットワークモード (172x30) → Network Mode

Color style (from GS dump analysis):
  Fill color:    RGBA(250, 231, 189, 128)  — cream/gold
  Normal outline: RGBA(50, 52, 109, 128)   — dark navy blue
  Selected outline: RGBA(140, 0, 36, 128)  — dark crimson/maroon
  Shadow/glow: semi-transparent black (various alpha values)
"""

import struct, os, shutil
from PIL import Image, ImageDraw, ImageFont

FA_PATH  = "cdimage_unpacked/seven_data_link/tsuyoshi/pic_obj/title.fa"
FONT_DIR = "/System/Library/Fonts"
OUT_DIR  = "ite_out/title_fa_patched"

# ── Color palette (PS2 alpha: 0-128, where 128=fully opaque) ──────────────────
FILL_COLOR     = (250, 231, 189, 128)  # cream/gold fill
OUTLINE_NORMAL = (50,  52,  109, 128)  # dark navy  (normal/unselected)
OUTLINE_SELECT = (140,  0,   36, 128)  # dark crimson (selected/highlighted)
SHADOW_COLOR   = (0,    0,    0,  48)  # soft shadow

# Translations: (label, width, height, normal_entry, selected_entry)
BUTTONS = [
    ("New Game",       100, 30,  4,  5),
    ("Continue",       100, 31,  6,  7),
    ("Chronicle Mode", 154, 29,  8,  9),
    ("Options",        102, 31, 10, 11),
    ("Network Mode",   172, 30, 12, 13),
]


# ── Font loading ──────────────────────────────────────────────────────────────
# The original Japanese menu buttons use a thick, rounded bold gothic font
# (similar to ヒラギノ丸ゴシック / Hiragino Maru Gothic). The closest match
# on macOS is Hiragino Gothic W9 (thickest weight). We render at 6x super-
# sampling with Pillow's native stroke_width for high-quality thick outlines.

SUPERSAMPLING = 6   # render at 6x then downscale for anti-aliased result

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",   # macOS Hiragino Gothic W9
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",   # macOS Hiragino Gothic W8
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def find_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ── Text rendering ────────────────────────────────────────────────────────────

def render_button(text, width, height, fill_color, outline_color):
    """
    Render English button text matching the PS2 bold-outlined style.
    Returns an RGBA Image of exactly (width, height) with PS2 alpha (0-128 range).

    The rendering uses 6x supersampling with Pillow's native stroke_width
    for high-quality thick outlines that match the original Japanese text density.
    """
    S = SUPERSAMPLING
    cw, ch = width * S, height * S

    # Map PS2 alpha (0-128) → Pillow alpha (0-255) for rendering
    fill_rgba = (fill_color[0], fill_color[1], fill_color[2],
                 min(255, fill_color[3] * 2))
    outline_rgba = (outline_color[0], outline_color[1], outline_color[2],
                    min(255, outline_color[3] * 2))

    # Auto-size: find the largest font+stroke that fits within the canvas
    for fsize in range(int(ch * 0.95), 20, -2):
        font = find_font(fsize)
        stroke_w = max(8, fsize // 5)   # proportional stroke (~20% of font size)

        bb = font.getbbox(text)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        total_w = tw + stroke_w * 2
        total_h = th + stroke_w * 2

        if total_w <= cw - S and total_h <= ch - S:
            break

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Center the text
    tx = (cw - tw) // 2 - bb[0]
    ty = (ch - th) // 2 - bb[1]

    # Draw outlined text using Pillow's built-in stroke
    draw.text((tx, ty), text, font=font, fill=fill_rgba,
              stroke_width=stroke_w, stroke_fill=outline_rgba)

    # Downscale to target size with high quality anti-aliasing
    img = canvas.resize((width, height), Image.LANCZOS)

    # Clamp alpha to PS2 range (0-128, where 128=fully opaque)
    px = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b, a = px[x, y]
            a128 = (a * 128) // 255
            px[x, y] = (r, g, b, a128)

    return img


# ── title.fa parsing & patching ───────────────────────────────────────────────

def parse_fa(data):
    """Return list of (offset, size) for each entry."""
    n = struct.unpack_from('<I', data, 0)[0]
    entries = []
    for i in range(n):
        off = struct.unpack_from('<I', data, 4 + i * 8)[0]
        sz  = struct.unpack_from('<I', data, 4 + i * 8 + 4)[0]
        entries.append((off, sz))
    return entries


def get_entry_dims(data, off):
    """Read width/height from GIM header at data[off]."""
    w = struct.unpack_from('<H', data, off + 0x1C)[0]
    h = struct.unpack_from('<H', data, off + 0x1E)[0]
    return w, h


def encode_entry(img, orig_entry_bytes):
    """
    Re-encode a PIL RGBA image as a GIM entry with the same header.
    The original header (first 32 or 40 bytes) is preserved verbatim.
    Only the pixel data is replaced.
    """
    w, h = img.size
    pix_bytes = w * h * 4
    hdr_size = len(orig_entry_bytes) - pix_bytes

    if hdr_size < 0:
        raise ValueError(f"Entry size {len(orig_entry_bytes)} < pixel data {pix_bytes}?")

    # Build new pixel data (RGBA in file order = R, G, B, A bytes)
    new_pix = img.tobytes("raw", "RGBA")
    assert len(new_pix) == pix_bytes

    return bytes(orig_entry_bytes[:hdr_size]) + new_pix


def patch_fa(fa_data, entry_idx, new_img):
    """
    Patch one GIM entry in fa_data and return the modified fa_data.
    The entry dimensions must NOT change (we patch in-place, same size).
    """
    entries = parse_fa(fa_data)
    off, sz = entries[entry_idx]
    orig_entry = fa_data[off:off + sz]

    new_entry = encode_entry(new_img, orig_entry)
    assert len(new_entry) == sz, f"Size mismatch: {len(new_entry)} != {sz}"

    result = bytearray(fa_data)
    result[off:off + sz] = new_entry
    return bytes(result)


# ── Verification: decode entry back to PNG ────────────────────────────────────

def decode_entry(fa_data, entry_idx):
    entries = parse_fa(fa_data)
    off, sz = entries[entry_idx]
    entry = fa_data[off:off + sz]
    w, h = get_entry_dims(fa_data, off)
    pix_bytes = w * h * 4
    hdr = sz - pix_bytes
    pix = entry[hdr:hdr + pix_bytes]

    # Scale alpha 0-128 → 0-255 for display
    raw = bytearray(pix)
    for i in range(3, len(raw), 4):
        raw[i] = min(255, raw[i] * 2)
    return Image.frombytes('RGBA', (w, h), bytes(raw))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Loading {FA_PATH}...")
    with open(FA_PATH, 'rb') as f:
        fa_data = f.read()

    print(f"  File size: {len(fa_data)} bytes")
    entries = parse_fa(fa_data)
    print(f"  Entries: {len(entries)}")

    # Decode and save originals for reference
    print("\n── Originals ────────────────────────────────────────────")
    for label, w, h, ni, si in BUTTONS:
        for idx, state in [(ni, 'normal'), (si, 'selected')]:
            img = decode_entry(fa_data, idx)
            out = f"{OUT_DIR}/orig_entry{idx:02d}_{label.replace(' ','_')}_{state}.png"
            img.save(out)
            print(f"  {out}")

    # Render and patch
    print("\n── Patching ─────────────────────────────────────────────")
    for label, w, h, ni, si in BUTTONS:
        for idx, state, outline_col in [
            (ni, 'normal',   OUTLINE_NORMAL),
            (si, 'selected', OUTLINE_SELECT),
        ]:
            print(f"  Entry {idx:2d} [{state:8s}]: \"{label}\" → {w}x{h}", end='')

            img = render_button(label, w, h, FILL_COLOR, outline_col)

            # Save preview (with alpha ×2 for visibility)
            preview = img.copy()
            px = preview.load()
            for y in range(h):
                for x in range(w):
                    r, g, b, a = px[x, y]
                    px[x, y] = (r, g, b, min(255, a * 2))
            out_prev = f"{OUT_DIR}/new_entry{idx:02d}_{label.replace(' ','_')}_{state}.png"
            preview.save(out_prev)

            fa_data = patch_fa(fa_data, idx, img)
            print(f"  → patched")

    # Save patched FA file (alongside original; do NOT overwrite yet)
    out_fa = FA_PATH.replace('.fa', '_patched.fa')
    with open(out_fa, 'wb') as f:
        f.write(fa_data)
    print(f"\n── Saved patched FA: {out_fa}")

    # Verify by decoding patched entries
    print("\n── Verification ─────────────────────────────────────────")
    for label, w, h, ni, si in BUTTONS:
        for idx, state in [(ni, 'normal'), (si, 'selected')]:
            img = decode_entry(fa_data, idx)
            out = f"{OUT_DIR}/verify_entry{idx:02d}_{label.replace(' ','_')}_{state}.png"
            img.save(out)
            print(f"  {out}")

    print("\n✓ All done! Review previews in", OUT_DIR)
    print("  Then run:  python3 patch_title_fa.py --apply")
    print("  to overwrite the actual title.fa")

    return out_fa


def apply_patch():
    """Copy the patched FA over the original (irreversible without backup)."""
    out_fa = FA_PATH.replace('.fa', '_patched.fa')
    if not os.path.exists(out_fa):
        print(f"ERROR: {out_fa} not found. Run without --apply first.")
        return

    backup = FA_PATH + '.bak'
    if not os.path.exists(backup):
        shutil.copy2(FA_PATH, backup)
        print(f"Backup: {backup}")

    shutil.copy2(out_fa, FA_PATH)
    print(f"✓ Applied patch: {FA_PATH}")


if __name__ == "__main__":
    import sys
    if '--apply' in sys.argv:
        apply_patch()
    else:
        main()
