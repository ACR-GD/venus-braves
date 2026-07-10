"""Recherche de chaînes (Shift-JIS, ASCII) pour la traduction."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

# Lead bytes Shift-JIS / CP932
_SJIS_LEAD = tuple(range(0x81, 0xA0)) + tuple(range(0xE0, 0xFD))
_SJIS_TRAIL = tuple(range(0x40, 0x7F)) + tuple(range(0x80, 0xFD))


@dataclass
class FoundString:
    address: int
    encoding: str
    text: str
    raw: bytes
    length: int


def _is_sjis_lead(b: int) -> bool:
    return b in _SJIS_LEAD


def _is_sjis_trail(b: int) -> bool:
    return b in _SJIS_TRAIL


def _decode_sjis(data: bytes) -> str | None:
    try:
        return data.decode("cp932")
    except UnicodeDecodeError:
        return None


def _looks_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30FF\u4E00-\u9FFF\uFF66-\uFF9D]", text))


def _looks_printable_ascii(data: bytes) -> bool:
    if len(data) < 2:
        return False
    printable = sum(1 for b in data if 0x20 <= b <= 0x7E or b in (0x09, 0x0A, 0x0D))
    return printable / len(data) >= 0.85


def scan_memory(
    data: bytes,
    base_addr: int = 0,
    *,
    encodings: Iterable[str] = ("sjis", "ascii"),
    min_len: int = 4,
    max_len: int = 512,
    japanese_only: bool = False,
) -> list[FoundString]:
    """Scan linéaire d'un buffer (dump, segment ELF fusionné, etc.)."""
    want_sjis = "sjis" in encodings or "cp932" in encodings
    want_ascii = "ascii" in encodings or "latin1" in encodings
    found: list[FoundString] = []
    seen_addrs: set[int] = set()
    i = 0
    n = len(data)

    while i < n:
        b = data[i]

        # Shift-JIS : lead + trail
        if want_sjis and _is_sjis_lead(b) and i + 1 < n and _is_sjis_trail(data[i + 1]):
            start = i
            chars: list[bytes] = []
            while i < n and len(chars) < max_len:
                if _is_sjis_lead(data[i]) and i + 1 < n and _is_sjis_trail(data[i + 1]):
                    chars.append(data[i : i + 2])
                    i += 2
                    continue
                if data[i] == 0:
                    break
                if 0x20 <= data[i] <= 0x7E:
                    chars.append(bytes([data[i]]))
                    i += 1
                    continue
                break
            raw = b"".join(chars)
            if len(raw) >= min_len:
                text = _decode_sjis(raw)
                if text and (not japanese_only or _looks_japanese(text)):
                    addr = base_addr + start
                    if addr not in seen_addrs:
                        seen_addrs.add(addr)
                        found.append(FoundString(addr, "sjis", text, raw, len(raw)))
            continue

        # ASCII / Latin-1
        if want_ascii and (0x20 <= b <= 0x7E):
            start = i
            while i < n and 0x20 <= data[i] <= 0x7E and (i - start) < max_len:
                i += 1
            raw = data[start:i]
            if len(raw) >= min_len and _looks_printable_ascii(raw):
                text = raw.decode("ascii", errors="replace")
                if not japanese_only:
                    addr = base_addr + start
                    if addr not in seen_addrs:
                        seen_addrs.add(addr)
                        found.append(FoundString(addr, "ascii", text, raw, len(raw)))
            continue

        i += 1

    return found


def scan_ghidra_program(
    flat_api: Any,
    *,
    encodings: Iterable[str] = ("sjis", "ascii"),
    min_len: int = 4,
    japanese_only: bool = False,
) -> list[FoundString]:
    """Scan des blocs mémoire initialisés du programme Ghidra."""
    program = flat_api.getCurrentProgram()
    mem = program.getMemory()
    blocks = [b for b in mem.getBlocks() if b.isInitialized()]
    found: list[FoundString] = []
    for block in blocks:
        data = bytes(block.getBytes(block.getStart(), int(block.getSize())))
        base = block.getStart().getOffset()
        found.extend(
            scan_memory(
                data,
                base_addr=base,
                encodings=encodings,
                min_len=min_len,
                japanese_only=japanese_only,
            )
        )
    # Dédupliquer par adresse
    uniq: dict[int, FoundString] = {}
    for s in found:
        uniq[s.address] = s
    return sorted(uniq.values(), key=lambda s: s.address)


def export_strings_csv(strings: list[FoundString], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["address", "encoding", "length", "text", "raw_hex", "translation_en", "translation_fr"])
        for s in strings:
            w.writerow([
                f"0x{s.address:X}",
                s.encoding,
                s.length,
                s.text,
                s.raw.hex(),
                "",
                "",
            ])


def filter_for_translation(
    strings: list[FoundString],
    *,
    langs: Iterable[str] = ("ja", "en"),
) -> list[FoundString]:
    """Filtre les chaînes utiles pour un projet de traduction."""
    out: list[FoundString] = []
    for s in strings:
        if "ja" in langs and s.encoding == "sjis" and _looks_japanese(s.text):
            out.append(s)
        elif "en" in langs and s.encoding == "ascii" and re.search(r"[A-Za-z]{3}", s.text):
            out.append(s)
    return out
