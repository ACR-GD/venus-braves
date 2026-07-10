"""Chasse aux codecs custom via ELF + Ghidra."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from .compression_probe import codec_fingerprint_elf
from .loaders import PS2Target, open_ps2_program, parse_addr


def load_elf_text_words(elf_path: Path) -> tuple[list[int], int, int]:
    """Extrait les mots de .text d'un ELF PS2 pour fingerprint statique."""
    try:
        from elftools.elf.elffile import ELFFile
    except ImportError:
        raise RuntimeError("pip install pyelftools")

    with elf_path.open("rb") as f:
        elf = ELFFile(f)
        text = elf.get_section_by_name(".text")
        if text is None:
            for seg in elf.iter_segments():
                if seg["p_type"] == "PT_LOAD" and seg["p_vaddr"] <= elf.header["e_entry"] < seg["p_vaddr"] + seg["p_memsz"]:
                    data = seg.data()
                    vaddr = seg["p_vaddr"]
                    words = list(struct.unpack(f"<{len(data)//4}I", data[: len(data) // 4 * 4]))
                    return words, vaddr, len(data)
            raise ValueError("section .text introuvable")
        data = text.data()
        return list(struct.unpack(f"<{len(data)//4}I", data)), text["sh_addr"], len(data)


def hunt_codec_static(elf_path: Path) -> dict[str, Any]:
    words, vaddr, size = load_elf_text_words(elf_path)
    hits = codec_fingerprint_elf(words, vaddr)
    return {
        "elf": str(elf_path),
        "text_vaddr": f"0x{vaddr:X}",
        "text_size": size,
        "bitstream_candidates": hits,
        "next_steps": [
            "Décompiler chaque adresse candidate avec: ps2_ghidra.py decompile ... --funcs ADDR",
            "Chercher TextureUpload / DMA vers GS (format dispatch +0xE)",
            "Comparer consommation octets source vs taille plane attendue (2048, 8192…)",
            "Valider via savestate Scratchpad.bin ou dump textures PCSX2",
        ],
    }


def hunt_codec_ghidra(
    target: PS2Target,
    candidate_addrs: list[int],
    *,
    decompile: bool = True,
) -> dict[str, Any]:
    """Décompile les candidats codec identifiés statiquement."""
    from .analysis import decompile_at, disassemble_range

    report: dict[str, Any] = {"candidates": [], "decompiled": []}
    with open_ps2_program(target) as api:
        for addr in candidate_addrs:
            report["candidates"].append(f"0x{addr:X}")
            if decompile:
                func, c = decompile_at(api, addr, f"CodecCandidate_{addr:08x}")
                report["decompiled"].append({
                    "address": f"0x{addr:X}",
                    "c": c,
                })
    return report


def workflow_identify_custom_compression(
    *,
    asset_path: Path | None = None,
    elf_path: Path | None = None,
    ee_dump: Path | None = None,
    chunk_offset: int | None = None,
    chunk_size: int | None = None,
) -> dict[str, Any]:
    """
    Guide méthodologique complet — combine probes fichier + fingerprint ELF.

    Étapes recommandées pour identifier une compression custom graphique :
    1. Inventorier le conteneur (FHM/ITE/GIM/ARC)
    2. Sonder chaque chunk (entropie, lead byte, décodeurs connus)
    3. Si échec : fingerprint .text (srl/andi bitstream)
    4. Ghidra : suivre TextureUpload → dispatch format → decode
    5. Valider : round-trip encodeur ou match VRAM/PCSX2
    """
    from .compression_probe import probe_chunk
    from .graphics_extract import inventory_fhm

    out: dict[str, Any] = {"steps": []}

    if asset_path and asset_path.suffix.lower() == ".fhm":
        inv = inventory_fhm(asset_path)
        out["container_inventory"] = inv
        out["steps"].append({
            "step": 1,
            "action": "Inventaire FHM",
            "result": f"{len(inv.get('translatable_candidates', []))} ITE candidates",
        })

    if asset_path and chunk_offset is not None and chunk_size is not None:
        data = asset_path.read_bytes()
        probe = probe_chunk(data, chunk_offset, chunk_size, expected_out=2048)
        out["chunk_probe"] = {
            "likely": probe.likely,
            "entropy": probe.entropy,
            "probes": [{"name": p.name, "confidence": p.confidence, "notes": p.notes} for p in probe.probes],
        }
        out["steps"].append({
            "step": 2,
            "action": "Probe chunk",
            "result": probe.likely,
        })

    if elf_path:
        static = hunt_codec_static(elf_path)
        out["elf_fingerprint"] = static
        out["steps"].append({
            "step": 3,
            "action": "Fingerprint ELF bitstream",
            "result": f"{len(static['bitstream_candidates'])} candidats",
        })

    if ee_dump:
        out["steps"].append({
            "step": 4,
            "action": "Dump EE",
            "hint": (
                f"Charger {ee_dump} avec --preset ee-dump, "
                "décompiler les candidats, breakpoints sur lecture chunk compressé"
            ),
        })

    out["methodology"] = {
        "container_signs": {
            "FHM": "table d'offsets, entrées ITE ou meta",
            "ITE": "magic ITE\\0, WxH, table tuiles (bit31=compressé)",
            "GIM": "textures Namco, souvent LZSS variant ei/ej",
            "TIM": "Sony, rarement compressé",
        },
        "compression_signs": {
            "zlib": "lead 0x78 0x9C etc.",
            "lzss": "entropie 6-7.5, décompression partielle standard",
            "ulz-namco": "lead 0x48-0x51, acc0=6bits, plane 2048 deltas",
            "custom": "entropie >7, aucun décodeur standard, footer taille chunk",
        },
        "ghidra_hints": [
            "DMAchain / sceGsSyncPath → upload texture",
            "switch(format_id) : 0=VU1 microcode, 2=EE codec",
            "ReadBits : fenêtre 24 bits MSB-first, acc0>>1 initial",
            "DecodePlane : 2048 itérations, littéraux 7-bit signés + LZ",
            "Scratchpad 0x70002000 utilisé pendant décompression",
        ],
        "validation": [
            "Round-trip encodeur Python vs chunk original (même taille si repack ISO)",
            "Match scratchpad savestate pendant breakpoint decode",
            "Dump PCSX2 texture PNG vs tuile décodée",
            "Patch une tuile test en jeu",
        ],
    }
    return out


def export_hunt_report(data: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
