#!/usr/bin/env python3
"""Faithful Namco ULZ decoder (per ZFX/esperknight ref) + headerless layout search.

Each ITE chunk is a headerless ULZ blob: 3 contiguous regions (flags/dta/lz) in
some order. Brute force the 2 split points, region assignment, offsetBits, type.
Validate: output == 2048, each stream exactly consumed, and output found in
the GS VRAM / EE staging dump.
"""
import struct
from itertools import permutations

FHM = 'cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm'
GS  = 'scratch/options_savestate/GS.bin'
EE  = 'scratch/options_savestate/eeMemory.bin'
SIZE = 2048

data = open(FHM, 'rb').read()
offs = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
offs.append(len(data))
e1 = data[offs[1]:offs[2]]
tab = [struct.unpack_from('<I', e1, 0x10 + i*4)[0] & 0x7FFFFFFF for i in range(140)]
tab.append(len(e1))
chunks = [e1[tab[i]:tab[i+1]] for i in range(140)]


def ulz_decode(chunk, flg_off, flg_end, dta_off, dta_end, lz_off, lz_end,
               offset_bits, ztype, size=SIZE):
    """Returns (out, flg_used_bytes, dta_used, lz_used) or None on overrun."""
    out = bytearray()
    offset_mask = (1 << offset_bits) - 1
    fpos = flg_off
    dpos = dta_off
    lpos = lz_off
    flags = 0
    mask_if_consumed = 1 if ztype == 0 else 0
    flag_mask = mask_if_consumed   # forces refill on first iteration
    bytes_left = size
    while bytes_left > 0:
        if flag_mask == mask_if_consumed:   # all flags consumed -> refill
            if fpos + 4 > flg_end:
                return None
            flags = struct.unpack_from('<I', chunk, fpos)[0]
            fpos += 4
            flag_mask = 0x80000000
        if flags & flag_mask:
            if dpos >= dta_end:
                return None
            out.append(chunk[dpos]); dpos += 1
            bytes_left -= 1
        else:
            if lpos + 2 > lz_end:
                return None
            val = struct.unpack_from('<H', chunk, lpos)[0]; lpos += 2
            offset = val & offset_mask
            length = 3 + (val >> offset_bits)
            if length > bytes_left:
                return None
            src = len(out) - 1 - offset
            if src < 0:
                return None
            for _ in range(length):
                out.append(out[src]); src += 1
            bytes_left -= length
        flag_mask >>= 1
    return bytes(out), fpos - flg_off, dpos - dta_off, lpos - lz_off


def crack(chunk, gs, stg):
    n = len(chunk)
    out_hits = []
    for ob in (10, 11, 12, 13):
        for zt in (0, 2):
            for dta_off in range(2, n):
                for lz_off in range(0, n - 1, 2):
                    r = ulz_decode(chunk, 0, n, dta_off, n, lz_off, n, ob, zt)
                    if not r:
                        continue
                    out, fu, du, lu = r
                    if len(out) != SIZE:
                        continue
                    probe = out[:64]
                    ig = gs.find(probe); ie = stg.find(probe)
                    if ig < 0 and ie < 0:
                        continue
                    tag = (f' GS@{ig:#x}' if ig >= 0 else '') + \
                          (f' EE@{ie:#x}' if ie >= 0 else '')
                    out_hits.append((0, lz_off, (0, dta_off, lz_off), ob, zt,
                                     fu, du, lu, tag, out))
    return out_hits


if __name__ == '__main__':
    gs = open(GS, 'rb').read()
    ee = open(EE, 'rb').read()
    c0 = chunks[0]
    print(f'chunk0 len={len(c0)}')
    res = crack(c0, gs, ee)
    print(f'{len(res)} layouts decode to exactly 2048 with clean stream consumption')
    # prefer ones with RAM matches
    res.sort(key=lambda r: (r[8] == '',))
    for s1, s2, perm, ob, zt, fu, du, lu, tag, out in res[:30]:
        names = ['?','?','?']
        for role, idx in zip(('flg','dta','lz'), perm):
            names[idx] = role
        layout = ' '.join(f'[{a}:{b})={names[i]}' for i,(a,b) in
                          enumerate([(0,s1),(s1,s2),(s2,len(c0))]))
        print(f'  obits={ob} type={zt} | {layout} | fu={fu} du={du} lu={lu}{tag}')
