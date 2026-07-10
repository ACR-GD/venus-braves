"""Formats conteneurs graphiques PS2 (Namco, Sony, etc.)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class FhmEntry:
    index: int
    offset: int
    size: int
    magic: str
    width: int | None = None
    height: int | None = None
    tile_count: int | None = None
    kind: str = "unknown"


@dataclass
class IteTile:
    index: int
    offset: int
    size: int
    compressed: bool
    lead_byte: int
    empty: bool


@dataclass
class IteInfo:
    offset: int
    width: int
    height: int
    tiles: list[IteTile]
    tile_w: int = 64
    tile_h: int = 32


def read_magic(data: bytes, off: int) -> str:
    if off + 4 > len(data):
        return "????"
    raw = data[off : off + 4]
    if raw == b"ITE\x00":
        return "ITE"
    return raw.decode("ascii", errors="replace").rstrip("\x00")


def is_ite(data: bytes, off: int) -> bool:
    return off + 4 <= len(data) and data[off : off + 4] == b"ITE\x00"


def parse_fhm(data: bytes) -> list[FhmEntry]:
    if len(data) < 8:
        return []
    count = struct.unpack_from("<I", data, 0)[0]
    entries: list[FhmEntry] = []
    for i in range(count + 1):
        off = struct.unpack_from("<I", data, 4 + i * 4)[0]
        if off >= len(data):
            continue
        end = len(data)
        if i + 1 <= count:
            nxt = struct.unpack_from("<I", data, 4 + (i + 1) * 4)[0]
            if nxt > off:
                end = nxt
        size = end - off
        magic = read_magic(data, off)
        entry = FhmEntry(index=i, offset=off, size=size, magic=magic)
        if is_ite(data, off):
            try:
                ite = parse_ite(data, off)
                entry.width = ite.width
                entry.height = ite.height
                entry.tile_count = len(ite.tiles)
                entry.kind = "ite_texture"
            except Exception:
                entry.kind = "ite_broken"
        elif i == 0:
            entry.kind = "fhm_meta"
        else:
            entry.kind = _guess_kind(magic)
        entries.append(entry)
    return entries


def _guess_kind(magic: str) -> str:
    if magic.startswith("GIM"):
        return "gim"
    if magic in ("TIM\x00", "TIM2", "CLT2"):
        return "tim" if magic.startswith("TIM") and magic != "TIM2" else "tim2"
    return "blob"


def parse_ite(data: bytes, ite_off: int) -> IteInfo:
    if data[ite_off : ite_off + 4] != b"ITE\x00":
        raise ValueError(f"ITE magic manquant @ {ite_off:#x}")
    w = struct.unpack_from("<I", data, ite_off + 4)[0]
    h = struct.unpack_from("<I", data, ite_off + 8)[0]
    first_raw = struct.unpack_from("<I", data, ite_off + 0x10)[0]
    first = first_raw & 0x7FFFFFFF
    n = (first - 0x10) // 4
    if n <= 0 or n > 10_000:
        raise ValueError(f"nombre de tuiles invalide ({n}) @ {ite_off:#x}")

    raw_offs = [
        struct.unpack_from("<I", data, ite_off + 0x10 + k * 4)[0]
        for k in range(n)
    ]
    tiles: list[IteTile] = []
    for idx, raw in enumerate(raw_offs):
        rel = raw & 0x7FFFFFFF
        compressed = bool(raw & 0x80000000)
        src = ite_off + rel
        if idx + 1 < n:
            nxt = ite_off + (raw_offs[idx + 1] & 0x7FFFFFFF)
            size = nxt - src
        else:
            size = len(data) - src
        lead = data[src] if src < len(data) else 0
        tiles.append(IteTile(
            index=idx,
            offset=src,
            size=size,
            compressed=compressed,
            lead_byte=lead,
            empty=lead == 0 and size <= 16,
        ))
    return IteInfo(offset=ite_off, width=w, height=h, tiles=tiles)


def scan_directory(root: Path, patterns: tuple[str, ...] = ("*.fhm", "*.gim", "*.arc", "*.tim", "*.tm2", "*.TM2")) -> list[Path]:
    root = root.resolve()
    out: list[Path] = []
    for pat in patterns:
        out.extend(root.rglob(pat))
    return sorted(set(out))


def summarize_file(path: Path) -> dict:
    data = path.read_bytes()
    magic = read_magic(data, 0)
    summary: dict = {
        "path": str(path),
        "size": len(data),
        "magic": magic,
        "kind": "unknown",
        "entries": [],
    }
    if path.suffix.lower() == ".fhm":
        try:
            entries = parse_fhm(data)
            summary["kind"] = "fhm"
            for e in entries:
                summary["entries"].append({
                    "index": e.index,
                    "offset": f"0x{e.offset:X}",
                    "size": e.size,
                    "magic": e.magic,
                    "kind": e.kind,
                    "width": e.width,
                    "height": e.height,
                    "tiles": e.tile_count,
                })
        except Exception as exc:
            summary["error"] = str(exc)
    elif is_ite(data, 0):
        try:
            ite = parse_ite(data, 0)
            summary["kind"] = "ite"
            summary["width"] = ite.width
            summary["height"] = ite.height
            summary["tiles"] = len(ite.tiles)
        except Exception as exc:
            summary["error"] = str(exc)
    return summary
