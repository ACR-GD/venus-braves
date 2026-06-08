#!/usr/bin/env python3
"""Outils FHM/ITE : extraire, décoder, réencoder et réinsérer des tuiles."""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from PIL import Image

from ulz_codec import decode_tile_chunk, encode_tile_chunk
from ulz_decode import decode_plane, load_ite


def iter_tiles(f: bytes, ite_off: int):
    w, h, n, offs = load_ite(f, ite_off)
    tgts = [ite_off + o for o in offs]
    for idx, o in enumerate(offs):
        src = ite_off + o
        end = min([t for t in tgts if t > src] + [len(f)])
        yield idx, w, h, n, src, f[src:end]


def decode_ite_to_image(f: bytes, ite_off: int) -> Image.Image:
    w, h, n, offs = load_ite(f, ite_off)
    tx, ty = w // 64, h // 32
    img = Image.new("L", (w, h))
    px = img.load()
    for idx, _, _, _, src, chunk in iter_tiles(f, ite_off):
        if chunk[0] == 0:
            continue
        plane, _ = decode_plane(f, src)
        txi = idx % tx
        tyi = idx // tx
        for i in range(2048):
            lx, ly = i % 64, i // 64
            x, y = txi * 64 + lx, tyi * 32 + ly
            if x < w and y < h:
                px[x, y] = plane[i]
    return img


def replace_tile(f: bytearray, ite_off: int, tile_idx: int, new_chunk: bytes) -> bytearray:
    w, h, n, offs = load_ite(f, ite_off)
    if tile_idx >= n:
        raise IndexError(f"tile {tile_idx} hors limites ({n})")
    src = ite_off + offs[tile_idx]
    tgts = sorted(set(ite_off + o for o in offs))
    end = min([t for t in tgts if t > src] + [len(f)])
    old_size = end - src
    delta = len(new_chunk) - old_size
    out = bytearray(f)
    out[src:end] = new_chunk
    if delta:
        # décaler les offsets des tuiles suivantes dans cette ITE
        for i, o in enumerate(offs):
            if i > tile_idx:
                new_o = o + delta
                struct.pack_into("<I", out, ite_off + 0x10 + i * 4, new_o)
        # décaler les offsets FHM globaux après cette ITE
        fhm_count = struct.unpack_from("<I", out, 0)[0]
        for i in range(1, fhm_count + 1):
            off_ptr = 4 + i * 4
            entry_off = struct.unpack_from("<I", out, off_ptr)[0]
            if entry_off > src:
                struct.pack_into("<I", out, off_ptr, entry_off + delta)
    return out


def main():
    ap = argparse.ArgumentParser(description="FHM/ITE texture tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_dec = sub.add_parser("decode", help="Décode une ITE → PNG")
    p_dec.add_argument("fhm")
    p_dec.add_argument("--ite", type=lambda x: int(x, 0), default=0, help="offset ITE (hex)")
    p_dec.add_argument("-o", "--output", default="decoded.png")

    p_enc = sub.add_parser("reencode-tile", help="Test round-trip tuile")
    p_enc.add_argument("fhm")
    p_enc.add_argument("--ite", type=lambda x: int(x, 0), default=0xEF0)
    p_enc.add_argument("--tile", type=int, default=0)

    p_rep = sub.add_parser("replace-png-tile", help="Remplace tuile depuis PNG 64x32 grayscale")
    p_rep.add_argument("fhm")
    p_rep.add_argument("png")
    p_rep.add_argument("--ite", type=lambda x: int(x, 0), default=0xEF0)
    p_rep.add_argument("--tile", type=int, required=True)
    p_rep.add_argument("-o", "--output", required=True)

    args = ap.parse_args()
    fhm = Path(args.fhm)

    if args.cmd == "decode":
        data = fhm.read_bytes()
        img = decode_ite_to_image(data, args.ite)
        img.save(args.output)
        print(f"saved {args.output} ({img.size[0]}x{img.size[1]})")

    elif args.cmd == "reencode-tile":
        data = fhm.read_bytes()
        _, _, _, src, chunk = next(t for t in iter_tiles(data, args.ite) if t[0] == args.tile)
        plane, _ = decode_plane(data, src)
        new = encode_tile_chunk(bytes(plane))
        dec = decode_tile_chunk(new)
        m = sum(a == b for a, b in zip(plane, dec))
        print(f"tile {args.tile}: orig={len(chunk)} new={len(new)} match={m}/2048")

    elif args.cmd == "replace-png-tile":
        data = bytearray(fhm.read_bytes())
        img = Image.open(args.png).convert("L")
        if img.size != (64, 32):
            sys.exit("PNG doit être 64x32 grayscale")
        plane = bytes(img.getdata())
        chunk = encode_tile_chunk(plane)
        out = replace_tile(data, args.ite, args.tile, chunk)
        Path(args.output).write_bytes(out)
        print(f"saved {args.output} (tile {args.tile}, chunk {len(chunk)} bytes)")


if __name__ == "__main__":
    main()
