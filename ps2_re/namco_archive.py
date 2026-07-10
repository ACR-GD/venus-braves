"""Archives Namco PS2 (CDIMAGE / BGMIMAGE / MOVIMAGE)."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALIGNMENT = 0x800


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + (alignment - 1)) & ~(alignment - 1)


INDEX_SCAN_BYTES = 131072  # l'index Namco tient dans les premiers 128 Ko


def parse_index_pairs(data: bytes, *, scan_bytes: int = INDEX_SCAN_BYTES) -> tuple[list[int], list[int]]:
    if len(data) < 8:
        raise ValueError("Archive trop petite pour l'index")
    chunk = data[: min(scan_bytes, len(data))]
    dword_count = len(chunk) // 4
    dwords = struct.unpack(f"<{dword_count}I", chunk[: dword_count * 4])
    name_offsets = list(dwords[0::2])
    sizes = list(dwords[1::2])
    entry_count = 1
    for i in range(1, len(name_offsets)):
        if name_offsets[i] < name_offsets[i - 1]:
            break
        if sizes[i] == 0 and sizes[i - 1] == 0:
            break
        entry_count += 1
    return name_offsets[:entry_count], sizes[:entry_count]


def parse_filelist_names(filelist_blob: bytes) -> list[str]:
    names: list[str] = []
    if b"\x00" in filelist_blob:
        for part in filelist_blob.split(b"\x00"):
            if len(part) < 4:
                continue
            try:
                text = part.decode("ascii")
            except UnicodeDecodeError:
                continue
            if "/" in text and "." in text:
                names.append(text)
    else:
        for line in filelist_blob.decode("utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "/" in line:
                names.append(line)
    return names


def sanitize_relative_path(path_str: str) -> Path:
    clean = path_str.replace("\\", "/").strip("/")
    for prefix in ("home/tsuyoshi/venus/", "seven_data_link/"):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix) :]
    rel = Path(clean)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Chemin unsafe: {path_str!r}")
    return rel


@dataclass
class ArchiveEntry:
    index: int
    name: str
    size: int
    name_offset: int


@dataclass
class NamcoArchiveInfo:
    path: Path | None
    entry_count: int
    data_start: int
    total_size: int
    layout: str
    entries: list[ArchiveEntry]


def analyze_archive(data: bytes, path: Path | None = None) -> NamcoArchiveInfo:
    file_size = len(data)
    name_offsets, sizes = parse_index_pairs(data)
    entry_count = len(sizes)
    payload_size = sum(align_up(s) for s in sizes)
    header_size = align_up(entry_count * 8)
    data_start_trailing = file_size - payload_size

    # forward : données juste après le header aligné
    if abs(data_start_trailing - header_size) <= 0x2000:
        layout = "forward"
        data_start = header_size
    else:
        layout = "trailing"
        data_start = data_start_trailing

    names = _resolve_names(data, name_offsets, sizes, data_start, entry_count)
    entries = [
        ArchiveEntry(index=i, name=names[i], size=sizes[i], name_offset=name_offsets[i])
        for i in range(entry_count)
    ]
    return NamcoArchiveInfo(
        path=path,
        entry_count=entry_count,
        data_start=data_start,
        total_size=file_size,
        layout=layout,
        entries=entries,
    )


def _resolve_names(
    data: bytes,
    name_offsets: list[int],
    sizes: list[int],
    data_start: int,
    entry_count: int,
) -> list[str]:
    cursor = data_start
    filelist_blob = data[cursor : cursor + sizes[0]]
    parsed = parse_filelist_names(filelist_blob)
    names = ["filelist.bin"]
    for i in range(1, entry_count):
        idx = i - 1
        names.append(parsed[idx] if idx < len(parsed) else f"unknown/{i:05d}.bin")
    return names


def unpack_archive(
    archive_path: Path,
    output_dir: Path,
    *,
    save_index_template: bool = True,
) -> NamcoArchiveInfo:
    data = archive_path.read_bytes()
    info = analyze_archive(data, archive_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    if save_index_template:
        raw_index = struct.pack(
            f"<{info.entry_count * 2}I",
            *sum(([e.name_offset, e.size] for e in info.entries), []),
        )
        (output_dir / "archive_index.bin").write_bytes(raw_index)
        meta = {
            "source": str(archive_path),
            "layout": info.layout,
            "data_start": info.data_start,
            "total_size": info.total_size,
            "entry_count": info.entry_count,
        }
        (output_dir / "archive_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    cursor = info.data_start
    for entry in info.entries:
        start = cursor
        end = start + entry.size
        rel = sanitize_relative_path(entry.name)
        out_path = output_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data[start:end])
        cursor += align_up(entry.size)

    return info


def verify_unpacked(unpacked_dir: Path, *, require_filelist: bool = True) -> dict[str, Any]:
    unpacked_dir = unpacked_dir.resolve()
    report: dict[str, Any] = {"unpacked_dir": str(unpacked_dir), "ok": True, "missing": [], "files": []}

    meta_path = unpacked_dir / "archive_meta.json"
    index_path = unpacked_dir / "archive_index.bin"
    filelist_path = unpacked_dir / "filelist.bin"

    if not filelist_path.exists():
        report["ok"] = False
        report["missing"].append("filelist.bin")
        return report

    filelist = filelist_path.read_bytes()
    names = parse_filelist_names(filelist)
    report["expected_count"] = len(names) + 1

    for name in ["filelist.bin", *names]:
        p = unpacked_dir / sanitize_relative_path(name)
        if not p.exists():
            report["ok"] = False
            report["missing"].append(name)
        else:
            report["files"].append({"name": name, "size": p.stat().st_size})

    if require_filelist and not index_path.exists():
        report["warnings"] = report.get("warnings", []) + [
            "archive_index.bin absent — repack utilisera les offsets de filelist"
        ]

    return report


def projected_archive_size(unpacked_dir: Path, max_size: int | None = None, layout: str | None = None) -> dict[str, int]:
    verify = verify_unpacked(unpacked_dir)
    if not verify["ok"]:
        raise FileNotFoundError(f"Fichiers manquants: {verify['missing']}")
    meta_path = unpacked_dir / "archive_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    payload = sum(align_up(f["size"]) for f in verify["files"])
    entry_count = verify["expected_count"]
    header_size = align_up(entry_count * 8)
    chosen = layout or meta.get("layout", "trailing")
    if chosen == "trailing" and max_size:
        return {
            "payload_size": payload,
            "archive_size": max_size,
            "data_start": max_size - payload,
            "header_size": header_size,
            "overflow": max(0, payload + header_size - max_size),
        }
    archive_size = header_size + payload
    return {
        "payload_size": payload,
        "archive_size": archive_size,
        "data_start": header_size,
        "header_size": header_size,
        "overflow": max(0, archive_size - max_size) if max_size else 0,
    }


def repack_archive(
    unpacked_dir: Path,
    output_path: Path,
    *,
    max_size: int | None = None,
    layout: str | None = None,
    index_template: Path | None = None,
) -> dict[str, Any]:
    unpacked_dir = unpacked_dir.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta_path = unpacked_dir / "archive_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    if index_template is None:
        index_template = unpacked_dir / "archive_index.bin"
    if not index_template.exists():
        raise FileNotFoundError(
            f"Template d'index introuvable ({index_template}). "
            "Décompressez avec save_index_template ou fournissez --index-template."
        )

    template = index_template.read_bytes()
    name_offsets, _orig_sizes = parse_index_pairs(template)
    entry_count = len(name_offsets)

    verify = verify_unpacked(unpacked_dir)
    if not verify["ok"]:
        raise FileNotFoundError(f"Fichiers manquants: {verify['missing']}")

    names = ["filelist.bin"]
    filelist = (unpacked_dir / "filelist.bin").read_bytes()
    names.extend(parse_filelist_names(filelist)[: max(0, entry_count - 1)])
    while len(names) < entry_count:
        names.append(f"unknown/{len(names):05d}.bin")

    file_contents: list[bytes] = []
    new_sizes: list[int] = []
    for name in names:
        p = unpacked_dir / sanitize_relative_path(name)
        content = p.read_bytes()
        file_contents.append(content)
        new_sizes.append(len(content))

    chosen_layout = layout or meta.get("layout", "trailing")
    header_raw = entry_count * 8
    header_size = align_up(header_raw)
    payload_size = sum(align_up(s) for s in new_sizes)

    if max_size is None:
        max_size = meta.get("total_size")

    if chosen_layout == "trailing" and max_size:
        data_start = max_size - payload_size
        if data_start < header_size:
            overflow = header_size - data_start
            raise ValueError(
                f"Archive trop grande de {overflow:,} o pour max_size={max_size:,} "
                f"(payload={payload_size:,})"
            )
        archive_size = max_size
    else:
        data_start = header_size
        archive_size = header_size + payload_size

    if max_size and archive_size > max_size:
        raise ValueError(
            f"Taille projetée {archive_size:,} > budget {max_size:,} "
            f"(excès {archive_size - max_size:,} o)"
        )

    index_bytes = bytearray()
    for i in range(entry_count):
        index_bytes.extend(struct.pack("<2I", name_offsets[i], new_sizes[i]))
    header_bytes = index_bytes + b"\x00" * (header_size - len(index_bytes))

    out = bytearray(archive_size)
    out[:header_size] = header_bytes

    cursor = data_start
    for content in file_contents:
        end = cursor + len(content)
        out[cursor:end] = content
        cursor += align_up(len(content))

    output_path.write_bytes(out)
    return {
        "output": str(output_path),
        "layout": chosen_layout,
        "entry_count": entry_count,
        "data_start": data_start,
        "archive_size": archive_size,
        "payload_size": payload_size,
        "sizes_changed": sum(a != b for a, b in zip(new_sizes, _orig_sizes)),
    }
