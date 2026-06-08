import struct
import os

with open('scratch/options_savestate/eeMemory.bin', 'rb') as f:
    ee_ram = bytearray(f.read())

# The width and height of the target image is 230x55
# VRAM padded sizes would be something like 256x64 (PSMT4) = 8192 bytes
target_size = 8192

print("Scanning for blocks with high transparency (many zeroes)...")

found_count = 0
for offset in range(0, len(ee_ram) - target_size, 256):
    block = ee_ram[offset:offset+target_size]
    
    # Quick heuristic: count zeroes
    zero_count = block.count(0x00)
    
    # If the block is more than 85% zeroes (typical for text UI elements with lots of empty space)
    # but not 100% zeroes
    if zero_count > (target_size * 0.85) and zero_count < target_size:
        # Save potential block
        out_path = f"scratch/options_dump/candidate_0x{offset:08X}.bin"
        with open(out_path, 'wb') as outf:
            outf.write(block)
        found_count += 1
        if found_count > 50:
            break

print(f"Found {found_count} potential uncompressed texture candidates in EE RAM.")
