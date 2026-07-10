"""Identification et test de méthodes de compression (standard + custom)."""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CompressionProbe:
    name: str
    confidence: float  # 0..1
    notes: str
    decoded_size: int | None = None
    decoder: str | None = None


@dataclass
class ChunkAnalysis:
    offset: int
    size: int
    lead_byte: int
    entropy: float
    probes: list[CompressionProbe] = field(default_factory=list)
    likely: str = "unknown"


def byte_entropy(data: bytes) -> float:
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


def _looks_decompressed(buf: bytes, expected: int | None = None) -> bool:
    if len(buf) < 32:
        return False
    if expected and abs(len(buf) - expected) > expected * 0.1:
        return False
    unique = len(set(buf))
    if unique < 4:
        return False
    return byte_entropy(buf) < 7.0


def try_zlib(data: bytes) -> bytes | None:
    for wbits in (15, -15, 15 + 16, -15 - 16):
        try:
            return zlib.decompress(data, wbits)
        except zlib.error:
            continue
    return None


def lzss_standard(data: bytes, window: int = 0x1000, min_len: int = 3) -> bytes | None:
    """LZSS classique (flag byte, 8 tokens, littéral si bit=1)."""
    out = bytearray()
    pos = 0
    while pos < len(data):
        if pos >= len(data):
            break
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if pos >= len(data):
                break
            if (flags >> bit) & 1:
                out.append(data[pos])
                pos += 1
            else:
                if pos + 1 >= len(data):
                    return None
                lo, hi = data[pos], data[pos + 1]
                pos += 2
                offset = lo | ((hi & 0xF0) << 4)
                length = (hi & 0x0F) + min_len
                if offset < 1:
                    return None
                src = len(out) - offset
                if src < 0:
                    return None
                for _ in range(length):
                    if src >= len(out):
                        return None
                    out.append(out[src])
                    src += 1
    return bytes(out) if out else None


def lzss_namco_variant(data: bytes, ei: int = 11, ej: int = 4, offset_bias: int = 1) -> bytes | None:
    """Variante LZSS Namco (paramètres ei/ej comme decode_gim.py)."""
    n = 1 << ei
    f = (1 << ej) + 2
    r = n - f
    text_buf = bytearray([0x00] * n)
    out = bytearray()
    pos = 0
    flag_bit = 0
    flags = 0
    while pos < len(data):
        if flag_bit == 0:
            if pos >= len(data):
                break
            flags = data[pos]
            pos += 1
            flag_bit = 8
        flag_bit -= 1
        bit = (flags >> flag_bit) & 1
        if bit:
            if pos >= len(data):
                break
            c = data[pos]
            pos += 1
            out.append(c)
            text_buf[r] = c
            r = (r + 1) & (n - 1)
        else:
            if pos + 1 >= len(data):
                break
            b0, b1 = data[pos], data[pos + 1]
            pos += 2
            offset = b0 | ((b1 & 0xF0) << 4)
            length = (b1 & 0x0F) + 3
            offset += offset_bias
            if offset < 1:
                return None
            for _ in range(length):
                src = (r - offset) & (n - 1)
                if src < 0 or src >= len(text_buf):
                    return None
                c = text_buf[src]
                out.append(c)
                text_buf[r] = c
                r = (r + 1) & (n - 1)
    return bytes(out) if out else None


def _score_decoder(name: str, raw: bytes, decoded: bytes | None, expected: int | None) -> CompressionProbe | None:
    if not decoded:
        return None
    if not _looks_decompressed(decoded, expected):
        return None
    ratio = len(decoded) / max(len(raw), 1)
    conf = min(0.95, 0.4 + ratio * 0.1)
    if expected and len(decoded) == expected:
        conf = 0.85
    elif expected and abs(len(decoded) - expected) < 64:
        conf = 0.7
    return CompressionProbe(
        name=name,
        confidence=conf,
        notes=f"sortie {len(decoded)} o (ratio {ratio:.1f}x)",
        decoded_size=len(decoded),
        decoder=name,
    )


def probe_chunk(
    data: bytes,
    offset: int,
    size: int,
    *,
    expected_out: int | None = None,
    lead_byte: int | None = None,
) -> ChunkAnalysis:
    """Teste un bloc contre plusieurs familles de compression connues."""
    chunk = data[offset : offset + size]
    lead = lead_byte if lead_byte is not None else (chunk[0] if chunk else 0)
    analysis = ChunkAnalysis(
        offset=offset,
        size=size,
        lead_byte=lead,
        entropy=byte_entropy(chunk),
    )

    if not chunk or (lead == 0 and size <= 16):
        analysis.probes.append(CompressionProbe("empty", 1.0, "tuile vide / padding"))
        analysis.likely = "empty"
        return analysis

    if lead == 0x78 or (len(chunk) > 2 and chunk[0] == 0x78 and chunk[1] in (0x01, 0x5E, 0x9C, 0xDA)):
        z = try_zlib(chunk)
        p = _score_decoder("zlib/deflate", chunk, z, expected_out)
        if p:
            analysis.probes.append(p)

    # entropique élevé → probablement compressé custom ou LZ
    if analysis.entropy > 6.5:
        analysis.probes.append(CompressionProbe(
            "custom-bitstream",
            0.55,
            f"entropie élevée ({analysis.entropy:.2f}); tenter Ghidra (ReadBits/LZ)",
        ))

    # signatures connues jeux Namco / Venus
    if lead in (0x49, 0x48, 0x4A, 0x51):
        analysis.probes.append(CompressionProbe(
            "ulz-namco",
            0.75,
            f"octet lead 0x{lead:02x} typique codec EE Venus (acc0>>1 + bitstream MSB)",
            decoder="ulz-namco",
        ))

    for name, fn in (
        ("lzss-standard", lzss_standard),
        ("lzss-namco-ei11", lambda d: lzss_namco_variant(d, 11, 4, 1)),
        ("lzss-namco-ei12", lambda d: lzss_namco_variant(d, 12, 4, 18)),
    ):
        try:
            dec = fn(chunk)
            p = _score_decoder(name, chunk, dec, expected_out)
            if p:
                analysis.probes.append(p)
        except Exception:
            pass

    # ULZ via décodeur projet si disponible
    try:
        from ulz_decode import decode_plane
        plane, br = decode_plane(data, offset)
        consumed = br.consumed_bytes()
        if consumed <= size and max(plane) > min(plane):
            analysis.probes.append(CompressionProbe(
                "ulz-namco-verified",
                0.95,
                f"decode_plane OK, {consumed}/{size} o consommés",
                decoded_size=2048,
                decoder="ulz-namco",
            ))
    except Exception:
        pass

    if analysis.probes:
        best = max(analysis.probes, key=lambda p: p.confidence)
        analysis.likely = best.decoder or best.name
    elif analysis.entropy < 5.5:
        analysis.likely = "raw-uncompressed"
        analysis.probes.append(CompressionProbe("raw", 0.6, "entropie basse, possiblement brut"))
    else:
        analysis.likely = "unknown-custom"
        analysis.probes.append(CompressionProbe(
            "unknown",
            0.3,
            "aucun décodeur standard; analyse EE requise (voir hunt-codec)",
        ))

    return analysis


def probe_ite_tiles(data: bytes, ite_off: int) -> list[ChunkAnalysis]:
    from .containers import parse_ite
    ite = parse_ite(data, ite_off)
    expected_plane = 64 * 32  # 1 plan 8 bits / tuile Venus
    return [
        probe_chunk(data, t.offset, t.size, expected_out=expected_plane, lead_byte=t.lead_byte)
        for t in ite.tiles
        if not t.empty
    ]


def codec_fingerprint_elf(text_words: list[int], text_vaddr: int = 0x100000) -> list[dict]:
    """
    Cherche dans .text des motifs typiques de décodeurs entropiques MIPS :
    srl/sra par 10-13 bits + andi avec masque correspondant (ReadBits / LZ distance).
    """
    masks = {0x3FF: 10, 0x7FF: 11, 0xFFF: 12, 0x1FFF: 13}
    srls: dict[int, int] = {}
    andis: dict[int, int] = {}

    for i, w in enumerate(text_words):
        va = text_vaddr + i * 4
        op = (w >> 26) & 0x3F
        rs = (w >> 21) & 0x1F
        rt = (w >> 16) & 0x1F
        rd = (w >> 11) & 0x1F
        sa = (w >> 6) & 0x1F
        funct = w & 0x3F
        imm = w & 0xFFFF

        if op == 0 and funct == 0x02 and sa in (10, 11, 12, 13):
            srls[va] = sa
        if op == 0 and funct == 0x03 and sa in (10, 11, 12, 13):
            srls[va] = sa
        if op == 0x0C and imm in masks:
            andis[va] = masks[imm]

    hits: list[dict] = []
    seen: set[int] = set()
    for va, bits in andis.items():
        for off in range(-32, 36, 4):
            v2 = va + off
            if srls.get(v2) == bits and v2 not in seen:
                seen.add(v2)
                hits.append({
                    "address": min(va, v2),
                    "bit_width_hint": bits,
                    "pattern": "srl/andi bitstream",
                    "confidence": 0.7,
                })
    return sorted(hits, key=lambda h: h["address"])
