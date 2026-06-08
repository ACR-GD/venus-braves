import struct

with open('SLPS_251.96.orig', 'rb') as f:
    elf = f.read()

ph_off = struct.unpack_from('<I', elf, 0x1C)[0]
ph_ent = struct.unpack_from('<H', elf, 0x2A)[0]
ph_num = struct.unpack_from('<H', elf, 0x2C)[0]

print("Program Headers:")
for i in range(ph_num):
    offset = ph_off + i * ph_ent
    p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = struct.unpack_from('<IIIIIIII', elf, offset)
    print(f"  [{i}] type={p_type} offset=0x{p_offset:X} vaddr=0x{p_vaddr:X} filesz=0x{p_filesz:X} memsz=0x{p_memsz:X}")

def vaddr_to_offset(vaddr):
    for i in range(ph_num):
        offset = ph_off + i * ph_ent
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = struct.unpack_from('<IIIIIIII', elf, offset)
        if p_type == 1 and p_vaddr <= vaddr < p_vaddr + p_memsz:
            return p_offset + (vaddr - p_vaddr)
    return None

target = 0x001AF020
print(f"\nOffset for {hex(target)}: {hex(vaddr_to_offset(target)) if vaddr_to_offset(target) else 'Not Found'}")

