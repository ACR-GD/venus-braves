#!/usr/bin/env python3
"""Crée option_trad.fhm (test visible) et l'installe dans cdimage_unpacked."""
from __future__ import annotations

import shutil
import struct
from pathlib import Path

from PIL import Image

from fhm_tool import replace_tile
from ulz_codec import encode_tile_chunk, pad_chunk
from ulz_decode import decode_plane, load_ite

ROOT = Path(__file__).resolve().parent
# cdimage_temp_unpacked = offsets FHM valides ; cdimage_unpacked était corrompu
SRC_FHM = ROOT / "cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm"
INSTALL_FHM = ROOT / "cdimage_unpacked/seven_data_link/futa/screen/option.fhm"
OUT_FHM = ROOT / "option_trad.fhm"
SCRATCH = ROOT / "scratch/test_patch"
ITE_BG = 0xEF0  # fond parchemin 640x448 (1ère ITE)
TEST_TILES = [0, 1, 2]  # bande haute visible à l'écran option


def make_checker_plane(phase: int = 0) -> bytes:
    """Damier visible ; valeurs <= 126 pour rester encodables."""
    plane = bytearray()
    for y in range(32):
        for x in range(64):
            on = ((x // 8) + (y // 8) + phase) % 2 == 0
            plane.append(120 if on else 24)
    return bytes(plane)


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    orig_size = SRC_FHM.stat().st_size
    data = bytearray(SRC_FHM.read_bytes())
    w, h, n, offs = load_ite(data, ITE_BG)
    print(f"Source: {SRC_FHM} ({len(data)} bytes)")
    print(f"ITE @{ITE_BG:#x} {w}x{h} tiles={n}")

    # Sauver l'original des tuiles test
    for ti in TEST_TILES:
        src = ITE_BG + offs[ti]
        orig, _ = decode_plane(data, src)
        img = Image.frombytes("L", (64, 32), bytes(orig))
        img.save(SCRATCH / f"tile{ti:03d}_orig.png")

    # Appliquer damier + réencoder
    tgts = sorted(set(ITE_BG + o for o in offs))

    for i, ti in enumerate(TEST_TILES):
        plane = make_checker_plane(phase=i)
        src = ITE_BG + offs[ti]
        end = min([t for t in tgts if t > src] + [len(data)])
        old_size = end - src
        chunk = pad_chunk(encode_tile_chunk(plane), old_size)
        data = replace_tile(data, ITE_BG, ti, chunk)
        dec = decode_plane(bytes(data), ITE_BG + load_ite(data, ITE_BG)[3][ti])[0]
        assert bytes(dec) == plane, f"round-trip failed tile {ti}"
        Image.frombytes("L", (64, 32), plane).save(SCRATCH / f"tile{ti:03d}_patched.png")
        print(f"  tile {ti}: chunk {len(chunk)} bytes OK")

    OUT_FHM.write_bytes(data)
    print(f"Écrit {OUT_FHM} ({len(data)} bytes, delta {len(data)-orig_size:+d})")

    # Installer dans l'arborescence de repack (les deux arborescences)
    for dest in (INSTALL_FHM, SRC_FHM):
        backup = dest.with_suffix(".fhm.bak")
        if dest.exists() and not backup.exists():
            shutil.copy2(dest, backup)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT_FHM, dest)
        print(f"Installé → {dest}")


if __name__ == "__main__":
    main()
