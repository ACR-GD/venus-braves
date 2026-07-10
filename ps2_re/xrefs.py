"""Références croisées (xrefs) — qui appelle quoi, qui lit quelle chaîne."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .loaders import parse_addr


@dataclass
class XRef:
    from_addr: int
    to_addr: int
    ref_type: str
    from_function: str | None
    is_call: bool
    is_data: bool


def _func_name_at(program: Any, addr) -> str | None:
    fm = program.getFunctionManager()
    func = fm.getFunctionContaining(addr)
    return func.getName() if func else None


def refs_to(flat_api: Any, target: int | str) -> list[XRef]:
    """Références pointant vers une adresse (ex. début d'une chaîne)."""
    program = flat_api.getCurrentProgram()
    refmgr = program.getReferenceManager()
    addr = flat_api.toAddr(parse_addr(str(target)) if isinstance(target, str) else target)
    out: list[XRef] = []
    for ref in refmgr.getReferencesTo(addr):
        from_addr = ref.getFromAddress()
        out.append(XRef(
            from_addr=from_addr.getOffset(),
            to_addr=addr.getOffset(),
            ref_type=str(ref.getReferenceType()),
            from_function=_func_name_at(program, from_addr),
            is_call=ref.isCall(),
            is_data=not ref.isCall(),
        ))
    return out


def refs_from(flat_api: Any, source: int | str) -> list[XRef]:
    """Références sortantes depuis une adresse ou une fonction."""
    program = flat_api.getCurrentProgram()
    refmgr = program.getReferenceManager()
    addr = flat_api.toAddr(parse_addr(str(source)) if isinstance(source, str) else source)
    out: list[XRef] = []
    for ref in refmgr.getReferencesFrom(addr):
        to_addr = ref.getToAddress()
        out.append(XRef(
            from_addr=addr.getOffset(),
            to_addr=to_addr.getOffset(),
            ref_type=str(ref.getReferenceType()),
            from_function=_func_name_at(program, addr),
            is_call=ref.isCall(),
            is_data=not ref.isCall(),
        ))
    return out


def string_xref_report(
    flat_api: Any,
    string_addrs: list[int],
    min_refs: int = 1,
) -> list[dict[str, Any]]:
    """Pour chaque chaîne, liste les fonctions qui y font référence."""
    rows: list[dict[str, Any]] = []
    for saddr in string_addrs:
        xrefs = refs_to(flat_api, saddr)
        if len(xrefs) < min_refs:
            continue
        funcs = sorted({x.from_function or f"@{x.from_addr:#x}" for x in xrefs})
        rows.append({
            "string_addr": saddr,
            "ref_count": len(xrefs),
            "functions": funcs,
            "code_refs": [x.from_addr for x in xrefs if x.is_call or x.is_data],
        })
    return rows


def hot_text_functions(
    flat_api: Any,
    string_addrs: list[int],
    min_strings: int = 3,
) -> list[dict[str, Any]]:
    """
    Heuristique : fonctions référençant plusieurs chaînes
    (candidats affichage texte / menus / dialogues).
    """
    hits: dict[str, set[int]] = {}
    for saddr in string_addrs:
        for xref in refs_to(flat_api, saddr):
            key = xref.from_function or f"loc_{xref.from_addr:08x}"
            hits.setdefault(key, set()).add(saddr)

    rows = [
        {"function": name, "string_count": len(addrs), "strings": sorted(addrs)}
        for name, addrs in hits.items()
        if len(addrs) >= min_strings
    ]
    return sorted(rows, key=lambda r: r["string_count"], reverse=True)
