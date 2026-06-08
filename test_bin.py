import os
from PIL import Image

def view_bin(path, w, h, bpp):
    with open(path, 'rb') as f:
        data = f.read()
    
    if bpp == 4:
        # PSMT4
        unpacked = bytearray()
        for b in data:
            unpacked.append(b & 0x0F)
            unpacked.append((b >> 4) & 0x0F)
        img = Image.frombytes('L', (w, h), bytes(unpacked))
        img = img.point(lambda p: p * 17)
        img.save(f"{path}.png")
        print(f"Saved {path}.png")

view_bin("scratch/options_dump/upload_1276_DBP0x2340_PSMT4_44x88.bin", 44, 88, 4)
