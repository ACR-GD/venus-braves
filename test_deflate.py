import zlib
import struct

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    data = f.read()

offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
entry3 = data[offsets[3]:offsets[4]]
offsets_list = [struct.unpack_from('<I', entry3, 0x10 + k*4)[0] for k in range(8)]
chunk0 = entry3[offsets_list[0]:offsets_list[1]]

for wbits in range(-15, 16):
    if wbits == 0: continue
    try:
        decomp = zlib.decompress(chunk0, wbits)
        print(f"Success with wbits={wbits}! Decompressed size: {len(decomp)}")
    except Exception as e:
        pass

print("Done.")
