import struct
import itertools

with open('scratch/options_savestate/eeMemory.bin', 'rb') as f:
    ee_ram = f.read()

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    data = f.read()

offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
entry3 = data[offsets[3]:offsets[4]]
offsets_list = [struct.unpack_from('<I', entry3, 0x10 + k*4)[0] for k in range(8)]
offsets_list.append(len(entry3))

chunks = []
for k in range(8):
    chunks.append(entry3[offsets_list[k]:offsets_list[k+1]])

def try_lzss(data, F, T, start_pos, flag_inv, flag_msb, pack_type, init_byte=0):
    N = 2048
    r = start_pos
    text_buf = bytearray([init_byte] * N)
    out = bytearray()
    pos = 0
    while pos < len(data) and len(out) < 64:
        flags = data[pos]; pos += 1
        if flag_inv: flags = ~flags & 0xFF
        for i in range(8):
            if pos >= len(data) or len(out) >= 64: break
            bit = (flags >> i) & 1 if not flag_msb else (flags >> (7-i)) & 1
            if bit == 1:
                c = data[pos]; pos += 1
                out.append(c)
                text_buf[r] = c
                r = (r + 1) & (N - 1)
            else:
                if pos + 1 >= len(data): break
                lo = data[pos]; hi = data[pos+1]; pos += 2
                
                if pack_type == 0:
                    match_offset = lo | ((hi & 0x0F) << 8)
                    match_len = (hi >> 4) + T
                elif pack_type == 1:
                    match_offset = (hi << 4) | (lo >> 4)
                    match_len = (lo & 0x0F) + T
                elif pack_type == 2:
                    match_offset = lo | ((hi & 0xF0) << 4)
                    match_len = (hi & 0x0F) + T
                elif pack_type == 3:
                    match_offset = (lo << 4) | (hi >> 4)
                    match_len = (hi & 0x0F) + T
                else:
                    return None
                    
                for k in range(match_len):
                    c = text_buf[(match_offset + k) & (N-1)]
                    out.append(c)
                    text_buf[r] = c
                    r = (r + 1) & (N-1)
    return bytes(out)

print("Starting brute force...")
found = False

for chunk_idx, chunk in enumerate(chunks[:4]):
    print(f"Testing chunk {chunk_idx}...")
    for F in [18, 16, 17, 34]:
        for T in [2, 3, 1]:
            for start_pos in [2048 - F, 2048 - F - T, 0, 2048 - 16, 2048 - 18, 2048 - 1]:
                for flag_inv in [False, True]:
                    for flag_msb in [False, True]:
                        for pack_type in range(4):
                            for init_byte in [0, 0x20, 0xFF]:
                                out = try_lzss(chunk, F, T, start_pos, flag_inv, flag_msb, pack_type, init_byte)
                                if out is None or len(out) < 32: continue
                                
                                idx = ee_ram.find(out[:32])
                                if idx != -1:
                                    print(f"MATCH FOUND at RAM offset {hex(idx)} for chunk {chunk_idx}!")
                                    print(f"Parameters: F={F}, T={T}, start_pos={start_pos}, flag_inv={flag_inv}, flag_msb={flag_msb}, pack_type={pack_type}, init_byte={hex(init_byte)}")
                                    
                                    if len(out) >= 64 and ee_ram.find(out[:64]) != -1:
                                        print("64-byte match VERIFIED!")
                                        found = True
                                        break
                        if found: break
                    if found: break
                if found: break
            if found: break
        if found: break
    if found: break

if not found:
    print("No match found in first 4 chunks.")
