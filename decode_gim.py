#!/usr/bin/env python3
"""
decode_gim.py  –  Decode Venus & Braves GIM / ITE compressed textures
======================================================================
The game compresses all texture data (GIM body and ITE sub-blocks) using a
variant of LZSS. This script determines the correct parameters by testing
against the known GIM file format.

Usage:
    python3 decode_gim.py
"""

import struct, os
from PIL import Image

ARC_FILE = "cdimage_unpacked/seven_data_link/taka/title/btlst1.arc"
NAMING_FHM = "cdimage_unpacked/seven_data_link/futa/screen/naming.fhm"

# ── LZSS implementations ──────────────────────────────────────────────────────

def lzss_decompress(data, ei=11, ej=4, init_char=0x00, offset_bias=1):
    """
    Generic LZSS decompressor.
    ei = number of bits for back-reference offset
    ej = number of bits for back-reference length
    init_char = fill character for initial dictionary
    offset_bias = added to match offset (1 = standard, 18 = Namco variant)
    """
    N = 1 << ei          # dictionary size
    F = (1 << ej) + 2    # max match length
    threshold = 2        # min match length stored
    
    r = N - F              # initial fill position
    text_buf = bytearray([init_char] * N)
    
    out = bytearray()
    pos = 0
    flags = 0
    flag_bit = 0
    
    while pos < len(data):
        if flag_bit == 0:
            if pos >= len(data):
                break
            flags = data[pos]
            pos += 1
            flag_bit = 8
        
        flag_bit -= 1
        bit = (flags >> flag_bit) & 1
        
        if bit:  # literal
            if pos >= len(data):
                break
            c = data[pos]
            pos += 1
            out.append(c)
            text_buf[r] = c
            r = (r + 1) & (N - 1)
        else:    # back-reference
            if pos + 1 >= len(data):
                break
            i = data[pos] | (data[pos+1] << 8)
            pos += 2
            
            match_offset = (i & (N-1)) + offset_bias
            match_len = (i >> ei) + threshold
            
            for k in range(match_len):
                c = text_buf[(match_offset + k) & (N-1)]
                out.append(c)
                text_buf[r] = c
                r = (r + 1) & (N-1)
    
    return bytes(out)


def lzss_decompress_be(data, ei=11, ej=4, init_char=0x00):
    """LZSS with bit-flag read from MSB (big-endian flag byte)."""
    N = 1 << ei
    F = (1 << ej) + 2
    threshold = 2
    r = N - F
    text_buf = bytearray([init_char] * N)
    out = bytearray()
    pos = 0
    
    while pos < len(data):
        flags = data[pos]; pos += 1
        for bit_i in range(7, -1, -1):
            if pos >= len(data):
                break
            if (flags >> bit_i) & 1:  # literal
                c = data[pos]; pos += 1
                out.append(c)
                text_buf[r] = c
                r = (r + 1) & (N - 1)
            else:  # back-reference
                if pos + 1 >= len(data): break
                hi = data[pos]; lo = data[pos+1]; pos += 2
                match_offset = ((hi & 0x0F) << 8) | lo
                match_len = (hi >> 4) + threshold
                for k in range(match_len):
                    c = text_buf[(match_offset + k) & (N-1)]
                    out.append(c)
                    text_buf[r] = c
                    r = (r + 1) & (N-1)
    return bytes(out)


def namco_lzss(data):
    """
    Namco LZSS (used in Tales of series, etc.)
    Flag byte: bit 1 = literal, bit 0 = reference
    """
    out = bytearray()
    pos = 0
    N = 4096  # dictionary size (12 bits)
    threshold = 2
    r = N - 66  # initial fill position
    text_buf = bytearray(N)
    
    while pos < len(data) - 1:
        flags = data[pos]; pos += 1
        for i in range(8):
            if pos >= len(data): break
            if (flags >> i) & 1:  # literal
                c = data[pos]; pos += 1
                out.append(c)
                text_buf[r] = c
                r = (r + 1) & (N - 1)
            else:  # back-reference
                if pos + 1 >= len(data): break
                lo = data[pos]; hi = data[pos+1]; pos += 2
                match_offset = lo | ((hi & 0xF0) << 4)
                match_len = (hi & 0x0F) + threshold
                for k in range(match_len):
                    c = text_buf[(match_offset + k) & (N-1)]
                    out.append(c)
                    text_buf[r] = c
                    r = (r + 1) & (N-1)
    return bytes(out)


def rlz_decompress(data):
    """Simple RLE+LZ: flag byte bit=1→literal, bit=0→copy(offset,len)"""
    out = bytearray()
    pos = 0
    while pos < len(data):
        cmd = data[pos]; pos += 1
        for bit_pos in range(8):
            if pos >= len(data): break
            if (cmd >> bit_pos) & 1:  # literal run
                n = data[pos]; pos += 1
                for _ in range(n + 1):
                    if pos >= len(data): break
                    out.append(data[pos]); pos += 1
            else:  # back-reference
                if pos + 1 >= len(data): break
                offset = data[pos] | ((data[pos+1] & 0xF0) << 4); pos += 1
                length = (data[pos] & 0x0F) + 3; pos += 1
                for k in range(length):
                    c = out[len(out) - offset - 1] if len(out) > offset else 0
                    out.append(c)
    return bytes(out)


# ── Test against GIM ──────────────────────────────────────────────────────────

def test_decompress_gim():
    with open(ARC_FILE, 'rb') as f:
        arc = f.read()
    
    offsets = [struct.unpack_from('<I', arc, 4 + i*4)[0] for i in range(4)]
    gim_raw = arc[offsets[0]:offsets[1]]
    
    # GIM header is first 16 bytes, then compressed body
    gim_header = gim_raw[:16]
    gim_body   = gim_raw[16:]
    
    print(f"GIM: {len(gim_raw)} bytes total, body={len(gim_body)} bytes")
    print(f"Header: {gim_header.hex()}")
    print()
    
    # Try various LZSS configurations
    configs = [
        ("LZSS_11_4_LE_b0", lambda d: lzss_decompress(d, ei=11, ej=4, init_char=0x00, offset_bias=0)),
        ("LZSS_11_4_LE_b1", lambda d: lzss_decompress(d, ei=11, ej=4, init_char=0x00, offset_bias=1)),
        ("LZSS_12_4_LE_b0", lambda d: lzss_decompress(d, ei=12, ej=4, init_char=0x00, offset_bias=0)),
        ("LZSS_12_4_LE_b1", lambda d: lzss_decompress(d, ei=12, ej=4, init_char=0x00, offset_bias=1)),
        ("LZSS_11_4_BE",    lambda d: lzss_decompress_be(d, ei=11, ej=4)),
        ("LZSS_12_4_BE",    lambda d: lzss_decompress_be(d, ei=12, ej=4)),
        ("NAMCO_LZSS",      namco_lzss),
    ]
    
    for name, fn in configs:
        for skip in [0, 4, 8, 16]:
            try:
                result = fn(gim_body[skip:])
                # A valid GIM body would start with 0x02 (Picture block type)
                # or contain recognizable block types
                valid = len(result) > 1000
                # Check if result looks like GIM blocks (has 0x0002 or 0x0004 at aligned offsets)
                has_gim_blocks = False
                for off in range(0, min(len(result), 4096), 16):
                    bt = struct.unpack_from('<H', result, off)[0]
                    if bt in [0x0002, 0x0003, 0x0004, 0x0005]:
                        bs = struct.unpack_from('<I', result, off+4)[0]
                        if 16 < bs < len(result):
                            has_gim_blocks = True
                            break
                
                if valid and has_gim_blocks:
                    print(f"  ★ {name} (skip={skip}): {len(result)} bytes - HAS GIM BLOCKS!")
                    return name, fn, skip, result
                elif valid and len(result) > 50000:
                    print(f"  ✓ {name} (skip={skip}): {len(result)} bytes (large, might be valid)")
                    print(f"    First 32 bytes: {result[:32].hex()}")
                else:
                    if len(result) > 100:
                        print(f"  - {name} (skip={skip}): {len(result)} bytes")
            except Exception as e:
                pass
    
    return None, None, None, None


if __name__ == '__main__':
    os.makedirs("ite_out", exist_ok=True)
    test_decompress_gim()
