#!/usr/bin/env python3
"""Exact esperknight ULZ decoder + brute-force of stream partition vs ground-truth uploads."""
import struct, glob, os, itertools

data = open('cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm', 'rb').read()
offs = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]; offs.append(len(data))
e1 = data[offs[1]:offs[2]]
tab = [struct.unpack_from('<I', e1, 0x10 + i*4)[0] & 0x7FFFFFFF for i in range(140)]; tab.append(len(e1))
chunks = [e1[tab[i]:tab[i+1]] for i in range(140)]


def decode(buf, f0, f_end, s0, s_end, l0, l_end, ob, typ, target):
    """Exact ULZ decode; compare to target on the fly. Return matched length."""
    out = bytearray(); mask = (1 << ob) - 1
    fpos, spos, lpos = f0, s0, l0
    consumed = 1 if typ == 0 else 0
    flagMask = consumed; flags = 0
    tlen = len(target)
    while len(out) < tlen:
        if flagMask == consumed:
            if fpos + 4 > f_end:
                break
            flags = buf[fpos] | (buf[fpos+1]<<8) | (buf[fpos+2]<<16) | (buf[fpos+3]<<24); fpos += 4
            flagMask = 0x80000000
        if flags & flagMask:
            # SET = literal
            if spos >= s_end:
                break
            b = buf[spos]; spos += 1
            if b != target[len(out)]:
                break
            out.append(b)
        else:
            # CLEAR = LZ match
            if lpos + 2 > l_end:
                break
            v = buf[lpos] | (buf[lpos+1] << 8); lpos += 2
            offset = v & mask; length = 3 + (v >> ob)
            src = len(out) - 1 - offset
            if src < 0:
                break
            bad = False
            for _ in range(length):
                if len(out) >= tlen or out[src] != target[len(out)]:
                    bad = True; break
                out.append(out[src]); src += 1
            if bad:
                break
        flagMask >>= 1
    return len(out)


def search(chunk, target, want_full=True):
    n = len(chunk); best = (0, None)
    # two split points a<=b partition [0,a)[a,b)[b,n); assign to (flags,sym,lz) in 6 ways
    for a in range(0, n + 1, 4):
        for b in range(a, n + 1, 2):
            parts = [(0, a), (a, b), (b, n)]
            for perm in itertools.permutations(range(3)):
                fr = parts[perm[0]]; sr = parts[perm[1]]; lr = parts[perm[2]]
                if (fr[1] - fr[0]) % 4 != 0 or fr[1] == fr[0]:
                    continue
                for ob in range(8, 16):
                    for typ in (0, 2):
                        m = decode(chunk, fr[0], fr[1], sr[0], sr[1], lr[0], lr[1], ob, typ, target)
                        if m > best[0]:
                            best = (m, (fr, sr, lr, ob, typ))
                            if want_full and m == len(target):
                                return best
    return best


if __name__ == '__main__':
    import sys
    t = open('scratch/gs_uploads/up000_dbp2300.bin', 'rb').read()
    m, p = search(chunks[0], t)
    print('chunk0 -> up000: matched %d / %d  params=%s' % (m, len(t), p))
