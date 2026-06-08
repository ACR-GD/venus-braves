from decode_compressed_ite import lzss_decompress, deswizzle_psmt8
import math
from PIL import Image

def deswizzle_psmt4(raw, w, h):
    PSMT4_BLOCK_TABLE = [
        [ 0,  1,  4,  5, 16, 17, 20, 21],
        [ 2,  3,  6,  7, 18, 19, 22, 23],
        [ 8,  9, 12, 13, 24, 25, 28, 29],
        [10, 11, 14, 15, 26, 27, 30, 31],
    ]
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

with open('scratch/option_test/option_e03_230x55.raw', 'rb') as f:
    comp_data = f.read()

print(f"Compressed size: {len(comp_data)}")
try:
    raw_data = lzss_decompress(comp_data)
    print(f"Decompressed size: {len(raw_data)}")
except Exception as e:
    print("Error:", e)

# Save PSMT8 gray
sw8, sw_w8, sw_h8 = deswizzle_psmt8(raw_data, 230, 55)
gray8 = bytes(sw8[:sw_w8 * sw_h8])
img = Image.frombytes('L', (sw_w8, sw_h8), gray8)
img.crop((0, 0, 230, 55)).save('scratch/e03_lzss_psmt8.png')

# Save PSMT4 gray
sw4, sw_w4, sw_h4 = deswizzle_psmt4(raw_data, 230, 55)
gray4 = bytes(b * 17 for b in sw4[:sw_w4 * sw_h4])
img = Image.frombytes('L', (sw_w4, sw_h4), gray4)
img.crop((0, 0, 230, 55)).save('scratch/e03_lzss_psmt4.png')
print("Done.")

