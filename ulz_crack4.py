#!/usr/bin/env python3
"""Self-consistency crack: contiguous 3-region ULZ per chunk, sweeping token math.
No RAM needed: rely on output==2048 AND all three streams consumed exactly."""
import struct

FHM = 'cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm'
SIZE = 2048
data = open(FHM, 'rb').read()
offs = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]; offs.append(len(data))
e1 = data[offs[1]:offs[2]]
tab = [struct.unpack_from('<I', e1, 0x10 + i*4)[0] & 0x7FFFFFFF for i in range(140)]; tab.append(len(e1))
chunks = [e1[tab[i]:tab[i+1]] for i in range(140)]


def decode(chunk, flg, flg_end, dta, dta_end, lz, lz_end,
           ob, ztype, add_len, dist_bias, off_high):
    out = bytearray()
    mask = (1 << ob) - 1
    fpos, dpos, lpos = flg, dta, lz
    flags = 0
    fm = 0
    guard = 0
    while True:
        # stop when both data and lz streams are exhausted
        if dpos >= dta_end and lpos + 2 > lz_end:
            break
        guard += 1
        if guard > 4096:
            return None
        if fm == 0:
            if fpos + 4 > flg_end:
                return None
            flags = struct.unpack_from('<I', chunk, fpos)[0]; fpos += 4
            fm = 0x80000000
        bit = flags & fm
        fm >>= 1
        is_lit = (bit != 0) if ztype == 0 else (bit == 0)
        if is_lit:
            if dpos >= dta_end:
                return None
            out.append(chunk[dpos]); dpos += 1
        else:
            if lpos + 2 > lz_end:
                return None
            v = struct.unpack_from('<H', chunk, lpos)[0]; lpos += 2
            if off_high:
                length = (v & mask) + add_len
                offset = v >> ob
            else:
                offset = v & mask
                length = (v >> ob) + add_len
            dist = offset + dist_bias
            src = len(out) - dist
            if dist < 1 or src < 0:
                return None
            for _ in range(length):
                out.append(out[src]); src += 1
    return bytes(out), fpos - flg, dpos - dta, lpos - lz


def crack(chunk):
    n = len(chunk)
    res = []
    for order in ('fdl', 'fld'):
        for s1 in range(4, n - 1, 4):
            for s2 in range(s1 + 2, n, 2):
                if order == 'fdl':
                    fr, dr, lr = (0, s1), (s1, s2), (s2, n)
                else:
                    fr, dr, lr = (0, s1), (s2, n), (s1, s2)
                for ob in (10, 11, 12, 13):
                    for zt in (0, 2):
                        for add_len in (0, 1, 2, 3):
                            for dist_bias in (0, 1):
                                for off_high in (False, True):
                                    r = decode(chunk, fr[0], fr[1], dr[0], dr[1],
                                               lr[0], lr[1], ob, zt, add_len,
                                               dist_bias, off_high)
                                    if not r:
                                        continue
                                    out, fu, du, lu = r
                                    dpos_end = dr[0] + du
                                    lpos_end = lr[0] + lu
                                    if (dpos_end == dr[1]
                                            and lr[1] - lpos_end in (0, 1)
                                            and fr[1] - (fr[0]+fu) in (0, 1, 2, 3)
                                            and len(out) >= len(chunk)):
                                        res.append((order, s1, s2, ob, zt, add_len,
                                                    dist_bias, off_high, len(out), out))
    return res


if __name__ == '__main__':
    c0 = chunks[0]
    print('chunk0 len', len(c0))
    r = crack(c0)
    print(len(r), 'self-consistent layouts')
    from collections import Counter
    sizes = Counter(x[8] for x in r)
    print('output sizes:', dict(sizes))
    for order, s1, s2, ob, zt, al, db, oh, sz, out in r[:30]:
        print(f'  order={order} flags[0:{s1}] split@{s2} bits={ob} type={zt} '
              f'addlen={al} distbias={db} offhigh={oh} outsize={sz}  out[:12]={out[:12].hex()}')
