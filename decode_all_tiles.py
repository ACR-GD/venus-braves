import struct
from PIL import Image
from ulz_decode import decode_plane

f = open('cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm', 'rb').read()
ITE = 0x13810  # entry index 1 in FHM header? actually entry0 ITE is at 0xef0
ITE = 0xef0
W = struct.unpack_from('<I', f, ITE+4)[0]
H = struct.unpack_from('<I', f, ITE+8)[0]
first = struct.unpack_from('<I', f, ITE+0x10)[0] & 0x7fffffff
n = (first - 0x10)//4
offs = [struct.unpack_from('<I', f, ITE+0x10+k*4)[0] & 0x7fffffff for k in range(n)]
print('ITE %dx%d n=%d' % (W, H, n))

tiles_x = W // 64   # 10
tiles_y = H // 32   # 14
print('grid', tiles_x, 'x', tiles_y, '=', tiles_x*tiles_y)

img = Image.new('L', (W, H))
px = img.load()
for idx in range(min(n, tiles_x*tiles_y)):
    src = ITE + offs[idx]
    if f[src] == 0:   # tuile vide
        continue
    try:
        plane, br, s3 = decode_plane(f, src)
    except Exception as e:
        print('tile', idx, 'erreur', e); continue
    tx = idx % tiles_x
    ty = idx // tiles_x
    # plan = 2048 valeurs, essai layout row-major 64x32
    for i in range(2048):
        lx = i % 64; ly = i // 64
        X = tx*64 + lx; Y = ty*32 + ly
        if X < W and Y < H:
            px[X, Y] = plane[i]
img.save('tiles_rowmajor.png')
print('saved tiles_rowmajor.png')
