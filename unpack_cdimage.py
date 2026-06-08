#!/usr/bin/env python3
"""
Unpacker for Venus & Braves CDIMAGE.BIN archives.

Observed format:
- Header starts with (name_offset, size) uint32 little-endian pairs.
- Pairs are listed in ascending name_offset order; the table ends when the
  next name_offset is smaller than the previous one.
- File data is stored sequentially and each file payload is aligned to 0x800.
- The first payload is "filelist.bin", which contains NUL-separated internal
  paths for the remaining files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
from typing import List, Tuple


ALIGNMENT = 0x800


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + (alignment - 1)) & ~(alignment - 1)


def parse_index_pairs(data: bytes) -> Tuple[List[int], List[int]]:
    if len(data) < 8:
        raise ValueError("Archive too small to contain an index.")

    dword_count = len(data) // 4
    dwords = struct.unpack(f"<{dword_count}I", data[: dword_count * 4])

    name_offsets = list(dwords[0::2])
    sizes = list(dwords[1::2])
    if not name_offsets:
        raise ValueError("Could not parse any index entries.")

    entry_count = 1
    for i in range(1, len(name_offsets)):
        if name_offsets[i] < name_offsets[i - 1]:
            break
        entry_count += 1

    return name_offsets[:entry_count], sizes[:entry_count]


def compute_data_start(file_size: int, sizes: List[int]) -> int:
    payload_size = sum(align_up(size) for size in sizes)
    data_start = file_size - payload_size
    if data_start < 0:
        raise ValueError("Computed data start is negative. Invalid archive?")
    return data_start


def parse_filelist_names(filelist_blob: bytes) -> List[str]:
    names: List[str] = []
    for part in filelist_blob.split(b"\x00"):
        if len(part) < 4:
            continue
        try:
            text = part.decode("ascii")
        except UnicodeDecodeError:
            continue

        # Keep only path-like entries. filelist.bin is handled separately.
        if "/" in text and "." in text:
            names.append(text)
    return names


def sanitize_relative_path(path_str: str) -> Path:
    clean = path_str.replace("\\", "/").strip("/")
    rel = Path(clean)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe path in file list: {path_str!r}")
    return rel


def unpack_archive(archive_path: Path, output_dir: Path) -> None:
    data = archive_path.read_bytes()
    file_size = len(data)

    name_offsets, sizes = parse_index_pairs(data)
    entry_count = len(sizes)
    data_start = compute_data_start(file_size, sizes)

    print(f"[+] Archive: {archive_path}")
    print(f"[+] Entries: {entry_count}")
    print(f"[+] Data start: 0x{data_start:X}")
    print(f"[+] Alignment: 0x{ALIGNMENT:X}")

    if data_start >= file_size:
        raise ValueError("Computed data start is outside archive bounds.")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Entry 0 is the embedded path list blob.
    first_size = sizes[0]
    first_end = data_start + first_size
    if first_end > file_size:
        raise ValueError("First file payload exceeds archive size.")
    filelist_blob = data[data_start:first_end]
    parsed_names = parse_filelist_names(filelist_blob)

    expected_paths = max(0, entry_count - 1)
    if len(parsed_names) < expected_paths:
        print(
            f"[!] Warning: parsed {len(parsed_names)} paths for "
            f"{expected_paths} expected entries. Fallback names will be used."
        )
    else:
        # Keep only as many names as needed if there is extra noise.
        parsed_names = parsed_names[:expected_paths]

    names: List[str] = ["filelist.bin"]
    for i in range(1, entry_count):
        idx = i - 1
        if idx < len(parsed_names):
            names.append(parsed_names[idx])
        else:
            names.append(f"unknown/{i:05d}.bin")

    cursor = data_start
    for i, (name, size) in enumerate(zip(names, sizes)):
        start = cursor
        end = start + size
        if end > file_size:
            raise ValueError(
                f"Entry {i} ({name}) exceeds archive bounds: "
                f"0x{start:X}-0x{end:X} > 0x{file_size:X}"
            )

        rel_path = sanitize_relative_path(name)
        out_path = output_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data[start:end])

        cursor += align_up(size)

    if cursor != file_size:
        print(
            f"[!] Warning: final cursor 0x{cursor:X} does not match "
            f"archive size 0x{file_size:X}."
        )

    print(f"[+] Extracted to: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unpack Venus & Braves CDIMAGE.BIN archives."
    )
    parser.add_argument("archive", type=Path, help="Path to CDIMAGE.BIN")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("cdimage_unpacked"),
        help="Output directory (default: ./cdimage_unpacked)",
    )
    args = parser.parse_args()

    unpack_archive(args.archive, args.output)


if __name__ == "__main__":
    main()
