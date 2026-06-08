#!/usr/bin/env python3
import sys
from capstone import *

ee = open('scratch/options_savestate/eeMemory.bin', 'rb').read()
md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)

def disasm(center, before=40, after=80):
    start = center - before*4
    print(f'\n===== around {center:#x} =====')
    for off in range(start, center + after*4, 4):
        word = ee[off:off+4]
        ins = list(md.disasm(word, off))
        if ins:
            i = ins[0]
            mark = ' <<<' if off == center else ''
            print(f'  {off:#x}: {i.mnemonic:8} {i.op_str}{mark}')
        else:
            v = int.from_bytes(word, 'little')
            mark = ' <<<' if off == center else ''
            print(f'  {off:#x}: .word    {v:#010x}{mark}')

for a in [int(x, 16) for x in sys.argv[1:]]:
    disasm(a)
