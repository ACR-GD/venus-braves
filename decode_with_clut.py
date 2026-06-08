import os
from PIL import Image

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
        pal.extend([r, g, b, 255])
    return pal

def apply_palette(index_bytes, w, h, palette):
    pix = (index_bytes + bytes(w*h))[:w*h]
    img = Image.frombytes('P', (w, h), pix)
    img.putpalette(palette, rawmode='RGBA')
    return img.convert('RGBA')

def deswizzle_psmt8(raw, w, h):
    import math
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

def process_fhm_dir(fhm_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    e0_path = None
    for f in os.listdir(fhm_dir):
        if 'e00' in f and f.endswith('.raw'): e0_path = os.path.join(fhm_dir, f)
        if 'entry_0' in f and f.endswith('.bin'): e0_path = os.path.join(fhm_dir, f)
    
    if not e0_path:
        print(f"No e00 found in {fhm_dir}")
        return

    with open(e0_path, 'rb') as f:
        clut_raw = f.read()

    # We don't know if CLUT is swizzled, try both
    pal_sw = build_palette(clut_raw, 256, swizzle=True)
    pal_lin = build_palette(clut_raw, 256, swizzle=False)

    for f in os.listdir(fhm_dir):
        if not (f.endswith('.raw') or f.endswith('.bin')): continue
        if 'e00' in f or 'entry_0' in f: continue
        
        # Parse w, h from filename if possible
        import re
        m = re.search(r'_(\d+)x(\d+)', f)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
        else:
            w, h = 512, 512 # Fallback
            
        with open(os.path.join(fhm_dir, f), 'rb') as fp:
            data = fp.read()
            
        # Naming screen uses LZSS for entry_1.bin etc if we got them from raw .bin without decode_gim.py?
        # Wait, naming.fhm was extracted via extract_ite.py, so .raw files are just pixel payloads
        
        sw8, sw_w8, sw_h8 = deswizzle_psmt8(data, w, h)
        img_sw = apply_palette(sw8, sw_w8, sw_h8, pal_sw)
        img_lin = apply_palette(sw8, sw_w8, sw_h8, pal_lin)
        
        if w != 512:
            img_sw = img_sw.crop((0, 0, w, h))
            img_lin = img_lin.crop((0, 0, w, h))
            
        base = os.path.splitext(f)[0]
        img_sw.save(os.path.join(out_dir, f"{base}_sw.png"))
        img_lin.save(os.path.join(out_dir, f"{base}_lin.png"))
        print(f"Saved {base}")

process_fhm_dir('/Users/acr/Develop/venus-braves/ite_out/naming', '/Users/acr/Develop/venus-braves/ite_out/naming_decoded')
# For options, we extracted to option_imgs using raw script? Let me check how option was extracted
