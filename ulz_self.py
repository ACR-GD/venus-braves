#!/usr/bin/env python3
"""Self-consistent exact-ULZ decode of a chunk: all 3 streams consumed cleanly."""
import struct, itertools
from ulz_exact import chunks

def decode_self(buf, f0, f_end, s0, s_end, l0, l_end, ob, typ, outlen):
    out = bytearray(); mask = (1 << ob) - 1
    fpos, spos, lpos = f0, s0, l0
    consumed = 1 if typ == 0 else 0
    flagMask = consumed; flags = 0
    while len(out) < outlen:
        if flagMask == consumed:
            if fpos + 4 > f_end:
                return None
            flags = buf[fpos] | (buf[fpos+1]<<8) | (buf[fpos+2]<<16) | (buf[fpos+3]<<24); fpos += 4
            flagMask = 0x80000000
        if flags & flagMask:
            # SET = literal (copy uncompressed byte)
            if spos >= s_end:
                return None
            out.append(buf[spos]); spos += 1
        else:
            # CLEAR = LZ match
            if lpos + 2 > l_end:
                return None
            v = buf[lpos] | (buf[lpos+1] << 8); lpos += 2
            offset = v & mask; length = 3 + (v >> ob)
            src = len(out) - 1 - offset
            if src < 0 or length > outlen - len(out):
                return None
            for _ in range(length):
                out.append(out[src]); src += 1
        flagMask >>= 1
    # require sym & lz consumed exactly, flags within last word
    if spos == s_end and lpos == l_end and 0 <= (f_end - fpos) < 4:
        return bytes(out)
    return None


def search(chunk, outlens=(8192,)):
    n = len(chunk); res = []
    for outlen in outlens:
        for a in range(0, n + 1, 2):
            for b in range(a, n + 1, 2):
                parts = [(0, a), (a, b), (b, n)]
                for perm in itertools.permutations(range(3)):
                    fr = parts[perm[0]]; sr = parts[perm[1]]; lr = parts[perm[2]]
                    if fr[1] - fr[0] < 4 or (fr[1] - fr[0]) % 4 != 0:
                        continue
                    for ob in range(8, 16):
                        for typ in (0, 2):
                            r = decode_self(chunk, fr[0], fr[1], sr[0], sr[1], lr[0], lr[1], ob, typ, outlen)
                            if r:
                                res.append((outlen, fr, sr, lr, ob, typ, r))
    return res

if __name__ == '__main__':
    for ci in (0, 1, 2):
        c = chunks[ci]
        r = search(c, outlens=(8192, 4096, 2048, 16384))
        print('chunk%d (len %d): %d clean decodes' % (ci, len(c), len(r)))
        seen = set()
        for outlen, fr, sr, lr, ob, typ, out in r:
            key = (outlen, ob, typ)
            print('   outlen=%d flags=%s sym=%s lz=%s ob=%d typ=%d  out[:8]=%s' %
                  (outlen, fr, sr, lr, ob, typ, out[:8].hex()))
