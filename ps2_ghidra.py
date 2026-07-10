#!/usr/bin/env python3
"""
ps2_ghidra.py — CLI PyGhidra réutilisable pour jeux PS2.

Exemples :
  # Infos sur l'exécutable EE
  python3 ps2_ghidra.py info SLPS_251.96.orig --preset ee-elf

  # Décompiler des fonctions connues
  python3 ps2_ghidra.py decompile eeMemory.bin --preset ee-dump \\
      --funcs 0x1aef20:ReadBits,0x1afc08:DecodePlane -o out/codec.c

  # Scanner les chaînes japonaises (traduction)
  python3 ps2_ghidra.py strings SLPS_251.96.orig --preset ee-elf \\
      --encoding sjis --japanese-only -o strings_ja.csv

  # Xrefs vers une chaîne / adresse
  python3 ps2_ghidra.py xrefs-to SLPS_251.96.orig 0x123456 --preset ee-elf --analyze

  # Rapport complet depuis une config JSON
  python3 ps2_ghidra.py report ps2_re/examples/venus_codec.json

  # Graphismes : inventorier FHM, sonder compression, extraire PNG
  python3 ps2_ghidra.py scan-graphics ./cdimage_temp_unpacked -o out/graphics_scan.json
  python3 ps2_ghidra.py inventory-fhm option.fhm -o out/option_inventory.json
  python3 ps2_ghidra.py probe-chunk option.fhm --offset 0xF40 --size 0x500
  python3 ps2_ghidra.py extract-graphics option.fhm --entries 1,3,4 -o out/option_png/

  # Identifier compression custom (ELF + chunk)
  python3 ps2_ghidra.py hunt-codec SLPS_251.96.orig -o out/codec_hits.json
  # TIM2 (textures standard PS2)
  python3 ps2_ghidra.py scan-tim2 ./cdimage_unpacked --embedded -o out/tim2_scan.json
  python3 ps2_ghidra.py tim2-info texture.tm2
  python3 ps2_ghidra.py tim2-export texture.tm2 -o out/tim2/
  python3 ps2_ghidra.py tim2-replace texture.tm2 edited.png -o texture_fr.tm2 --picture 0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ps2_re.analysis import (
    decompile_at,
    disassemble_range,
    list_functions,
    resolve_addresses,
)
from ps2_re.ghidra_env import find_ghidra_install
from ps2_re.loaders import PRESETS, PS2Target, open_ps2_program, parse_addr
from ps2_re.report import run_report
from ps2_re.strings import (
    export_strings_csv,
    filter_for_translation,
    scan_ghidra_program,
    scan_memory,
)
from ps2_re.xrefs import hot_text_functions, refs_from, refs_to
from ps2_re.graphics_extract import extract_fhm, inventory_fhm, scan_graphics_tree
from ps2_re.compression_probe import probe_chunk, probe_ite_tiles
from ps2_re.codec_hunt import (
    export_hunt_report,
    hunt_codec_static,
    workflow_identify_custom_compression,
)
from ps2_re.containers import summarize_file
from ps2_re.tim2 import (
    export_tim2,
    parse_tim2,
    replace_tim2_picture,
    scan_tim2_tree,
)


def _add_target_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("binary", type=Path, help="ELF, dump EE/IOP, ou binaire brut")
    p.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        default="ee-elf",
        help="Profil de chargement PS2 (défaut: ee-elf)",
    )
    p.add_argument("--language", help="Langue Ghidra (ex. MIPS:LE:32:default)")
    p.add_argument("--image-base", type=lambda x: int(x, 0), help="Image base (hex)")
    p.add_argument("--project-dir", type=Path, help="Dossier projets Ghidra locaux")
    p.add_argument("--project-name", help="Nom du projet Ghidra")
    p.add_argument("--analyze", action="store_true", help="Lancer l'analyse Ghidra auto")
    p.add_argument("--ghidra", type=Path, help="Chemin installation Ghidra (libexec)")


def _make_target(args: argparse.Namespace) -> PS2Target:
    if args.ghidra:
        from ps2_re.ghidra_env import ensure_started
        ensure_started(args.ghidra)
    return PS2Target(
        binary=args.binary.resolve(),
        preset=args.preset,
        language=args.language,
        image_base=args.image_base,
        project_dir=args.project_dir,
        project_name=args.project_name,
        analyze=args.analyze,
    )


def cmd_info(args: argparse.Namespace) -> int:
    target = _make_target(args)
    with open_ps2_program(target) as api:
        p = api.getCurrentProgram()
        print(f"Fichier     : {target.binary}")
        print(f"Preset      : {target.preset}")
        print(f"Language    : {p.getLanguageID()}")
        print(f"Image base  : {p.getImageBase()}")
        print(f"Adresses    : {p.getMinAddress()} .. {p.getMaxAddress()}")
        print(f"Fonctions   : {p.getFunctionManager().getFunctionCount()}")
    return 0


def cmd_decompile(args: argparse.Namespace) -> int:
    target = _make_target(args)
    funcs = resolve_addresses(args.funcs)
    lines: list[str] = []
    with open_ps2_program(target) as api:
        for addr, name in funcs:
            _, c = decompile_at(api, addr, name)
            lines.append(f"\n{'='*60}\n// {name or 'FUNC'} @ {addr:#010x}\n{'='*60}\n{c}\n")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")
    print(f"Écrit {out} ({out.stat().st_size} octets)")
    return 0


def cmd_disasm(args: argparse.Namespace) -> int:
    target = _make_target(args)
    start = parse_addr(args.start)
    with open_ps2_program(target) as api:
        asm = disassemble_range(api, start, args.length)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(asm, encoding="utf-8")
    print(f"Écrit {out}")
    return 0


def cmd_functions(args: argparse.Namespace) -> int:
    target = _make_target(args)
    with open_ps2_program(target) as api:
        funcs = list_functions(api, limit=args.limit)
    for f in funcs:
        print(f"{f['entry']:#010x}  {f['name']:<32}  size={f['size']}")
    return 0


def cmd_strings(args: argparse.Namespace) -> int:
    target = _make_target(args)
    encodings = [e.strip() for e in args.encoding.split(",")]

    if args.raw_scan:
        from ps2_re.loaders import prepare_binary
        src, cfg = prepare_binary(target)
        data = src.read_bytes()
        base = int(cfg.get("image_base") or 0)
        strings = scan_memory(
            data,
            base_addr=base,
            encodings=encodings,
            min_len=args.min_len,
            japanese_only=args.japanese_only,
        )
    else:
        with open_ps2_program(target) as api:
            strings = scan_ghidra_program(
                api,
                encodings=encodings,
                min_len=args.min_len,
                japanese_only=args.japanese_only,
            )

    if args.translation_filter:
        strings = filter_for_translation(strings, langs=args.langs.split(","))

    out = Path(args.output)
    export_strings_csv(strings, out)
    print(f"{len(strings)} chaînes -> {out}")
    return 0


def cmd_xrefs_to(args: argparse.Namespace) -> int:
    target = _make_target(args)
    addr = parse_addr(args.address)
    with open_ps2_program(target) as api:
        xrefs = refs_to(api, addr)
    if not xrefs:
        print(f"Aucune xref vers {addr:#x}")
        return 0
    for x in xrefs:
        fn = x.from_function or "?"
        kind = "call" if x.is_call else "data"
        print(f"{x.from_addr:#010x}  [{kind}]  {fn}  ({x.ref_type})")
    return 0


def cmd_xrefs_from(args: argparse.Namespace) -> int:
    target = _make_target(args)
    addr = parse_addr(args.address)
    with open_ps2_program(target) as api:
        xrefs = refs_from(api, addr)
    for x in xrefs:
        kind = "call" if x.is_call else "data"
        print(f"-> {x.to_addr:#010x}  [{kind}]  ({x.ref_type})")
    return 0


def cmd_hunt_text(args: argparse.Namespace) -> int:
    """Trouve les fonctions liées à beaucoup de chaînes (UI / dialogue)."""
    target = _make_target(args)
    encodings = [e.strip() for e in args.encoding.split(",")]
    with open_ps2_program(target) as api:
        strings = scan_ghidra_program(
            api,
            encodings=encodings,
            min_len=args.min_len,
            japanese_only=args.japanese_only,
        )
        if args.translation_filter:
            strings = filter_for_translation(strings, langs=args.langs.split(","))
        hot = hot_text_functions(api, [s.address for s in strings], min_strings=args.min_strings)

    out = Path(args.output) if args.output else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(hot, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{len(hot)} fonctions -> {out}")
    else:
        for row in hot:
            print(f"{row['string_count']:3d}  {row['function']}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if args.ghidra:
        from ps2_re.ghidra_env import ensure_started
        ensure_started(args.ghidra)
    out = run_report(args.config.resolve(), args.output.resolve())
    print(f"Rapport -> {out}")
    return 0


def cmd_presets(_: argparse.Namespace) -> int:
    ghidra = find_ghidra_install()
    print(f"Ghidra détecté : {ghidra or '(non trouvé)'}")
    print()
    for name, cfg in PRESETS.items():
        print(f"  {name}")
        for k, v in cfg.items():
            print(f"    {k}: {v}")
    return 0


def cmd_scan_graphics(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if root.is_file():
        items = [summarize_file(root)]
    else:
        items = scan_graphics_tree(root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(items)} fichiers -> {out}")
    return 0


def cmd_inventory_fhm(args: argparse.Namespace) -> int:
    inv = inventory_fhm(args.fhm.resolve())
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Inventaire FHM -> {out}")
    for c in inv.get("translatable_candidates", []):
        print(f"  [{c['priority']}] entry {c['index']}: {c['dimensions']} ({c['tiles']} tuiles)")
    return 0


def cmd_probe_chunk(args: argparse.Namespace) -> int:
    data = args.file.read_bytes()
    if args.ite is not None:
        probes = probe_ite_tiles(data, parse_addr(args.ite))
        payload = [_chunk_probe_dict(p) for p in probes]
        print(f"ITE @ {args.ite}: {len(probes)} tuiles sondées")
    else:
        off = parse_addr(args.offset)
        probe = probe_chunk(data, off, args.size, expected_out=args.expected)
        payload = _chunk_probe_dict(probe)
        print(f"Chunk @ {off:#x} ({args.size} o) -> likely: {probe.likely}")
    out = Path(args.output) if args.output else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Écrit {out}")
    return 0


def _chunk_probe_dict(p) -> dict:
    return {
        "offset": f"0x{p.offset:X}",
        "size": p.size,
        "lead_byte": f"0x{p.lead_byte:02x}",
        "entropy": round(p.entropy, 3),
        "likely": p.likely,
        "probes": [
            {"name": x.name, "confidence": round(x.confidence, 2), "notes": x.notes}
            for x in p.probes
        ],
    }


def cmd_extract_graphics(args: argparse.Namespace) -> int:
    indices = None
    if args.entries:
        indices = [int(x) for x in args.entries.split(",")]
    result = extract_fhm(
        args.fhm.resolve(),
        Path(args.output),
        entry_indices=indices,
        export_tiles=args.tiles,
        export_probe=not args.no_probe,
    )
    print(f"Extrait {len(result['extracted'])} entrées -> {args.output}")
    if result.get("manifest"):
        print(f"Manifest: {result['manifest']}")
    return 0


def cmd_hunt_codec(args: argparse.Namespace) -> int:
    report = hunt_codec_static(args.elf.resolve())
    out = Path(args.output)
    export_hunt_report(report, out)
    print(f"{len(report['bitstream_candidates'])} candidats bitstream -> {out}")
    for hit in report["bitstream_candidates"][:10]:
        print(f"  {hit['address']:#x}  bits={hit['bit_width_hint']}  ({hit['pattern']})")
    return 0


def cmd_identify_compression(args: argparse.Namespace) -> int:
    report = workflow_identify_custom_compression(
        asset_path=args.asset.resolve() if args.asset else None,
        elf_path=args.elf.resolve() if args.elf else None,
        ee_dump=args.ee_dump.resolve() if args.ee_dump else None,
        chunk_offset=parse_addr(args.chunk_offset) if args.chunk_offset else None,
        chunk_size=args.chunk_size,
    )
    out = Path(args.output)
    export_hunt_report(report, out)
    print(f"Rapport méthodologie -> {out}")
    for step in report.get("steps", []):
        print(f"  étape {step['step']}: {step['action']} -> {step.get('result', step.get('hint', ''))}")
    return 0


def cmd_scan_tim2(args: argparse.Namespace) -> int:
    items = scan_tim2_tree(args.root.resolve(), scan_embedded=args.embedded)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(items)} TIM2 trouvés -> {out}")
    for item in items[:15]:
        src = item.get("embedded_offset", "0")
        pics = item.get("picture_count", 0)
        print(f"  {item.get('path')} (+{src})  {pics} image(s)")
    return 0


def cmd_tim2_info(args: argparse.Namespace) -> int:
    tf = parse_tim2(args.file.read_bytes(), args.file.resolve())
    print(f"Fichier    : {args.file}")
    print(f"Version    : {tf.version}  format={tf.format_id}  header={tf.header_size} o")
    print(f"Images     : {len(tf.pictures)}")
    for p in tf.pictures:
        clut = f"clut={p.clut_colors}" if p.clut_size else "sans CLUT"
        print(
            f"  [{p.index}] {p.width}x{p.height}  {p.image_type_name}/{p.psm_name}  "
            f"mip={p.mipmap_count}  {clut}  bitmap={p.image_size} o"
        )
    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(tf.to_dict(), indent=2), encoding="utf-8")
        print(f"JSON -> {out}")
    return 0


def cmd_tim2_export(args: argparse.Namespace) -> int:
    idx = int(args.picture) if args.picture is not None else None
    result = export_tim2(
        args.file.resolve(),
        Path(args.output),
        picture_index=idx,
        export_clut=not args.no_clut,
    )
    for item in result["exported"]:
        print(f"  pic {item['picture']}: {item['png']} ({item['format']})")
    print(f"Métadonnées: {result['metadata']}")
    return 0


def cmd_tim2_replace(args: argparse.Namespace) -> int:
    result = replace_tim2_picture(
        args.file.resolve(),
        args.png.resolve(),
        Path(args.output),
        picture_index=args.picture,
        clut_png=args.clut.resolve() if args.clut else None,
    )
    print(f"TIM2 modifié -> {result['output']} ({result['format']}, {result['bitmap_bytes']} o)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PyGhidra toolkit PS2 — reverse engineering & traduction",
    )
    parser.add_argument("--ghidra", type=Path, help="Chemin Ghidra libexec")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_presets = sub.add_parser("presets", help="Lister les profils de chargement")
    p_presets.set_defaults(func=cmd_presets)

    p_info = sub.add_parser("info", help="Infos programme Ghidra")
    _add_target_args(p_info)
    p_info.set_defaults(func=cmd_info)

    p_dec = sub.add_parser("decompile", help="Décompiler des fonctions")
    _add_target_args(p_dec)
    p_dec.add_argument("--funcs", required=True, help="0xADDR:Nom,0xADDR,...")
    p_dec.add_argument("-o", "--output", default="out/decompiled.c")
    p_dec.set_defaults(func=cmd_decompile)

    p_dis = sub.add_parser("disasm", help="Désassembler une zone")
    _add_target_args(p_dis)
    p_dis.add_argument("--start", required=True, help="Adresse de début")
    p_dis.add_argument("--length", type=lambda x: int(x, 0), default=0x200)
    p_dis.add_argument("-o", "--output", default="out/disasm.s")
    p_dis.set_defaults(func=cmd_disasm)

    p_fn = sub.add_parser("functions", help="Lister les fonctions")
    _add_target_args(p_fn)
    p_fn.add_argument("--limit", type=int, default=100)
    p_fn.set_defaults(func=cmd_functions)

    p_str = sub.add_parser("strings", help="Scanner chaînes (SJIS/ASCII) pour traduction")
    _add_target_args(p_str)
    p_str.add_argument("--encoding", default="sjis,ascii")
    p_str.add_argument("--min-len", type=int, default=4)
    p_str.add_argument("--japanese-only", action="store_true")
    p_str.add_argument("--translation-filter", action="store_true", help="Garde JA + EN pertinents")
    p_str.add_argument("--langs", default="ja,en")
    p_str.add_argument("--raw-scan", action="store_true", help="Scan fichier brut sans mémoire Ghidra")
    p_str.add_argument("-o", "--output", default="out/strings.csv")
    p_str.set_defaults(func=cmd_strings)

    p_xto = sub.add_parser("xrefs-to", help="Qui référence cette adresse ?")
    _add_target_args(p_xto)
    p_xto.add_argument("address", help="Adresse cible")
    p_xto.set_defaults(func=cmd_xrefs_to)

    p_xfr = sub.add_parser("xrefs-from", help="Que référence cette adresse ?")
    _add_target_args(p_xfr)
    p_xfr.add_argument("address", help="Adresse source")
    p_xfr.set_defaults(func=cmd_xrefs_from)

    p_hunt = sub.add_parser("hunt-text", help="Fonctions liées à beaucoup de chaînes")
    _add_target_args(p_hunt)
    p_hunt.add_argument("--encoding", default="sjis,ascii")
    p_hunt.add_argument("--min-len", type=int, default=6)
    p_hunt.add_argument("--min-strings", type=int, default=3)
    p_hunt.add_argument("--japanese-only", action="store_true")
    p_hunt.add_argument("--translation-filter", action="store_true")
    p_hunt.add_argument("--langs", default="ja,en")
    p_hunt.add_argument("-o", "--output", default="out/hot_text_functions.json")
    p_hunt.set_defaults(func=cmd_hunt_text)

    p_rep = sub.add_parser("report", help="Rapport depuis config JSON")
    p_rep.add_argument("config", type=Path)
    p_rep.add_argument("-o", "--output", type=Path, default=Path("out/report"))
    p_rep.set_defaults(func=cmd_report)

    p_sg = sub.add_parser("scan-graphics", help="Scanner arborescence FHM/GIM/ARC")
    p_sg.add_argument("root", type=Path, help="Dossier ou fichier")
    p_sg.add_argument("-o", "--output", default="out/graphics_scan.json")
    p_sg.set_defaults(func=cmd_scan_graphics)

    p_inv = sub.add_parser("inventory-fhm", help="Inventaire FHM + candidats traduction")
    p_inv.add_argument("fhm", type=Path)
    p_inv.add_argument("-o", "--output", default="out/fhm_inventory.json")
    p_inv.set_defaults(func=cmd_inventory_fhm)

    p_prb = sub.add_parser("probe-chunk", help="Identifier compression d'un chunk ou ITE")
    p_prb.add_argument("file", type=Path)
    p_prb.add_argument("--offset", default="0", help="Offset chunk (hex)")
    p_prb.add_argument("--size", type=lambda x: int(x, 0), default=0x200)
    p_prb.add_argument("--ite", help="Offset ITE (hex) — sonde toutes les tuiles")
    p_prb.add_argument("--expected", type=int, default=2048, help="Taille sortie attendue")
    p_prb.add_argument("-o", "--output")
    p_prb.set_defaults(func=cmd_probe_chunk)

    p_ext = sub.add_parser("extract-graphics", help="Extraire ITE d'un FHM en PNG")
    p_ext.add_argument("fhm", type=Path)
    p_ext.add_argument("-o", "--output", type=Path, default=Path("out/graphics"))
    p_ext.add_argument("--entries", help="Indices FHM (ex. 1,3,4)")
    p_ext.add_argument("--tiles", action="store_true", help="Exporter aussi chaque tuile 64x32")
    p_ext.add_argument("--no-probe", action="store_true")
    p_ext.set_defaults(func=cmd_extract_graphics)

    p_hc = sub.add_parser("hunt-codec", help="Fingerprint codec custom dans ELF .text")
    p_hc.add_argument("elf", type=Path)
    p_hc.add_argument("-o", "--output", default="out/codec_hits.json")
    p_hc.set_defaults(func=cmd_hunt_codec)

    p_id = sub.add_parser("identify-compression", help="Workflow complet identification compression")
    p_id.add_argument("--asset", type=Path, help="FHM ou fichier asset")
    p_id.add_argument("--elf", type=Path, help="Exécutable EE pour fingerprint")
    p_id.add_argument("--ee-dump", type=Path, help="eeMemory.bin pour analyse Ghidra")
    p_id.add_argument("--chunk-offset", help="Offset chunk à sonder (hex)")
    p_id.add_argument("--chunk-size", type=lambda x: int(x, 0))
    p_id.add_argument("-o", "--output", default="out/compression_report.json")
    p_id.set_defaults(func=cmd_identify_compression)

    p_t2s = sub.add_parser("scan-tim2", help="Chercher fichiers TIM2 (.tm2 ou embarqués)")
    p_t2s.add_argument("root", type=Path, help="Dossier ISO décompressé ou fichier")
    p_t2s.add_argument("--embedded", action="store_true", help="Scanner TIM2 dans archives/.bin")
    p_t2s.add_argument("-o", "--output", default="out/tim2_scan.json")
    p_t2s.set_defaults(func=cmd_scan_tim2)

    p_t2i = sub.add_parser("tim2-info", help="Infos structure TIM2")
    p_t2i.add_argument("file", type=Path)
    p_t2i.add_argument("-o", "--output", help="Export JSON")
    p_t2i.set_defaults(func=cmd_tim2_info)

    p_t2e = sub.add_parser("tim2-export", help="Exporter TIM2 → PNG (+ CLUT)")
    p_t2e.add_argument("file", type=Path)
    p_t2e.add_argument("-o", "--output", type=Path, default=Path("out/tim2"))
    p_t2e.add_argument("--picture", type=int, help="Index image (défaut: toutes)")
    p_t2e.add_argument("--no-clut", action="store_true")
    p_t2e.set_defaults(func=cmd_tim2_export)

    p_t2r = sub.add_parser("tim2-replace", help="Réimporter PNG modifié dans TIM2")
    p_t2r.add_argument("file", type=Path, help="TIM2 source")
    p_t2r.add_argument("png", type=Path, help="PNG édité (mêmes dimensions)")
    p_t2r.add_argument("-o", "--output", type=Path, required=True)
    p_t2r.add_argument("--picture", type=int, default=0)
    p_t2r.add_argument("--clut", type=Path, help="PNG palette optionnel")
    p_t2r.set_defaults(func=cmd_tim2_replace)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
