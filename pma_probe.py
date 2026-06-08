#!/usr/bin/env python3
"""
Probe and chunk analyzer for Venus & Braves PMA files.

Goal:
- Parse PMA structure enough to split internal chunks.
- Export chunks for reverse engineering.
- Score chunks likely to contain script/dialogue payloads.

This is an analysis tool, not a final extractor/injector yet.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import re
import struct
from typing import Iterable, List, Optional, Tuple


PMA_MAGIC = b"PMA\x00"
ASCII_RUN_RE = re.compile(rb"[\x20-\x7E]{6,}")
JP_CHAR_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


@dataclass
class ChunkInfo:
    index: int
    start: int
    end: int
    size: int
    entropy: float
    sjis_pairs: int
    ascii_runs: int
    ascii_total: int
    likely_text: bool
    sample_ascii: str
    sample_sjis: str


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    n = len(data)
    ent = 0.0
    for c in freq:
        if c:
            p = c / n
            ent -= p * math.log2(p)
    return ent


def count_sjis_pairs(data: bytes) -> int:
    i = 0
    count = 0
    n = len(data)
    while i < n - 1:
        b1 = data[i]
        if (0x81 <= b1 <= 0x9F) or (0xE0 <= b1 <= 0xEF):
            b2 = data[i + 1]
            if (0x40 <= b2 <= 0x7E) or (0x80 <= b2 <= 0xFC):
                count += 1
                i += 2
                continue
        i += 1
    return count


def extract_ascii_runs(data: bytes) -> List[bytes]:
    return ASCII_RUN_RE.findall(data)


def decode_sjis_preview(data: bytes, max_chars: int = 80) -> str:
    text = data.decode("shift_jis", errors="ignore")
    if not text:
        return ""
    text = text.replace("\n", "\\n").replace("\r", "\\r")
    return text[:max_chars]


def parse_tail_offset_table(data: bytes, max_scan_dwords: int = 1200) -> Tuple[int, List[int]]:
    """Find best increasing offset run near EOF and return (table_offset, offsets)."""
    if len(data) < 8:
        raise ValueError("File too small for PMA parsing.")

    dword_count = len(data) // 4
    vals = struct.unpack(f"<{dword_count}I", data[: dword_count * 4])

    scan_start = max(0, dword_count - max_scan_dwords)
    best: Optional[Tuple[int, int, int]] = None  # (run_len, start_idx, end_idx)

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

    if best is None:
        raise ValueError("Could not find a plausible tail offset table.")

    run_len, start_idx, end_idx = best
    if run_len < 8:
        raise ValueError("Offset run found is too short to be reliable.")

    table = list(vals[start_idx : end_idx + 1])
    table_offset = start_idx * 4
    return table_offset, table


def build_chunks(data: bytes, table_offset: int, offsets: List[int]) -> List[Tuple[int, int, int]]:
    chunks: List[Tuple[int, int, int]] = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else table_offset
        if end > start:
            chunks.append((i, start, end))
    return chunks


def analyze_chunk(index: int, start: int, end: int, blob: bytes) -> ChunkInfo:
    ent = shannon_entropy(blob)
    sjis_pairs = count_sjis_pairs(blob)
    ascii_runs = extract_ascii_runs(blob)
    ascii_total = sum(len(r) for r in ascii_runs)
    sample_ascii = ascii_runs[0].decode("ascii", errors="ignore")[:80] if ascii_runs else ""
    sample_sjis = decode_sjis_preview(blob, 80)
    jp_count = len(JP_CHAR_RE.findall(sample_sjis))

    # Heuristic for "script-likely" chunks:
    # - moderate entropy (not raw textures/audio),
    # - has ASCII control-like fragments and/or many SJIS pairs.
    likely_text = (
        (6.2 <= ent <= 7.9 and sjis_pairs >= 40)
        or (ascii_total >= 24 and 5.0 <= ent <= 7.8)
        or (jp_count >= 6)
    )

    return ChunkInfo(
        index=index,
        start=start,
        end=end,
        size=end - start,
        entropy=ent,
        sjis_pairs=sjis_pairs,
        ascii_runs=len(ascii_runs),
        ascii_total=ascii_total,
        likely_text=likely_text,
        sample_ascii=sample_ascii,
        sample_sjis=sample_sjis,
    )


def write_csv(path: Path, rows: Iterable[ChunkInfo]) -> None:
    header = (
        "index,start_hex,end_hex,size,entropy,sjis_pairs,ascii_runs,ascii_total,"
        "likely_text,sample_ascii,sample_sjis\n"
    )
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(header)
        for r in rows:
            sample_ascii = r.sample_ascii.replace('"', "''")
            sample_sjis = r.sample_sjis.replace('"', "''")
            line = (
                f"{r.index},0x{r.start:X},0x{r.end:X},{r.size},{r.entropy:.4f},"
                f"{r.sjis_pairs},{r.ascii_runs},{r.ascii_total},{int(r.likely_text)},"
                f"\"{sample_ascii}\","
                f"\"{sample_sjis}\"\n"
            )
            f.write(line)


def probe_pma(pma_path: Path, out_dir: Path, export_chunks: bool) -> Tuple[List[ChunkInfo], int, List[int]]:
    data = pma_path.read_bytes()
    if not data.startswith(PMA_MAGIC):
        raise ValueError(f"{pma_path} is not a PMA file (missing PMA magic).")

    table_offset, offsets = parse_tail_offset_table(data)
    chunks = build_chunks(data, table_offset, offsets)
    infos: List[ChunkInfo] = []

    chunk_dir = out_dir / "chunks"
    if export_chunks:
        chunk_dir.mkdir(parents=True, exist_ok=True)

    for idx, start, end in chunks:
        blob = data[start:end]
        info = analyze_chunk(idx, start, end, blob)
        infos.append(info)
        if export_chunks:
            chunk_path = chunk_dir / f"chunk_{idx:04d}_{start:06X}_{end:06X}.bin"
            chunk_path.write_bytes(blob)

    return infos, table_offset, offsets


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe PMA files and rank likely script chunks.")
    parser.add_argument("pma", type=Path, help="Path to .pma file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("pma_probe_out"),
        help="Output directory (default: ./pma_probe_out)",
    )
    parser.add_argument(
        "--no-export-chunks",
        action="store_true",
        help="Do not export individual chunk binary files",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="How many top likely chunks to print (default: 20)",
    )
    args = parser.parse_args()

    pma_path = args.pma
    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    infos, table_offset, offsets = probe_pma(
        pma_path, out_dir, export_chunks=not args.no_export_chunks
    )

    csv_path = out_dir / "chunk_report.csv"
    write_csv(csv_path, infos)

    likely = [r for r in infos if r.likely_text]
    likely.sort(key=lambda r: (r.sjis_pairs, r.ascii_total, -r.entropy), reverse=True)

    print(f"[+] PMA: {pma_path}")
    print(f"[+] Tail table offset: 0x{table_offset:X}")
    print(f"[+] Offset entries: {len(offsets)}")
    print(f"[+] Chunk count: {len(infos)}")
    print(f"[+] Likely script/text chunks: {len(likely)}")
    print(f"[+] Report: {csv_path}")
    if not args.no_export_chunks:
        print(f"[+] Chunk files: {out_dir / 'chunks'}")

    print("\nTop likely chunks:")
    for r in likely[: args.top]:
        print(
            f"  - #{r.index:04d} off=0x{r.start:X}-0x{r.end:X} size={r.size:6d} "
            f"ent={r.entropy:.3f} sjis={r.sjis_pairs:4d} ascii={r.ascii_total:4d} "
            f"ascii_sample={r.sample_ascii!r}"
        )


if __name__ == "__main__":
    main()
