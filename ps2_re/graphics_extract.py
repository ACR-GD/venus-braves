"""Extraction de graphismes traduisibles (FHM/ITE et conteneurs similaires)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .compression_probe import ChunkAnalysis, probe_chunk, probe_ite_tiles
from .containers import parse_fhm, parse_ite, scan_directory, summarize_file


def _try_decode_tile_plane(data: bytes, tile_offset: int) -> bytes | None:
    try:
        from ulz_decode import decode_plane
        plane, _ = decode_plane(data, tile_offset)
        return bytes(plane)
    except Exception:
        return None


def _plane_to_png(plane: bytes, width: int = 64, height: int = 32, path: Path | None = None):
    try:
        from PIL import Image
    except ImportError:
        return None
    if len(plane) < width * height:
        return None
    img = Image.new("L", (width, height))
    img.putdata(list(plane[: width * height]))
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
    return img


def _assemble_ite_image(data: bytes, ite: IteInfo, decode: bool = True):
    try:
        from PIL import Image
    except ImportError:
        return None
    tw, th = ite.tile_w, ite.tile_h
    cols = max(1, (ite.width + tw - 1) // tw)
    rows = max(1, (ite.height + th - 1) // th)
    img = Image.new("L", (ite.width, ite.height), 0)
    px = img.load()
    for tile in ite.tiles:
        if tile.empty:
            continue
        plane = None
        if decode:
            plane = _try_decode_tile_plane(data, tile.offset)
        if plane is None and tile.lead_byte != 0 and not tile.compressed:
            raw = data[tile.offset : tile.offset + tile.size]
            if len(raw) >= tw * th:
                plane = raw[: tw * th]
        if plane is None:
            continue
        txi = tile.index % cols
        tyi = tile.index // cols
        for i in range(min(len(plane), tw * th)):
            lx, ly = i % tw, i // tw
            x, y = txi * tw + lx, tyi * th + ly
            if x < ite.width and y < ite.height:
                px[x, y] = plane[i]
    return img


def inventory_fhm(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    entries = parse_fhm(data)
    report: dict[str, Any] = {
        "file": str(path),
        "size": len(data),
        "entry_count": len(entries),
        "translatable_candidates": [],
        "compression_summary": {},
    }
    codec_counts: dict[str, int] = {}

    for entry in entries:
        if entry.kind != "ite_texture":
            continue
        ite = parse_ite(data, entry.offset)
        probes = probe_ite_tiles(data, entry.offset)
        for p in probes:
            codec_counts[p.likely] = codec_counts.get(p.likely, 0) + 1

        # candidats traduction : petites ITE (UI) ou beaucoup de tuiles compressées
        w, h = ite.width, ite.height
        is_ui = (w <= 640 and h <= 480 and len(ite.tiles) < 200) or (w * h < 500_000)
        report["translatable_candidates"].append({
            "index": entry.index,
            "offset": f"0x{entry.offset:X}",
            "size": entry.size,
            "dimensions": f"{w}x{h}",
            "tiles": len(ite.tiles),
            "ui_likely": is_ui,
            "priority": "high" if is_ui and w * h < 200_000 else "medium",
        })

    report["compression_summary"] = codec_counts
    return report


def extract_fhm(
    path: Path,
    out_dir: Path,
    *,
    entry_indices: list[int] | None = None,
    export_tiles: bool = False,
    export_probe: bool = True,
) -> dict[str, Any]:
    data = path.read_bytes()
    entries = parse_fhm(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {"file": str(path), "extracted": []}

    for entry in entries:
        if entry.kind != "ite_texture":
            continue
        if entry_indices is not None and entry.index not in entry_indices:
            continue

        ite = parse_ite(data, entry.offset)
        tag = f"entry{entry.index:02d}_{ite.width}x{ite.height}"
        item: dict[str, Any] = {
            "index": entry.index,
            "offset": f"0x{entry.offset:X}",
            "dimensions": f"{ite.width}x{ite.height}",
            "tiles": len(ite.tiles),
            "outputs": [],
        }

        img = _assemble_ite_image(data, ite)
        if img is not None:
            png = out_dir / f"{path.stem}_{tag}.png"
            img.save(png)
            item["outputs"].append(str(png))

        if export_probe:
            probes = probe_ite_tiles(data, entry.offset)
            probe_path = out_dir / f"{path.stem}_{tag}_compression.json"
            probe_path.write_text(
                json.dumps([_chunk_to_dict(p) for p in probes], indent=2),
                encoding="utf-8",
            )
            item["outputs"].append(str(probe_path))
            item["codecs"] = _summarize_codecs(probes)

        if export_tiles:
            tile_dir = out_dir / f"{path.stem}_{tag}_tiles"
            tile_dir.mkdir(exist_ok=True)
            for tile in ite.tiles:
                if tile.empty:
                    continue
                plane = _try_decode_tile_plane(data, tile.offset)
                if plane:
                    tp = tile_dir / f"tile_{tile.index:03d}.png"
                    _plane_to_png(plane, path=tp)
            item["outputs"].append(str(tile_dir))

        results["extracted"].append(item)

    manifest = out_dir / f"{path.stem}_manifest.json"
    manifest.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    results["manifest"] = str(manifest)
    return results


def _chunk_to_dict(p: ChunkAnalysis) -> dict:
    return {
        "offset": f"0x{p.offset:X}",
        "size": p.size,
        "lead_byte": f"0x{p.lead_byte:02x}",
        "entropy": round(p.entropy, 3),
        "likely": p.likely,
        "probes": [
            {"name": x.name, "confidence": x.confidence, "notes": x.notes}
            for x in p.probes
        ],
    }


def _summarize_codecs(probes: list[ChunkAnalysis]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in probes:
        counts[p.likely] = counts.get(p.likely, 0) + 1
    return counts


def scan_graphics_tree(root: Path) -> list[dict]:
    return [summarize_file(p) for p in scan_directory(root)]
