"""Chargement binaire PS2 dans Ghidra (ELF, dumps EE/IOP)."""

from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator, Iterator

from .ghidra_env import ensure_started

try:
    from elftools.elf.elffile import ELFFile
except ImportError:
    ELFFile = None  # type: ignore[misc, assignment]


# Profils courants PS2
PRESETS: dict[str, dict[str, Any]] = {
    # Exécutable EE (SLPS/SLUS/SCUS…) — contourne l'ElfLoader cassé sans plugin EE
    "ee-elf": {
        "language": "MIPS:LE:32:default",
        "loader": "ghidra.app.util.opinion.BinaryLoader",
        "merge_elf_segments": True,
    },
    # Dump RAM EE PCSX2 (adresse fichier ≈ offset basse mémoire)
    "ee-dump": {
        "language": "MIPS:LE:64:default",
        "loader": "ghidra.app.util.opinion.BinaryLoader",
        "image_base": 0,
    },
    # Variante si les adresses EE sont en 0x80xxxxxx dans vos notes
    "ee-dump-high": {
        "language": "MIPS:LE:64:default",
        "loader": "ghidra.app.util.opinion.BinaryLoader",
        "image_base": 0x80000000,
    },
    # IOP (R3000), dumps ou binaires bruts
    "iop-dump": {
        "language": "MIPS:LE:32:default",
        "loader": "ghidra.app.util.opinion.BinaryLoader",
        "image_base": 0,
    },
}


@dataclass
class PS2Target:
    """Description d'une cible à analyser."""

    binary: Path
    preset: str = "ee-elf"
    language: str | None = None
    loader: str | None = None
    image_base: int | None = None
    merge_elf_segments: bool | None = None
    analyze: bool = False
    project_dir: Path | None = None
    project_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_dir: Path | None = None) -> "PS2Target":
        base = base_dir or Path.cwd()
        binary = Path(data["binary"])
        if not binary.is_absolute():
            binary = (base / binary).resolve()
        known = {k: data[k] for k in (
            "preset", "language", "loader", "image_base",
            "merge_elf_segments", "analyze", "project_dir", "project_name",
        ) if k in data}
        if "project_dir" in known and known["project_dir"] is not None:
            pd = Path(known["project_dir"])
            known["project_dir"] = pd if pd.is_absolute() else (base / pd).resolve()
        extra = {k: v for k, v in data.items() if k not in known and k != "binary"}
        return cls(binary=binary, extra=extra, **known)

    @classmethod
    def from_json(cls, path: Path) -> "PS2Target":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data, base_dir=path.parent)


def _preset_values(target: PS2Target) -> dict[str, Any]:
    cfg = dict(PRESETS.get(target.preset, PRESETS["ee-elf"]))
    for key in ("language", "loader", "image_base", "merge_elf_segments"):
        val = getattr(target, key)
        if val is not None:
            cfg[key] = val
    cfg.update(target.extra)
    return cfg


def merge_elf_pt_load(path: Path, out_dir: Path | None = None) -> tuple[Path, int]:
    """Fusionne les segments PT_LOAD d'un ELF PS2 en binaire plat."""
    if ELFFile is None:
        raise RuntimeError("Installez pyelftools : pip install pyelftools")

    out_dir = out_dir or Path(tempfile.mkdtemp(prefix="ps2_re_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    with path.open("rb") as f:
        elf = ELFFile(f)
        loads = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
        if not loads:
            raise ValueError(f"Aucun segment PT_LOAD dans {path}")

        base = min(s["p_vaddr"] for s in loads)
        end = max(s["p_vaddr"] + s["p_memsz"] for s in loads)
        blob = bytearray(end - base)
        for seg in loads:
            data = seg.data()
            off = seg["p_vaddr"] - base
            blob[off : off + len(data)] = data

    out_path = out_dir / f"{path.stem}_merged.bin"
    out_path.write_bytes(blob)
    return out_path, base


def prepare_binary(target: PS2Target) -> tuple[Path, dict[str, Any]]:
    """Prépare le fichier à importer et les options Ghidra."""
    cfg = _preset_values(target)
    src = target.binary

    if cfg.get("merge_elf_segments"):
        if src.suffix.lower() not in (".elf", ".orig", "") and "elf" not in target.preset:
            pass
        elif ELFFile is not None:
            try:
                with src.open("rb") as f:
                    if ELFFile(f).header["e_machine"] == "EM_MIPS":
                        merged, base = merge_elf_pt_load(
                            src,
                            out_dir=target.project_dir or src.parent / "ps2_re_cache",
                        )
                        src = merged
                        if cfg.get("image_base") is None:
                            cfg["image_base"] = base
            except Exception:
                pass

    return src, cfg


@contextmanager
def open_ps2_program(target: PS2Target) -> Generator[Any, None, None]:
    """
    Ouvre un binaire PS2 dans Ghidra.

    Yield un FlatProgramAPI. Gère image base et transaction Ghidra.
    """
    ensure_started()
    from pyghidra import open_program, transaction

    src, cfg = prepare_binary(target)
    project_dir = target.project_dir or (src.parent / "ps2_re_projects")
    project_dir.mkdir(parents=True, exist_ok=True)
    project_name = target.project_name or f"{target.binary.stem}_{target.preset}"

    with open_program(
        str(src),
        project_location=str(project_dir),
        project_name=project_name,
        language=cfg["language"],
        loader=cfg["loader"],
        analyze=target.analyze,
    ) as flat_api:
        program = flat_api.getCurrentProgram()
        image_base = cfg.get("image_base")
        if image_base is not None:
            addr_space = program.getAddressFactory().getDefaultAddressSpace()
            new_base = addr_space.getAddress(int(image_base))
            with transaction(program, "PS2 image base"):
                program.setImageBase(new_base, True)
        yield flat_api


def parse_addr(text: str) -> int:
    """Parse une adresse hex (0x1aef20, 1aef20, @1aef20)."""
    t = text.strip().lower().removeprefix("@")
    if t.startswith("0x"):
        return int(t, 16)
    return int(t, 16)
