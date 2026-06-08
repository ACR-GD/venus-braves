#!/usr/bin/env python3
"""Classic Okumura ring-buffer LZSS, interleaved flags. Self-consistency on chunks."""
from ulz_exact import chunks

def decode(buf, end, N, F, thresh, init, ob, msb_first, lit_set, max_out=65536):
    win = bytearray([init]) * N
    r = (N - F) & (N - 1) if (N & (N-1)) == 0 else (N - F)
    out = bytearray(); p = 0; flags = 0; cnt = 0
    omask = (1 << ob) - 1
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
            c = buf[p]; p += 1
            out.append(c); win[r] = c; r = (r + 1) % N
        else:
            if p + 2 > end: break
            b0 = buf[p]; b1 = buf[p+1]; p += 2
            # classic: offset = b0 | ((b1 & 0xF0) << 4); length = (b1 & 0x0F) + thresh
            offset = b0 | ((b1 & 0xF0) << 4)
            length = (b1 & 0x0F) + thresh
            offset &= (N - 1)
            for _ in range(length):
                c = win[(offset) % N]; offset += 1
                out.append(c); win[r] = c; r = (r + 1) % N
                if len(out) >= max_out: break
    return bytes(out), p

if __name__ == '__main__':
    for ci in (0,1,2,3,4):
        c = chunks[ci]; real = len(c.rstrip(b'\x00'))
        found = []
        for N in (4096, 2048, 1024):
            for F in (18, 34, 66):
                for thresh in (2, 3):
                    for init in (0x00, 0x20):
                        for msb in (True, False):
                            for ls in (True, False):
                                out, cons = decode(c, real, N, F, thresh, init, 12, msb, ls)
                                if cons >= real-1 and 512 <= len(out) <= 16384:
                                    found.append((len(out), N, F, thresh, init, msb, ls, cons))
        from collections import Counter
        szs = Counter(f[0] for f in found)
        print('chunk%d real=%d : %d clean decodes, output sizes=%s' % (ci, real, len(found), dict(szs)))
        for f in found[:4]:
            print('   out=%d N=%d F=%d th=%d init=%#x msb=%s lit_set=%s consumed=%d'%f)
