#!/usr/bin/env python3
"""
Table hunt for custom text decoding in Venus & Braves.

Strategy:
- Search binaries for likely lookup-table blocks (256/512-byte patterns).
- Build candidate single-byte substitution maps.
- Apply maps to PMA pointer-derived segments and score readability.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Dict, List, Optional, Tuple


PMA_MAGIC = b"PMA\x00"
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")


@dataclass
class MappingCandidate:
    source_file: str
    offset: int
    kind: str
    mapping: List[int]  # 256-byte substitution table


@dataclass
class DecodeHit:
    mapping_name: str
    seg_start: int
    score: float
    jp: int
    kana: int
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
        raise ValueError("No PMA tail table found.")
    _, s, e = best
    return s * 4, list(vals[s : e + 1])


def u32_at(blob: bytes, off: int) -> int:
    if off + 4 > len(blob):
        return 0
    return struct.unpack_from("<I", blob, off)[0]


def collect_type2_pointer_segments(pma_bytes: bytes) -> List[Tuple[int, int, bytes]]:
    table_offset, offsets = parse_tail_offset_table(pma_bytes)
    ptrs: List[int] = []
    for i, st in enumerate(offsets):
        ed = offsets[i + 1] if i + 1 < len(offsets) else table_offset
        if ed <= st:
            continue
        blob = pma_bytes[st:ed]
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
            segs.append((st, ed, pma_bytes[st:ed]))
    return segs


def is_permutation_256(block: bytes) -> bool:
    return len(block) == 256 and len(set(block)) == 256


def hunt_mappings_from_blob(blob: bytes, file_label: str, stride: int = 16, max_candidates: int = 80) -> List[MappingCandidate]:
    out: List[MappingCandidate] = []
    n = len(blob)
    for off in range(0, max(0, n - 256), stride):
        b = blob[off : off + 256]
        if is_permutation_256(b):
            out.append(
                MappingCandidate(
                    source_file=file_label,
                    offset=off,
                    kind="perm256",
                    mapping=list(b),
                )
            )
            if len(out) >= max_candidates:
                break

    # Also try 512-byte table as pairs (in->out)
    if len(out) < max_candidates:
        for off in range(0, max(0, n - 512), stride):
            b = blob[off : off + 512]
            left = b[0::2]
            right = b[1::2]
            if len(left) == 256 and len(set(left)) == 256:
                m = [0] * 256
                for i, src in enumerate(left):
                    m[src] = right[i]
                out.append(
                    MappingCandidate(
                        source_file=file_label,
                        offset=off,
                        kind="pairs512",
                        mapping=m,
                    )
                )
                if len(out) >= max_candidates:
                    break
    return out


def build_baseline_mappings() -> List[MappingCandidate]:
    return [
        MappingCandidate("builtin", 0, "identity", list(range(256))),
        MappingCandidate("builtin", 0, "xor55", [i ^ 0x55 for i in range(256)]),
        MappingCandidate("builtin", 0, "xoraa", [i ^ 0xAA for i in range(256)]),
        MappingCandidate("builtin", 0, "xorff", [i ^ 0xFF for i in range(256)]),
    ]


def apply_mapping(data: bytes, mapping: List[int]) -> bytes:
    return bytes(mapping[b] for b in data)


def score_text(decoded: str) -> Tuple[int, int, float]:
    jp = len(JP_RE.findall(decoded))
    kana = len(KANA_RE.findall(decoded))
    ratio = kana / max(1, jp)
    score = jp * 1.2 + kana * 2.0 + ratio * 40.0 + min(len(decoded), 300) / 100.0
    return jp, kana, score


def evaluate_mapping(name: str, mapping: List[int], segments: List[Tuple[int, int, bytes]], top_seg_n: int = 20) -> List[DecodeHit]:
    hits: List[DecodeHit] = []
    for st, ed, blob in segments[:top_seg_n]:
        mapped = apply_mapping(blob, mapping)
        txt = mapped.decode("shift_jis", errors="ignore")
        jp, kana, score = score_text(txt)
        if score < 40 or kana < 4:
            continue
        preview = txt.replace("\n", "\\n").replace("\r", "\\r")[:150]
        hits.append(
            DecodeHit(
                mapping_name=name,
                seg_start=st,
                score=score,
                jp=jp,
                kana=kana,
                preview=preview,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description="Hunt and test substitution tables for PMA decoding.")
    parser.add_argument("--slps", type=Path, default=Path("/Users/acr/venus-braves/extracted_iso/SLPS_251.96"))
    parser.add_argument("--cdimage", type=Path, default=Path("/Users/acr/venus-braves/extracted_iso/IMAGE/CDIMAGE.BIN"))
    parser.add_argument("--pma", type=Path, required=True, help="Event PMA file to test mappings on")
    parser.add_argument("-o", "--output", type=Path, default=Path("venus_table_hunt_out"))
    parser.add_argument("--max-maps", type=int, default=120)
    args = parser.parse_args()

    out = args.output
    out.mkdir(parents=True, exist_ok=True)

    pma_bytes = args.pma.read_bytes()
    if not pma_bytes.startswith(PMA_MAGIC):
        raise SystemExit("Input PMA invalid.")
    segments = collect_type2_pointer_segments(pma_bytes)

    mappings = build_baseline_mappings()
    slps_maps = hunt_mappings_from_blob(args.slps.read_bytes(), "SLPS_251.96", stride=16, max_candidates=args.max_maps // 2)
    mappings.extend(slps_maps)
    # sample first ~8MB of CDIMAGE for speed
    cd_blob = args.cdimage.read_bytes()[: 8 * 1024 * 1024]
    cd_maps = hunt_mappings_from_blob(cd_blob, "CDIMAGE.BIN[:8MB]", stride=32, max_candidates=args.max_maps // 2)
    mappings.extend(cd_maps)

    summary_lines = [
        f"PMA: {args.pma}",
        f"Pointer-derived segments: {len(segments)}",
        f"Mappings tested: {len(mappings)}",
        "",
    ]

    global_hits: List[DecodeHit] = []
    for i, m in enumerate(mappings):
        name = f"{m.kind}:{m.source_file}:0x{m.offset:X}"
        hits = evaluate_mapping(name, m.mapping, segments, top_seg_n=30)
        if hits:
            global_hits.extend(hits[:4])
            summary_lines.append(f"[{i:03d}] {name} -> {len(hits)} hits (best {hits[0].score:.2f})")

    global_hits.sort(key=lambda h: h.score, reverse=True)
    summary_lines.append("")
    summary_lines.append("Top decode hits:")
    for h in global_hits[:80]:
        summary_lines.append(
            f"- {h.mapping_name} seg=0x{h.seg_start:X} score={h.score:.2f} jp={h.jp} kana={h.kana} :: {h.preview!r}"
        )

    (out / "summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"[+] Wrote: {out / 'summary.txt'}")
    print(f"[+] Segments: {len(segments)} | mappings: {len(mappings)} | hits: {len(global_hits)}")
    for h in global_hits[:20]:
        print(f"  - {h.mapping_name} seg=0x{h.seg_start:X} score={h.score:.2f} jp={h.jp} kana={h.kana}")


if __name__ == "__main__":
    main()
