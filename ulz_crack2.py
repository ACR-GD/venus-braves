#!/usr/bin/env python3
"""Locate the 3-stream (flg/dta/lz) split inside an ITE chunk, using the
Namco ULZ algorithm (nocash PSXSPX spec)."""
import struct

FHM = 'cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm'
GS  = 'scratch/options_savestate/GS.bin'
EE  = 'scratch/options_savestate/eeMemory.bin'
TARGET = 2048

data = open(FHM, 'rb').read()
offs = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(14)]
offs.append(len(data))
e1 = data[offs[1]:offs[2]]
tab = [struct.unpack_from('<I', e1, 0x10 + i*4)[0] & 0x7FFFFFFF for i in range(140)]
tab.append(len(e1))
chunks = [e1[tab[i]:tab[i+1]] for i in range(140)]


def ulz_decode(chunk, flg_off, dta_off, lz_off, disp_bits, add_len,
               flg_msb=True, lit_when=1, limit=TARGET):
    """Decode using separate streams. Returns (out, dta_used, lz_used, flg_words)."""
    out = bytearray()
    fpos = flg_off
    dpos = dta_off
    lpos = lz_off
    n = len(chunk)
    disp_mask = (1 << disp_bits) - 1
    flg_words = 0
    collected = 0
    bits_left = 0
    while len(out) < limit:
        if bits_left == 0:
            if fpos + 4 > dta_off:
                break
            collected = struct.unpack_from('<I', chunk, fpos)[0]
            fpos += 4
            flg_words += 1
            bits_left = 32
        if flg_msb:
            bit = (collected >> 31) & 1
            collected = (collected << 1) & 0xFFFFFFFF
        else:
            bit = collected & 1
            collected >>= 1
        bits_left -= 1
        if bit == lit_when:  # literal
            if dpos >= lz_off:
                break
            out.append(chunk[dpos]); dpos += 1
        else:  # match
            if lpos + 2 > n:
                break
            disp = struct.unpack_from('<H', chunk, lpos)[0]; lpos += 2
            ln = (disp >> disp_bits) + add_len
            d = (disp & disp_mask) + 1
            for _ in range(ln):
                if len(out) >= limit:
                    break
                out.append(out[-d] if d <= len(out) else 0)
    return bytes(out), dpos - dta_off, lpos - lz_off, flg_words


def crack(chunk, want_ram=None, target=TARGET, strict=True):
    n = len(chunk)
    results = []
    for disp_bits in (10, 11, 12, 13):
        for add_len in (2, 3):
            for flg_msb in (True, False):
                for lit_when in (1, 0):
                    for k in range(1, 65):
                        dta_off = 4 * k          # strict: flags fill [0,dta_off)
                        if dta_off >= n:
                            break
                        for lz_off in range(dta_off, n - 1, 2):
                            out, du, lu, fw = ulz_decode(
                                chunk, 0, dta_off, lz_off, disp_bits, add_len,
                                flg_msb, lit_when, limit=target)
                            if len(out) != target:
                                continue
                            if strict:
                                if fw * 4 != dta_off:
                                    continue
                                if dta_off + du != lz_off:    # dta exactly meets lz
                                    continue
                                if lz_off + lu != n:          # lz exactly fills end
                                    continue
                            tag = ''
                            if want_ram is not None:
                                gs, ee = want_ram
                                ig = gs.find(out[:64]); ie = ee.find(out[:64])
                                if ig >= 0: tag += f' GS@{ig:#x}'
                                if ie >= 0: tag += f' EE@{ie:#x}'
                            results.append((disp_bits, add_len, flg_msb, lit_when,
                                            k, dta_off, lz_off, du, lu, fw, tag, out))
    return results


if __name__ == '__main__':
    gs = open(GS, 'rb').read()
    ee = open(EE, 'rb').read()
    c0 = chunks[0]
    print(f'chunk0 len={len(c0)}')
    res = crack(c0, want_ram=(gs, ee))
    print(f'{len(res)} candidate layouts produce exactly 2048 bytes & consume streams')
    for r in res[:40]:
        db, al, msb, lw, k, do, lo, du, lu, fw, tag, out = r
        print(f'  disp_bits={db} add_len={al} msb={msb} lit={lw} flgwords={fw} '
              f'dta@{do}(use{du}) lz@{lo}(use{lu}){tag}')
