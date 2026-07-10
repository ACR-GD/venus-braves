"""Pipeline de rebuild ISO PS2 — manifeste, validation, patch."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .iso9660 import (
    clone_iso,
    inventory_iso,
    max_extent_before_next,
    patch_same_size,
    write_at_lba,
)
from .namco_archive import repack_archive, unpack_archive, verify_unpacked


@dataclass
class BuildCheck:
    step: str
    ok: bool
    detail: str


@dataclass
class BuildReport:
    checks: list[BuildCheck] = field(default_factory=list)
    patches: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    output_iso: str | None = None

    @property
    def success(self) -> bool:
        return not self.errors and all(c.ok for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output_iso": self.output_iso,
            "checks": [{"step": c.step, "ok": c.ok, "detail": c.detail} for c in self.checks],
            "patches": self.patches,
            "errors": self.errors,
        }


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_checklist() -> list[dict[str, str]]:
    return [
        {"id": "1", "task": "ISO originale présente", "cmd": "ps2_iso.py inventory game.iso"},
        {"id": "2", "task": "Archives décompressées (filelist.bin + tous les fichiers)", "cmd": "ps2_iso.py verify-unpacked cdimage_unpacked"},
        {"id": "3", "task": "Modifs appliquées (FHM, TIM2, ELF, textes…)", "cmd": "(vos scripts de traduction)"},
        {"id": "4", "task": "Repack archives Namco", "cmd": "ps2_iso.py repack-archive cdimage_unpacked -o staging/CDIMAGE.BIN"},
        {"id": "5", "task": "Vérifier budgets taille", "cmd": "ps2_iso.py verify-build build.json"},
        {"id": "6", "task": "Build ISO finale", "cmd": "ps2_iso.py build build.json"},
    ]


def inventory_to_json(iso_path: Path) -> dict[str, Any]:
    inv = inventory_iso(iso_path)
    files = [
        {
            "path": e.path,
            "lba": e.lba,
            "size": e.size,
            "iso_offset": f"0x{e.iso_offset:X}",
            "is_dir": e.is_dir,
        }
        for e in sorted(inv.entries, key=lambda x: x.lba)
        if not e.is_dir
    ]
    return {"iso": str(iso_path), "file_count": len(files), "files": files}


def verify_build_manifest(manifest_path: Path) -> BuildReport:
    cfg = load_manifest(manifest_path.resolve())
    base = manifest_path.parent
    report = BuildReport()

    orig = _resolve(cfg["original_iso"], base)
    if not orig.exists():
        report.errors.append(f"ISO originale introuvable: {orig}")
        report.checks.append(BuildCheck("original_iso", False, str(orig)))
    else:
        report.checks.append(BuildCheck("original_iso", True, str(orig)))

    for arch in cfg.get("archives", []):
        unpacked = _resolve(arch["unpacked_dir"], base)
        v = verify_unpacked(unpacked)
        ok = v["ok"]
        detail = f"{len(v.get('files', []))} fichiers" if ok else f"manquants: {v.get('missing')}"
        report.checks.append(BuildCheck(f"archive:{arch.get('name', unpacked.name)}", ok, detail))
        if not ok:
            report.errors.append(f"Archive incomplète: {unpacked}")
        elif ok:
            try:
                proj = projected_archive_size(
                    unpacked,
                    max_size=arch.get("max_size"),
                    layout=arch.get("layout"),
                )
                if proj["overflow"]:
                    report.errors.append(
                        f"{arch.get('name')}: dépasse budget de {proj['overflow']:,} o"
                    )
                    report.checks.append(
                        BuildCheck(f"budget:{arch.get('name')}", False, f"overflow {proj['overflow']:,}")
                    )
                else:
                    report.checks.append(
                        BuildCheck(
                            f"budget:{arch.get('name')}",
                            True,
                            f"payload {proj['payload_size']:,} / {proj['archive_size']:,} o",
                        )
                    )
            except Exception as exc:
                report.errors.append(str(exc))

    if orig.exists():
        inv = inventory_iso(orig)
        for item in cfg.get("same_size_patches", []):
            iso_path = item["iso_path"]
            src = _resolve(item["source"], base)
            entry = inv.find(iso_path)
            if entry is None:
                report.errors.append(f"Fichier ISO introuvable: {iso_path}")
                continue
            if not src.exists():
                report.errors.append(f"Source patch introuvable: {src}")
                continue
            data = src.read_bytes()
            if len(data) != entry.size:
                report.errors.append(
                    f"{iso_path}: taille source {len(data):,} != ISO {entry.size:,}"
                )
            else:
                report.checks.append(BuildCheck(f"same_size:{iso_path}", True, f"{len(data):,} o"))

        for item in cfg.get("replace_files", []):
            iso_path = item["iso_path"]
            src = _resolve(item["source"], base)
            entry = inv.find(iso_path)
            if entry is None:
                report.errors.append(f"Fichier ISO introuvable: {iso_path}")
                continue
            if not src.exists():
                report.errors.append(f"Source replace introuvable: {src}")
                continue
            data = src.read_bytes()
            extent = max_extent_before_next(inv, entry) if item.get("check_extent", True) else None
            max_allowed = item.get("max_size", extent)
            if max_allowed and len(data) > max_allowed:
                report.errors.append(
                    f"{iso_path}: {len(data):,} o > max {max_allowed:,} o"
                )
            else:
                pad = max(0, entry.size - len(data))
                report.checks.append(
                    BuildCheck(
                        f"replace:{iso_path}",
                        True,
                        f"{len(data):,} o (pad {pad:,})",
                    )
                )

    return report


def build_iso(manifest_path: Path, *, dry_run: bool = False) -> BuildReport:
    cfg = load_manifest(manifest_path.resolve())
    base = manifest_path.parent
    report = BuildReport()

    orig = _resolve(cfg["original_iso"], base)
    out = _resolve(cfg.get("output_iso", "output_translated.iso"), base)

    if not orig.exists():
        report.errors.append(f"ISO originale introuvable: {orig}")
        return report

    # 1. Repack archives si demandé
    for arch in cfg.get("archives", []):
        if not arch.get("repack_before_build", True):
            continue
        unpacked = _resolve(arch["unpacked_dir"], base)
        out_arch = _resolve(arch.get("output", f"staging/{arch.get('name', 'ARCHIVE.BIN')}"), base)
        try:
            info = repack_archive(
                unpacked,
                out_arch,
                max_size=arch.get("max_size"),
                layout=arch.get("layout"),
                index_template=_resolve(arch["index_template"], base) if arch.get("index_template") else None,
            )
            report.checks.append(
                BuildCheck("repack", True, f"{arch.get('name')} → {info['archive_size']:,} o")
            )
            # Auto-ajouter au replace_files si absent
            iso_target = arch.get("iso_path", f"IMAGE/{arch.get('name', out_arch.name)}")
            replaces = cfg.setdefault("replace_files", [])
            if not any(r.get("iso_path") == iso_target for r in replaces):
                replaces.append({
                    "iso_path": iso_target,
                    "source": str(out_arch.relative_to(base)) if out_arch.is_relative_to(base) else str(out_arch),
                    "check_extent": True,
                })
        except Exception as exc:
            report.errors.append(f"Repack {arch.get('name')}: {exc}")
            report.checks.append(BuildCheck("repack", False, str(exc)))
            return report

    if dry_run:
        report.checks.append(BuildCheck("dry_run", True, "Aucune écriture ISO"))
        return report

    # 2. Clone ISO
    staging = _resolve(cfg.get("staging_dir", "staging"), base)
    staging.mkdir(parents=True, exist_ok=True)
    work_iso = staging / out.name if cfg.get("use_staging_copy", True) else out
    clone_iso(orig, work_iso)
    report.checks.append(BuildCheck("clone", True, str(work_iso)))

    inv = inventory_iso(work_iso)

    # 3. Same-size patches (ELF, SYSTEM.CNF…)
    for item in cfg.get("same_size_patches", []):
        iso_path = item["iso_path"]
        src = _resolve(item["source"], base)
        entry = inv.find(iso_path)
        if entry is None:
            report.errors.append(f"Introuvable dans ISO: {iso_path}")
            continue
        orig_data = _read_iso_slice(work_iso, entry)
        patch_data = src.read_bytes()
        if len(patch_data) != entry.size:
            report.errors.append(f"{iso_path}: taille patch != ISO")
            continue
        n = patch_same_size(work_iso, entry, orig_data, patch_data)
        report.patches.append({"type": "same_size", "path": iso_path, "changes": n})

    # 4. Replace files (CDIMAGE, TIM2, etc.)
    for item in cfg.get("replace_files", []):
        iso_path = item["iso_path"]
        src = _resolve(item["source"], base)
        entry = inv.find(iso_path)
        if entry is None:
            report.errors.append(f"Introuvable dans ISO: {iso_path}")
            continue
        data = src.read_bytes()
        extent = max_extent_before_next(inv, entry) if item.get("check_extent", True) else None
        if extent and len(data) > extent:
            report.errors.append(f"{iso_path}: déborde ({len(data):,} > {extent:,})")
            continue
        info = write_at_lba(
            work_iso,
            entry,
            data,
            max_extent=extent,
            pad_to_original=item.get("pad_to_original", True),
        )
        info["type"] = "replace"
        report.patches.append(info)

    # 5. Copie finale
    if work_iso != out:
        clone_iso(work_iso, out)

    report.output_iso = str(out)
    report.checks.append(
        BuildCheck("done", True, f"{out} ({out.stat().st_size:,} o)")
    )
    return report


def _resolve(path: str | Path, base: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (base / p).resolve()


def _read_iso_slice(iso_path: Path, entry) -> bytes:
    with iso_path.open("rb") as f:
        f.seek(entry.iso_offset)
        return f.read(entry.size)
