#!/usr/bin/env python3
"""Ring-buffer LZSS with flexible match encoding; rank decodes of chunk0 by output entropy."""
import math
from collections import Counter
from ulz_exact import chunks

def ent(b):
    if not b: return 99
    c = Counter(b); n = len(b)
    return -sum(v/n*math.log2(v/n) for v in c.values())

def decode(buf, end, N, F, thresh, init, ob, msb_first, lit_set, split, max_out=70000):
    """split: 'lo' offset in low ob bits / length in high ; 'classic' = b0|((b1&0xF0)<<4),len=(b1&0xF)+thresh"""
    win = bytearray([init]) * N
    r = N - F
    out = bytearray(); p = 0; flags = 0; cnt = 0
    omask = (1 << ob) - 1
    lenbits = 16 - ob
    while p < end and len(out) < max_out:
        if cnt == 0:
            if p >= end: break
            flags = buf[p]; p += 1; cnt = 8
        if msb_first:
            bit = (flags >> 7) & 1; flags = (flags << 1) & 0xff
        else:
            bit = flags & 1; flags >>= 1
        cnt -= 1
        is_lit = (bit == 1) if lit_set else (bit == 0)
        if is_lit:
            if p >= end: break
            c = buf[p]; p += 1; out.append(c); win[r] = c; r = (r + 1) % N
        else:
            if p + 2 > end: break
            b0 = buf[p]; b1 = buf[p+1]; p += 2
            if split == 'classic':
                offset = b0 | ((b1 & 0xF0) << 4); length = (b1 & 0x0F) + thresh
            else:  # 16-bit little-endian, offset low ob bits, length high
                v = b0 | (b1 << 8); offset = v & omask; length = (v >> ob) + thresh
            offset %= N
            for _ in range(length):
                c = win[offset % N]; offset += 1
                out.append(c); win[r] = c; r = (r + 1) % N
                if len(out) >= max_out: break
    return bytes(out), p

if __name__ == '__main__':
    c = chunks[0]; real = len(c.rstrip(b'\x00'))
    cands = []
    for N in (4096, 2048, 8192):
        for F in (18, 34, 66, 18):
            for thresh in (2, 3):
                for init in (0, 0x20):
                    for msb in (True, False):
                        for ls in (True, False):
                            for split in ('classic', 'lo'):
                                for ob in ((12,) if split == 'classic' else (10, 11, 12, 13)):
                                    out, cons = decode(c, real, N, F, thresh, init, ob, msb, ls, split)
                                    if cons >= real - 1 and len(out) >= 256:
                                        cands.append((ent(out), len(out), N, F, thresh, init, msb, ls, split, ob, out))
    cands.sort(key=lambda x: x[0])
    print('lowest-entropy chunk0 decodes (most image-like):')
    seen=set()
    for e, L, N, F, th, ini, msb, ls, sp, ob, out in cands[:15]:
        print('  ent=%.2f out=%5d N=%d F=%d th=%d init=%#x msb=%s ls=%s split=%s ob=%d head=%s'
              % (e, L, N, F, th, ini, msb, ls, sp, ob, out[:12].hex()))
