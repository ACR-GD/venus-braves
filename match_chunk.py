import sys, struct, os
from PIL import Image

def lzss_decompress(data):
    N = 2048
    r = N - 18
    text_buf = bytearray(N)
    out = bytearray()
    pos = 0
    while pos < len(data):
        flags = data[pos]; pos += 1
        for i in range(8):
            if pos >= len(data): break
            if (flags >> i) & 1:
                c = data[pos]; pos += 1
                out.append(c)
                text_buf[r] = c
                r = (r + 1) & (N - 1)
            else:
                if pos + 1 >= len(data): break
                lo = data[pos]; hi = data[pos+1]; pos += 2
                match_offset = lo | ((hi & 0x0F) << 8)
                match_len = (hi >> 4) + 2
                for k in range(match_len):
                    c = text_buf[(match_offset + k) & (N-1)]
                    out.append(c)
                    text_buf[r] = c
                    r = (r + 1) & (N-1)
    return bytes(out)

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    data = f.read()

offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
entry3 = data[offsets[3]:offsets[4]]

offsets_list = [struct.unpack_from('<I', entry3, 0x10 + k*4)[0] for k in range(8)]
offsets_list.append(len(entry3))

chunk0 = entry3[offsets_list[0]:offsets_list[1]]
decomp0 = lzss_decompress(chunk0)

# Load the GS dump
dump_path = 'ite_out/gs_dumps/Venus & Braves_SLPS-25196_20260530182101.png'
dump_img = Image.open(dump_path).convert('RGBA')

# The "Options" header is the top green banner. 
# Let's find reference pixels inside the white text "オプション"
reference_pixels = []
for y in range(20, 80):
    for x in range(200, 400):
        r, g, b, a = dump_img.getpixel((x, y))
        # The text is white, so r,g,b > 200
        if r > 200 and g > 200 and b > 200 and a > 100:
            reference_pixels.append((x, y, r, g, b, a))
            if len(reference_pixels) >= 20: break
    if len(reference_pixels) >= 20: break

print(f"Reference pixels found: {len(reference_pixels)}")

formats = [
    ("RGBA32", 4, [256, 512, 640]),
    ("RGBA16", 2, [256, 512, 640]),
    ("PSMT8", 1, [256, 512, 640]),
]

for fmt_name, bpp, widths in formats:
    for w in widths:
        for offset in range(0, len(decomp0) - 4, 1): # Try every byte offset just in case!
            matched = 0
            # Test a few reference pixels
            for px, py, pr, pg, pb, pa in reference_pixels[:5]:
                # We don't know the exact starting X/Y of the chunk in the screen.
                # But if we assume this chunk corresponds to some region, we can't just do `py * w + px`
                pass

# A better way is to just generate a small PNG from the decompressed chunk and see if it looks like the header text!
os.makedirs('scratch/chunk_views', exist_ok=True)
for w in [32, 64, 128, 256]:
    for bpp in [1, 2, 4]:
        try:
            h = len(decomp0) // (w * bpp)
            if h < 4: continue
            if bpp == 1:
                img = Image.frombytes('L', (w, h), decomp0[:w*h])
                img.save(f'scratch/chunk_views/c0_{w}x{h}_8bpp.png')
            elif bpp == 4:
                px = bytearray(w*h*4)
                for i in range(w*h):
                    px[i*4:i*4+4] = decomp0[i*4:i*4+4]
                img = Image.frombytes('RGBA', (w, h), bytes(px))
                img.save(f'scratch/chunk_views/c0_{w}x{h}_32bpp.png')
        except Exception as e:
            pass
print("Created chunk views.")
