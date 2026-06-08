#!/usr/bin/env python3
"""
find_button_hashes.py
After dumping textures at the title screen, run this script to identify
which dump files contain the menu button textures (NEW GAME / CONTINUE / OPTIONS).
"""
import os
import sys
from PIL import Image
import numpy as np

# The button textures have these distinctive properties:
# - Contain cream/peach colored pixels RGBA(250,231,189,~255)
# - Are relatively small (but PCSX2 may store them in larger pages)
# - Uploaded at TBP0=0x2BE0, DBW=2

DUMP_DIR = "/Users/acr/Develop/venus-braves/Dump/SLPS-25196/dumps"
TEXTURES_EN = "/Users/acr/Develop/venus-braves/textures_en"
REPLACEMENT_DIR = "/Users/acr/Develop/venus-braves/replacements"

def find_button_dumps():
    """Find PCSX2 dump files that contain the title menu button textures."""
    print("Scanning dump directory for title screen button textures...")
    print(f"Dump dir: {DUMP_DIR}\n")
    
    button_files = []
    
    for fname in sorted(os.listdir(DUMP_DIR)):
        if not fname.endswith('.png'):
            continue
        fpath = os.path.join(DUMP_DIR, fname)
        try:
            img = Image.open(fpath).convert('RGBA')
            arr = np.array(img)
            
            # Look for cream/peach pixels: R>240, G>215, B>165, A>200
            cream = ((arr[:,:,0] > 240) & (arr[:,:,1] > 215) & 
                     (arr[:,:,2] > 165) & (arr[:,:,3] > 200))
            count = cream.sum()
            
            if count >= 30:  # At least 30 cream pixels = likely a button
                w, h = img.size
                print(f"CANDIDATE: {fname} ({w}x{h}) — {count} cream pixels")
                
                # Try to crop the button region
                rows = np.where(cream.any(axis=1))[0]
                cols = np.where(cream.any(axis=0))[0]
                if len(rows) > 0 and len(cols) > 0:
                    r0, r1 = max(0, rows[0]-5), min(h, rows[-1]+5)
                    c0, c1 = max(0, cols[0]-5), min(w, cols[-1]+5)
                    crop = img.crop((c0, r0, c1, r1))
                    crop_path = f"/tmp/crop_{fname}"
                    crop.save(crop_path)
                    print(f"  Crop saved: {crop_path} ({c1-c0}x{r1-r0})")
                
                button_files.append(fname)
        except Exception as e:
            pass
    
    return button_files

def install_replacements(mapping):
    """
    mapping = {
        'hash_filename.png': ('textures_en/btn1_13pt_unselected.png', 'NEW GAME unselected'),
        ...
    }
    """
    os.makedirs(REPLACEMENT_DIR, exist_ok=True)
    for hash_file, (replacement, label) in mapping.items():
        src = os.path.join(TEXTURES_EN, os.path.basename(replacement))
        dst = os.path.join(REPLACEMENT_DIR, hash_file)
        
        src_img = Image.open(src)
        
        # Open original dump to get its full size
        dump_path = os.path.join(DUMP_DIR, hash_file)
        if os.path.exists(dump_path):
            dump_img = Image.open(dump_path).convert('RGBA')
            dw, dh = dump_img.size
            
            # Find where the button actually sits in the dump page
            # Create a transparent canvas the same size as the dump
            canvas = Image.new('RGBA', (dw, dh), (0, 0, 0, 0))
            
            # TODO: Figure out exact position from crop analysis
            # For now, paste at top-left with detected offset
            canvas.paste(src_img, (0, 0))
            canvas.save(dst)
            print(f"Installed: {label} → {dst}")
        else:
            src_img.save(dst)
            print(f"Installed (no dump ref): {label} → {dst}")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--install':
        # After identifying hashes, call with mapping
        # Example: python3 find_button_hashes.py --install
        print("Please run without --install first to identify hashes.")
    else:
        found = find_button_dumps()
        if not found:
            print("\nNo button textures found yet.")
            print("→ Make sure you've dumped textures while the title screen menu is VISIBLE.")
            print("→ The game must be at the screen showing はじめから/つづきから/オプション")
        else:
            print(f"\nFound {len(found)} candidate file(s): {found}")
            print("\nNext step: Identify which hash = which button, then run install.")
