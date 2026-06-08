#!/usr/bin/env python3
"""
Record-level PMA decoder attempt.

Builds on PMA structural findings:
- PMA files contain chunk records indexed by a tail offset table.
- Most records start with patterns like:
  - 02 00 00 00 FF FF 00 00
  - 03 00 00 00 FF FF 00 00
  - 01 00 00 00 01 00 00 00

This tool:
- parses PMA chunk records,
- attempts payload decoding from plausible record-relative offsets,
- exports candidate text lines to TSV/CSV for manual verification.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Iterable, List, Optional, Tuple
import zlib


PMA_MAGIC = b"PMA\x00"
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
PUNCT_RE = re.compile(r"[。、・「」『』！？ー]")


@dataclass
class CandidateLine:
    file: str
    chunk_index: int
    rec_type: int
    chunk_start: int
    chunk_end: int
    method: str
    payload_offset: int
    payload_size: int
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


def record_type(blob: bytes) -> int:
    if len(blob) < 4:
        return -1
    return struct.unpack_from("<I", blob, 0)[0]


def decode_text(data: bytes) -> str:
    return data.decode("shift_jis", errors="ignore")


def text_score(text: str) -> Tuple[int, int, float]:
    if not text:
        return 0, 0, 0.0
    jp = len(JP_RE.findall(text))
    kana = len(KANA_RE.findall(text))
    punct = len(PUNCT_RE.findall(text))
    # prefer kana-rich output to avoid kanji-like noise
    ratio = kana / max(1, jp)
    score = jp * 1.2 + kana * 1.8 + punct * 2.0 + ratio * 40.0 + min(len(text), 400) / 60.0
    return jp, kana, score


def clean_preview(text: str, max_len: int = 160) -> str:
    return text.replace("\n", "\\n").replace("\r", "\\r")[:max_len]


def try_decode_payload(payload: bytes) -> Iterable[Tuple[str, bytes]]:
    # direct attempts
    yield "raw", payload

    # try zlib/deflate wrappers directly
    for wbits, name in [(15, "zlib"), (-15, "deflate"), (31, "gzip")]:
        try:
            out = zlib.decompress(payload, wbits)
        except Exception:
            out = b""
        if out:
            yield name, out

    # offset-based for framed data
    for skip in range(1, 9):
        if len(payload) <= skip + 8:
            break
        sub = payload[skip:]
        for wbits, name in [(15, "zlib_skip"), (-15, "deflate_skip")]:
            try:
                out = zlib.decompress(sub, wbits)
            except Exception:
                out = b""
            if out:
                yield f"{name}_{skip}", out

    # simple XOR probes used often in legacy game formats
    for key in [0x20, 0x55, 0xAA, 0xFF]:
        x = bytes(b ^ key for b in payload)
        yield f"xor_{key:02X}", x
        try:
            out = zlib.decompress(x, 15)
        except Exception:
            out = b""
        if out:
            yield f"xor_{key:02X}_zlib", out


def payload_offsets_for_type(rec_t: int) -> List[int]:
    # empiric candidates from observed record families
    if rec_t == 2:
        return [0x10, 0x14, 0x18, 0x1C, 0x20]
    if rec_t == 3:
        return [0x10, 0x14, 0x18, 0x1C, 0x20, 0x24]
    if rec_t == 1:
        return [0x10, 0x14, 0x18, 0x1C]
    # fallback generic offsets
    return [0x10, 0x14, 0x18, 0x1C, 0x20]


def analyze_pma_records(
    pma_path: Path, min_jp: int, min_kana: int, min_score: float
) -> List[CandidateLine]:
    data = pma_path.read_bytes()
    if not data.startswith(PMA_MAGIC):
        raise ValueError(f"Not a PMA file: {pma_path}")

    table_offset, offsets = parse_tail_offset_table(data)
    ranges = chunk_ranges(table_offset, offsets)
    results: List[CandidateLine] = []

    for idx, start, end in ranges:
        blob = data[start:end]
        rec_t = record_type(blob)
        if rec_t not in (1, 2, 3):
            continue

        per_chunk_best: List[CandidateLine] = []
        seen_preview = set()
        for off in payload_offsets_for_type(rec_t):
            if off >= len(blob):
                continue
            payload = blob[off:]
            if len(payload) < 8:
                continue

            for method, out in try_decode_payload(payload):
                text = decode_text(out)
                jp, kana, score = text_score(text)
                if jp < min_jp or kana < min_kana or score < min_score:
                    continue
                preview = clean_preview(text)
                if preview in seen_preview:
                    continue
                seen_preview.add(preview)

                per_chunk_best.append(
                    CandidateLine(
                        file=str(pma_path),
                        chunk_index=idx,
                        rec_type=rec_t,
                        chunk_start=start,
                        chunk_end=end,
                        method=method,
                        payload_offset=off,
                        payload_size=len(payload),
                        jp_chars=jp,
                        kana_chars=kana,
                        score=score,
                        preview=preview,
                    )
                )
        if per_chunk_best:
            per_chunk_best.sort(key=lambda r: r.score, reverse=True)
            results.extend(per_chunk_best[:2])

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def write_tsv(path: Path, rows: List[CandidateLine]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "file",
                "chunk_index",
                "rec_type",
                "chunk_start_hex",
                "chunk_end_hex",
                "method",
                "payload_offset_hex",
                "payload_size",
                "jp_chars",
                "kana_chars",
                "score",
                "preview",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.file,
                    r.chunk_index,
                    r.rec_type,
                    f"0x{r.chunk_start:X}",
                    f"0x{r.chunk_end:X}",
                    r.method,
                    f"0x{r.payload_offset:X}",
                    r.payload_size,
                    r.jp_chars,
                    r.kana_chars,
                    f"{r.score:.2f}",
                    r.preview,
                ]
            )


def gather_inputs(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.pma"))
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record-level decode attempts for PMA script candidates."
    )
    parser.add_argument("input", type=Path, help="PMA file or directory")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("pma_record_decode_out"),
        help="Output directory (default: ./pma_record_decode_out)",
    )
    parser.add_argument(
        "--glob",
        type=str,
        default="",
        help="Optional substring filter (example: 'ev_')",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max files (0=all)")
    parser.add_argument("--min-jp", type=int, default=12)
    parser.add_argument("--min-kana", type=int, default=6)
    parser.add_argument("--min-score", type=float, default=55.0)
    parser.add_argument("--top", type=int, default=60)
    args = parser.parse_args()

    files = gather_inputs(args.input)
    if args.glob:
        files = [p for p in files if args.glob in str(p)]
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        raise SystemExit("No PMA files found.")

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[CandidateLine] = []
    print(f"[+] Files to decode: {len(files)}")
    for p in files:
        try:
            rows = analyze_pma_records(p, args.min_jp, args.min_kana, args.min_score)
        except Exception as e:
            print(f"[!] Skip {p}: {e}")
            continue
        all_rows.extend(rows)
        print(f"  - {p.name}: {len(rows)} candidates")

    all_rows.sort(key=lambda r: r.score, reverse=True)
    tsv_path = out_dir / "record_candidates.tsv"
    write_tsv(tsv_path, all_rows)

    print(f"[+] Total candidates: {len(all_rows)}")
    print(f"[+] TSV: {tsv_path}")
    print("\nTop candidates:")
    for r in all_rows[: args.top]:
        print(
            f"  - {Path(r.file).name} chunk#{r.chunk_index} t={r.rec_type} "
            f"off=0x{r.payload_offset:X} m={r.method} score={r.score:.2f} "
            f"jp={r.jp_chars} kana={r.kana_chars} :: {r.preview!r}"
        )


if __name__ == "__main__":
    main()
