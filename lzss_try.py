#!/usr/bin/env python3
"""Brute-force interleaved-LZSS variants of chunk0 against ground-truth uploads."""
import glob, os, struct
from ulz_exact import chunks

CAP = 128

def decode(buf, ob, lb, lbase, msb_first, lit_is_one, dist_plus, off_high, target, cap):
    """Interleaved LZSS: control byte then 8 tokens. Compare prefix vs target."""
    out = bytearray(); n = len(buf); p = 0
    mask = (1 << ob) - 1
    tlen = min(len(target), cap)
    ctrl = 0; cnt = 0
    while len(out) < tlen:
        if cnt == 0:
            if p >= n: break
            ctrl = buf[p]; p += 1; cnt = 8
        if msb_first:
            bit = (ctrl >> 7) & 1; ctrl = (ctrl << 1) & 0xff
        else:
            bit = ctrl & 1; ctrl >>= 1
        cnt -= 1
        is_lit = (bit == 1) if lit_is_one else (bit == 0)
        if is_lit:
            if p >= n: break
            b = buf[p]; p += 1
            if b != target[len(out)]: break
            out.append(b)
        else:
            if p + 2 > n: break
            v = buf[p] | (buf[p+1] << 8); p += 2
            if off_high:
                length = (v & ((1<<lb)-1)) + lbase; offset = v >> lb
            else:
                offset = v & mask; length = (v >> ob) + lbase
            src = len(out) - (offset + dist_plus)
            if offset + dist_plus < 1 or src < 0: break
            bad = False
            for _ in range(length):
                if len(out) >= tlen or out[src] != target[len(out)]:
                    bad = True; break
                out.append(out[src]); src += 1
            if bad: break
    return len(out)

def best(chunk, target):
    b = (0, None)
    for ob in (10,11,12,13):
        lb = 16 - ob
        for lbase in (1,2,3):
            for msb in (True,False):
                for lit1 in (True,False):
                    for dp in (0,1):
                        for oh in (False,True):
                            m = decode(chunk, ob, lb, lbase, msb, lit1, dp, oh, target, CAP)
                            if m > b[0]:
                                b = (m, (ob,lbase,msb,lit1,dp,oh))
    return b

if __name__ == '__main__':
    ups = sorted(glob.glob('scratch/gs_uploads/up*_8192.bin'))
    print('chunk0 vs %d uploads, interleaved LZSS, cap=%d' % (len(ups), CAP))
    res = []
    for u in ups:
        t = open(u,'rb').read()
        m,p = best(chunks[0], t)
        res.append((m, os.path.basename(u), p))
    res.sort(reverse=True)
    for m,name,p in res[:10]:
        print('  %-26s match=%3d %s' % (name,m,p))
