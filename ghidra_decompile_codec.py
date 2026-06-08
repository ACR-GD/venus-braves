#!/usr/bin/env python3
"""Analyse pyghidra du codec Venus & Braves (eeMemory.bin)."""
import os
from pathlib import Path

GHIDRA = "/opt/homebrew/Cellar/ghidra/12.1.1/libexec"
os.environ["GHIDRA_INSTALL_DIR"] = GHIDRA

import pyghidra

pyghidra.start(install_dir=GHIDRA)

from ghidra.app.cmd.disassemble import DisassembleCommand  # type: ignore
from ghidra.program.model.address import AddressSet  # type: ignore
from ghidra.app.decompiler import DecompInterface  # type: ignore
from ghidra.program.model.symbol import SourceType  # type: ignore
from ghidra.util.task import ConsoleTaskMonitor  # type: ignore

EE = Path("/Users/acr/Develop/venus-braves/option_savestate/extracted/eeMemory.bin")
OUT = Path("/Users/acr/Develop/venus-braves/scratch/ghidra_out")
OUT.mkdir(parents=True, exist_ok=True)

# Fonctions connues du pipeline de décompression
FUNCS = {
    0x1AEF00: "BitState_Clear",
    0x1AEF10: "BitState_Init",
    0x1AEF20: "ReadBits",
    0x1AEFB8: "Scratchpad_Init",
    0x1AFB08: "VU1_Microcode_Load",
    0x1AFC08: "DecodePlane",
    0x1AFDC8: "TextureUpload_Main",
    0x1AF990: "TextureDesc_Setup",
    0x1B9A58: "DMA_Wait",
}

# Appelants / zone upload
EXTRA = [0x1AFF00, 0x1B00B4, 0x1B0218, 0x1B0378, 0x1B04EC]


def create_function(flat_api, addr, name):
    program = flat_api.getCurrentProgram()
    fm = program.getFunctionManager()
    func = fm.getFunctionAt(flat_api.toAddr(addr))
    if func is None:
        flat_api.createFunction(flat_api.toAddr(addr), name)
        func = fm.getFunctionAt(flat_api.toAddr(addr))
    if func is not None:
        func.setName(name, SourceType.USER_DEFINED)
    return func


def decompile(program, func):
    ifunc = DecompInterface()
    ifunc.openProgram(program)
    res = ifunc.decompileFunction(func, 120, ConsoleTaskMonitor())
    if res.decompileCompleted():
        return res.getDecompiledFunction().getC()
    return f"// DECOMPILE FAILED: {res.getErrorMessage()}"


def disasm_range(flat_api, start, length=0x200):
    listing = flat_api.getCurrentProgram().getListing()
    lines = []
    addr = flat_api.toAddr(start)
    end = start + length
    while addr.getOffset() < end:
        ins = listing.getInstructionAt(addr)
        if ins is None:
            break
        lines.append(f"{ins.getAddress()}  {ins}")
        addr = ins.getMaxAddress().add(1)
    return "\n".join(lines)


from pyghidra import open_program

report = []

with open_program(
    str(EE),
    project_location=OUT,
    project_name="vb_codec3",
    language="MIPS:LE:64:default",
    loader="ghidra.app.util.opinion.BinaryLoader",
    analyze=False,
) as flat_api:
    program = flat_api.getCurrentProgram()

    monitor = ConsoleTaskMonitor()

    # Désassembler agressivement chaque fonction + zone upload
    ranges = [
        (0x1AEF00, 0x1B0000),
        (0x1AFDC8, 0x1B0600),
        (0x1AF990, 0x1AFC00),
        (0x1B9A00, 0x1B9B00),
    ]
    for start, end in ranges:
        addr_set = AddressSet(flat_api.toAddr(start), flat_api.toAddr(end))
        cmd = DisassembleCommand(addr_set, None, True)
        cmd.applyTo(program, monitor)

    # Créer les fonctions nommées
    func_objs = {}
    for addr, name in FUNCS.items():
        func_objs[addr] = create_function(flat_api, addr, name)

    # Décompiler chaque fonction
    for addr, name in FUNCS.items():
        func = func_objs.get(addr)
        if func is None:
            report.append(f"\n{'='*60}\n// {name} @ {addr:#x} — FUNCTION NOT CREATED\n")
            continue
        c = decompile(program, func)
        report.append(f"\n{'='*60}\n// {name} @ {addr:#08x}\n{'='*60}\n{c}\n")

    # Désassemblage de la zone upload (boucle tuiles)
    report.append(f"\n{'='*60}\n// DISASM upload loop 0x1afeb8..0x1b0520\n{'='*60}\n")
    report.append(disasm_range(flat_api, 0x1AFEB8, 0x680))

out_file = OUT / "codec_decompiled.c"
out_file.write_text("".join(report), encoding="utf-8")
print(f"Wrote {out_file} ({out_file.stat().st_size} bytes)")
