#!/usr/bin/env python3
"""Known-plaintext cracker for the ITE/ULZ chunk compression.

Constraint: each entry-1 chunk must decompress to exactly 2048 bytes while
consuming (almost) the whole compressed chunk. We brute force the token
layout and validate the winner against GS VRAM / EE RAM from the savestate.
"""
import struct, itertools

FHM = 'cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm'
GS  = 'scratch/options_savestate/GS.bin'
EE  = 'scratch/options_savestate/eeMemory.bin'

data = open(FHM, 'rb').read()
offs = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
offs.append(len(data))
e1 = data[offs[1]:offs[2]]
first = struct.unpack_from('<I', e1, 0x10)[0] & 0x7FFFFFFF
nchunks = (first - 0x10) // 4
tab = [struct.unpack_from('<I', e1, 0x10 + i*4)[0] & 0x7FFFFFFF for i in range(nchunks)]
tab2 = tab + [len(e1)]
chunks = [e1[tab2[i]:tab2[i+1]] for i in range(nchunks)]

TARGET = 2048


def decode(d, *, lit_bit, msb, off_bits, len_bits, T, le16, pack, mode, init, rstart):
    """Generic LZSS-style decoder. Returns (out_bytes, consumed) or None."""
    N = 1 << off_bits
    win = bytearray([init]) * N
    r = rstart % N
    out = bytearray()
    pos = 0
    n = len(d)
    off_mask = (1 << off_bits) - 1
    len_mask = (1 << len_bits) - 1
    while pos < n and len(out) < TARGET:
        flags = d[pos]; pos += 1
        for i in range(8):
            if len(out) >= TARGET:
                break
            if pos >= n:
                break
            bit = (flags >> (7 - i)) & 1 if msb else (flags >> i) & 1
            literal = (bit == lit_bit)
            if literal:
                c = d[pos]; pos += 1
                out.append(c)
                win[r] = c; r = (r + 1) & (N - 1)
            else:
                if pos + 1 >= n:
                    return bytes(out), pos
                b0 = d[pos]; b1 = d[pos+1]; pos += 2
                v = (b0 | (b1 << 8)) if le16 else (b1 | (b0 << 8))
                if pack == 'lo_off':
                    off = v & off_mask; ln = (v >> off_bits) & len_mask
                elif pack == 'lo_len':
                    ln = v & len_mask; off = (v >> len_bits) & off_mask
                elif pack == 'okumura':  # off=lo|((hi&0xf0)<<4), len=hi&0xf
                    off = b0 | ((b1 & 0xF0) << 4); ln = b1 & 0x0F
                else:
                    return None
                ln += T
                if mode == 'abs':
                    for k in range(ln):
                        if len(out) >= TARGET:
                            break
                        c = win[(off + k) & (N - 1)]
                        out.append(c); win[r] = c; r = (r + 1) & (N - 1)
                else:  # rel: distance back from current position
                    dist = off + 1
                    for k in range(ln):
                        if len(out) >= TARGET:
                            break
                        c = out[-dist] if dist <= len(out) else init
                        out.append(c); win[r] = c; r = (r + 1) & (N - 1)
    return bytes(out), pos


def main():
    gs = open(GS, 'rb').read()
    ee = open(EE, 'rb').read()
    stg = ee  # search entire EE RAM for the decompression target buffer
    c0 = chunks[0]
    print(f'chunk0 len={len(c0)} (compressed) target={TARGET}')
    hits = []
    grid = dict(
        lit_bit=[1, 0], msb=[False, True],
        T=[1, 2, 3],
        le16=[True, False],
        pack=['lo_off', 'lo_len', 'okumura'],
        mode=['abs', 'rel'],
        init=[0, 0x20],
    )
    obits_map = {'okumura': [(12, 4)]}
    default_bits = [(11, 5), (12, 4), (13, 3), (10, 6)]
    keys = list(grid)
    total = 0
    for combo in itertools.product(*[grid[k] for k in keys]):
        p = dict(zip(keys, combo))
        bitsets = obits_map.get(p['pack'], default_bits)
        for off_bits, len_bits in bitsets:
            N = 1 << off_bits
            rstarts = [0, N - (len_bits and (1 << len_bits)), N - 18, N - 1]
            for rstart in set(x % N for x in rstarts):
                total += 1
                try:
                    res = decode(c0, off_bits=off_bits, len_bits=len_bits,
                                 rstart=rstart, **p)
                except Exception:
                    continue
                if not res:
                    continue
                out, consumed = res
                if len(out) < 64:
                    continue
                probe = out[:48]
                if len(set(probe)) < 12:   # skip trivial/constant outputs
                    continue
                istg = stg.find(probe)
                igs = gs.find(probe)
                if istg >= 0 or igs >= 0:
                    tag = ''
                    if istg >= 0: tag += f' EE@{istg:#x}'
                    if igs >= 0: tag += f' GS@{igs:#x}'
                    hits.append((p, off_bits, len_bits, rstart, consumed, len(out), tag))
    print(f'tested {total} param sets, {len(hits)} matched staging/GS')
    for p, ob, lb, rs, cons, ln, tag in hits:
        print(f"  {p} ob={ob} lb={lb} rs={rs} consumed={cons} outlen={ln}{tag}")


if __name__ == '__main__':
    main()
