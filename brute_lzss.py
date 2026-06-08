import sys, struct

def try_lzss(data, F, THRESHOLD, offset_bias):
    N = 2048
    r = N - F
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
                match_offset = (lo | ((hi & 0x0F) << 8)) + offset_bias
                match_len = (hi >> 4) + THRESHOLD
                for k in range(match_len):
                    c = text_buf[(match_offset + k) & (N-1)]
                    out.append(c)
                    text_buf[r] = c
                    r = (r + 1) & (N-1)
    return bytes(out)

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    data = f.read()

offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
entry3 = data[offsets[3]:offsets[4]]
chunk0 = entry3[0x30:0x3C0]

print('Brute forcing LZSS parameters...')
valid = set()
for F in range(16, 20):
    for T in range(1, 4):
        for bias in [0, 1, 18]:
            try:
                dec = try_lzss(chunk0, F, T, bias)
                valid.add((F, T, bias, len(dec)))
            except:
                pass

for v in sorted(valid, key=lambda x: x[3]):
    print(f'F={v[0]} T={v[1]} Bias={v[2]} -> {v[3]} bytes')

