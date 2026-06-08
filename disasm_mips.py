import sys
from capstone import *
from capstone.mips import *

def read_elf_section(filename, offset, size):
    with open(filename, 'rb') as f:
        f.seek(offset)
        return f.read(size)

def disassemble(code, vaddr):
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    
    # We will disassemble instruction by instruction, and if one fails, we skip 4 bytes
    
    offset = 0
    while offset < len(code):
        try:
            insns = list(md.disasm(code[offset:offset+4], vaddr + offset))
            if insns:
                i = insns[0]
                print("0x%x:\t%s\t%s" % (i.address, i.mnemonic, i.op_str))
            else:
                print("0x%x:\t.word\t0x%08x" % (vaddr + offset, int.from_bytes(code[offset:offset+4], byteorder='little')))
        except Exception as e:
            print("0x%x:\t.word\t0x%08x" % (vaddr + offset, int.from_bytes(code[offset:offset+4], byteorder='little')))
        offset += 4

if __name__ == '__main__':
    target_pc = 0x001AF020
    start_vaddr = 0x001AF008
    end_vaddr = 0x001AF200
    
    start_offset = 0xb0020 - (target_pc - start_vaddr)
    code = read_elf_section('SLPS_251.96.orig', start_offset, end_vaddr - start_vaddr)
    
    with open('scratch/disasm.txt', 'w') as f:
        f.write(f"--- Disassembly around {hex(target_pc)} ---\n")
        sys.stdout = f
        disassemble(code, start_vaddr)
        sys.stdout = sys.__stdout__
