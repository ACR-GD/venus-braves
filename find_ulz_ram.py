#!/usr/bin/env python3
"""Scan all of EE RAM for ULZ decompressor signatures."""
import struct

ee = open('scratch/options_savestate/eeMemory.bin', 'rb').read()
N = len(ee) // 4
words = struct.unpack('<%dI' % N, ee[:N*4])

MASKS = {0x3ff: 10, 0x7ff: 11, 0xfff: 12, 0x1fff: 13}


def dec(w):
    op = (w >> 26) & 0x3f
    rt = (w >> 16) & 0x1f
    rd = (w >> 11) & 0x1f
    rs = (w >> 21) & 0x1f
    sa = (w >> 6) & 0x1f
    funct = w & 0x3f
    imm = w & 0xffff
    if op == 0x0c:
        return ('andi', rt, rs, imm)
    if op == 0 and funct == 0x02:
        return ('srl', rd, rt, sa)
    if op == 0 and funct == 0x06:
        return ('srlv', rd, rt, rs)
    if op == 0 and funct == 0x23:
        return ('subu', rd, rs, rt)
    if op == 0x24:
        return ('lbu', rt, rs, imm)
    if op == 0x28:
        return ('sb', rt, rs, imm)
    return None


srl_bits = {}
andi_bits = {}
srlv_at = []
copy_at = []  # lbu followed soon by sb
decoded = {}
for i, w in enumerate(words):
    d = dec(w)
    if not d:
        continue
    decoded[i] = d
    if d[0] == 'srl' and d[3] in (10, 11, 12, 13):
        srl_bits[i] = d[3]
    elif d[0] == 'andi' and d[3] in MASKS:
        andi_bits[i] = MASKS[d[3]]
    elif d[0] == 'srlv':
        srlv_at.append(i)

# 1) srl(bits) co-located with andi(matching mask)
print('=== srl/andi disp_bits signature ===')
hits = []
for i, bits in andi_bits.items():
    for j in range(i-8, i+9):
        if srl_bits.get(j) == bits:
            hits.append((min(i, j)*4, bits)); break
for off, bits in hits[:40]:
    print(f'  EE @ {off:#x}  disp_bits={bits}')
print(f'total {len(hits)}')

# 2) subu rd,rDst,rDisp near lbu/sb copy loop
print('\n=== subu near lbu+sb (dst-disp copy loop) ===')
cnt = 0
for i in range(len(words)-6):
    d = decoded.get(i)
    if not d or d[0] != 'subu':
        continue
    window = [decoded.get(i+k) for k in range(-2, 7)]
    has_lbu = any(x and x[0] == 'lbu' for x in window)
    has_sb = any(x and x[0] == 'sb' for x in window)
    if has_lbu and has_sb:
        cnt += 1
        if cnt <= 25:
            print(f'  EE @ {i*4:#x}')
print(f'total subu+copy windows: {cnt}')
