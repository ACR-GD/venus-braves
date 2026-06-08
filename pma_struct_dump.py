#!/usr/bin/env python3
"""
Structural analyzer for Venus & Braves PMA files.

Goal:
- Parse stable PMA metadata.
- Recover tail offset table and chunk boundaries.
- Build chunk fingerprints to compare PMA internals across files.
- Emit machine-readable reports (JSON/CSV).
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Dict, List, Optional, Tuple


PMA_MAGIC = b"PMA\x00"


@dataclass
class ChunkRecord:
    index: int
    start: int
    end: int
    size: int
    entropy: float
    first_u32: int
    first_u16: int
    header8_hex: str
    sha1_16: str
    zlib_header_hits: int


@dataclass
class PmaReport:
    path: str
    file_size: int
    magic: str
    version: int
    header_u32: List[int]
    table_offset: int
    table_entries: int
    chunks: int
    chunk_size_min: int
    chunk_size_max: int
    chunk_size_median: int
    top_chunk_signatures: List[Dict[str, object]]


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    n = len(data)
    e = 0.0
    for c in freq:
        if c:
            p = c / n
            e -= p * math.log2(p)
    return e


def parse_tail_offset_table(data: bytes, max_scan_dwords: int = 1400) -> Tuple[int, List[int]]:
    dword_count = len(data) // 4
    vals = struct.unpack(f"<{dword_count}I", data[: dword_count * 4])
    scan_start = max(0, dword_count - max_scan_dwords)

    best: Optional[Tuple[int, int, int]] = None
    i = scan_start
    while i < dword_count - 2:
        cur = vals[i]
        nxt = vals[i + 1]
        if cur < len(data) and nxt < len(data) and nxt > cur:
            j = i + 1
            while j + 1 < dword_count:
                nv = vals[j + 1]
                if nv >= len(data) or nv <= vals[j]:
                    break
                j += 1
            run_len = j - i + 1
            if best is None or run_len > best[0]:
                best = (run_len, i, j)
            i = j + 1
        else:
            i += 1

    if not best or best[0] < 8:
        raise ValueError("No plausible tail offset table found.")

    _, start_idx, end_idx = best
    table_offset = start_idx * 4
    offsets = list(vals[start_idx : end_idx + 1])
    return table_offset, offsets


def chunk_records(data: bytes, table_offset: int, offsets: List[int]) -> List[ChunkRecord]:
    records: List[ChunkRecord] = []
    zlib_heads = [b"\x78\x01", b"\x78\x5e", b"\x78\x9c", b"\x78\xda"]

    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else table_offset
        if end <= start:
            continue
        blob = data[start:end]
        first_u32 = struct.unpack_from("<I", blob + b"\x00\x00\x00\x00", 0)[0]
        first_u16 = struct.unpack_from("<H", blob + b"\x00\x00", 0)[0]
        sha1_16 = hashlib.sha1(blob).hexdigest()[:16]
        zhits = sum(blob.count(h) for h in zlib_heads)
        rec = ChunkRecord(
            index=i,
            start=start,
            end=end,
            size=end - start,
            entropy=entropy(blob),
            first_u32=first_u32,
            first_u16=first_u16,
            header8_hex=blob[:8].hex(),
            sha1_16=sha1_16,
            zlib_header_hits=zhits,
        )
        records.append(rec)
    return records


def median_int(values: List[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    m = n // 2
    if n % 2:
        return s[m]
    return (s[m - 1] + s[m]) // 2


def make_signature_summary(records: List[ChunkRecord], top_n: int = 15) -> List[Dict[str, object]]:
    groups: Dict[str, List[ChunkRecord]] = {}
    for r in records:
        key = f"{r.header8_hex}:{r.first_u16:04x}"
        groups.setdefault(key, []).append(r)

    ranked = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)[:top_n]
    out: List[Dict[str, object]] = []
    for key, recs in ranked:
        sizes = [r.size for r in recs]
        out.append(
            {
                "signature": key,
                "count": len(recs),
                "size_min": min(sizes),
                "size_max": max(sizes),
                "size_median": median_int(sizes),
                "sample_chunk_index": recs[0].index,
                "sample_chunk_offset": f"0x{recs[0].start:X}",
            }
        )
    return out


def analyze_pma(p: Path) -> Tuple[PmaReport, List[ChunkRecord]]:
    data = p.read_bytes()
    if len(data) < 0x40:
        raise ValueError("File too small.")
    if not data.startswith(PMA_MAGIC):
        raise ValueError("Missing PMA magic.")

    header_u32 = list(struct.unpack("<16I", data[: 16 * 4]))
    version = header_u32[1]
    table_offset, offsets = parse_tail_offset_table(data)
    records = chunk_records(data, table_offset, offsets)

    sizes = [r.size for r in records]
    report = PmaReport(
        path=str(p),
        file_size=len(data),
        magic=data[:4].decode("ascii", errors="replace"),
        version=version,
        header_u32=header_u32,
        table_offset=table_offset,
        table_entries=len(offsets),
        chunks=len(records),
        chunk_size_min=min(sizes) if sizes else 0,
        chunk_size_max=max(sizes) if sizes else 0,
        chunk_size_median=median_int(sizes),
        top_chunk_signatures=make_signature_summary(records),
    )
    return report, records


def write_chunks_csv(path: Path, records: List[ChunkRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "index",
                "start_hex",
                "end_hex",
                "size",
                "entropy",
                "first_u32_hex",
                "first_u16_hex",
                "header8_hex",
                "sha1_16",
                "zlib_header_hits",
            ]
        )
        for r in records:
            w.writerow(
                [
                    r.index,
                    f"0x{r.start:X}",
                    f"0x{r.end:X}",
                    r.size,
                    f"{r.entropy:.4f}",
                    f"0x{r.first_u32:08X}",
                    f"0x{r.first_u16:04X}",
                    r.header8_hex,
                    r.sha1_16,
                    r.zlib_header_hits,
                ]
            )


def write_json(path: Path, obj: object) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def compare_reports(reports: List[PmaReport]) -> Dict[str, object]:
    sig_global: Dict[str, int] = {}
    versions = sorted(set(r.version for r in reports))
    table_entries = [r.table_entries for r in reports]
    chunk_counts = [r.chunks for r in reports]

    for r in reports:
        for s in r.top_chunk_signatures:
            sig = str(s["signature"])
            sig_global[sig] = sig_global.get(sig, 0) + int(s["count"])

    top_sig = sorted(sig_global.items(), key=lambda kv: kv[1], reverse=True)[:30]
    return {
        "files_analyzed": len(reports),
        "versions": versions,
        "table_entries_min": min(table_entries) if table_entries else 0,
        "table_entries_max": max(table_entries) if table_entries else 0,
        "chunk_count_min": min(chunk_counts) if chunk_counts else 0,
        "chunk_count_max": max(chunk_counts) if chunk_counts else 0,
        "global_top_signatures": [{"signature": k, "count": v} for k, v in top_sig],
    }


def gather_inputs(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.pma"))
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump PMA structure and compare chunk signatures across files."
    )
    parser.add_argument("input", type=Path, help="PMA file or directory containing PMA files")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("pma_struct_out"),
        help="Output directory (default: ./pma_struct_out)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max number of PMA files to analyze (0 = all)",
    )
    parser.add_argument(
        "--glob",
        type=str,
        default="",
        help="Optional substring filter on PMA path (example: 'ev_')",
    )
    args = parser.parse_args()

    files = gather_inputs(args.input)
    if args.glob:
        files = [p for p in files if args.glob in str(p)]
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        raise SystemExit("No PMA files found with current filters.")

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    reports: List[PmaReport] = []

    print(f"[+] PMA files to analyze: {len(files)}")
    for p in files:
        try:
            rep, chunks = analyze_pma(p)
        except Exception as e:
            print(f"[!] Skip {p}: {e}")
            continue

        reports.append(rep)
        stem = p.name.replace(".pma", "")
        per_file_dir = out / stem
        per_file_dir.mkdir(parents=True, exist_ok=True)
        write_json(per_file_dir / "report.json", asdict(rep))
        write_chunks_csv(per_file_dir / "chunks.csv", chunks)
        print(
            f"  - {p.name}: table=0x{rep.table_offset:X} entries={rep.table_entries} "
            f"chunks={rep.chunks} size={rep.file_size}"
        )

    overview = {
        "summary": compare_reports(reports),
        "files": [asdict(r) for r in reports],
    }
    write_json(out / "overview.json", overview)
    print(f"[+] Wrote overview: {out / 'overview.json'}")


if __name__ == "__main__":
    main()
