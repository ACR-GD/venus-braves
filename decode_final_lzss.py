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
        a = min(255, a * 2)
        pal.extend([r, g, b, a])
    return pal

def apply_palette(index_bytes, w, h, palette):
    pix = (index_bytes + bytes(w*h))[:w*h]
    img = Image.frombytes('P', (w, h), pix)
    img.putpalette(palette, rawmode='RGBA')
    return img.convert('RGBA')

def decode_final_dir(in_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(in_dir, 'entry_00.bin'), 'rb') as f:
        clut_data = f.read()
        
    if clut_data.startswith(b'ITE\x00'):
        clut_data = clut_data[0x30:]
        
    pal_sw = build_palette(clut_data, 256, swizzle=True)
    pal_lin = build_palette(clut_data, 256, swizzle=False)
    
    # Need dimensions for each entry! I'll read the original FHM again.
    import glob
    fhm_path = 'cdimage_unpacked/seven_data_link/futa/screen/' + ('option.fhm' if 'option' in in_dir else 'naming.fhm')
    with open(fhm_path, 'rb') as f:
        data = f.read()
    n_entries = struct.unpack_from('<I', data, 0)[0]
    offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(n_entries)]
    offsets.append(len(data))
    
    for i in range(1, n_entries):
        bin_path = os.path.join(in_dir, f'entry_{i:02d}.bin')
        if not os.path.exists(bin_path): continue
        with open(bin_path, 'rb') as f:
            entry_bin = f.read()
            
        # Get dimensions from the uncompressed ITE header in the original FHM
        entry_raw = data[offsets[i]:offsets[i+1]]
        if entry_raw.startswith(b'ITE\x00'):
            # It's not LZSS compressed?? Or is the ITE header outside the LZSS block?
            # In venus_braves, usually the whole block is compressed.
            pass
            
        # Instead of parsing the FHM, we can just parse the ITE header from entry_bin
        if entry_bin.startswith(b'ITE\x00'):
            w = struct.unpack_from('<I', entry_bin, 0x04)[0]
            h = struct.unpack_from('<I', entry_bin, 0x08)[0]
            pixels = entry_bin[0x30:]
            
            sw8, sw_w8, sw_h8 = deswizzle_psmt8(pixels, w, h)
            img_sw = apply_palette(sw8, sw_w8, sw_h8, pal_sw)
            if w != sw_w8 or h != sw_h8:
                img_sw = img_sw.crop((0, 0, w, h))
            img_sw.save(os.path.join(out_dir, f'entry_{i:02d}_{w}x{h}_sw.png'))
            
            img_lin = apply_palette(sw8, sw_w8, sw_h8, pal_lin)
            if w != sw_w8 or h != sw_h8:
                img_lin = img_lin.crop((0, 0, w, h))
            img_lin.save(os.path.join(out_dir, f'entry_{i:02d}_{w}x{h}_lin.png'))
            print(f"Saved entry_{i:02d} {w}x{h}")

decode_final_dir('ite_out/option_final', 'ite_out/option_decoded_lzss')
decode_final_dir('ite_out/naming_final', 'ite_out/naming_decoded_lzss')
