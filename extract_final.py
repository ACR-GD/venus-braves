import os, struct
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

def process_fhm(filepath, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(filepath, 'rb') as f:
        data = f.read()
    n_entries = struct.unpack_from('<I', data, 0)[0]
    offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(n_entries)]
    offsets.append(len(data))
    
    entries = []
    for i in range(n_entries):
        entry_data = data[offsets[i]:offsets[i+1]]
        if len(entry_data) > 0:
            first = struct.unpack_from('<I', entry_data, 0)[0]
            start = 0
            if first & 0xFF000000 == 0x80000000:
                start = 0x50
            try:
                decomp = lzss_decompress(entry_data[start:])
                entries.append(decomp)
                with open(os.path.join(out_dir, f'entry_{i:02d}.bin'), 'wb') as fout:
                    fout.write(decomp)
            except Exception as e:
                entries.append(None)
                print(f"Error decompressing {i}: {e}")
        else:
            entries.append(None)
            
    # Assuming entry 0 is CLUT
    if entries[0]:
        # Usually it has an ITE header too? No, CLUT is often just raw bytes or another format
        # If it starts with ITE\x00 it has a header.
        clut_data = entries[0]
        if clut_data.startswith(b'ITE\x00'):
            clut_data = clut_data[0x30:]
        pal_sw = build_palette(clut_data, 256, swizzle=True)
        pal_lin = build_palette(clut_data, 256, swizzle=False)
        
        for i in range(1, len(entries)):
            if not entries[i]: continue
            if entries[i].startswith(b'ITE\x00'):
                w = struct.unpack_from('<I', entries[i], 0x04)[0]
                h = struct.unpack_from('<I', entries[i], 0x08)[0]
                pixels = entries[i][0x30:]
                
                sw8, sw_w8, sw_h8 = deswizzle_psmt8(pixels, w, h)
                img_sw = apply_palette(sw8, sw_w8, sw_h8, pal_sw)
                if w != sw_w8 or h != sw_h8:
                    img_sw = img_sw.crop((0, 0, w, h))
                img_sw.save(os.path.join(out_dir, f'entry_{i:02d}_{w}x{h}_sw.png'))
                
                img_lin = apply_palette(sw8, sw_w8, sw_h8, pal_lin)
                if w != sw_w8 or h != sw_h8:
                    img_lin = img_lin.crop((0, 0, w, h))
                img_lin.save(os.path.join(out_dir, f'entry_{i:02d}_{w}x{h}_lin.png'))

process_fhm("cdimage_unpacked/seven_data_link/futa/screen/option.fhm", "ite_out/option_final")
process_fhm("cdimage_unpacked/seven_data_link/futa/screen/naming.fhm", "ite_out/naming_final")
