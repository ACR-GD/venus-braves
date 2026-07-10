"""ISO 9660 Level 1 — lecture et patch in-place (PS2)."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator

SECTOR_SIZE = 2048


@dataclass
class IsoEntry:
    path: str
    name: str
    lba: int
    size: int
    is_dir: bool
    flags: int

    @property
    def iso_offset(self) -> int:
        return self.lba * SECTOR_SIZE


@dataclass
class IsoInventory:
    iso_path: Path
    entries: list[IsoEntry] = field(default_factory=list)

    def find(self, target: str) -> IsoEntry | None:
        t = target.replace("\\", "/").strip("/").upper()
        for e in self.entries:
            if e.path.upper() == t or e.name.upper() == t.split("/")[-1]:
                return e
        return None

    def children_of(self, dir_path: str) -> list[IsoEntry]:
        prefix = dir_path.replace("\\", "/").strip("/")
        if prefix:
            prefix += "/"
        out = []
        for e in self.entries:
            if not e.path.startswith(prefix) or e.path == prefix.rstrip("/"):
                continue
            rest = e.path[len(prefix):]
            if "/" not in rest:
                out.append(e)
        return out


def _parse_dir_records(data: bytes, base_path: str) -> list[IsoEntry]:
    entries: list[IsoEntry] = []
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            pos += 1
            continue
        entry = data[pos : pos + rec_len]
        if len(entry) < 33:
            break
        lba = struct.unpack_from("<I", entry, 2)[0]
        size = struct.unpack_from("<I", entry, 10)[0]
        flags = entry[25]
        name_len = entry[32]
        name = entry[33 : 33 + name_len].decode("ascii", errors="replace").split(";")[0]
        pos += rec_len
        if name in ("\x00", "\x01", ""):
            continue
        path = f"{base_path}/{name}".strip("/") if base_path else name
        entries.append(IsoEntry(path=path, name=name, lba=lba, size=size, is_dir=bool(flags & 2), flags=flags))
    return entries


def _walk_iso(f: BinaryIO, lba: int, size: int, base_path: str = "") -> list[IsoEntry]:
    f.seek(lba * SECTOR_SIZE)
    data = f.read(size)
    local = _parse_dir_records(data, base_path)
    all_entries: list[IsoEntry] = []
    for e in local:
        all_entries.append(e)
        if e.is_dir:
            saved = f.tell()
            all_entries.extend(_walk_iso(f, e.lba, e.size, e.path))
            f.seek(saved)
    return all_entries


def inventory_iso(iso_path: Path) -> IsoInventory:
    iso_path = iso_path.resolve()
    with iso_path.open("rb") as f:
        f.seek(16 * SECTOR_SIZE)
        pvd = f.read(SECTOR_SIZE)
        root_lba = struct.unpack_from("<I", pvd, 156 + 2)[0]
        root_size = struct.unpack_from("<I", pvd, 156 + 10)[0]
        entries = _walk_iso(f, root_lba, root_size)
    return IsoInventory(iso_path=iso_path, entries=entries)


def max_extent_before_next(inv: IsoInventory, entry: IsoEntry) -> int:
    """Octets écritables à partir de entry.lba avant le fichier suivant."""
    later = sorted({e.lba for e in inv.entries if e.lba > entry.lba and not e.is_dir})
    if later:
        return (later[0] - entry.lba) * SECTOR_SIZE
    return os.path.getsize(inv.iso_path) - entry.iso_offset


def clone_iso(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        r = subprocess.run(["cp", "-c", str(source), str(dest)], capture_output=True, text=True)
        if r.returncode == 0:
            return
    except FileNotFoundError:
        pass
    shutil.copy2(source, dest)


def patch_same_size(iso_path: Path, entry: IsoEntry, original: bytes, patched: bytes) -> int:
    if len(original) != len(patched):
        raise ValueError(f"Tailles différentes pour patch same-size: {len(original)} vs {len(patched)}")
    changes = sum(1 for a, b in zip(original, patched) if a != b)
    with iso_path.open("r+b") as f:
        off = entry.iso_offset
        for i, (a, b) in enumerate(zip(original, patched)):
            if a != b:
                f.seek(off + i)
                f.write(bytes([b]))
    return changes


def write_at_lba(
    iso_path: Path,
    entry: IsoEntry,
    new_data: bytes,
    *,
    max_extent: int | None = None,
    pad_to_original: bool = True,
) -> dict:
    if max_extent is not None and len(new_data) > max_extent:
        raise ValueError(
            f"{entry.path}: {len(new_data):,} o > espace disponible {max_extent:,} o"
        )
    pad = max(0, entry.size - len(new_data)) if pad_to_original else 0
    with iso_path.open("r+b") as f:
        f.seek(entry.iso_offset)
        f.write(new_data)
        if pad:
            f.write(b"\x00" * pad)
    return {
        "path": entry.path,
        "lba": entry.lba,
        "written": len(new_data),
        "padded": pad,
        "original_size": entry.size,
    }
