"""Déséswizzle / swizzle mémoire GS pour TIM2 (PSMCT32, PSMT8, PSMT4)."""

from __future__ import annotations

import math
import struct
from typing import Tuple

# Tables de blocs GS (PS2Tek / OpenKh)
BT32 = [
    [0, 1, 4, 5, 16, 17, 20, 21],
    [2, 3, 6, 7, 18, 19, 22, 23],
    [8, 9, 12, 13, 24, 25, 28, 29],
    [10, 11, 14, 15, 26, 27, 30, 31],
]

BT8 = [
    [0, 1, 4, 5, 16, 17, 20, 21],
    [2, 3, 6, 7, 18, 19, 22, 23],
    [8, 9, 12, 13, 24, 25, 28, 29],
    [10, 11, 14, 15, 26, 27, 30, 31],
    [32, 33, 36, 37, 48, 49, 52, 53],
    [34, 35, 38, 39, 50, 51, 54, 55],
    [40, 41, 44, 45, 56, 57, 60, 61],
    [42, 43, 46, 47, 58, 59, 62, 63],
]

BT4 = BT32  # PSMT4 utilise la table 4x8 sur pages 128x128


def deswizzle_psmct32(raw: bytes, w: int, h: int) -> bytes:
    """PSMCT32 / RGBA32 — pages 64x32, blocs 8x8."""
    pw = math.ceil(w / 64)
    ph = math.ceil(h / 32)
    page_size = 8192
    total = pw * ph * page_size
    src = bytearray(raw[:total])
    if len(src) < total:
        src.extend(b"\x00" * (total - len(src)))
    out = bytearray(w * h * 4)
    for y in range(h):
        py = y // 32
        ly = y % 32
        brow = ly // 8
        by = ly % 8
        for x in range(w):
            px = x // 64
            lx = x % 64
            page_off = (py * pw + px) * page_size
            bcol = lx // 8
            bx = lx % 8
            block = BT32[brow][bcol]
            word = by * 8 + bx
            off = page_off + block * 256 + word * 4
            di = (y * w + x) * 4
            out[di : di + 4] = src[off : off + 4]
    return bytes(out)


def swizzle_psmct32(rgba: bytes, w: int, h: int) -> bytes:
    pw = math.ceil(w / 64)
    ph = math.ceil(h / 32)
    page_size = 8192
    total = pw * ph * page_size
    dst = bytearray(total)
    for y in range(h):
        py = y // 32
        ly = y % 32
        brow = ly // 8
        by = ly % 8
        for x in range(w):
            px = x // 64
            lx = x % 64
            page_off = (py * pw + px) * page_size
            bcol = lx // 8
            bx = lx % 8
            block = BT32[brow][bcol]
            word = by * 8 + bx
            off = page_off + block * 256 + word * 4
            si = (y * w + x) * 4
            dst[off : off + 4] = rgba[si : si + 4]
    return bytes(dst)


def deswizzle_psmt8(raw: bytes, w: int, h: int) -> Tuple[bytes, int, int]:
    pw = math.ceil(w / 128)
    ph = math.ceil(h / 64)
    page_size = 8192
    total = pw * ph * page_size
    src = bytearray(raw[:total])
    if len(src) < total:
        src.extend(b"\x00" * (total - len(src)))
    out_w, out_h = pw * 128, ph * 64
    out = bytearray(out_w * out_h)
    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = src[page_off : page_off + page_size]
            for block_row in range(8):
                for block_col in range(8):
                    block_idx = BT8[block_row][block_col]
                    block_data = page[block_idx * 128 : block_idx * 128 + 128]
                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 64 + block_row * 8
                    for row in range(8):
                        for col in range(16):
                            si = row * 16 + col
                            sx, sy = dst_x + col, dst_y + row
                            di = sy * out_w + sx
                            if si < len(block_data) and di < len(out):
                                out[di] = block_data[si]
    return bytes(out), out_w, out_h


def swizzle_psmt8(indices: bytes, w: int, h: int) -> bytes:
    pw = math.ceil(w / 128)
    ph = math.ceil(h / 64)
    page_size = 8192
    dst = bytearray(pw * ph * page_size)
    out_w = pw * 128
    padded = bytearray(indices[: w * h])
    if len(padded) < w * h:
        padded.extend(b"\x00" * (w * h - len(padded)))
    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = bytearray(page_size)
            for block_row in range(8):
                for block_col in range(8):
                    block_idx = BT8[block_row][block_col]
                    block_data = bytearray(128)
                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 64 + block_row * 8
                    for row in range(8):
                        for col in range(16):
                            sx, sy = dst_x + col, dst_y + row
                            if sx < w and sy < h:
                                block_data[row * 16 + col] = padded[sy * w + sx]
                    page[block_idx * 128 : block_idx * 128 + 128] = block_data
            dst[page_off : page_off + page_size] = page
    return bytes(dst)


def deswizzle_psmt4(raw: bytes, w: int, h: int) -> Tuple[bytes, int, int]:
    pw = math.ceil(w / 128)
    ph = math.ceil(h / 128)
    page_size = 8192
    total = pw * ph * page_size
    src = bytearray(raw[:total])
    if len(src) < total:
        src.extend(b"\x00" * (total - len(src)))
    out_w, out_h = pw * 128, ph * 128
    out = bytearray(out_w * out_h)
    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = src[page_off : page_off + page_size]
            for block_row in range(4):
                for block_col in range(8):
                    block_idx = BT4[block_row][block_col]
                    block_data = page[block_idx * 128 : block_idx * 128 + 128]
                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 128 + block_row * 16
                    for row in range(16):
                        for col in range(16):
                            bi = (row * 16 + col) // 2
                            nib = (row * 16 + col) % 2
                            if bi < len(block_data):
                                v = (block_data[bi] & 0x0F) if nib == 0 else (block_data[bi] >> 4) & 0x0F
                            else:
                                v = 0
                            di = (dst_y + row) * out_w + (dst_x + col)
                            if di < len(out):
                                out[di] = v
    return bytes(out), out_w, out_h


def swizzle_psmt4(nibbles: bytes, w: int, h: int) -> bytes:
    pw = math.ceil(w / 128)
    ph = math.ceil(h / 128)
    page_size = 8192
    dst = bytearray(pw * ph * page_size)
    padded = list(nibbles[: w * h])
    while len(padded) < w * h:
        padded.append(0)
    for py in range(ph):
        for px in range(pw):
            page_off = (py * pw + px) * page_size
            page = bytearray(page_size)
            for block_row in range(4):
                for block_col in range(8):
                    block_idx = BT4[block_row][block_col]
                    block_data = bytearray(128)
                    dst_x = px * 128 + block_col * 16
                    dst_y = py * 128 + block_row * 16
                    for row in range(16):
                        for col in range(16):
                            sx, sy = dst_x + col, dst_y + row
                            v = padded[sy * w + sx] if sx < w and sy < h else 0
                            bi = (row * 16 + col) // 2
                            nib = (row * 16 + col) % 2
                            if nib == 0:
                                block_data[bi] = (block_data[bi] & 0xF0) | (v & 0x0F)
                            else:
                                block_data[bi] = (block_data[bi] & 0x0F) | ((v & 0x0F) << 4)
                    page[block_idx * 128 : block_idx * 128 + 128] = block_data
            dst[page_off : page_off + page_size] = page
    return bytes(dst)


def unswizzle_clut_csm1(raw: bytes, n_colors: int) -> bytes:
    """CLUT en mode CSM1 (swizzle tous les 0x20 octets)."""
    c = bytearray(raw[: n_colors * 4])
    for bank in range(n_colors // 32):
        b = bank * 32 * 4
        c[b + 8 * 4 : b + 16 * 4], c[b + 16 * 4 : b + 24 * 4] = (
            bytearray(c[b + 16 * 4 : b + 24 * 4]),
            bytearray(c[b + 8 * 4 : b + 16 * 4]),
        )
    return bytes(c)


def swizzle_clut_csm1(linear: bytes, n_colors: int) -> bytes:
    c = bytearray(linear[: n_colors * 4])
    for bank in range(n_colors // 32):
        b = bank * 32 * 4
        c[b + 8 * 4 : b + 16 * 4], c[b + 16 * 4 : b + 24 * 4] = (
            bytearray(c[b + 16 * 4 : b + 24 * 4]),
            bytearray(c[b + 8 * 4 : b + 16 * 4]),
        )
    return bytes(c)


def clut_to_rgba(raw: bytes, n_colors: int, csm1: bool = True) -> bytes:
    data = unswizzle_clut_csm1(raw, n_colors) if csm1 else raw[: n_colors * 4]
    out = bytearray(n_colors * 4)
    for i in range(n_colors):
        b, g, r, a = data[i * 4 : i * 4 + 4]
        # TIM2 : alpha souvent semi (0x80 = opaque)
        alpha = 255 if a >= 0x80 else min(255, a * 2)
        out[i * 4 : i * 4 + 4] = bytes([r, g, b, alpha])
    return bytes(out)


def rgba_to_clut(raw_rgba: bytes, n_colors: int, csm1: bool = True) -> bytes:
    linear = bytearray(n_colors * 4)
    for i in range(n_colors):
        r, g, b, a = raw_rgba[i * 4 : i * 4 + 4]
        alpha = 0x80 if a >= 128 else a // 2
        linear[i * 4 : i * 4 + 4] = bytes([b, g, r, alpha])
    return swizzle_clut_csm1(bytes(linear), n_colors) if csm1 else bytes(linear)
