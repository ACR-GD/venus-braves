import math
from PIL import Image

PSMT4_BLOCK_TABLE = [
    [ 0,  1,  4,  5, 16, 17, 20, 21],
    [ 2,  3,  6,  7, 18, 19, 22, 23],
    [ 8,  9, 12, 13, 24, 25, 28, 29],
    [10, 11, 14, 15, 26, 27, 30, 31],
]

def deswizzle_psmt4(raw, w, h):
    pw = math.ceil(w / 128)
    ph = math.ceil(h / 128)
    page_size = 8192
    total = pw * ph * page_size
    src = bytearray(raw[:total])
    if len(src) < total: src += bytearray(total - len(src))
    out = bytearray(pw * 128 * ph * 128)
    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = src[page_off:page_off + page_size]
            for block_row in range(4):
                for block_col in range(8):
                    block_idx = PSMT4_BLOCK_TABLE[block_row][block_col] if block_row < 4 else 0
                    src_byte_off = block_idx * 128
                    block_data   = page[src_byte_off:src_byte_off + 128]
                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 128 + block_row * 16
                    for row in range(16):
                        for col in range(16):
                            bi  = (row * 16 + col) // 2
                            nib = (row * 16 + col) % 2
                            if bi < len(block_data):
                                v = (block_data[bi] & 0x0F) if nib == 0 else (block_data[bi] >> 4) & 0x0F
                            else: v = 0
                            di = (dst_y + row) * (pw * 128) + (dst_x + col)
                            if di < len(out): out[di] = v
    return bytes(out), pw * 128, ph * 128

with open('scratch/decompressed_e3.bin', 'rb') as f:
    decomp_data = f.read()

w = 230
h = 55
sw4, sw_w4, sw_h4 = deswizzle_psmt4(decomp_data, w, h)
gray4 = bytes(b * 17 for b in sw4[:sw_w4 * sw_h4])
img = Image.frombytes('L', (sw_w4, sw_h4), gray4)
img.crop((0, 0, w, h)).save('scratch/decompressed_e3_deswizzled.png')
print("Done.")

