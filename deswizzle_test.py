import struct
from PIL import Image

GS = open('option_savestate/extracted/GS.bin','rb').read()

BT32 = [
 [ 0,  1,  4,  5, 16, 17, 20, 21],
 [ 2,  3,  6,  7, 18, 19, 22, 23],
 [ 8,  9, 12, 13, 24, 25, 28, 29],
 [10, 11, 14, 15, 26, 27, 30, 31],
]

# PCSX2 GSLocal columnTable32: full 8x8 within-block word index, word(by,bx)
COLT32 = [
 [  0,  1,  4,  5,  8,  9, 12, 13],
 [  2,  3,  6,  7, 10, 11, 14, 15],
 [ 16, 17, 20, 21, 24, 25, 28, 29],
 [ 18, 19, 22, 23, 26, 27, 30, 31],
 [ 32, 33, 36, 37, 40, 41, 44, 45],
 [ 34, 35, 38, 39, 42, 43, 46, 47],
 [ 48, 49, 52, 53, 56, 57, 60, 61],
 [ 50, 51, 54, 55, 58, 59, 62, 63],
]

def deswizzle(gs, tbp, tbw, w, h, order='rgba'):
    base=tbp*256; out=bytearray(w*h*4)
    for y in range(h):
        py=y//32; ly=y%32; brow=ly//8; by=ly%8
        for x in range(w):
            px=x//64; lx=x%64; page=py*tbw+px; bcol=lx//8; bx=lx%8
            block=BT32[brow][bcol]; word=COLT32[by][bx]
            off=base+page*8192+block*256+word*4
            b0,b1,b2,b3=gs[off],gs[off+1],gs[off+2],gs[off+3]
            ch=(b0,b1,b2) if order=='rgba' else (b2,b1,b0)
            di=(y*w+x)*4; out[di],out[di+1],out[di+2]=ch; out[di+3]=255
    return bytes(out)

d=deswizzle(GS,0x2300,10,640,448,'rgba')
Image.frombytes('RGBA',(640,448),d).save('gt_colt32.png')
print('saved gt_colt32.png')
