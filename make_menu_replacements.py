#!/usr/bin/env python3
"""
make_menu_replacements.py
=========================
Generates PCSX2 texture replacement PNGs for Venus & Braves main menu buttons.

The original Japanese menu buttons are stored as texture pages (1024x1024).
The button label text occupies the top-left corner (~90x25 pixels).

Translations:
  はじめから  → "New Game"
  つづきから  → "Continue"
  オプション  → "Options"

Output: Dump/SLPS-25196/replacements/<hash>-<clut>.png
"""

import os
import struct
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Configuration ────────────────────────────────────────────────────────────

DUMPS_DIR   = "Dump/SLPS-25196/dumps"
REPLACE_DIR = "Dump/SLPS-25196/replacements"

# Button text region in the 1024×1024 texture
# (determined by pixel analysis of the dumped textures)
BTN_X, BTN_Y = 0, 0       # top-left of region to clear
BTN_W, BTN_H = 100, 30    # width/height of region to clear

# Text style matching the original
# Original: warm cream RGBA(250, 231, 189, 128) = ~50% alpha
TEXT_COLOR       = (250, 231, 189, 200)   # slightly more opaque for readability
TEXT_SHADOW_COL  = (60,  40,   20, 100)   # dark brown shadow

# Mapping: hash prefix → (japanese_text, english_translation)
# Each Japanese string has TWO dumps (normal + highlighted state)
TEXTURE_MAP = {
    # New Game (はじめから)
    "22256c3d3ca61d7a-00002a80": ("はじめから", "New Game"),
    "f051bf54a66ad6dd-00002a80": ("はじめから", "New Game"),
    # Continue (つづきから)
    "7e5db600f94499e8-00002a80": ("つづきから", "Continue"),
    "a8aeddb0c53d2397-00002a80": ("つづきから", "Continue"),
    # Options (オプション)
    "2ddc468541cd6963-00002a80": ("オプション", "Options"),
    "c1f82cf11586ba67-00002a80": ("オプション", "Options"),
}

# ── Font loading ──────────────────────────────────────────────────────────────

def get_font(size=14):
    """Try to find a good serif/decorative font matching the game style."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Palatino.ttc",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Times.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Replacement generator ────────────────────────────────────────────────────

def create_replacement(src_path, dest_path, english_text):
    """
    Create a replacement texture by:
    1. Copying the original dump
    2. Clearing the button label area
    3. Drawing English text in the same style
    """
    img = Image.open(src_path).convert("RGBA")

    # --- Clear the button label region ---
    draw = ImageDraw.Draw(img)
    draw.rectangle([BTN_X, BTN_Y, BTN_X + BTN_W - 1, BTN_Y + BTN_H - 1],
                   fill=(0, 0, 0, 0))

    # --- Draw English text ---
    # Use a 14-point font to fill roughly the same visual space
    # The original text occupies ~87×18 px.  With "New Game" at 14pt that's ~80px wide.
    font_size = 14
    font = get_font(font_size)

    # Measure text to center it in the original button area
    try:
        bbox = font.getbbox(english_text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except AttributeError:
        tw, th = font.getsize(english_text)

    # Position: same x as original (starts around x=3), vertically centered (y=6-22)
    tx = 3
    ty = max(0, (BTN_H - th) // 2 - 1)

    # Draw shadow (1px offset)
    draw.text((tx + 1, ty + 1), english_text, font=font, fill=TEXT_SHADOW_COL)
    # Draw main text
    draw.text((tx, ty), english_text, font=font, fill=TEXT_COLOR)

    img.save(dest_path, "PNG")
    print(f"  → {os.path.basename(dest_path)}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(REPLACE_DIR, exist_ok=True)

    print(f"Creating PCSX2 texture replacements in: {REPLACE_DIR}/")
    print()

    for filename, (jp_text, en_text) in TEXTURE_MAP.items():
        src  = os.path.join(DUMPS_DIR,   filename + ".png")
        dest = os.path.join(REPLACE_DIR, filename + ".png")

        if not os.path.exists(src):
            print(f"  SKIP (not found): {src}")
            continue

        print(f"{jp_text} → '{en_text}'")
        create_replacement(src, dest, en_text)

    print()
    print("Done! Place the replacements folder at:")
    print(f"  {os.path.abspath(REPLACE_DIR)}")
    print()
    print("In PCSX2: Settings → Graphics → Texture Replacement")
    print("  ☑ Load Textures")
    print(f"  Path: {os.path.abspath('Dump/SLPS-25196')}")


if __name__ == "__main__":
    main()
