"""Désassemblage, décompilation et gestion des fonctions."""

from __future__ import annotations

from typing import Any

from .ghidra_env import ensure_started
from .loaders import parse_addr


def _ghidra():
    ensure_started()
    from ghidra.app.cmd.disassemble import DisassembleCommand  # type: ignore
    from ghidra.app.decompiler import DecompInterface  # type: ignore
    from ghidra.program.model.address import AddressSet  # type: ignore
    from ghidra.program.model.symbol import SourceType  # type: ignore
    from ghidra.util.task import ConsoleTaskMonitor  # type: ignore
    return DisassembleCommand, DecompInterface, AddressSet, SourceType, ConsoleTaskMonitor


def to_addr(flat_api: Any, addr: int):
    return flat_api.toAddr(addr)


def create_function(flat_api: Any, addr: int, name: str | None = None):
    _, _, _, SourceType, _ = _ghidra()
    program = flat_api.getCurrentProgram()
    fm = program.getFunctionManager()
    ghidra_addr = flat_api.toAddr(addr)
    func = fm.getFunctionAt(ghidra_addr)
    if func is None:
        flat_api.createFunction(ghidra_addr, name or f"FUN_{addr:08x}")
        func = fm.getFunctionAt(ghidra_addr)
    if func is not None and name:
        func.setName(name, SourceType.USER_DEFINED)
    return func


def disassemble_range(
    flat_api: Any,
    start: int,
    length: int = 0x200,
    force: bool = True,
) -> str:
    DisassembleCommand, _, AddressSet, _, ConsoleTaskMonitor = _ghidra()
    program = flat_api.getCurrentProgram()
    monitor = ConsoleTaskMonitor()
    if force:
        end = start + length
        addr_set = AddressSet(flat_api.toAddr(start), flat_api.toAddr(end))
        DisassembleCommand(addr_set, None, True).applyTo(program, monitor)

    listing = program.getListing()
    lines: list[str] = []
    addr = flat_api.toAddr(start)
    limit = start + length
    while addr.getOffset() < limit:
        ins = listing.getInstructionAt(addr)
        if ins is None:
            break
        lines.append(f"{ins.getAddress()}  {ins}")
        addr = ins.getMaxAddress().add(1)
    return "\n".join(lines)


def decompile_function(program: Any, func: Any, timeout_sec: int = 120) -> str:
    _, DecompInterface, _, _, ConsoleTaskMonitor = _ghidra()
    iface = DecompInterface()
    iface.openProgram(program)
    res = iface.decompileFunction(func, timeout_sec, ConsoleTaskMonitor())
    if res.decompileCompleted():
        return res.getDecompiledFunction().getC()
    return f"// DECOMPILE FAILED: {res.getErrorMessage()}"


def decompile_at(flat_api: Any, addr: int, name: str | None = None) -> tuple[Any | None, str]:
    func = create_function(flat_api, addr, name)
    if func is None:
        return None, f"// FUNCTION NOT CREATED @ {addr:#x}"
    program = flat_api.getCurrentProgram()
    return func, decompile_function(program, func)


def list_functions(flat_api: Any, limit: int = 200) -> list[dict[str, Any]]:
    program = flat_api.getCurrentProgram()
    fm = program.getFunctionManager()
    out: list[dict[str, Any]] = []
    funcs = fm.getFunctions(True)
    for i, func in enumerate(funcs):
        if i >= limit:
            break
        out.append({
            "name": func.getName(),
            "entry": func.getEntryPoint().getOffset(),
            "size": func.getBody().getNumAddresses(),
        })
    return out


def resolve_addresses(spec: str) -> list[tuple[int, str | None]]:
    """
    Parse une liste d'adresses/noms : '0x1aef20:ReadBits,0x1afc08' ou fichier.
    """
    if "\n" in spec or ";" in spec:
        chunks = [c.strip() for c in spec.replace(";", "\n").splitlines() if c.strip()]
    else:
        chunks = [c.strip() for c in spec.split(",") if c.strip()]

    result: list[tuple[int, str | None]] = []
    for chunk in chunks:
        if ":" in chunk:
            addr_s, name = chunk.split(":", 1)
            result.append((parse_addr(addr_s), name.strip() or None))
        else:
            result.append((parse_addr(chunk), None))
    return result
