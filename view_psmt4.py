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
chunk0 = entry3[offsets_list[0]:offsets_list[1]]
decomp0 = lzss_decompress(chunk0)

# Unpack PSMT4 (4bpp) to 8bpp
unpacked = bytearray()
for b in decomp0:
    unpacked.append(b & 0x0F)
    unpacked.append((b >> 4) & 0x0F)

# Create an image with a grayscale palette
img = Image.frombytes('L', (128, len(unpacked)//128), bytes(unpacked))
# Stretch contrast so 0-15 becomes 0-255
img = img.point(lambda p: p * 17)
img.save('scratch/chunk0_psmt4_unpacked.png')
print("Saved unpacked PSMT4.")

