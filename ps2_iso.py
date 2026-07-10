#!/usr/bin/env python3
"""
ps2_iso.py — Rebuild ISO PS2 (patch in-place, archives Namco, checklist).

Workflow recommandé :
  1. ps2_iso.py inventory game.iso -o out/iso_files.json
  2. ps2_iso.py unpack-archive extracted_iso/IMAGE/CDIMAGE.BIN -o cdimage_unpacked
  3. (modifier fichiers : FHM, TIM2, ELF, textes…)
  4. ps2_iso.py verify-unpacked cdimage_unpacked
  5. ps2_iso.py verify-build ps2_re/examples/venus_iso_build.json
  6. ps2_iso.py build ps2_re/examples/venus_iso_build.json
  7. ps2_iso.py checklist
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ps2_re.iso_build import (
    build_iso,
    default_checklist,
    inventory_to_json,
    load_manifest,
    verify_build_manifest,
)
from ps2_re.iso9660 import inventory_iso, max_extent_before_next
from ps2_re.namco_archive import (
    analyze_archive,
    repack_archive,
    unpack_archive,
    verify_unpacked,
)


def cmd_inventory(args: argparse.Namespace) -> int:
    data = inventory_to_json(args.iso.resolve())
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Inventaire -> {out}")
    for f in data["files"]:
        print(f"  {f['path']:<30}  LBA={f['lba']:<8}  {f['size']:>12,} o")
    print(f"Total: {data['file_count']} fichiers")
    return 0


def cmd_checklist(_: argparse.Namespace) -> int:
    for item in default_checklist():
        print(f"  [{item['id']}] {item['task']}")
        print(f"       {item['cmd']}")
    return 0


def cmd_unpack_archive(args: argparse.Namespace) -> int:
    info = unpack_archive(args.archive.resolve(), Path(args.output), save_index_template=True)
    print(f"Décompressé {info.entry_count} entrées → {args.output}")
    print(f"  layout={info.layout}  data_start=0x{info.data_start:X}  size={info.total_size:,}")
    print(f"  archive_index.bin + archive_meta.json sauvegardés")
    return 0


def cmd_verify_unpacked(args: argparse.Namespace) -> int:
    report = verify_unpacked(args.dir.resolve())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        print(f"\n✗ {len(report['missing'])} fichier(s) manquant(s)", file=sys.stderr)
        return 1
    print(f"\n✓ {len(report['files'])} fichiers OK")
    return 0


def cmd_analyze_archive(args: argparse.Namespace) -> int:
    data = args.archive.read_bytes()
    info = analyze_archive(data, args.archive.resolve())
    print(f"Archive: {args.archive}")
    print(f"  entrées: {info.entry_count}")
    print(f"  layout:  {info.layout}")
    print(f"  data_start: 0x{info.data_start:X}")
    print(f"  taille: {info.total_size:,} o")
    for e in info.entries[:10]:
        print(f"    [{e.index}] {e.name}  {e.size:,} o")
    if info.entry_count > 10:
        print(f"    … +{info.entry_count - 10} entrées")
    return 0


def cmd_repack_archive(args: argparse.Namespace) -> int:
    result = repack_archive(
        args.dir.resolve(),
        Path(args.output),
        max_size=args.max_size,
        layout=args.layout,
        index_template=args.index_template.resolve() if args.index_template else None,
    )
    print(f"Repack OK → {result['output']}")
    print(f"  layout={result['layout']}  data_start=0x{result['data_start']:X}")
    print(f"  taille={result['archive_size']:,} o  payload={result['payload_size']:,} o")
    if result["sizes_changed"]:
        print(f"  ⚠ {result['sizes_changed']} tailles modifiées vs template")
    return 0


def cmd_verify_build(args: argparse.Namespace) -> int:
    report = verify_build_manifest(args.manifest.resolve())
    out = Path(args.output) if args.output else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"Rapport -> {out}")
    for c in report.checks:
        mark = "✓" if c.ok else "✗"
        print(f"  {mark} {c.step}: {c.detail}")
    if report.errors:
        print("\nErreurs:")
        for e in report.errors:
            print(f"  ✗ {e}")
        return 1
    print("\n✓ Prêt pour build")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    report = build_iso(args.manifest.resolve(), dry_run=args.dry_run)
    out_report = Path(args.report) if args.report else Path(args.manifest).parent / "build_report.json"
    out_report.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    for c in report.checks:
        mark = "✓" if c.ok else "✗"
        print(f"  {mark} {c.step}: {c.detail}")
    for p in report.patches:
        if p.get("type") == "same_size":
            print(f"  patch {p['path']}: {p['changes']} octets modifiés")
        else:
            print(f"  replace {p['path']}: {p['written']:,} o écrits (+{p.get('padded', 0):,} pad)")

    if report.errors:
        print("\nÉchec:")
        for e in report.errors:
            print(f"  ✗ {e}")
        print(f"Rapport: {out_report}")
        return 1

    if args.dry_run:
        print("\n(dry-run — ISO non écrite)")
    else:
        print(f"\n✓ ISO prête: {report.output_iso}")
    print(f"Rapport: {out_report}")
    return 0


def cmd_extent(args: argparse.Namespace) -> int:
    inv = inventory_iso(args.iso.resolve())
    entry = inv.find(args.path)
    if not entry:
        print(f"Fichier introuvable: {args.path}", file=sys.stderr)
        return 1
    extent = max_extent_before_next(inv, entry)
    print(f"{entry.path}")
    print(f"  LBA {entry.lba}  size={entry.size:,}  offset=0x{entry.iso_offset:X}")
    print(f"  espace max avant fichier suivant: {extent:,} o")
    print(f"  marge si même allocation: {extent - entry.size:,} o")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild ISO PS2 — patch in-place & archives Namco")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inv = sub.add_parser("inventory", help="Lister fichiers ISO9660 (LBA, tailles)")
    p_inv.add_argument("iso", type=Path)
    p_inv.add_argument("-o", "--output", help="Export JSON")
    p_inv.set_defaults(func=cmd_inventory)

    p_chk = sub.add_parser("checklist", help="Checklist rebuild complète")
    p_chk.set_defaults(func=cmd_checklist)

    p_unp = sub.add_parser("unpack-archive", help="Décompresser CDIMAGE/BGMIMAGE/MOVIMAGE")
    p_unp.add_argument("archive", type=Path)
    p_unp.add_argument("-o", "--output", required=True)
    p_unp.set_defaults(func=cmd_unpack_archive)

    p_vu = sub.add_parser("verify-unpacked", help="Vérifier dossier décompressé complet")
    p_vu.add_argument("dir", type=Path)
    p_vu.set_defaults(func=cmd_verify_unpacked)

    p_ana = sub.add_parser("analyze-archive", help="Analyser structure archive Namco")
    p_ana.add_argument("archive", type=Path)
    p_ana.set_defaults(func=cmd_analyze_archive)

    p_rep = sub.add_parser("repack-archive", help="Recompresser archive depuis dossier")
    p_rep.add_argument("dir", type=Path, help="Dossier décompressé")
    p_rep.add_argument("-o", "--output", required=True)
    p_rep.add_argument("--max-size", type=int, help="Taille max (ex. CDIMAGE=373645312)")
    p_rep.add_argument("--layout", choices=["trailing", "forward"])
    p_rep.add_argument("--index-template", type=Path)
    p_rep.set_defaults(func=cmd_repack_archive)

    p_vb = sub.add_parser("verify-build", help="Valider manifeste avant build")
    p_vb.add_argument("manifest", type=Path)
    p_vb.add_argument("-o", "--output", help="Rapport JSON")
    p_vb.set_defaults(func=cmd_verify_build)

    p_bld = sub.add_parser("build", help="Build ISO depuis manifeste JSON")
    p_bld.add_argument("manifest", type=Path)
    p_bld.add_argument("--dry-run", action="store_true")
    p_bld.add_argument("--report", type=Path, help="Chemin rapport build")
    p_bld.set_defaults(func=cmd_build)

    p_ext = sub.add_parser("extent", help="Espace writable avant le fichier ISO suivant")
    p_ext.add_argument("iso", type=Path)
    p_ext.add_argument("path", help="Chemin ISO ex. IMAGE/CDIMAGE.BIN")
    p_ext.set_defaults(func=cmd_extent)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
