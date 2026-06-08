import struct
import os

with open('cdimage_unpacked/seven_data_link/futa/screen/option.fhm', 'rb') as f:
    fhm_data = bytearray(f.read())

num_entries = struct.unpack_from('<I', fhm_data, 0)[0]
offsets = [struct.unpack_from('<I', fhm_data, 4 + i*4)[0] for i in range(num_entries + 1)]

entry3_off = offsets[3]
entry4_off = offsets[4]

entry3_data = bytearray(fhm_data[entry3_off:entry4_off])

# We will modify Entry 3 to be uncompressed.
# Let's say we want to upload 2 chunks of 8192 bytes each.
# VRAM addresses: 0x2340, 0x2360
# VRAM 0x2360 - 0x2340 = 0x20 (32 pages * 256 bytes = 8192 bytes)

# We write the uncompressed VRAM addresses to the header
struct.pack_into('<I', entry3_data, 0x10, 0x80002340)
struct.pack_into('<I', entry3_data, 0x14, 0x80002360)
struct.pack_into('<I', entry3_data, 0x18, 0x80002380) # End bound for chunk 1

# Zero out the rest of the 8 addresses
for i in range(3, 8):
    struct.pack_into('<I', entry3_data, 0x10 + i*4, 0x00000000)

# Create dummy swizzled pixel data (just all white/visible color)
dummy_payload = b'\xFF' * (8192 * 2)

new_entry3 = entry3_data[:0x30] + dummy_payload

# Rebuild the FHM file
new_fhm = fhm_data[:entry3_off] + new_entry3

# Fix the offsets for subsequent entries
size_diff = len(new_entry3) - len(entry3_data)
for i in range(4, num_entries):
    struct.pack_into('<I', new_fhm, 4 + i*4, offsets[i] + size_diff)

new_fhm += fhm_data[entry4_off:]

os.makedirs('scratch/iso_test', exist_ok=True)
with open('scratch/iso_test/option.fhm', 'wb') as f:
    f.write(new_fhm)

print("Created test uncompressed option.fhm")
