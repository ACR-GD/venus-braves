import struct
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

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    data = f.read()

offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
entry3 = data[offsets[3]:offsets[4]]
offsets_list = [struct.unpack_from('<I', entry3, 0x10 + k*4)[0] for k in range(8)]
offsets_list.append(len(entry3))

decompressed_data = bytearray()
for k in range(8):
    chunk = entry3[offsets_list[k]:offsets_list[k+1]]
    dec = lzss_decompress(chunk)
    decompressed_data.extend(dec)

print(f"Total decompressed size: {len(decompressed_data)}")

with open('scratch/decompressed_e3.bin', 'wb') as f:
    f.write(decompressed_data)

