import sys, struct
from capstone import *
from capstone.mips import *

with open('SLPS_251.96.orig', 'rb') as f:
    data = f.read()

start_vaddr = 0x32AE00
end_vaddr = 0x32B100

start_file = start_vaddr - 0x00100000 + 0x1000
end_file = end_vaddr - 0x00100000 + 0x1000

code = data[start_file:end_file]

md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
for i in md.disasm(code, start_vaddr):
    print(f"0x{i.address:x}:\t{i.mnemonic}\t{i.op_str}")

