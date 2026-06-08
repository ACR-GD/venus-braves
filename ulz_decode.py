"""Codec Venus & Braves — transcription depuis EE @0x1aef20 + @0x1afc08 (pyghidra MIPS64)."""
from __future__ import annotations

import struct
from typing import Tuple

PLANE_SIZE = 2048
SCRATCH_SIZE = 0x4000
DELTA_OFF = 0x2000
OUT_OFF = 0x0000


class BitReader:
    """ReadBits @0x1aef20 — MSB-first, fenêtre 24 bits."""

    __slots__ = ("buf", "base", "offset", "bitpos")

    def __init__(self, buf: bytes | bytearray, base: int = 0):
        self.buf = buf
        self.base = base
        self.offset = 0
        self.bitpos = 0

    def read(self, n: int) -> int:
        off = self.base + self.offset
        b0, b1, b2 = self.buf[off], self.buf[off + 1], self.buf[off + 2]
        window = (b0 << 16) | (b1 << 8) | b2
        shift = 24 - self.bitpos - n
        val = (window >> shift) & ((1 << n) - 1)
        self.bitpos += n
        while self.bitpos >= 8:
            self.offset += 1
            self.bitpos -= 8
        return val

    def consumed_bytes(self) -> int:
        return self.offset + (1 if self.bitpos else 0)


def decode_plane(buf: bytes | bytearray, src: int, scratch: bytearray | None = None) -> Tuple[bytearray, BitReader]:
    """
    DecodePlane @0x1afc08.

    - Deltas dans scratch[DELTA_OFF + i*4] (int32 LE)
    - Copies LZ lisent scratch[DELTA_OFF + (i-d)*4] (peut être < DELTA_OFF → zone output)
    - Sortie : scratch[OUT_OFF + i*4] = (acc << 24) après somme cumulée des deltas
    """
    if scratch is None:
        scratch = bytearray(SCRATCH_SIZE)
    if len(scratch) < SCRATCH_SIZE:
        raise ValueError("scratch >= 0x4000")

    br = BitReader(buf, src)
    acc = br.read(6) << 1
    s3 = 0

    while s3 < PLANE_SIZE:
        if br.read(1) == 0:
            cnt = br.read(2) + 1
            for _ in range(cnt):
                d = (br.read(7) << 1) - 0x80
                if s3 < PLANE_SIZE:
                    struct.pack_into("<i", scratch, DELTA_OFF + s3 * 4, d)
                s3 += 1
        else:
            dist = br.read(8) + 1
            if dist >= 0x100:
                dist = br.read(12) + 1
            length = br.read(4) + 1
            if length >= 0x10:
                length = br.read(12) + 1
            for _ in range(length):
                if s3 < PLANE_SIZE:
                    src_off = DELTA_OFF + (s3 - dist) * 4
                    val = struct.unpack_from("<i", scratch, src_off)[0]
                    struct.pack_into("<i", scratch, DELTA_OFF + s3 * 4, val)
                s3 += 1

    plane = bytearray(PLANE_SIZE)
    for i in range(PLANE_SIZE):
        acc = (acc + struct.unpack_from("<i", scratch, DELTA_OFF + i * 4)[0]) & 0xFFFFFFFF
        acc_s = struct.unpack("<i", struct.pack("<I", acc))[0]
        struct.pack_into("<I", scratch, OUT_OFF + i * 4, (acc_s << 24) & 0xFFFFFFFF)
        plane[i] = (acc_s) & 0xFF

    return plane, br


def decode_planes_in_chunk(buf: bytes | bytearray, src: int, max_planes: int = 8) -> list[bytearray]:
    """Décode des plans successifs tant que le flux le permet."""
    scratch = bytearray(SCRATCH_SIZE)
    planes = []
    pos = src
    for _ in range(max_planes):
        try:
            plane, br = decode_plane(buf, pos, scratch)
        except (IndexError, struct.error):
            break
        planes.append(plane)
        pos += br.consumed_bytes()
        if pos >= len(buf):
            break
    return planes


def chunk_size(f: bytes, ite_off: int, idx: int, offs: list[int]) -> int:
    tgt = ite_off + offs[idx]
    if idx + 1 < len(offs):
        return (ite_off + offs[idx + 1]) - tgt
    return len(f) - tgt


def load_ite(f: bytes, ite_off: int):
    assert f[ite_off : ite_off + 4] == b"ITE\x00"
    w = struct.unpack_from("<I", f, ite_off + 4)[0]
    h = struct.unpack_from("<I", f, ite_off + 8)[0]
    first = struct.unpack_from("<I", f, ite_off + 0x10)[0] & 0x7FFFFFFF
    n = (first - 0x10) // 4
    offs = [struct.unpack_from("<I", f, ite_off + 0x10 + k * 4)[0] & 0x7FFFFFFF for k in range(n)]
    return w, h, n, offs


if __name__ == "__main__":
    from pathlib import Path

    f = Path("cdimage_temp_unpacked/seven_data_link/futa/screen/option.fhm").read_bytes()
    ITE = 0xEF0
    w, h, n, offs = load_ite(f, ITE)
    src = ITE + offs[0]
    sz = chunk_size(f, ITE, 0, offs)
    print(f"ITE {w}x{h} tiles={n}")
    print(f"tile0 @ {src:#x} size={sz} magic={f[src]:#02x}")

    scratch_gt = Path("option_savestate/extracted/Scratchpad.bin").read_bytes()
    gt = [scratch_gt[0x2000 + i * 4 : 0x2000 + i * 4 + 4] for i in range(PLANE_SIZE)]
    gt_r = [b[0] for b in gt]
    gt_g = [b[1] for b in gt]
    gt_b = [b[2] for b in gt]

    scratch = bytearray(SCRATCH_SIZE)
    plane, br = decode_plane(f, src, scratch)
    print(f"plane0: consumed {br.consumed_bytes()} bytes, min={min(plane)} max={max(plane)}")
    print(f"match R: {sum(a==b for a,b in zip(plane, gt_r))}/{PLANE_SIZE}")
    print(f"match G: {sum(a==b for a,b in zip(plane, gt_g))}/{PLANE_SIZE}")
    print(f"match B: {sum(a==b for a,b in zip(plane, gt_b))}/{PLANE_SIZE}")
    print("first10 dec:", list(plane[:10]))
    print("first10 R:  ", gt_r[:10])

    # essai multi-plans alignés octet
    planes = decode_planes_in_chunk(f, src, 4)
    print(f"multi-plane count={len(planes)} bytes={[br.consumed_bytes() for br in []]}")
    for i, p in enumerate(planes):
        print(f"  plane{i}: match R={sum(a==b for a,b in zip(p,gt_r))}")
