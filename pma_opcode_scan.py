#!/usr/bin/env python3
"""
Opcode/record structure scanner for Venus & Braves PMA records.

Focus:
- Type 2/3 records discovered in PMA chunks.
- Infer recurring field patterns and internal offsets.
- Produce per-file and cross-file summaries for extractor design.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import struct
from typing import Dict, List, Optional, Tuple


PMA_MAGIC = b"PMA\x00"


@dataclass
class RecRow:
    file: str
    chunk_index: int
    rec_type: int
    size: int
    start_hex: str
    header_hex: str
    u32_0: int
    u32_1: int
    u32_2: int
    u32_3: int
    u16_8: int
    u16_10: int
    u16_12: int
    u16_14: int
    first_nonzero_after_0x10: int
    zlib_like_offsets: str


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


def chunk_ranges(table_offset: int, offsets: List[int]) -> List[Tuple[int, int, int]]:
    out: List[Tuple[int, int, int]] = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else table_offset
        if end > start:
            out.append((i, start, end))
    return out


def u32_at(blob: bytes, off: int) -> int:
    if off + 4 > len(blob):
        return 0
    return struct.unpack_from("<I", blob, off)[0]


def u16_at(blob: bytes, off: int) -> int:
    if off + 2 > len(blob):
        return 0
    return struct.unpack_from("<H", blob, off)[0]


def first_nonzero_offset(blob: bytes, start: int = 0x10, max_scan: int = 0x80) -> int:
    end = min(len(blob), max_scan)
    for i in range(start, end):
        if blob[i] != 0:
            return i
    return -1


def zlib_like_offsets(blob: bytes, max_scan: int = 0x100) -> List[int]:
    heads = [b"\x78\x01", b"\x78\x5E", b"\x78\x9C", b"\x78\xDA"]
    end = min(len(blob), max_scan)
    area = blob[:end]
    hits: List[int] = []
    for h in heads:
        pos = area.find(h)
        while pos != -1:
            hits.append(pos)
            pos = area.find(h, pos + 1)
    return sorted(set(hits))


def scan_pma(path: Path, types: Tuple[int, ...]) -> List[RecRow]:
    data = path.read_bytes()
    if not data.startswith(PMA_MAGIC):
        raise ValueError(f"Not PMA: {path}")

    table_offset, offsets = parse_tail_offset_table(data)
    ranges = chunk_ranges(table_offset, offsets)
    rows: List[RecRow] = []

    for idx, start, end in ranges:
        blob = data[start:end]
        if len(blob) < 0x10:
            continue
        rec_t = u32_at(blob, 0)
        if rec_t not in types:
            continue
        zhits = zlib_like_offsets(blob)
        rows.append(
            RecRow(
                file=str(path),
                chunk_index=idx,
                rec_type=rec_t,
                size=len(blob),
                start_hex=f"0x{start:X}",
                header_hex=blob[:16].hex(),
                u32_0=u32_at(blob, 0),
                u32_1=u32_at(blob, 4),
                u32_2=u32_at(blob, 8),
                u32_3=u32_at(blob, 12),
                u16_8=u16_at(blob, 8),
                u16_10=u16_at(blob, 10),
                u16_12=u16_at(blob, 12),
                u16_14=u16_at(blob, 14),
                first_nonzero_after_0x10=first_nonzero_offset(blob),
                zlib_like_offsets=",".join(hex(x) for x in zhits[:8]),
            )
        )
    return rows


def write_csv(path: Path, rows: List[RecRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "file",
                "chunk_index",
                "rec_type",
                "size",
                "start_hex",
                "header_hex",
                "u32_0",
                "u32_1",
                "u32_2",
                "u32_3",
                "u16_8",
                "u16_10",
                "u16_12",
                "u16_14",
                "first_nonzero_after_0x10",
                "zlib_like_offsets",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.file,
                    r.chunk_index,
                    r.rec_type,
                    r.size,
                    r.start_hex,
                    r.header_hex,
                    r.u32_0,
                    r.u32_1,
                    r.u32_2,
                    r.u32_3,
                    r.u16_8,
                    r.u16_10,
                    r.u16_12,
                    r.u16_14,
                    r.first_nonzero_after_0x10,
                    r.zlib_like_offsets,
                ]
            )


def summarize(rows: List[RecRow]) -> Dict[str, object]:
    by_type: Dict[int, int] = {}
    by_u32_1: Dict[int, int] = {}
    by_u16_8: Dict[int, int] = {}
    by_first_nonzero: Dict[int, int] = {}

    for r in rows:
        by_type[r.rec_type] = by_type.get(r.rec_type, 0) + 1
        by_u32_1[r.u32_1] = by_u32_1.get(r.u32_1, 0) + 1
        by_u16_8[r.u16_8] = by_u16_8.get(r.u16_8, 0) + 1
        by_first_nonzero[r.first_nonzero_after_0x10] = by_first_nonzero.get(r.first_nonzero_after_0x10, 0) + 1

    def top(d: Dict[int, int], n: int = 12) -> List[Dict[str, int]]:
        return [{"value": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]]

    return {
        "records": len(rows),
        "by_type_top": top(by_type),
        "u32_1_top": top(by_u32_1),
        "u16_8_top": top(by_u16_8),
        "first_nonzero_after_0x10_top": top(by_first_nonzero),
    }


def gather_inputs(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.pma"))
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan PMA type-2/3 record field patterns.")
    parser.add_argument("input", type=Path, help="PMA file or directory")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("pma_opcode_scan_out"), help="Output directory"
    )
    parser.add_argument("--glob", type=str, default="", help="Filter substring on path")
    parser.add_argument("--limit", type=int, default=0, help="Max number of files (0=all)")
    parser.add_argument("--types", type=str, default="2,3,1", help="Comma-separated record types")
    args = parser.parse_args()

    rec_types = tuple(int(x.strip()) for x in args.types.split(",") if x.strip())
    files = gather_inputs(args.input)
    if args.glob:
        files = [p for p in files if args.glob in str(p)]
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        raise SystemExit("No PMA files found.")

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[RecRow] = []
    file_summaries: Dict[str, object] = {}
    print(f"[+] Files to scan: {len(files)}")
    for p in files:
        try:
            rows = scan_pma(p, rec_types)
        except Exception as e:
            print(f"[!] Skip {p}: {e}")
            continue
        all_rows.extend(rows)
        file_summaries[p.name] = summarize(rows)
        print(f"  - {p.name}: {len(rows)} records")

    write_csv(out_dir / "records.csv", all_rows)
    summary_obj = {
        "record_types": list(rec_types),
        "files": file_summaries,
        "global_summary": summarize(all_rows),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary_obj, f, ensure_ascii=False, indent=2)

    print(f"[+] Wrote: {out_dir / 'records.csv'}")
    print(f"[+] Wrote: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
