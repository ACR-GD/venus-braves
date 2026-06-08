#!/usr/bin/env python3
"""
Attempt decoding/transformation strategies on PMA chunks.

Purpose:
- Run multiple decode attempts per chunk.
- Score outputs for likely Japanese text.
- Produce a ranked report to guide script extraction work.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import zlib
from typing import Iterable, List, Optional, Tuple


JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
CTRL_RE = re.compile(r"[\x00-\x08\x0B-\x1F]")
ASCII_RE = re.compile(r"[ -~]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")


@dataclass
class DecodeHit:
    chunk_file: str
    method: str
    out_size: int
    jp_chars: int
    printable_ratio: float
    ctrl_ratio: float
    score: float
    preview: str


def xor_bytes(data: bytes, key: int) -> bytes:
    return bytes(b ^ key for b in data)


def decode_shift_jis_text(data: bytes) -> str:
    return data.decode("shift_jis", errors="ignore")


def text_metrics(text: str) -> Tuple[int, int, float, float]:
    if not text:
        return 0, 0, 0.0, 1.0
    n = len(text)
    jp = len(JP_RE.findall(text))
    kana = len(KANA_RE.findall(text))
    printable = len([c for c in text if c.isprintable()])
    ctrl = len(CTRL_RE.findall(text))
    printable_ratio = printable / n
    ctrl_ratio = ctrl / n
    return jp, kana, printable_ratio, ctrl_ratio


def score_text(
    jp_chars: int,
    kana_chars: int,
    printable_ratio: float,
    ctrl_ratio: float,
    out_size: int,
) -> float:
    # Bias toward meaningful Japanese output with sane text structure.
    size_bonus = min(out_size, 8000) / 8000.0
    return (
        jp_chars * 1.8
        + kana_chars * 1.1
        + printable_ratio * 30.0
        - ctrl_ratio * 50.0
        + size_bonus * 8.0
    )


def safe_decompress(data: bytes, wbits: int) -> Optional[bytes]:
    try:
        return zlib.decompress(data, wbits)
    except Exception:
        return None


def decode_methods(blob: bytes) -> Iterable[Tuple[str, bytes]]:
    # 1) Raw as-is
    yield "raw", blob

    # 2) zlib/deflate attempts on full blob
    for wbits, name in [(15, "zlib_w15"), (-15, "deflate_raw"), (31, "gzip_w31")]:
        out = safe_decompress(blob, wbits)
        if out and len(out) > 16:
            yield name, out

    # 3) Offset-based deflate attempts (common for framed chunks)
    for skip in range(1, 9):
        sub = blob[skip:]
        if len(sub) < 16:
            continue
        for wbits, name in [(15, "zlib_skip"), (-15, "deflate_skip")]:
            out = safe_decompress(sub, wbits)
            if out and len(out) > 16:
                yield f"{name}_{skip}", out

    # 4) Single-byte XOR + optional zlib probe
    for key in [0x20, 0x55, 0xAA, 0xFF]:
        x = xor_bytes(blob, key)
        yield f"xor_{key:02X}", x
        out = safe_decompress(x, 15)
        if out and len(out) > 16:
            yield f"xor_{key:02X}_zlib", out


def analyze_chunk(chunk_path: Path, min_jp: int, min_score: float) -> List[DecodeHit]:
    blob = chunk_path.read_bytes()
    hits: List[DecodeHit] = []

    seen = set()
    for method, decoded in decode_methods(blob):
        # Deduplicate identical outputs
        sig = (len(decoded), decoded[:64])
        if sig in seen:
            continue
        seen.add(sig)

        text = decode_shift_jis_text(decoded)
        jp, kana, printable_ratio, ctrl_ratio = text_metrics(text)
        score = score_text(jp, kana, printable_ratio, ctrl_ratio, len(decoded))

        # Filter out mojibake-like outputs: for real dialogue we'd expect
        # at least some kana presence, not only sparse kanji glyph noise.
        if (jp < min_jp or kana < 4) and score < min_score:
            continue

        preview = text.replace("\n", "\\n").replace("\r", "\\r")[:140]
        hits.append(
            DecodeHit(
                chunk_file=chunk_path.name,
                method=method,
                out_size=len(decoded),
                jp_chars=jp,
                printable_ratio=printable_ratio,
                ctrl_ratio=ctrl_ratio,
                score=score,
                preview=preview,
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def write_csv(path: Path, hits: List[DecodeHit]) -> None:
    header = (
        "chunk_file,method,out_size,jp_chars,printable_ratio,ctrl_ratio,score,preview\n"
    )
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(header)
        for h in hits:
            preview = h.preview.replace('"', "''")
            f.write(
                f"{h.chunk_file},{h.method},{h.out_size},{h.jp_chars},"
                f"{h.printable_ratio:.4f},{h.ctrl_ratio:.4f},{h.score:.2f},"
                f"\"{preview}\"\n"
            )


def collect_chunks(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob("chunk_*.bin"))
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Try decode strategies on PMA chunks and rank likely text outputs."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Chunk file or directory generated by pma_probe.py (chunks/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("pma_decode_try_out"),
        help="Output directory (default: ./pma_decode_try_out)",
    )
    parser.add_argument(
        "--min-jp",
        type=int,
        default=8,
        help="Minimum Japanese characters to keep (default: 8)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=35.0,
        help="Minimum score to keep (default: 35.0)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=40,
        help="Number of top hits printed (default: 40)",
    )
    args = parser.parse_args()

    chunk_paths = collect_chunks(args.input)
    if not chunk_paths:
        raise SystemExit(f"No chunk files found in: {args.input}")

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    all_hits: List[DecodeHit] = []
    for chunk_path in chunk_paths:
        all_hits.extend(analyze_chunk(chunk_path, args.min_jp, args.min_score))

    all_hits.sort(key=lambda h: h.score, reverse=True)
    csv_path = out_dir / "decode_hits.csv"
    write_csv(csv_path, all_hits)

    print(f"[+] Input chunks: {len(chunk_paths)}")
    print(f"[+] Hits: {len(all_hits)}")
    print(f"[+] CSV: {csv_path}")
    print("\nTop hits:")
    for h in all_hits[: args.top]:
        print(
            f"  - {h.chunk_file} method={h.method} score={h.score:.2f} "
            f"jp={h.jp_chars} out={h.out_size} preview={h.preview!r}"
        )


if __name__ == "__main__":
    main()
