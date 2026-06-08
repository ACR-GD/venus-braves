import sys, struct, math, os
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

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    data = f.read()

offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
entry3 = data[offsets[3]:offsets[4]]

w = struct.unpack_from('<I', entry3, 0x04)[0]
h = struct.unpack_from('<I', entry3, 0x08)[0]
vram = []
pos = 0x10
while pos < len(entry3):
    val = struct.unpack_from('<I', entry3, pos)[0]
    if val & 0x80000000:
        vram.append(val & 0x7FFFFFFF)
        pos += 4
    else: break
# Wait, entry3 vram check was broken because no 0x80 bit.
# Let's just read exactly 8 for Entry 3.
vram = [struct.unpack_from('<I', entry3, 0x10 + k*4)[0] for k in range(8)]
pixels = entry3[0x30:]

os.makedirs('ite_out/vram_test', exist_ok=True)

# Test different multipliers and chunk sizes
for mult in [16, 64, 256]:
    chunk_size = len(pixels) // len(vram)
    vram_buf = bytearray(4 * 1024 * 1024)
    p = 0
    for addr in vram:
        vram_buf[addr * mult : addr * mult + chunk_size] = pixels[p:p+chunk_size]
        p += chunk_size
        
    sw4, sw_w4, sw_h4 = deswizzle_psmt4(vram_buf[vram[0]*mult:], w, h)
    gray4 = bytes(b * 17 for b in sw4[:sw_w4 * sw_h4])
    img = Image.frombytes('L', (sw_w4, sw_h4), gray4).convert('RGBA')
    img.crop((0, 0, w, h)).save(f'ite_out/vram_test/test_mult{mult}.png')

