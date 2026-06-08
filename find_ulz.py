#!/usr/bin/env python3
"""Scan EE .text raw words for ULZ signature (srl by 10..13 near andi mask)."""
import struct

ELF = 'SLPS_251.96.orig'
TEXT_OFF = 0x1000
TEXT_VADDR = 0x100000
TEXT_SIZE = 0x334C30

elf = open(ELF, 'rb').read()
words = struct.unpack_from('<%dI' % (TEXT_SIZE // 4), elf, TEXT_OFF)

MASKS = {0x3ff: 10, 0x7ff: 11, 0xfff: 12, 0x1fff: 13}
REGN = ['zero','at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7',
        's0','s1','s2','s3','s4','s5','s6','s7','t8','t9','k0','k1','gp','sp','fp','ra']


def decode(w):
    op = (w >> 26) & 0x3f
    rs = (w >> 21) & 0x1f
    rt = (w >> 16) & 0x1f
    rd = (w >> 11) & 0x1f
    sa = (w >> 6) & 0x1f
    funct = w & 0x3f
    imm = w & 0xffff
    if op == 0x0c:  # andi
        return ('andi', rt, rs, imm)
    if op == 0 and funct == 0x02:  # srl
        return ('srl', rd, rt, sa)
    if op == 0 and funct == 0x03:  # sra
        return ('sra', rd, rt, sa)
    if op == 0 and funct == 0x00 and w != 0:  # sll
        return ('sll', rd, rt, sa)
    return None


srls = {}   # vaddr -> bits
andis = {}  # vaddr -> bits
for i, w in enumerate(words):
    va = TEXT_VADDR + i*4
    d = decode(w)
    if not d:
        continue
    if d[0] == 'srl' and d[3] in (10, 11, 12, 13):
        srls[va] = d[3]
    if d[0] == 'andi' and d[3] in MASKS:
        andis[va] = MASKS[d[3]]

print(f'srl(10-13): {len(srls)}   andi(mask): {len(andis)}')
hits = []
for va, bits in andis.items():
    for off in range(-8*4, 9*4, 4):
        v2 = va + off
        if srls.get(v2) == bits:
            hits.append((min(va, v2), bits))
            break
print(f'co-located hits: {len(hits)}')
for va, bits in sorted(hits):
    print(f'  near {va:#x}  disp_bits={bits}')
