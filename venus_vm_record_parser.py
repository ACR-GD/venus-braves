#!/usr/bin/env python3
"""
Heuristic VM record parser for Venus & Braves PMA event data.

Goal:
- Apply a selected decode chain (xor/map/xor) on pointer-derived segments.
- Split decoded bytes into candidate text runs by control-byte boundaries.
- Score and export likely string candidates for manual review / ENG translation.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Iterable, List, Optional, Sequence, Tuple


PMA_MAGIC = b"PMA\x00"
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
PUNCT_RE = re.compile(r"[。、・「」『』！？ー…]")


@dataclass
class Candidate:
    seg_start: int
    seg_end: int
    run_offset: int
    run_size: int
    jp: int
    kana: int
    punct: int
    score: float
    text: str


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
        raise ValueError("No PMA tail table.")
    _, s, e = best
    return s * 4, list(vals[s : e + 1])


def u32_at(blob: bytes, off: int) -> int:
    if off + 4 > len(blob):
        return 0
    return struct.unpack_from("<I", blob, off)[0]


def pointer_segments_from_type2(pma: bytes) -> List[Tuple[int, int, bytes]]:
    table_offset, offsets = parse_tail_offset_table(pma)
    ptrs: List[int] = []
    for i, st in enumerate(offsets):
        ed = offsets[i + 1] if i + 1 < len(offsets) else table_offset
        if ed <= st:
            continue
        blob = pma[st:ed]
        if len(blob) < 12:
            continue
        if u32_at(blob, 0) != 2:
            continue
        p = u32_at(blob, 8)
        if 0 <= p < table_offset:
            ptrs.append(p)
    ptrs = sorted(set(ptrs))
    segs: List[Tuple[int, int, bytes]] = []
    for i, st in enumerate(ptrs):
        ed = ptrs[i + 1] if i + 1 < len(ptrs) else table_offset
        if ed > st:
            segs.append((st, ed, pma[st:ed]))
    return segs


def hunt_perm256(blob: bytes, wanted_offset: int) -> Optional[List[int]]:
    if 0 <= wanted_offset <= len(blob) - 256:
        b = blob[wanted_offset : wanted_offset + 256]
        if len(set(b)) == 256:
            return list(b)
    return None


def apply_xor(data: bytes, key: int) -> bytes:
    return bytes(b ^ key for b in data)


def apply_map(data: bytes, mapping: Sequence[int]) -> bytes:
    return bytes(mapping[b] for b in data)


def decode_chain(data: bytes, map256: Sequence[int], xor1: int, xor2: int) -> bytes:
    stage = apply_xor(data, xor1)
    stage = apply_map(stage, map256)
    stage = apply_xor(stage, xor2)
    return stage


def control_like_byte(b: int) -> bool:
    return (
        b < 0x20
        or b in (0x7F, 0x80, 0x81, 0x82, 0xFD, 0xFE, 0xFF)
    )


def split_runs(data: bytes, min_run: int = 10) -> List[Tuple[int, bytes]]:
    runs: List[Tuple[int, bytes]] = []
    i = 0
    n = len(data)
    while i < n:
        while i < n and control_like_byte(data[i]):
            i += 1
        st = i
        while i < n and not control_like_byte(data[i]):
            i += 1
        if i - st >= min_run:
            runs.append((st, data[st:i]))
    return runs


def score_text(txt: str) -> Tuple[int, int, int, float]:
    jp = len(JP_RE.findall(txt))
    kana = len(KANA_RE.findall(txt))
    punct = len(PUNCT_RE.findall(txt))
    ratio = kana / max(1, jp)
    printable = sum(1 for c in txt if c.isprintable()) / max(1, len(txt))
    score = jp * 0.9 + kana * 2.4 + punct * 2.6 + ratio * 60.0 + printable * 6.0
    return jp, kana, punct, score


def extract_candidates(
    segments: Iterable[Tuple[int, int, bytes]],
    map256: Sequence[int],
    xor1: int,
    xor2: int,
    min_score: float,
    max_segments: int,
) -> List[Candidate]:
    out: List[Candidate] = []
    for seg_idx, (st, ed, blob) in enumerate(list(segments)[:max_segments]):
        dec = decode_chain(blob, map256, xor1, xor2)
        for run_off, run in split_runs(dec, min_run=6):
            txt = run.decode("shift_jis", errors="ignore")
            if len(txt) < 3:
                continue
            jp, kana, punct, score = score_text(txt)
            if score < min_score:
                continue
            out.append(
                Candidate(
                    seg_start=st,
                    seg_end=ed,
                    run_offset=run_off,
                    run_size=len(run),
                    jp=jp,
                    kana=kana,
                    punct=punct,
                    score=score,
                    text=txt.replace("\n", "\\n").replace("\r", "\\r"),
                )
            )
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def write_tsv(path: Path, rows: List[Candidate]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "seg_start_hex",
                "seg_end_hex",
                "run_offset_hex",
                "run_size",
                "jp",
                "kana",
                "punct",
                "score",
                "text",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    f"0x{r.seg_start:X}",
                    f"0x{r.seg_end:X}",
                    f"0x{r.run_offset:X}",
                    r.run_size,
                    r.jp,
                    r.kana,
                    r.punct,
                    f"{r.score:.2f}",
                    r.text[:500],
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Heuristic VM record parser with decode chain.")
    parser.add_argument("--pma", type=Path, required=True, help="Event PMA file")
    parser.add_argument("--slps", type=Path, default=Path("/Users/acr/venus-braves/extracted_iso/SLPS_251.96"))
    parser.add_argument("--table-offset", type=lambda x: int(x, 16), default=0x45FC90)
    parser.add_argument("--xor1", type=lambda x: int(x, 16), default=0xFF)
    parser.add_argument("--xor2", type=lambda x: int(x, 16), default=0x20)
    parser.add_argument("--min-score", type=float, default=18.0)
    parser.add_argument("--max-segments", type=int, default=90)
    parser.add_argument("-o", "--output", type=Path, default=Path("venus_vm_record_parser_out"))
    args = parser.parse_args()

    pma = args.pma.read_bytes()
    if not pma.startswith(PMA_MAGIC):
        raise SystemExit("Not a PMA file.")
    slps = args.slps.read_bytes()
    mapping = hunt_perm256(slps, args.table_offset)
    if mapping is None:
        raise SystemExit(f"Could not build perm256 table at 0x{args.table_offset:X}")

    segs = pointer_segments_from_type2(pma)
    rows = extract_candidates(
        segs,
        mapping,
        xor1=args.xor1,
        xor2=args.xor2,
        min_score=args.min_score,
        max_segments=args.max_segments,
    )

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    write_tsv(out / "string_candidates.tsv", rows)

    summary = [
        f"PMA: {args.pma}",
        f"Segments (type2 pointers): {len(segs)}",
        f"Table offset: 0x{args.table_offset:X}",
        f"Chain: xor_{args.xor1:02X} -> table -> xor_{args.xor2:02X}",
        f"Candidates: {len(rows)}",
        "",
        "Top candidates:",
    ]
    for r in rows[:80]:
        summary.append(
            f"- seg=0x{r.seg_start:X} run=0x{r.run_offset:X} size={r.run_size} "
            f"score={r.score:.2f} jp={r.jp} kana={r.kana} punct={r.punct} :: {r.text[:150]!r}"
        )
    (out / "summary.txt").write_text("\n".join(summary), encoding="utf-8")

    print(f"[+] Wrote: {out / 'string_candidates.tsv'}")
    print(f"[+] Wrote: {out / 'summary.txt'}")
    print(f"[+] candidates: {len(rows)}")
    for r in rows[:20]:
        print(
            f"  - seg 0x{r.seg_start:X} run 0x{r.run_offset:X} score {r.score:.2f} "
            f"jp={r.jp} kana={r.kana} :: {r.text[:120]!r}"
        )


if __name__ == "__main__":
    main()
