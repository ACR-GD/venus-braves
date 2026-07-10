"""Démarrage PyGhidra et détection de l'installation Ghidra."""

from __future__ import annotations

import glob
import os
from pathlib import Path

_GHIDRA_STARTED = False


def find_ghidra_install() -> Path | None:
    """Cherche Ghidra (env, Homebrew, Applications)."""
    env = os.environ.get("GHIDRA_INSTALL_DIR")
    if env:
        p = Path(env)
        if (p / "Ghidra").exists() or (p / "support").exists():
            return p

    for pattern in (
        "/opt/homebrew/Cellar/ghidra/*/libexec",
        "/usr/local/Cellar/ghidra/*/libexec",
        "/Applications/ghidra_*/ghidra_*",
    ):
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return Path(matches[0])
    return None


def ensure_started(install_dir: Path | str | None = None) -> Path:
    """Démarre la JVM Ghidra une seule fois."""
    global _GHIDRA_STARTED

    if install_dir is None:
        install_dir = find_ghidra_install()
    if install_dir is None:
        raise RuntimeError(
            "Ghidra introuvable. Définissez GHIDRA_INSTALL_DIR "
            "(ex. /opt/homebrew/Cellar/ghidra/12.1.1/libexec)."
        )

    install_dir = Path(install_dir)
    os.environ["GHIDRA_INSTALL_DIR"] = str(install_dir)

    if not _GHIDRA_STARTED:
        import pyghidra

        pyghidra.start(install_dir=install_dir)
        _GHIDRA_STARTED = True

    return install_dir
