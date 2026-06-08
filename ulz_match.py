#!/usr/bin/env python3
"""Crack ULZ params using ground-truth uploads. Capped-prefix matching for speed."""
import struct, glob, os

data = open('cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm', 'rb').read()
offs = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]; offs.append(len(data))
e1 = data[offs[1]:offs[2]]
tab = [struct.unpack_from('<I', e1, 0x10 + i*4)[0] & 0x7FFFFFFF for i in range(140)]; tab.append(len(e1))
chunks = [e1[tab[i]:tab[i+1]] for i in range(140)]

CAP = 96  # match only first CAP bytes for speed


def prefix_len(chunk, flg, flg_end, dta, dta_end, lz, lz_end,
               ob, ztype, add_len, dist_bias, off_high, target, cap):
    out = bytearray(); mask = (1 << ob) - 1
    fpos, dpos, lpos = flg, dta, lz; flags = 0; fm = 0
    tlen = min(len(target), cap)
    while len(out) < tlen:
        if fm == 0:
            if fpos + 4 > flg_end:
                break
            flags = chunk[fpos] | (chunk[fpos+1]<<8) | (chunk[fpos+2]<<16) | (chunk[fpos+3]<<24); fpos += 4
            fm = 0x80000000
        bit = flags & fm; fm >>= 1
        is_lit = (bit != 0) if ztype == 0 else (bit == 0)
        if is_lit:
            if dpos >= dta_end: break
            b = chunk[dpos]; dpos += 1
            if b != target[len(out)]: break
            out.append(b)
        else:
            if lpos + 2 > lz_end: break
            v = chunk[lpos] | (chunk[lpos+1] << 8); lpos += 2
            if off_high:
                length = (v & mask) + add_len; offset = v >> ob
            else:
                offset = v & mask; length = (v >> ob) + add_len
            dist = offset + dist_bias; src = len(out) - dist
            if dist < 1 or src < 0: break
            bad = False
            for _ in range(length):
                if len(out) >= tlen or out[src] != target[len(out)]:
                    bad = True; break
                out.append(out[src]); src += 1
            if bad: break
    return len(out)


def best(chunk, target, cap=CAP):
    n = len(chunk); b = (0, None)
    for order in ('fdl', 'fld'):
        for ob in (10, 11, 12, 13):
            for zt in (0, 2):
                for add_len in (0, 1, 2, 3):
                    for dist_bias in (0, 1):
                        for off_high in (False, True):
                            for s1 in range(4, n, 4):
                                for s2 in range(s1, n + 1, 2):
                                    if order == 'fdl':
                                        fr, dr, lr = (0, s1), (s1, s2), (s2, n)
                                    else:
                                        fr, dr, lr = (0, s1), (s2, n), (s1, s2)
                                    m = prefix_len(chunk, fr[0], fr[1], dr[0], dr[1],
                                                   lr[0], lr[1], ob, zt, add_len,
                                                   dist_bias, off_high, target, cap)
                                    if m > b[0]:
                                        b = (m, (order, s1, s2, ob, zt, add_len, dist_bias, off_high))
                                        if m >= min(cap, len(target)):
                                            return b
    return b


if __name__ == '__main__':
    ups = sorted(glob.glob('scratch/gs_uploads/up*.bin'))
    ups = [u for u in ups if os.path.getsize(u) == 8192]
    print('chunk0 (%dB) vs %d uploads, cap=%d' % (len(chunks[0]), len(ups), CAP))
    res = []
    for u in ups:
        t = open(u, 'rb').read()
        m, p = best(chunks[0], t)
        res.append((m, os.path.basename(u), p))
    res.sort(reverse=True)
    for m, name, p in res[:8]:
        print('  %-22s prefix=%3d  %s' % (name, m, p))
