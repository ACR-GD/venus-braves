import struct, sys
from PIL import Image

GS = open('option_savestate/extracted/GS.bin','rb').read()

# PSMCT32 page block layout (4 rows x 8 cols of 8x8 blocks)
BT32 = [
 [ 0,  1,  4,  5, 16, 17, 20, 21],
 [ 2,  3,  6,  7, 18, 19, 22, 23],
 [ 8,  9, 12, 13, 24, 25, 28, 29],
 [10, 11, 14, 15, 26, 27, 30, 31],
]

def deswizzle_ct32(gs, tbp_blocks, tbw_pages, w, h):
    base = tbp_blocks * 256  # block = 256 bytes
    out = bytearray(w*h*4)
    for y in range(h):
        py = y // 32; ly = y % 32
        brow = ly // 8; by = ly % 8
        for x in range(w):
            px = x // 64; lx = x % 64
            page = py * tbw_pages + px
            bcol = lx // 8; bx = lx % 8
            block = BT32[brow][bcol]
            word = by*8 + bx
            off = base + page*8192 + block*256 + word*4
            r,g,b,a = gs[off],gs[off+1],gs[off+2],gs[off+3]
            di = (y*w+x)*4
            out[di]=r; out[di+1]=g; out[di+2]=b; out[di+3]=255
    return bytes(out)

tbp = 0x2300
W,H = 640,448
TBW = 10
data = deswizzle_ct32(GS, tbp, TBW, W, H)
img = Image.frombytes('RGBA',(W,H),data)
img.save('ground_truth_bg.png')
print('saved ground_truth_bg.png', W,'x',H,'from VRAM byte',hex(tbp*256))
