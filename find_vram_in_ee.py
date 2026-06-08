from PIL import Image
import struct

with open('scratch/options_savestate/eeMemory.bin', 'rb') as f:
    ee_ram = f.read()

# The GS dump PNG with the options text: 182101.png
# Wait, I extracted the options text into `options_dump/upload_XXXX.png` earlier?
# Let's just use the raw dump
