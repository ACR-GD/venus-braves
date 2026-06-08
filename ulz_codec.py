#!/usr/bin/env python3
"""
Codec de textures Venus & Braves (Namco FHM/ITE).

Reverse-engineering via pyghidra (MIPS64) sur eeMemory.bin :
  ReadBits      @ 0x1aef20
  DecodePlane   @ 0x1afc08
  TextureUpload @ 0x1afdc8  (format champ +0xe : 0=VU1, 2=codec EE)

Format d'une tuile compressée (64x32, 2048 octets/plan) :
  [magic 1B][bitstream...][footer 8B: 00 00 01 SS SS 00 00 00 00]
  footer : taille totale du chunk (BE32 aux octets +2..+5)

Bitstream (MSB-first) par plan :
  acc0 = Read(6) << 1
  repeat jusqu'à 2048 deltas :
    bit0=0 : run littéral
      count = Read(2)+1
      count × delta = (Read(7)<<1) - 0x80
    bit0=1 : run copie LZ (deltas int32 dans scratch 0x70002000)
      dist  = Read(8)+1 ; si 256 → Read(12)+1
      len   = Read(4)+1 ; si 16  → Read(12)+1
      copie len deltas depuis position courante - dist
      (dist > pos → lit la zone 0x70000000, historique plan précédent)
  sortie[i] = (acc0 + sum(deltas[0..i])) & 0xFF
"""
from __future__ import annotations

import struct
from typing import List, Tuple

from ulz_decode import BitReader, PLANE_SIZE, SCRATCH_SIZE, DELTA_OFF, decode_plane

CHUNK_FOOTER_MAGIC = bytes([0, 0, 1])  # suivi de 1 octet size-high? actually BE size


def plane_to_deltas(plane: bytes, acc0: int | None = None) -> Tuple[List[int], int]:
    """Convertit un plan 2048 octets en deltas signés."""
    if len(plane) != PLANE_SIZE:
        raise ValueError(f"plan doit faire {PLANE_SIZE} octets")
    if acc0 is None:
        acc0 = (plane[0] >> 1) << 1  # compatible avec acc0 = read(6)<<1
    deltas = []
    acc = acc0
    for b in plane:
        d = b - (acc & 0xFF)
        if d >= 0x80:
            d -= 0x100
        deltas.append(d)
        acc = b
    return deltas, acc0 >> 1


def write_bits(bits: List[int]) -> bytes:
    """Pack bits MSB-first (comme ReadBits)."""
    out = bytearray()
    cur = 0
    n = 0
    for bit in bits:
        cur = (cur << 1) | (bit & 1)
        n += 1
        if n == 8:
            out.append(cur)
            cur = 0
            n = 0
    if n:
        out.append(cur << (8 - n))
    return bytes(out)


def encode_delta_value(d: int, bits: List[int]) -> None:
    """Encode un delta littéral : fait partie d'un run literal (count dans run)."""
    v = ((d + 0x80) >> 1) & 0x7F
    for shift in range(6, -1, -1):
        bits.append((v >> shift) & 1)


def encode_plane(plane: bytes, acc0_nibble: int | None = None) -> bytes:
    """Encode un plan : le 1er octet du chunk = 6 bits acc0 + 2 bits de flux."""
    deltas, acc6 = plane_to_deltas(plane, None if acc0_nibble is None else acc0_nibble << 1)
    if acc0_nibble is None:
        acc0_nibble = acc6

    bits: List[int] = []
    i = 0
    while i < len(deltas):
        # Cherche la plus longue copie LZ dans les deltas déjà encodés
        best_len = 0
        best_dist = 0
        for dist in range(1, min(i, 0x1000) + 1):
            length = 0
            while i + length < len(deltas) and deltas[i + length] == deltas[i - dist + length]:
                length += 1
            if length > best_len:
                best_len = length
                best_dist = dist

        if best_len >= 3:
            bits.append(1)  # copie
            d = best_dist - 1
            if d < 0xFF:
                for shift in range(7, -1, -1):
                    bits.append((d >> shift) & 1)
            else:
                for shift in range(7, -1, -1):
                    bits.append(1)  # 0xFF → extended
                d2 = best_dist - 1
                for shift in range(11, -1, -1):
                    bits.append((d2 >> shift) & 1)
            ln = best_len - 1
            if ln < 0xF:
                for shift in range(3, -1, -1):
                    bits.append((ln >> shift) & 1)
            else:
                for shift in range(3, -1, -1):
                    bits.append(1)
                for shift in range(11, -1, -1):
                    bits.append((ln >> shift) & 1)
            i += best_len
        else:
            # run littéral (max 4 deltas : Read(2)+1)
            run = min(4, len(deltas) - i)
            bits.append(0)
            cnt = run - 1
            for shift in range(1, -1, -1):
                bits.append((cnt >> shift) & 1)
            for j in range(run):
                encode_delta_value(deltas[i + j], bits)
            i += run

    all_bits: List[int] = []
    for shift in range(5, -1, -1):
        all_bits.append((acc0_nibble >> shift) & 1)
    all_bits.extend(bits)
    return write_bits(all_bits)


def wrap_chunk(bitstream: bytes) -> bytes:
    """Ajoute footer taille (8 octets)."""
    size = len(bitstream) + 8
    footer = bytes([0, 0, 1, (size >> 8) & 0xFF, size & 0xFF, 0, 0, 0])
    return bitstream + footer


def pad_chunk(chunk: bytes, target_size: int) -> bytes:
    """Pad un chunk à la taille d'origine (zéros avant le footer) pour éviter de décaler le FHM."""
    if len(chunk) > target_size:
        raise ValueError(f"chunk {len(chunk)} > cible {target_size}")
    if len(chunk) == target_size:
        return chunk
    footer = chunk[-8:]
    body = chunk[:-8]
    pad = target_size - len(chunk)
    out = bytearray(body + b"\x00" * pad + footer)
    # footer : 00 00 01 SS SS 00 00 00
    out[-8] = 0
    out[-7] = 0
    out[-6] = 1
    out[-5] = (target_size >> 8) & 0xFF
    out[-4] = target_size & 0xFF
    out[-3] = 0
    out[-2] = 0
    out[-1] = 0
    return bytes(out)


def roundtrip_plane(plane: bytes) -> Tuple[bool, int]:
    enc = encode_plane(plane)
    chunk = wrap_chunk(enc)
    dec, _ = decode_plane(chunk, 0)
    matches = sum(a == b for a, b in zip(dec, plane))
    return matches == PLANE_SIZE, matches


def decode_tile_chunk(chunk: bytes, scratch: bytearray | None = None) -> bytes:
    """Décode le premier plan d'un chunk complet."""
    plane, _ = decode_plane(chunk, 0, scratch)
    return bytes(plane)


def encode_tile_chunk(plane: bytes) -> bytes:
    return wrap_chunk(encode_plane(plane))
