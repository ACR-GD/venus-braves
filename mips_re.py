#!/usr/bin/env python3
"""
mips_re.py - MIPS R5900 Reverse Engineering Toolkit for Venus & Braves
"""
import struct
import capstone

ELF_PATH = 'extracted_iso/SLPS_251.96'

# ELF section layout
SECTIONS = {
    '.text':   {'vaddr': 0x00100000, 'offset': 0x001000, 'size': 0x334B80},
    '.data':   {'vaddr': 0x00434C80, 'offset': 0x335C80, 'size': 0x0EB888},
    '.rodata': {'vaddr': 0x00520E80, 'offset': 0x421E80, 'size': 0x0456D0},
    '.sdata':  {'vaddr': 0x00567900, 'offset': 0x468900, 'size': 0x001CA5},
}

with open(ELF_PATH, 'rb') as f:
    ELF = f.read()

def vaddr_to_offset(va):
    for name, s in SECTIONS.items():
        if s['vaddr'] <= va < s['vaddr'] + s['size']:
            return va - s['vaddr'] + s['offset']
    return None

def offset_to_vaddr(off):
    for name, s in SECTIONS.items():
        if s['offset'] <= off < s['offset'] + s['size']:
            return off - s['offset'] + s['vaddr']
    return None

def read_word(va):
    off = vaddr_to_offset(va)
    if off is None: return None
    return struct.unpack_from('<I', ELF, off)[0]

def read_bytes(va, size):
    off = vaddr_to_offset(va)
    if off is None: return None
    return ELF[off:off+size]

# Capstone MIPS disassembler
cs = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN)
cs.detail = True

def disassemble(va, count=20):
    """Disassemble <count> instructions starting at virtual address <va>."""
    data = read_bytes(va, count * 4)
    if data is None:
        print(f"  Cannot read at 0x{va:08X}")
        return []
    insns = list(cs.disasm(data, va))
    return insns[:count]

def print_disasm(va, count=20, highlight_vas=None):
    """Pretty-print disassembly with address highlights."""
    insns = disassemble(va, count)
    highlight_vas = highlight_vas or set()
    for insn in insns:
        marker = " <--" if insn.address in highlight_vas else ""
        print(f"  0x{insn.address:08X}:  {insn.bytes.hex():<10}  {insn.mnemonic:<8} {insn.op_str}{marker}")
    return insns

def find_exact_address_loads(target_va, search_section='.text'):
    """
    Find all LUI+ADDIU instruction pairs that load exactly target_va.
    Returns list of (lui_va, addiu_va) tuples.
    """
    sec = SECTIONS[search_section]
    sec_data = ELF[sec['offset']:sec['offset']+sec['size']]
    base_va = sec['vaddr']
    
    hi = (target_va >> 16) & 0xFFFF
    lo = target_va & 0xFFFF
    
    # MIPS sign extension: if lo16 >= 0x8000, LUI value is hi+1
    if lo >= 0x8000:
        lui_imm = (hi + 1) & 0xFFFF
    else:
        lui_imm = hi
    
    # lo16 as signed 16-bit for ADDIU
    lo_signed = lo if lo < 0x8000 else lo - 0x10000
    
    results = []
    for i in range(0, len(sec_data)-7, 4):
        w = struct.unpack_from('<I', sec_data, i)[0]
        # LUI: opcode=0x0F, rt=any, imm=lui_imm
        if (w >> 26) == 0x0F and (w & 0xFFFF) == lui_imm:
            lui_va = base_va + i
            rt = (w >> 16) & 0x1F
            # Scan forward for ADDIU/ORI with same or related register
            for j in range(1, 10):
                if i + j*4 >= len(sec_data): break
                w2 = struct.unpack_from('<I', sec_data, i + j*4)[0]
                op2 = (w2 >> 26) & 0x3F
                rs2 = (w2 >> 21) & 0x1F
                rt2 = (w2 >> 16) & 0x1F
                imm2 = w2 & 0xFFFF
                imm2s = imm2 if imm2 < 0x8000 else imm2 - 0x10000
                
                # ADDIU rt, rs, imm where rs==rt (LUI result) and imm == lo16
                if op2 == 0x09 and rs2 == rt and imm2s == lo_signed:
                    addiu_va = base_va + i + j*4
                    results.append((lui_va, addiu_va))
                    break
                # ORI rt, rs, imm
                elif op2 == 0x0D and rs2 == rt and imm2 == lo:
                    ori_va = base_va + i + j*4
                    results.append((lui_va, ori_va))
                    break
    return results

def find_function_start(va):
    """Heuristically find the start of the function containing va by scanning back."""
    # Look for: addiu sp, sp, -N (function prologue)
    # MIPS function prologue: addiu $sp, $sp, -N where N > 0
    scan_va = (va & ~3)
    for back in range(0, 0x400, 4):
        check_va = scan_va - back
        w = read_word(check_va)
        if w is None: break
        # addiu sp, sp, imm: opcode=0x09, rs=sp(29), rt=sp(29), imm<0
        if (w >> 26) == 0x09 and ((w >> 21) & 0x1F) == 29 and ((w >> 16) & 0x1F) == 29:
            imm = w & 0xFFFF
            if imm >= 0x8000:  # negative value = stack allocation
                return check_va
    return None

def decompile_function(func_va, max_insns=200):
    """Disassemble an entire function and track LUI/ADDIU address loads."""
    insns = disassemble(func_va, max_insns)
    
    # Track register values (partial simulation for address loads)
    reg_vals = {}  # reg -> (value, source_va)
    
    loaded_addrs = []
    calls = []
    
    for insn in insns:
        words = struct.unpack('<I', insn.bytes)[0]
        op = (words >> 26) & 0x3F
        rs = (words >> 21) & 0x1F
        rt = (words >> 16) & 0x1F
        imm = words & 0xFFFF
        imms = imm if imm < 0x8000 else imm - 0x10000
        
        if op == 0x0F:  # LUI
            reg_vals[rt] = (imm << 16, insn.address)
        elif op == 0x09:  # ADDIU
            if rs in reg_vals:
                base, _ = reg_vals[rs]
                val = (base + imms) & 0xFFFFFFFF
                reg_vals[rt] = (val, insn.address)
                if 0x00520E80 <= val <= 0x00566700 or 0x00434C80 <= val <= 0x00520E80:
                    loaded_addrs.append((insn.address, val))
        elif op == 0x0D:  # ORI
            if rs in reg_vals:
                base, _ = reg_vals[rs]
                val = (base | imm) & 0xFFFFFFFF
                reg_vals[rt] = (val, insn.address)
                if 0x00520E80 <= val <= 0x00566700 or 0x00434C80 <= val <= 0x00520E80:
                    loaded_addrs.append((insn.address, val))
        elif op == 0x00:  # SPECIAL
            func6 = words & 0x3F
            if func6 == 0x09:  # JALR
                rs2 = (words >> 21) & 0x1F
                if rs2 in reg_vals:
                    calls.append((insn.address, reg_vals[rs2][0]))
        elif op == 0x03:  # JAL
            target = (words & 0x03FFFFFF) << 2 | (insn.address & 0xF0000000)
            calls.append((insn.address, target))
    
    return insns, loaded_addrs, calls


if __name__ == '__main__':
    print("MIPS RE toolkit loaded. Use interactively.")
    print(f"ELF loaded: {len(ELF)} bytes")
    
    # Quick test
    print("\nTest: Disassembly at entry point 0x100008:")
    print_disasm(0x100008, count=10)
