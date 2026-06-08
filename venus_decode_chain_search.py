#!/usr/bin/env python3
"""
Search short decode chains for Venus & Braves PMA segments.

Chain model (2-3 stages):
- optional XOR stage
- optional byte-substitution table stage
- optional second XOR stage

Scores decoded Shift-JIS readability and ranks best chains.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


PMA_MAGIC = b"PMA\x00"
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
PUNCT_RE = re.compile(r"[。、・「」『』！？ー]")


@dataclass
class ChainResult:
    chain_name: str
    total_score: float
    seg_hits: int
    best_seg_start: int
    best_preview: str


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


def is_permutation_256(block: bytes) -> bool:
    return len(block) == 256 and len(set(block)) == 256


def hunt_perm_tables(blob: bytes, label: str, stride: int = 16, max_tables: int = 10) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    n = len(blob)
    for off in range(0, max(0, n - 256), stride):
        b = blob[off : off + 256]
        if is_permutation_256(b):
            out[f"{label}@0x{off:X}"] = list(b)
            if len(out) >= max_tables:
                break
    return out


def apply_xor(data: bytes, key: int) -> bytes:
    return bytes(b ^ key for b in data)


def apply_map(data: bytes, mapping: Sequence[int]) -> bytes:
    return bytes(mapping[b] for b in data)


def score_decoded(text: str) -> float:
    if not text:
        return 0.0
    jp = len(JP_RE.findall(text))
    kana = len(KANA_RE.findall(text))
    punct = len(PUNCT_RE.findall(text))
    ratio = kana / max(1, jp)
    printable = sum(1 for c in text if c.isprintable()) / max(1, len(text))
    return jp * 1.0 + kana * 2.0 + punct * 2.2 + ratio * 45.0 + printable * 10.0


def build_chains(table_maps: Dict[str, List[int]]) -> List[Tuple[str, Callable[[bytes], bytes]]]:
    chains: List[Tuple[str, Callable[[bytes], bytes]]] = []

    xor_keys = [0x00, 0x20, 0x55, 0xAA, 0xFF]
    # 1-stage XOR baseline
    for k in xor_keys:
        chains.append((f"xor_{k:02X}", lambda d, k=k: apply_xor(d, k)))

    # 2-stage xor -> map and map -> xor
    for tname, tmap in table_maps.items():
        chains.append((f"map[{tname}]", lambda d, tmap=tmap: apply_map(d, tmap)))
        for k in xor_keys:
            chains.append(
                (f"xor_{k:02X} -> map[{tname}]", lambda d, k=k, tmap=tmap: apply_map(apply_xor(d, k), tmap))
            )
            chains.append(
                (f"map[{tname}] -> xor_{k:02X}", lambda d, k=k, tmap=tmap: apply_xor(apply_map(d, tmap), k))
            )

    # 3-stage xor -> map -> xor
    for tname, tmap in table_maps.items():
        for k1 in [0x55, 0xAA, 0xFF]:
            for k2 in [0x00, 0x20, 0x55]:
                chains.append(
                    (
                        f"xor_{k1:02X} -> map[{tname}] -> xor_{k2:02X}",
                        lambda d, k1=k1, k2=k2, tmap=tmap: apply_xor(apply_map(apply_xor(d, k1), tmap), k2),
                    )
                )
    return chains


def evaluate_chains(
    chains: List[Tuple[str, Callable[[bytes], bytes]]],
    segments: List[Tuple[int, int, bytes]],
    max_segments: int = 40,
) -> List[ChainResult]:
    results: List[ChainResult] = []
    for name, fn in chains:
        total = 0.0
        hits = 0
        best_score = -1.0
        best_seg = 0
        best_preview = ""
        for st, _, blob in segments[:max_segments]:
            out = fn(blob)
            txt = out.decode("shift_jis", errors="ignore")
            s = score_decoded(txt)
            if s > 40:
                hits += 1
                total += s
            if s > best_score:
                best_score = s
                best_seg = st
                best_preview = txt.replace("\n", "\\n").replace("\r", "\\r")[:150]
        if hits > 0:
            results.append(
                ChainResult(
                    chain_name=name,
                    total_score=total,
                    seg_hits=hits,
                    best_seg_start=best_seg,
                    best_preview=best_preview,
                )
            )
    results.sort(key=lambda r: (r.total_score, r.seg_hits), reverse=True)
    return results


def run_for_pma(pma_path: Path, slps_path: Path, out_dir: Path) -> None:
    pma = pma_path.read_bytes()
    if not pma.startswith(PMA_MAGIC):
        raise ValueError(f"Not PMA: {pma_path}")
    segs = pointer_segments_from_type2(pma)

    slps = slps_path.read_bytes()
    tables = {"identity": list(range(256))}
    tables.update(hunt_perm_tables(slps, "SLPS", stride=16, max_tables=12))

    chains = build_chains(tables)
    results = evaluate_chains(chains, segs, max_segments=50)

    lines = [
        f"PMA: {pma_path}",
        f"Segments: {len(segs)}",
        f"Tables: {len(tables)}",
        f"Chains tested: {len(chains)}",
        "",
        "Top chains:",
    ]
    for r in results[:80]:
        lines.append(
            f"- {r.chain_name} total={r.total_score:.2f} hits={r.seg_hits} "
            f"best_seg=0x{r.best_seg_start:X} preview={r.best_preview!r}"
        )
    (out_dir / "chain_results.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search decode chains for Venus PMA data.")
    parser.add_argument("--slps", type=Path, default=Path("/Users/acr/venus-braves/extracted_iso/SLPS_251.96"))
    parser.add_argument("--pma", type=Path, action="append", required=True, help="PMA file(s) to analyze")
    parser.add_argument("-o", "--output", type=Path, default=Path("venus_decode_chain_out"))
    args = parser.parse_args()

    root = args.output
    root.mkdir(parents=True, exist_ok=True)

    for p in args.pma:
        name = p.stem.replace(".", "_")
        out = root / name
        out.mkdir(parents=True, exist_ok=True)
        run_for_pma(p, args.slps, out)
        print(f"[+] Wrote: {out / 'chain_results.txt'}")


if __name__ == "__main__":
    main()
