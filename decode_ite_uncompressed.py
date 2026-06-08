import os, struct, math
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

def unswizzle_clut(raw, n):
    c = bytearray(raw[:n*4])
    for bank in range(n // 32):
        b = bank * 32 * 4
        c[b+8*4:b+16*4], c[b+16*4:b+24*4] = \
            bytearray(c[b+16*4:b+24*4]), bytearray(c[b+8*4:b+16*4])
    return bytes(c)

def build_palette(clut_bytes, n, swizzle=False):
    if swizzle:
        clut_bytes = unswizzle_clut(clut_bytes, n)
    pal = []
    for i in range(n):
        b, g, r, a = clut_bytes[i*4:i*4+4]
        # Ignore alpha completely to find the right images!
        pal.extend([r, g, b, 255])
    return pal

def apply_palette(index_bytes, w, h, palette):
    pix = (index_bytes + bytes(w*h))[:w*h]
    img = Image.frombytes('P', (w, h), pix)
    img.putpalette(palette, rawmode='RGBA')
    return img.convert('RGBA')

def process_fhm(fhm_path, ite_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    
    with open(fhm_path, 'rb') as f:
        data = f.read()
    
    n_entries = struct.unpack_from('<I', data, 0)[0]
    offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(n_entries)]
    offsets.append(len(data))
    
    entry0 = data[offsets[0]:offsets[1]]
    
    # FHM entry 0 is the CLUT. It usually doesn't have an ITE header, but it has some 0x50 header maybe?
    # Actually, in decode_with_clut.py I just loaded `option_e00_...raw` or `naming_e00_...raw`.
    # I didn't extract e00 using extract_ite.py because it skipped it.
    
    # I will just use the bytes after 0x50.
    start = 0x50
    raw_clut = entry0[start:]
        
    pal_sw = build_palette(raw_clut, 256, swizzle=True)
    pal_lin = build_palette(raw_clut, 256, swizzle=False)
    
    for f in os.listdir(ite_dir):
        if not f.endswith('.raw'): continue
        if 'e00_' in f: continue
        
        import re
        m = re.search(r'_(\d+)x(\d+)\.raw$', f)
        if not m: continue
        w, h = int(m.group(1)), int(m.group(2))
        
        with open(os.path.join(ite_dir, f), 'rb') as fp:
            raw_data = fp.read()
            
        sw8, sw_w8, sw_h8 = deswizzle_psmt8(raw_data, w, h)
        
        img_sw = apply_palette(sw8, sw_w8, sw_h8, pal_sw)
        if w != sw_w8 or h != sw_h8:
            img_sw = img_sw.crop((0, 0, w, h))
        img_sw.save(os.path.join(out_dir, f.replace('.raw', '_sw.png')))
        
        img_lin = apply_palette(sw8, sw_w8, sw_h8, pal_lin)
        if w != sw_w8 or h != sw_h8:
            img_lin = img_lin.crop((0, 0, w, h))
        img_lin.save(os.path.join(out_dir, f.replace('.raw', '_lin.png')))
        print(f"Saved {f}")

process_fhm('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'ite_out/option', 'ite_out/option_decoded_uncompressed')
process_fhm('cdimage_unpacked/seven_data_link/futa/screen/naming.fhm', 'ite_out/naming', 'ite_out/naming_decoded_uncompressed')
