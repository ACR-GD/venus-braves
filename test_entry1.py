import struct, math, os
from PIL import Image

def deswizzle_psmt8(raw, w, h):
    PSMT8_BLOCK_TABLE = [
        [ 0,  1,  4,  5, 16, 17, 20, 21],
        [ 2,  3,  6,  7, 18, 19, 22, 23],
        [ 8,  9, 12, 13, 24, 25, 28, 29],
        [10, 11, 14, 15, 26, 27, 30, 31],
        [32, 33, 36, 37, 48, 49, 52, 53],
        [34, 35, 38, 39, 50, 51, 54, 55],
        [40, 41, 44, 45, 56, 57, 60, 61],
        [42, 43, 46, 47, 58, 59, 62, 63],
    ]
    pw = math.ceil(w / 128)
    ph = math.ceil(h / 64)
    page_size = 8192
    total = pw * ph * page_size
    src = bytearray(raw[:total])
    if len(src) < total: src += bytearray(total - len(src))
    out = bytearray(pw * 128 * ph * 64)
    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = src[page_off:page_off + page_size]
            for block_row in range(8):
                for block_col in range(8):
                    block_idx = PSMT8_BLOCK_TABLE[block_row][block_col]
                    src_off   = block_idx * 128
                    block_data = page[src_off:src_off + 128]
                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 64  + block_row *  8
                    for row in range(8):
                        for col in range(16):
                            sx = dst_x + col
                            sy = dst_y + row
                            si = row * 16 + col
                            di = sy * (pw * 128) + sx
                            if si < len(block_data) and di < len(out):
                                out[di] = block_data[si]
    return bytes(out), pw * 128, ph * 64

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    data = f.read()
offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
entry = data[offsets[1]:offsets[2]]

w = struct.unpack_from('<I', entry, 0x04)[0]
h = struct.unpack_from('<I', entry, 0x08)[0]

vram = []
for k in range(8):
    val = struct.unpack_from('<I', entry, 0x10 + k*4)[0]
    if val & 0x80000000:
        vram.append(val & 0x7FFFFFFF)

pixels = entry[0x30:]
chunk_size = len(pixels) // len(vram)
print(f"Entry 1: w={w}, h={h}, chunks={len(vram)}, chunk_size={chunk_size}")

vram_buf = bytearray(4 * 1024 * 1024)
p = 0
mult = 256
for addr in vram:
    vram_buf[addr * mult : addr * mult + chunk_size] = pixels[p:p+chunk_size]
    p += chunk_size
    
sw8, sw_w8, sw_h8 = deswizzle_psmt8(vram_buf[vram[0]*mult:], w, h)
gray8 = bytes(sw8[:sw_w8 * sw_h8])
img = Image.frombytes('L', (sw_w8, sw_h8), gray8)
img.crop((0, 0, w, h)).save('scratch/entry1_recon.png')
print("Done.")

