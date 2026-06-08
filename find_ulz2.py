#!/usr/bin/env python3
"""Scan EE RAM for ULZ match-decode signature:
   srlv (length = val >> offsetBits) near addiu rX,rX,{2,3} (add base length),
   and sllv (mask = 1<<offsetBits) near addiu -1 (mask = (1<<bits)-1).
"""
import struct

ee = open('scratch/options_savestate/eeMemory.bin', 'rb').read()
N = len(ee) // 4
words = struct.unpack('<%dI' % N, ee[:N*4])


def dec(w):
    op = (w >> 26) & 0x3f
    rs = (w >> 21) & 0x1f
    rt = (w >> 16) & 0x1f
    rd = (w >> 11) & 0x1f
    funct = w & 0x3f
    imm = w & 0xffff
    simm = imm - 0x10000 if imm >= 0x8000 else imm
    if op == 0 and funct == 0x06:
        return ('srlv', rd, rt, rs)
    if op == 0 and funct == 0x04:
        return ('sllv', rd, rt, rs)
    if op == 0x09:
        return ('addiu', rt, rs, simm)
    return None


D = {}
for i, w in enumerate(words):
    d = dec(w)
    if d:
        D[i] = d

srlv_idx = [i for i, d in D.items() if d[0] == 'srlv']
sllv_idx = [i for i, d in D.items() if d[0] == 'sllv']
print('srlv:', len(srlv_idx), 'sllv:', len(sllv_idx))

# srlv near addiu +2/+3
print('\n=== srlv near addiu reg,reg,{2,3} (length = base + val>>bits) ===')
hits = []
for i in srlv_idx:
    for j in range(i-4, i+6):
        d = D.get(j)
        if d and d[0] == 'addiu' and d[3] in (2, 3) and d[1] == d[2]:
            hits.append((i*4, d[3])); break
for off, base in hits[:50]:
    print(f'  srlv near addiu+{base} @ EE {off:#x}')
print('total', len(hits))

# also: sllv near addiu -1  (mask=(1<<bits)-1)
print('\n=== sllv near addiu reg,reg,-1 (mask=(1<<bits)-1) ===')
hits2 = []
for i in sllv_idx:
    for j in range(i-2, i+6):
        d = D.get(j)
        if d and d[0] == 'addiu' and d[3] == -1:
            hits2.append(i*4); break
for off in hits2[:50]:
    print(f'  sllv near addiu-1 @ EE {off:#x}')
print('total', len(hits2))

# intersection: both signatures within 16 instructions -> the decompressor
print('\n=== regions with BOTH signatures (likely ULZ match decode) ===')
sa = set(h[0]//64 for h in hits)
sb = set(h//64 for h in hits2)
for blk in sorted(sa & sb):
    print(f'  ~EE {blk*64:#x}')
