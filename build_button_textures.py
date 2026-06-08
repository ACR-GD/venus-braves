#!/usr/bin/env python3
"""
build_button_textures.py  (Venus & Braves English Patch)
=========================================================
Renders English button textures that visually match the original game style.

Strategy:
  - Renders each button label as a whole phrase (not per-glyph) at high
    supersampling, then downscales to the exact canvas size.
  - Uses the same cream/gold fill + dark navy outline that the game uses.
  - All pixel operations use NumPy for speed (no slow pixel-by-pixel loops).

PS2 color palette (measured from GS dump):
  Fill:     RGBA(250, 231, 189) — cream/gold
  Normal:   RGBA( 50,  52, 109) — dark navy   (unselected state)
  Selected: RGBA(140,   0,  36) — dark crimson (selected/highlighted)
  PS2 alpha range: 0-128 (128 = fully opaque)

Usage:
  python3 build_button_textures.py          # build previews in ite_out/buttons/
  python3 build_button_textures.py --patch  # build + write title_patched.fa
  python3 build_button_textures.py --apply  # copy title_patched.fa → title.fa
"""

import struct, os, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FA_PATH = "cdimage_unpacked/seven_data_link/tsuyoshi/pic_obj/title.fa"
OUT_DIR = "ite_out/buttons"

# ── PS2 Color palette ─────────────────────────────────────────────────────────
FILL_RGB     = (250, 231, 189)
NORMAL_RGB   = ( 50,  52, 109)
SELECTED_RGB = (140,   0,  36)

# ── Button definitions ────────────────────────────────────────────────────────
# (label, canvas_w, canvas_h, normal_entry_idx, selected_entry_idx)
BUTTONS = [
    ("New Game",       100, 30,  4,  5),
    ("Continue",       100, 31,  6,  7),
    ("Chronicle Mode", 154, 29,  8,  9),
    ("Options",        102, 31, 10, 11),
    ("Network Mode",   172, 30, 12, 13),
]

# ── Font candidates (in order of preference) ─────────────────────────────────
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]
SUPERSAMPLING = 6   # render at 6x then LANCZOS-downscale


def find_font(pt):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, pt), path
            except Exception:
                pass
    return ImageFont.load_default(), "default"


# ── Core renderer ─────────────────────────────────────────────────────────────

def render_button(text, width, height, fill_rgb, outline_rgb):
    """
    Render a button label as a cream/gold + dark-outlined bitmap.

    Returns a PIL RGBA Image of exactly (width, height).
    Alpha is in PS2 range (0-128), where 128 = fully opaque.
    """
    S = SUPERSAMPLING
    cw, ch = width * S, height * S

    # Pillow uses 0-255 alpha
    fill_rgba    = (*fill_rgb,    255)
    outline_rgba = (*outline_rgb, 255)

    # Binary-search for the largest font+stroke that fits within the canvas
    for fsize in range(ch - 4, 12, -2):
        font, _ = find_font(fsize)
        stroke_w = max(6, fsize // 5)   # ~20% of font size
        bb = font.getbbox(text)
        tw = bb[2] - bb[0]
        th = bb[3] - bb[1]
        if tw + stroke_w * 2 <= cw - S and th + stroke_w * 2 <= ch - S:
            break

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)
    tx = (cw - tw) // 2 - bb[0]
    ty = (ch - th) // 2 - bb[1]
    draw.text((tx, ty), text,
              font=font, fill=fill_rgba,
              stroke_width=stroke_w, stroke_fill=outline_rgba)

    # Downscale to target dimensions with high-quality anti-aliasing
    img = canvas.resize((width, height), Image.LANCZOS)

    # Convert Pillow alpha (0-255) → PS2 alpha (0-128) using NumPy
    arr = np.array(img, dtype=np.uint16)
    arr[:, :, 3] = (arr[:, :, 3] * 128) // 255
    return Image.fromarray(arr.astype(np.uint8))


# ── title.fa parsing & patching ───────────────────────────────────────────────

def load_fa():
    with open(FA_PATH, 'rb') as f:
        return f.read()


def parse_fa(data):
    n = struct.unpack_from('<I', data, 0)[0]
    return [(struct.unpack_from('<I', data, 4 + i*8)[0],
             struct.unpack_from('<I', data, 4 + i*8 + 4)[0]) for i in range(n)]


def decode_entry(fa_data, idx):
    """Decode a GIM entry to PIL RGBA (alpha x2 for display)."""
    entries = parse_fa(fa_data)
    off, sz = entries[idx]
    entry   = fa_data[off:off+sz]
    w = struct.unpack_from('<H', entry, 0x1C)[0]
    h = struct.unpack_from('<H', entry, 0x1E)[0]
    hdr = sz - w * h * 4
    arr = np.frombuffer(entry[hdr:hdr + w*h*4], dtype=np.uint8).reshape(h, w, 4).copy()
    arr[:, :, 3] = np.clip(arr[:, :, 3].astype(np.uint16) * 2, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def patch_fa(fa_data, entry_idx, new_img):
    """
    Replace pixel data of a GIM entry in fa_data.
    The entry size must not change (new_img must have same dimensions as original).
    """
    entries = parse_fa(fa_data)
    off, sz = entries[entry_idx]
    orig_entry = fa_data[off:off+sz]

    w, h = new_img.size
    pix_bytes = w * h * 4
    hdr_size  = sz - pix_bytes
    if hdr_size < 0:
        raise ValueError(f"Entry {entry_idx}: sz={sz} < pix_bytes={pix_bytes}")

    new_pix   = new_img.tobytes("raw", "RGBA")
    new_entry = bytes(orig_entry[:hdr_size]) + new_pix
    assert len(new_entry) == sz, f"Size mismatch: {len(new_entry)} != {sz}"

    result = bytearray(fa_data)
    result[off:off+sz] = new_entry
    return bytes(result)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(do_patch=False):
    os.makedirs(OUT_DIR, exist_ok=True)

    fa_data = load_fa()

    # Find which font will be used
    _, font_path = find_font(100)
    print(f"Font: {font_path}")

    print("\n── Building button textures ──────────────────────────────────")
    for label, cw, ch, ni, si in BUTTONS:
        for idx, state, outline_rgb in [
            (ni, 'normal',   NORMAL_RGB),
            (si, 'selected', SELECTED_RGB),
        ]:
            img = render_button(label, cw, ch, FILL_RGB, outline_rgb)

            # Save display preview (alpha ×2 on dark navy background)
            arr = np.array(img, dtype=np.uint16)
            arr[:, :, 3] = np.clip(arr[:, :, 3] * 2, 0, 255).astype(np.uint16)
            preview = Image.fromarray(arr.astype(np.uint8))

            bg_color = (70, 70, 120) if state == 'normal' else (100, 30, 50)
            bg = Image.new('RGBA', (cw + 20, ch + 10), (*bg_color, 255))
            bg.paste(preview, (10, 5), preview)

            out = f"{OUT_DIR}/{label.replace(' ', '_')}_{state}.png"
            bg.save(out)
            print(f"  [{state:8s}] {label}: {cw}×{ch} → {out}")

            if do_patch:
                fa_data = patch_fa(fa_data, idx, img)

    if do_patch:
        out_fa = FA_PATH.replace('.fa', '_patched.fa')
        with open(out_fa, 'wb') as f:
            f.write(fa_data)
        print(f"\n✓ Patched FA: {out_fa}")
        print("  Run: python3 build_button_textures.py --apply")
    else:
        print(f"\nPreviews in {OUT_DIR}/")
        print("Run: python3 build_button_textures.py --patch")

    # Make a composite JP-vs-EN comparison
    print("\n── JP vs EN comparison ───────────────────────────────────────")
    scale = 3
    pairs = []
    for label, cw, ch, ni, _ in BUTTONS:
        jp = decode_entry(fa_data if not do_patch else load_fa(), ni)
        en_raw = render_button(label, cw, ch, FILL_RGB, NORMAL_RGB)
        arr = np.array(en_raw, dtype=np.uint16)
        arr[:, :, 3] = np.clip(arr[:, :, 3] * 2, 0, 255).astype(np.uint16)
        en = Image.fromarray(arr.astype(np.uint8))
        pairs.append((label, jp, en))

    dark_bg = (50, 50, 80, 255)
    max_w = max(max(jp.width, en.width) for _, jp, en in pairs)
    row_h  = max(max(jp.height, en.height) for _, jp, en in pairs)
    n_rows = len(pairs) * 2
    comp = Image.new('RGBA', ((max_w + 16) * scale, (row_h * n_rows + 20 * len(pairs)) * scale),
                     dark_bg)
    y = 0
    for label, jp, en in pairs:
        for img in (jp, en):
            xi = ((max_w - img.width) // 2 + 8) * scale
            img_s = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
            comp.paste(img_s, (xi, y * scale), img_s)
            y += row_h + 2
        y += 8

    comp_path = f"{OUT_DIR}/JP_vs_EN_{scale}x.png"
    comp.save(comp_path)
    print(f"  Saved: {comp_path}")


def apply_patch():
    out_fa = FA_PATH.replace('.fa', '_patched.fa')
    if not os.path.exists(out_fa):
        print(f"ERROR: {out_fa} not found. Run --patch first.")
        return
    backup = FA_PATH + '.bak'
    if not os.path.exists(backup):
        shutil.copy2(FA_PATH, backup)
        print(f"Backup: {backup}")
    shutil.copy2(out_fa, FA_PATH)
    print(f"✓ Applied: {FA_PATH}")


if __name__ == "__main__":
    import sys
    if '--apply' in sys.argv:
        apply_patch()
    elif '--patch' in sys.argv:
        main(do_patch=True)
    else:
        main(do_patch=False)
