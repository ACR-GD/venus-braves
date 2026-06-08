#!/usr/bin/env python3
"""
Build candidate data segments from PMA record pointer fields.

Hypothesis:
- For many type-2 records, u32 at offset 0x08 acts like an internal pointer
  to a shared payload zone.
- Sorting these pointers and slicing between them may recover meaningful blobs.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import List, Optional, Tuple


PMA_MAGIC = b"PMA\x00"
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")


@dataclass
class SegmentRow:
    start: int
    end: int
    size: int
    jp_chars: int
    kana_chars: int
    score: float
    preview: str


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
        raise ValueError("No plausible PMA tail offset table found.")
    _, s, e = best
    table_offset = s * 4
    offsets = list(vals[s : e + 1])
    return table_offset, offsets


def chunk_ranges(table_offset: int, offsets: List[int]) -> List[Tuple[int, int, int]]:
    out: List[Tuple[int, int, int]] = []
    for i, st in enumerate(offsets):
        ed = offsets[i + 1] if i + 1 < len(offsets) else table_offset
        if ed > st:
            out.append((i, st, ed))
    return out


def u32_at(blob: bytes, off: int) -> int:
    if off + 4 > len(blob):
        return 0
    return struct.unpack_from("<I", blob, off)[0]


def text_score(text: str) -> Tuple[int, int, float]:
    jp = len(JP_RE.findall(text))
    kana = len(KANA_RE.findall(text))
    score = jp * 1.4 + kana * 1.8 + (kana / max(1, jp)) * 25.0 + min(len(text), 500) / 80.0
    return jp, kana, score


def decode_preview(data: bytes, max_len: int = 180) -> Tuple[int, int, float, str]:
    text = data.decode("shift_jis", errors="ignore")
    jp, kana, score = text_score(text)
    preview = text.replace("\n", "\\n").replace("\r", "\\r")[:max_len]
    return jp, kana, score, preview


def collect_pointer_values(data: bytes, rec_type: int) -> List[int]:
    table_offset, offsets = parse_tail_offset_table(data)
    ranges = chunk_ranges(table_offset, offsets)
    vals: List[int] = []
    for _, st, ed in ranges:
        blob = data[st:ed]
        if len(blob) < 0x0C:
            continue
        t = u32_at(blob, 0)
        if t != rec_type:
            continue
        v = u32_at(blob, 8)
        if 0 <= v < table_offset:
            vals.append(v)
    vals = sorted(set(vals))
    return vals


def build_segments(data: bytes, ptrs: List[int], stop: int) -> List[SegmentRow]:
    rows: List[SegmentRow] = []
    points = [p for p in ptrs if 0 <= p < stop]
    if not points:
        return rows
    for i, st in enumerate(points):
        ed = points[i + 1] if i + 1 < len(points) else stop
        if ed <= st:
            continue
        blob = data[st:ed]
        jp, kana, score, preview = decode_preview(blob)
        rows.append(
            SegmentRow(
                start=st,
                end=ed,
                size=ed - st,
                jp_chars=jp,
                kana_chars=kana,
                score=score,
                preview=preview,
            )
        )
    rows.sort(key=lambda r: r.score, reverse=True)
    return rows


def write_csv(path: Path, rows: List[SegmentRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["start_hex", "end_hex", "size", "jp_chars", "kana_chars", "score", "preview"])
        for r in rows:
            w.writerow([f"0x{r.start:X}", f"0x{r.end:X}", r.size, r.jp_chars, r.kana_chars, f"{r.score:.2f}", r.preview])


def main() -> None:
    parser = argparse.ArgumentParser(description="Construct PMA candidate segments from record pointers.")
    parser.add_argument("pma", type=Path, help="PMA file path")
    parser.add_argument("-o", "--output", type=Path, default=Path("pma_pointer_segments_out"))
    parser.add_argument("--type", type=int, default=2, help="Record type used to collect pointers (default: 2)")
    parser.add_argument("--min-score", type=float, default=40.0)
    parser.add_argument("--min-kana", type=int, default=4)
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args()

    data = args.pma.read_bytes()
    if not data.startswith(PMA_MAGIC):
        raise SystemExit("Not a PMA file.")

    table_offset, _ = parse_tail_offset_table(data)
    ptrs = collect_pointer_values(data, args.type)
    rows = build_segments(data, ptrs, table_offset)
    rows = [r for r in rows if r.score >= args.min_score and r.kana_chars >= args.min_kana]

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "segments.csv", rows)

    print(f"[+] PMA: {args.pma}")
    print(f"[+] Table offset: 0x{table_offset:X}")
    print(f"[+] Unique pointers from type {args.type}: {len(ptrs)}")
    print(f"[+] Candidate segments: {len(rows)}")
    print(f"[+] CSV: {out / 'segments.csv'}")
    print("\nTop segments:")
    for r in rows[: args.top]:
        print(
            f"  - 0x{r.start:X}-0x{r.end:X} size={r.size} score={r.score:.2f} "
            f"jp={r.jp_chars} kana={r.kana_chars} :: {r.preview!r}"
        )


if __name__ == "__main__":
    main()
