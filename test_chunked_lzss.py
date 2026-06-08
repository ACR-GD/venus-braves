import sys, struct

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
offsets_list.append(len(entry3)) # The end of the entry

decompressed_chunks = []
for i in range(8):
    chunk_start = offsets_list[i]
    chunk_end = offsets_list[i+1]
    chunk_data = entry3[chunk_start:chunk_end]
    decomp = lzss_decompress(chunk_data)
    decompressed_chunks.append(decomp)
    print(f'Chunk {i}: size {len(chunk_data)} -> decompressed to {len(decomp)}')

total_decomp = b''.join(decompressed_chunks)
print(f'Total decompressed size: {len(total_decomp)}')
