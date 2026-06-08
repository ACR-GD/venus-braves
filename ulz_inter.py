#!/usr/bin/env python3
"""Test interleaved 32-bit-flag LZSS: [flag32][inline tokens]..."""
from ulz_exact import chunks

def decode(buf, end, ob, lit_set, dist_plus, lbase, max_out=65536):
    out = bytearray(); p = 0; mask = (1 << ob) - 1
    flags = 0; fm = 0
    while p < end and len(out) < max_out:
        if fm == 0:
            if p + 4 > end: break
            flags = buf[p] | (buf[p+1]<<8) | (buf[p+2]<<16) | (buf[p+3]<<24); p += 4
            fm = 0x80000000
        bit = (flags & fm) != 0; fm >>= 1
        is_lit = bit if lit_set else (not bit)
        if is_lit:
            if p >= end: break
            out.append(buf[p]); p += 1
        else:
            if p + 2 > end: break
            v = buf[p] | (buf[p+1]<<8); p += 2
            offset = v & mask; length = lbase + (v >> ob)
            src = len(out) - (offset + dist_plus)
            if offset + dist_plus < 1 or src < 0: break
            for _ in range(length):
                if len(out) >= max_out: break
                out.append(out[src]); src += 1
    return bytes(out), p

if __name__ == '__main__':
    for ci in (0,1,2,3):
        c = chunks[ci]
        real = len(c.rstrip(b'\x00'))  # data without trailing zero padding
        print('chunk%d len=%d realdata=%d' % (ci, len(c), real))
        best = []
        for ob in (10,11,12,13):
            for lit_set in (True, False):
                for dp in (0,1):
                    for lbase in (2,3):
                        out, consumed = decode(c, real, ob, lit_set, dp, lbase)
                        # clean = consumed all real data, sensible output
                        if consumed >= real-2 and len(out) in (1024,2048,4096,8192):
                            best.append((len(out), ob, lit_set, dp, lbase, consumed, out[:8].hex()))
        for sz,ob,ls,dp,lb,cons,h in best[:8]:
            print('   OUT=%d ob=%d lit_set=%s dp=%d lbase=%d consumed=%d/%d head=%s'%(sz,ob,ls,dp,lb,cons,real,h))
        if not best:
            # show what sizes we get for ob=12 variants
            for ob in (12,):
                for lit_set in (True,False):
                    out,cons=decode(c,real,ob,lit_set,1,3)
                    print('   (diag ob12 lit_set=%s) out=%d consumed=%d/%d'%(lit_set,len(out),cons,real))
