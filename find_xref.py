import sys, struct

with open('SLPS_251.96.orig', 'rb') as f:
    data = f.read()

target = 0x553d78
target_hi = target >> 16
target_lo = target & 0xFFFF
if target_lo >= 0x8000:
    target_hi += 1

print(f"Looking for lui reg, {hex(target_hi)} and addiu reg, reg, {hex(target_lo)}")

# Find all LUI instructions
for i in range(0x1000, len(data) - 4, 4):
    word = struct.unpack_from('<I', data, i)[0]
    if (word >> 26) == 0x0F: # LUI
        imm = word & 0xFFFF
        if imm == target_hi:
            # Check next few instructions for addiu
            for j in range(i, i + 32, 4):
                word2 = struct.unpack_from('<I', data, j)[0]
                if (word2 >> 26) == 0x09: # ADDIU
                    imm2 = word2 & 0xFFFF
                    if imm2 == target_lo:
                        vaddr = 0x00100000 + i - 0x1000
                        print(f"Found xref at file offset {hex(i)}, virtual addr {hex(vaddr)}")
