import os, struct, math
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
        a = min(255, a * 2)
        pal.extend([r, g, b, a])
    return pal

def apply_palette(index_bytes, w, h, palette):
    pix = (index_bytes + bytes(w*h))[:w*h]
    img = Image.frombytes('P', (w, h), pix)
    img.putpalette(palette, rawmode='RGBA')
    return img.convert('RGBA')

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

def process_extracted_ite(ite_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    
    # 1. Find e00.raw (CLUT)
    e0_file = None
    for f in os.listdir(ite_dir):
        if 'e00_' in f and f.endswith('.raw'):
            e0_file = f
            break
            
    if not e0_file:
        print(f"No e00 found in {ite_dir}")
        return
        
    with open(os.path.join(ite_dir, e0_file), 'rb') as f:
        comp_clut = f.read()
    
    try:
        raw_clut = lzss_decompress(comp_clut)
    except Exception as e:
        print(f"Failed to decompress CLUT: {e}")
        return
        
    pal_sw = build_palette(raw_clut, 256, swizzle=True)
    pal_lin = build_palette(raw_clut, 256, swizzle=False)
    
    for f in os.listdir(ite_dir):
        if not f.endswith('.raw'): continue
        if 'e00_' in f: continue
        
        # Parse w, h from filename
        import re
        m = re.search(r'_(\d+)x(\d+)\.raw$', f)
        if not m: continue
        w, h = int(m.group(1)), int(m.group(2))
        
        with open(os.path.join(ite_dir, f), 'rb') as fp:
            comp_data = fp.read()
            
        try:
            raw_data = lzss_decompress(comp_data)
        except Exception as e:
            print(f"Failed to decompress {f}: {e}")
            continue
            
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

process_extracted_ite('ite_out/option', 'ite_out/option_decoded_lzss')
process_extracted_ite('ite_out/naming', 'ite_out/naming_decoded_lzss')
