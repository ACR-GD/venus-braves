#!/usr/bin/env python3
"""
PMA VM hypothesis analyzer.

Purpose:
- Treat PMA pointer-derived segments as instruction streams.
- Estimate opcode candidates and variable-length instruction boundaries.
- Extract immediate arguments that look like string/resource IDs.
- Correlate these IDs with values found in other game assets (MDT/DAT/BIN).
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import struct
from typing import Dict, Iterable, List, Optional, Set, Tuple


PMA_MAGIC = b"PMA\x00"
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


@dataclass
class Segment:
    start: int
    end: int
    blob: bytes


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
        raise ValueError("No plausible PMA tail table.")
    _, s, e = best
    return s * 4, list(vals[s : e + 1])


def chunk_ranges(table_offset: int, offsets: List[int]) -> List[Tuple[int, int]]:
    out = []
    for i, st in enumerate(offsets):
        ed = offsets[i + 1] if i + 1 < len(offsets) else table_offset
        if ed > st:
            out.append((st, ed))
    return out


def u32_at(blob: bytes, off: int) -> int:
    if off + 4 > len(blob):
        return 0
    return struct.unpack_from("<I", blob, off)[0]


def collect_type2_pointers(data: bytes) -> List[int]:
    table_offset, offsets = parse_tail_offset_table(data)
    ptrs = []
    for st, ed in chunk_ranges(table_offset, offsets):
        blob = data[st:ed]
        if len(blob) < 12:
            continue
        if u32_at(blob, 0) != 2:
            continue
        p = u32_at(blob, 8)
        if 0 <= p < table_offset:
            ptrs.append(p)
    return sorted(set(ptrs))


def build_segments(data: bytes, pointers: List[int], stop: int) -> List[Segment]:
    segs: List[Segment] = []
    for i, st in enumerate(pointers):
        ed = pointers[i + 1] if i + 1 < len(pointers) else stop
        if ed > st:
            segs.append(Segment(start=st, end=ed, blob=data[st:ed]))
    return segs


def likely_text_score(b: bytes) -> float:
    text = b.decode("shift_jis", errors="ignore")
    jp = len(JP_RE.findall(text))
    return jp / max(1, len(b))


def mine_opcode_candidates(segs: Iterable[Segment]) -> Tuple[Counter, Dict[int, Counter]]:
    """
    Heuristic VM assumption:
    - low-byte values with high recurrence at many positions may be opcodes
    - next byte may encode operand-length/type class
    """
    op_counter: Counter = Counter()
    follower: Dict[int, Counter] = defaultdict(Counter)

    for s in segs:
        b = s.blob
        # skip highly text-like segments to focus on control streams
        if likely_text_score(b) > 0.12:
            continue
        for i in range(0, len(b) - 1):
            op = b[i]
            nx = b[i + 1]
            op_counter[op] += 1
            follower[op][nx] += 1
    return op_counter, follower


def extract_immediates(segs: Iterable[Segment], interesting_ops: Set[int]) -> Dict[int, Counter]:
    """
    For each interesting opcode, collect immediate u16/u32 values at +1/+2.
    """
    vals: Dict[int, Counter] = {op: Counter() for op in interesting_ops}
    for s in segs:
        b = s.blob
        for i in range(len(b) - 5):
            op = b[i]
            if op not in interesting_ops:
                continue
            v16 = struct.unpack_from("<H", b, i + 1)[0]
            v32 = struct.unpack_from("<I", b, i + 1)[0]
            if 0 < v16 < 0xF000:
                vals[op][v16] += 1
            if 0 < v32 < 0x200000:
                vals[op][v32] += 1
    return vals


def scan_resource_ids(resource_root: Path, exts: Tuple[str, ...], limit_files: int = 400) -> Counter:
    """
    Build frequency map of u16 values observed across resource files.
    """
    files: List[Path] = []
    for ext in exts:
        files.extend(resource_root.rglob(f"*{ext}"))
    files = sorted(files)[:limit_files]

    c = Counter()
    for p in files:
        try:
            b = p.read_bytes()
        except Exception:
            continue
        n = len(b)
        for i in range(0, n - 1, 2):
            v = struct.unpack_from("<H", b, i)[0]
            if 0 < v < 0xF000:
                c[v] += 1
    return c


def correlate_ids(op_vals: Dict[int, Counter], resource_vals: Counter) -> List[Tuple[int, int, int, int]]:
    """
    Return tuples: (opcode, value, op_count, resource_count)
    """
    out = []
    for op, vc in op_vals.items():
        for v, n in vc.items():
            r = resource_vals.get(v, 0)
            if n >= 3 and r >= 3:
                out.append((op, v, n, r))
    out.sort(key=lambda x: (x[2] * x[3]), reverse=True)
    return out


def write_opcode_csv(path: Path, op_counter: Counter, follower: Dict[int, Counter], top_n: int = 128) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["opcode_hex", "count", "top_followers"])
        for op, n in op_counter.most_common(top_n):
            flw = " ".join(f"{b:02X}:{c}" for b, c in follower[op].most_common(8))
            w.writerow([f"0x{op:02X}", n, flw])


def write_corr_csv(path: Path, rows: List[Tuple[int, int, int, int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["opcode_hex", "value_hex", "in_opcode_stream", "in_resources", "product_score"])
        for op, v, a, b in rows:
            w.writerow([f"0x{op:02X}", f"0x{v:04X}", a, b, a * b])


def main() -> None:
    parser = argparse.ArgumentParser(description="PMA VM/opcode hypothesis analyzer.")
    parser.add_argument("pma", type=Path, help="Target PMA file")
    parser.add_argument(
        "--resource-root",
        type=Path,
        default=Path("/Users/acr/venus-braves/cdimage_unpacked/seven_data_link"),
        help="Root folder for resource correlation scan",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("pma_vm_hypothesis_out"), help="Output directory"
    )
    parser.add_argument("--top-opcodes", type=int, default=24)
    parser.add_argument("--resource-file-limit", type=int, default=500)
    args = parser.parse_args()

    data = args.pma.read_bytes()
    if not data.startswith(PMA_MAGIC):
        raise SystemExit("Input is not PMA.")

    table_offset, _ = parse_tail_offset_table(data)
    pointers = collect_type2_pointers(data)
    segs = build_segments(data, pointers, table_offset)
    op_counter, follower = mine_opcode_candidates(segs)

    interesting_ops = {op for op, _ in op_counter.most_common(args.top_opcodes)}
    op_vals = extract_immediates(segs, interesting_ops)

    resource_vals = scan_resource_ids(
        args.resource_root, exts=(".mdt", ".dat", ".bin", ".pma"), limit_files=args.resource_file_limit
    )
    corr = correlate_ids(op_vals, resource_vals)

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    write_opcode_csv(out / "opcode_profile.csv", op_counter, follower)
    write_corr_csv(out / "id_correlation.csv", corr)

    # quick text summary
    summary = [
        f"PMA: {args.pma}",
        f"Table offset: 0x{table_offset:X}",
        f"Type2 pointers: {len(pointers)}",
        f"Pointer-derived segments: {len(segs)}",
        "",
        "Top opcodes:",
    ]
    for op, n in op_counter.most_common(20):
        flw = ", ".join(f"{b:02X}:{c}" for b, c in follower[op].most_common(5))
        summary.append(f"- 0x{op:02X} count={n} followers=[{flw}]")
    summary.append("")
    summary.append("Top correlated IDs:")
    for op, v, a, b in corr[:40]:
        summary.append(f"- op=0x{op:02X} value=0x{v:04X} stream={a} resources={b}")
    (out / "summary.txt").write_text("\n".join(summary), encoding="utf-8")

    print(f"[+] Wrote: {out / 'opcode_profile.csv'}")
    print(f"[+] Wrote: {out / 'id_correlation.csv'}")
    print(f"[+] Wrote: {out / 'summary.txt'}")
    print("[+] Top opcodes:")
    for op, n in op_counter.most_common(12):
        print(f"  - 0x{op:02X}: {n}")
    print("[+] Top correlations:")
    for op, v, a, b in corr[:20]:
        print(f"  - op 0x{op:02X} -> 0x{v:04X} (stream {a}, resources {b})")


if __name__ == "__main__":
    main()
