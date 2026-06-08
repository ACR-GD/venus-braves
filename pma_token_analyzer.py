#!/usr/bin/env python3
"""
Token-level analyzer for PMA pointer-derived segments.

This tool inspects binary segments (reconstructed from internal pointers)
as token streams to identify:
- frequent control-like bytes,
- repeated n-gram motifs,
- candidate text windows (higher printable / kana density),
- likely delimiter bytes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, List, Tuple


JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")


@dataclass
class Segment:
    start: int
    end: int
    size: int
    blob: bytes


@dataclass
class WindowHit:
    seg_start: int
    win_start: int
    win_end: int
    kana: int
    jp: int
    score: float
    preview: str


def parse_hex(s: str) -> int:
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s)


def load_segments_from_csv(path: Path, pma_bytes: bytes) -> List[Segment]:
    segs: List[Segment] = []
    # Some upstream previews may contain NUL characters; strip them first.
    raw = path.read_bytes().replace(b"\x00", b"")
    text = raw.decode("utf-8", errors="replace")
    from io import StringIO

    with StringIO(text) as f:
        r = csv.DictReader(f)
        for row in r:
            st = parse_hex(row["start_hex"])
            ed = parse_hex(row["end_hex"])
            if 0 <= st < ed <= len(pma_bytes):
                segs.append(Segment(start=st, end=ed, size=ed - st, blob=pma_bytes[st:ed]))
    return segs


def top_bytes(segs: Iterable[Segment], top_n: int = 32) -> List[Tuple[int, int]]:
    c = Counter()
    for s in segs:
        c.update(s.blob)
    return c.most_common(top_n)


def top_bigrams(segs: Iterable[Segment], top_n: int = 40) -> List[Tuple[Tuple[int, int], int]]:
    c = Counter()
    for s in segs:
        b = s.blob
        for i in range(len(b) - 1):
            c[(b[i], b[i + 1])] += 1
    return c.most_common(top_n)


def top_trigrams(segs: Iterable[Segment], top_n: int = 30) -> List[Tuple[Tuple[int, int, int], int]]:
    c = Counter()
    for s in segs:
        b = s.blob
        for i in range(len(b) - 2):
            c[(b[i], b[i + 1], b[i + 2])] += 1
    return c.most_common(top_n)


def decode_sjis(data: bytes) -> str:
    return data.decode("shift_jis", errors="ignore")


def scan_text_windows(
    segs: Iterable[Segment], win_size: int = 192, step: int = 32, min_score: float = 30.0
) -> List[WindowHit]:
    hits: List[WindowHit] = []
    for seg in segs:
        b = seg.blob
        if len(b) < win_size:
            continue
        for i in range(0, len(b) - win_size + 1, step):
            w = b[i : i + win_size]
            t = decode_sjis(w)
            if not t:
                continue
            jp = len(JP_RE.findall(t))
            kana = len(KANA_RE.findall(t))
            ratio = kana / max(1, jp)
            score = jp * 1.0 + kana * 1.8 + ratio * 20.0
            if score < min_score:
                continue
            hits.append(
                WindowHit(
                    seg_start=seg.start,
                    win_start=seg.start + i,
                    win_end=seg.start + i + win_size,
                    kana=kana,
                    jp=jp,
                    score=score,
                    preview=t.replace("\n", "\\n").replace("\r", "\\r")[:150],
                )
            )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def delimiter_candidates(segs: Iterable[Segment], top_n: int = 16) -> List[Tuple[int, int]]:
    """
    Find bytes that frequently appear in short repeating patterns:
    xx 00 xx or xx FF xx etc. Very rough heuristic for control delimiters.
    """
    c = Counter()
    for seg in segs:
        b = seg.blob
        for i in range(1, len(b) - 1):
            mid = b[i]
            if mid in (0x00, 0xFF, 0xFE, 0xFD, 0x1B, 0x1C, 0x1D, 0x7F):
                c[mid] += 1
    return c.most_common(top_n)


def write_summary(
    out: Path,
    byte_top: List[Tuple[int, int]],
    bigram_top: List[Tuple[Tuple[int, int], int]],
    trigram_top: List[Tuple[Tuple[int, int, int], int]],
    delims: List[Tuple[int, int]],
) -> None:
    lines: List[str] = []
    lines.append("## Top bytes")
    for b, n in byte_top:
        lines.append(f"- 0x{b:02X}: {n}")
    lines.append("")
    lines.append("## Top bigrams")
    for (a, b), n in bigram_top:
        lines.append(f"- {a:02X} {b:02X}: {n}")
    lines.append("")
    lines.append("## Top trigrams")
    for (a, b, c), n in trigram_top:
        lines.append(f"- {a:02X} {b:02X} {c:02X}: {n}")
    lines.append("")
    lines.append("## Delimiter-like bytes")
    for b, n in delims:
        lines.append(f"- 0x{b:02X}: {n}")
    out.write_text("\n".join(lines), encoding="utf-8")


def write_windows_csv(path: Path, hits: List[WindowHit]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seg_start_hex", "win_start_hex", "win_end_hex", "jp", "kana", "score", "preview"])
        for h in hits:
            w.writerow(
                [
                    f"0x{h.seg_start:X}",
                    f"0x{h.win_start:X}",
                    f"0x{h.win_end:X}",
                    h.jp,
                    h.kana,
                    f"{h.score:.2f}",
                    h.preview,
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze PMA pointer segments as token streams.")
    parser.add_argument("pma", type=Path, help="Path to PMA file")
    parser.add_argument("segments_csv", type=Path, help="segments.csv produced by pma_pointer_segments.py")
    parser.add_argument("-o", "--output", type=Path, default=Path("pma_token_analyzer_out"))
    parser.add_argument("--win-size", type=int, default=192)
    parser.add_argument("--step", type=int, default=32)
    parser.add_argument("--min-score", type=float, default=32.0)
    parser.add_argument("--top-windows", type=int, default=120)
    args = parser.parse_args()

    pma_bytes = args.pma.read_bytes()
    segs = load_segments_from_csv(args.segments_csv, pma_bytes)
    if not segs:
        raise SystemExit("No valid segments loaded from CSV.")

    out = args.output
    out.mkdir(parents=True, exist_ok=True)

    btop = top_bytes(segs)
    g2 = top_bigrams(segs)
    g3 = top_trigrams(segs)
    delims = delimiter_candidates(segs)
    wins = scan_text_windows(segs, args.win_size, args.step, args.min_score)[: args.top_windows]

    write_summary(out / "token_summary.md", btop, g2, g3, delims)
    write_windows_csv(out / "window_hits.csv", wins)

    print(f"[+] Segments loaded: {len(segs)}")
    print(f"[+] Wrote: {out / 'token_summary.md'}")
    print(f"[+] Wrote: {out / 'window_hits.csv'}")
    print("[+] Top windows:")
    for h in wins[:20]:
        print(
            f"  - {h.win_start:#x}-{h.win_end:#x} score={h.score:.2f} jp={h.jp} kana={h.kana} :: {h.preview!r}"
        )


if __name__ == "__main__":
    main()
