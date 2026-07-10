"""Génération de rapports à partir d'une config jeu."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .analysis import decompile_at, disassemble_range, resolve_addresses
from .loaders import PS2Target, open_ps2_program, parse_addr
from .strings import export_strings_csv, filter_for_translation, scan_ghidra_program
from .xrefs import hot_text_functions, string_xref_report


def load_game_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_report(config_path: Path, out_dir: Path) -> Path:
    """
    Exécute un rapport complet décrit par un JSON de config.

    Voir ps2_re/examples/ pour le format.
    """
    cfg = load_game_config(config_path)
    target = PS2Target.from_dict(cfg.get("target", {}), base_dir=config_path.parent)
    if cfg.get("target", {}).get("analyze"):
        target.analyze = True

    out_dir.mkdir(parents=True, exist_ok=True)
    sections: list[str] = [f"// PS2 RE report — {target.binary.name}\n"]

    with open_ps2_program(target) as api:
        program = api.getCurrentProgram()
        sections.append(
            f"// Language: {program.getLanguageID()}\n"
            f"// Image base: {program.getImageBase()}\n"
            f"// Range: {program.getMinAddress()} .. {program.getMaxAddress()}\n\n"
        )

        for block in cfg.get("decompile", []):
            addr = parse_addr(str(block["addr"]))
            name = block.get("name")
            _, c = decompile_at(api, addr, name)
            sections.append(f"\n{'='*60}\n// {name or 'FUNC'} @ {addr:#010x}\n{'='*60}\n{c}\n")

        for block in cfg.get("disassemble", []):
            start = parse_addr(str(block["start"]))
            length = int(block.get("length", 0x200))
            label = block.get("label", f"disasm_{start:08x}")
            asm = disassemble_range(api, start, length)
            sections.append(f"\n{'='*60}\n// {label}\n{'='*60}\n{asm}\n")

        strings_cfg = cfg.get("strings")
        if strings_cfg:
            strings = scan_ghidra_program(
                api,
                encodings=strings_cfg.get("encodings", ["sjis", "ascii"]),
                min_len=int(strings_cfg.get("min_len", 4)),
                japanese_only=bool(strings_cfg.get("japanese_only", False)),
            )
            if strings_cfg.get("translation_filter"):
                strings = filter_for_translation(
                    strings,
                    langs=strings_cfg.get("langs", ["ja", "en"]),
                )
            csv_path = out_dir / strings_cfg.get("csv", "strings.csv")
            export_strings_csv(strings, csv_path)
            sections.append(f"\n// Exported {len(strings)} strings -> {csv_path}\n")

            xref_cfg = strings_cfg.get("xrefs")
            if xref_cfg and strings:
                addrs = [s.address for s in strings]
                if xref_cfg.get("hot_functions"):
                    hot = hot_text_functions(
                        api,
                        addrs,
                        min_strings=int(xref_cfg.get("min_strings", 3)),
                    )
                    hot_path = out_dir / xref_cfg.get("hot_json", "hot_text_functions.json")
                    hot_path.write_text(json.dumps(hot, indent=2, ensure_ascii=False), encoding="utf-8")
                    sections.append(f"// Hot text functions -> {hot_path}\n")

    out_file = out_dir / cfg.get("output", "report.c")
    out_file.write_text("".join(sections), encoding="utf-8")
    return out_file
