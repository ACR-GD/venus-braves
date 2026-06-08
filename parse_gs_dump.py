#!/usr/bin/env python3
"""
parse_gs_dump.py
================
Parses a PCSX2 GS dump file (.gs) to extract texture upload information
(BITBLTBUF, TEX0, TRXREG, TRXPOS registers) and pixel data.

This gives us the TBP0, TBW, PSM values needed to decode/encode
the Venus & Braves menu button textures in btlst1.arc.

Usage:
    python3 parse_gs_dump.py path/to/dump.gs
"""

import argparse
import struct, sys, os
from PIL import Image

# ── GS register IDs (from PS2 GS User's Manual) ──────────────────────────────

GS_REGS = {
    0x00: "PRIM",
    0x01: "RGBAQ",
    0x02: "ST",
    0x03: "UV",
    0x04: "XYZF2",
    0x05: "XYZ2",
    0x06: "TEX0_1",
    0x07: "TEX0_2",
    0x08: "CLAMP_1",
    0x09: "CLAMP_2",
    0x0A: "FOG",
    0x0C: "XYZF3",
    0x0D: "XYZ3",
    0x14: "TEX1_1",
    0x15: "TEX1_2",
    0x16: "TEX2_1",
    0x17: "TEX2_2",
    0x18: "XYOFFSET_1",
    0x19: "XYOFFSET_2",
    0x1A: "PRMODECONT",
    0x1B: "PRMODE",
    0x1C: "TEXCLUT",
    0x22: "SCANMSK",
    0x34: "MIPTBP1_1",
    0x35: "MIPTBP1_2",
    0x36: "MIPTBP2_1",
    0x37: "MIPTBP2_2",
    0x3B: "TEXA",
    0x3D: "FOGCOL",
    0x3F: "TEXFLUSH",
    0x40: "SCISSOR_1",
    0x41: "SCISSOR_2",
    0x42: "ALPHA_1",
    0x43: "ALPHA_2",
    0x44: "DIMX",
    0x45: "DTHE",
    0x46: "COLCLAMP",
    0x47: "TEST_1",
    0x48: "TEST_2",
    0x49: "PABE",
    0x4A: "FBA_1",
    0x4B: "FBA_2",
    0x4C: "FRAME_1",
    0x4D: "FRAME_2",
    0x4E: "ZBUF_1",
    0x4F: "ZBUF_2",
    0x50: "BITBLTBUF",
    0x51: "TRXPOS",
    0x52: "TRXREG",
    0x53: "TRXDIR",
    0x54: "HWREG",
    0x60: "SIGNAL",
    0x61: "FINISH",
    0x62: "LABEL",
}

PSM_NAMES = {
    0x00: "PSMCT32",
    0x01: "PSMCT24",
    0x02: "PSMCT16",
    0x0A: "PSMCT16S",
    0x13: "PSMT8",
    0x14: "PSMT4",
    0x1B: "PSMT8H",
    0x24: "PSMT4HL",
    0x2C: "PSMT4HH",
    0x30: "PSMZ32",
    0x31: "PSMZ24",
    0x32: "PSMZ16",
    0x3A: "PSMZ16S",
}


def parse_tex0(val):
    """Parse TEX0 GS register (64-bit)."""
    tbp0 = val & 0x3FFF
    tbw  = (val >> 14) & 0x3F
    psm  = (val >> 20) & 0x3F
    tw   = (val >> 26) & 0xF
    th   = (val >> 30) & 0xF
    tcc  = (val >> 34) & 0x1
    tfx  = (val >> 35) & 0x3
    cbp  = (val >> 37) & 0x3FFF
    cpsm = (val >> 51) & 0xF
    csm  = (val >> 55) & 0x1
    csa  = (val >> 56) & 0x1F
    cld  = (val >> 61) & 0x7

    tex_w = 1 << tw if tw > 0 else 1
    tex_h = 1 << th if th > 0 else 1

    return {
        "TBP0": tbp0,
        "TBW":  tbw,
        "PSM":  psm,
        "PSM_name": PSM_NAMES.get(psm, f"unknown_0x{psm:02X}"),
        "TW":   tw,
        "TH":   th,
        "tex_width":  tex_w,
        "tex_height": tex_h,
        "TCC":  tcc,
        "TFX":  tfx,
        "CBP":  cbp,
        "CPSM": cpsm,
        "CSM":  csm,
        "CSA":  csa,
        "CLD":  cld,
    }


def parse_bitbltbuf(val):
    """Parse BITBLTBUF GS register (64-bit)."""
    sbp  = val & 0x3FFF
    sbw  = (val >> 16) & 0x3F
    spsm = (val >> 24) & 0x3F
    dbp  = (val >> 32) & 0x3FFF
    dbw  = (val >> 48) & 0x3F
    dpsm = (val >> 56) & 0x3F
    return {
        "SBP": sbp, "SBW": sbw, "SPSM": spsm,
        "DBP": dbp, "DBW": dbw, "DPSM": dpsm,
        "SPSM_name": PSM_NAMES.get(spsm, f"0x{spsm:02X}"),
        "DPSM_name": PSM_NAMES.get(dpsm, f"0x{dpsm:02X}"),
    }


def parse_trxpos(val):
    ssax = val & 0x7FF
    ssay = (val >> 16) & 0x7FF
    dsax = (val >> 32) & 0x7FF
    dsay = (val >> 48) & 0x7FF
    dir_ = (val >> 59) & 0x3
    return {"SSAX": ssax, "SSAY": ssay, "DSAX": dsax, "DSAY": dsay, "DIR": dir_}


def parse_trxreg(val):
    rrw = val & 0xFFF
    rrh = (val >> 32) & 0xFFF
    return {"RRW": rrw, "RRH": rrh}


def parse_frame(val):
    fbp  = val & 0x1FF
    fbw  = (val >> 16) & 0x3F
    psm  = (val >> 24) & 0x3F
    fbmsk = (val >> 32)
    return {
        "FBP": fbp, "FBW": fbw, "PSM": psm,
        "PSM_name": PSM_NAMES.get(psm, f"0x{psm:02X}"),
        "FBMSK": fbmsk,
    }


# ── PCSX2 .gs file format ─────────────────────────────────────────────────────
# Header: "GS\x01\x00" (4 bytes) or similar
# Then: GIF packet data (raw VIF/DMA-stripped GIF tags)

def parse_gif_packets(data, verbose=False, current_xfer=None):
    """
    Parse a stream of GIF packets and extract register writes and IMAGE data.
    Returns (events, current_xfer) so transfer state can carry across calls.
    """
    events = []
    pos = 0

    while pos + 16 <= len(data):
        # GIF tag: 128 bits = 16 bytes
        lo = struct.unpack_from("<Q", data, pos)[0]
        hi = struct.unpack_from("<Q", data, pos + 8)[0]
        pos += 16

        nloop = lo & 0x7FFF
        eop   = (lo >> 15) & 1
        pre   = (lo >> 46) & 1
        prim  = (lo >> 47) & 0x7FF
        flg   = (lo >> 58) & 3    # 0=PACKED, 1=REGLIST, 2=IMAGE, 3=DISABLE
        nreg  = (lo >> 60) & 0xF  # actual count = nreg or 16 if 0

        nreg_actual = nreg if nreg > 0 else 16

        if verbose:
            print(f"  GIF @0x{pos-16:06X}: nloop={nloop} eop={eop} flg={flg} nreg={nreg_actual}")

        if flg == 2:
            # IMAGE mode: nloop qwords of raw pixel data
            px_data = data[pos:pos + nloop * 16]
            pos += nloop * 16

            if current_xfer:
                current_xfer["data"].extend(px_data)
            continue

        elif flg == 0:
            # PACKED mode: nloop × nreg registers
            reg_ids = []
            for r in range(nreg_actual):
                reg_ids.append((hi >> (r * 4)) & 0xF)  # REGS field (only 4 bits per reg)

            # Actually REGS is in the high qword differently:
            # REGS[0] = bits 60-63 of lo? No...
            # GIF tag format: 
            #   qword[63:60] = NREG
            #   qword[59:58] = FLG
            #   qword[57:47] = PRIM
            #   qword[46] = PRE
            #   qword[45:16] = (unused in PACKED mode)
            #   qword[15] = EOP
            #   qword[14:0] = NLOOP
            #   qword[127:64] = REGS (4 bits per register descriptor, 16 max)

            reg_ids = []
            for r in range(nreg_actual):
                reg_ids.append((hi >> (r * 4)) & 0xF)

            for loop in range(nloop):
                for r_idx, reg_desc in enumerate(reg_ids):
                    if pos + 16 > len(data):
                        break
                    qlo = struct.unpack_from("<Q", data, pos)[0]
                    qhi = struct.unpack_from("<Q", data, pos + 8)[0]
                    pos += 16

                    # reg_desc 0x0E = AD (register with Address in upper bytes)
                    if reg_desc == 0x0E:
                        actual_reg = qhi & 0xFF
                        val = qlo
                        reg_name = GS_REGS.get(actual_reg, f"REG_0x{actual_reg:02X}")

                        if actual_reg == 0x06 or actual_reg == 0x07:  # TEX0_1 or TEX0_2
                            parsed = parse_tex0(val)
                            ev = {"type": "TEX0", "reg": actual_reg, "raw": val, **parsed}
                            events.append(ev)
                            if verbose:
                                print(f"    TEX0: TBP0=0x{parsed['TBP0']:04X} TBW={parsed['TBW']} "
                                      f"PSM={parsed['PSM_name']} {parsed['tex_width']}x{parsed['tex_height']}")

                        elif actual_reg == 0x50:  # BITBLTBUF
                            parsed = parse_bitbltbuf(val)
                            # Finalize previous upload if it has data
                            if current_xfer and len(current_xfer["data"]) > 0:
                                events.append(current_xfer)
                                if verbose:
                                    sz = len(current_xfer["data"])
                                    bb = current_xfer["bitbltbuf"]
                                    print(f"    → IMAGE transfer complete: {sz} bytes → DBP=0x{bb['DBP']:04X} DBW={bb['DBW']} DPSM={bb['DPSM_name']}")
                            current_xfer = {
                                "type": "TEXTURE_UPLOAD",
                                "bitbltbuf": parsed,
                                "trxpos": None,
                                "trxreg": None,
                                "data": bytearray(),
                                "offset": pos,
                            }
                            events.append({"type": "BITBLTBUF", "raw": val, **parsed})
                            if verbose:
                                print(f"    BITBLTBUF: DBP=0x{parsed['DBP']:04X} DBW={parsed['DBW']} "
                                      f"DPSM={parsed['DPSM_name']}")

                        elif actual_reg == 0x51:  # TRXPOS
                            parsed = parse_trxpos(val)
                            if current_xfer:
                                current_xfer["trxpos"] = parsed
                            events.append({"type": "TRXPOS", "raw": val, **parsed})
                            if verbose:
                                print(f"    TRXPOS: DSAX={parsed['DSAX']} DSAY={parsed['DSAY']}")

                        elif actual_reg == 0x52:  # TRXREG
                            parsed = parse_trxreg(val)
                            if current_xfer:
                                current_xfer["trxreg"] = parsed
                            events.append({"type": "TRXREG", "raw": val, **parsed})
                            if verbose:
                                print(f"    TRXREG: {parsed['RRW']}x{parsed['RRH']}")

                        elif actual_reg == 0x53:  # TRXDIR (0=host-to-local = upload)
                            direction = val & 0x3
                            events.append({"type": "TRXDIR", "direction": direction})

                        elif actual_reg in (0x4C, 0x4D):  # FRAME_1 or FRAME_2
                            parsed = parse_frame(val)
                            events.append({"type": "FRAME", "reg": actual_reg, **parsed})
                            if verbose:
                                print(f"    FRAME: FBP=0x{parsed['FBP']:04X} FBW={parsed['FBW']} "
                                      f"PSM={parsed['PSM_name']}")

        elif flg == 1:
            # REGLIST mode
            pos += nloop * nreg_actual * 8

    return events, current_xfer


def decode_upload_pixels(up):
    """Decode raw pixel data from a TEXTURE_UPLOAD event into an RGBA Image.

    Returns an Image or None if the format is not directly decodable.
    """
    bb = up["bitbltbuf"]
    tr = up["trxreg"]
    w, h = tr["RRW"], tr["RRH"]
    dpsm = bb["DPSM"]
    raw = bytes(up["data"])

    if w == 0 or h == 0:
        return None

    if dpsm == 0x00:  # PSMCT32 – 4 bytes/pixel (R G B A)
        expected = w * h * 4
        if len(raw) < expected:
            raw = raw + b"\x00" * (expected - len(raw))
        img = Image.frombytes("RGBA", (w, h), raw[:expected], "raw", "RGBA")
        return img

    if dpsm == 0x01:  # PSMCT24 – stored as 32-bit with A ignored
        expected = w * h * 4
        if len(raw) < expected:
            raw = raw + b"\x00" * (expected - len(raw))
        img = Image.frombytes("RGBX", (w, h), raw[:expected], "raw", "RGBX")
        return img.convert("RGB")

    if dpsm in (0x02, 0x0A):  # PSMCT16 / PSMCT16S – ABGR-1555
        expected = w * h * 2
        if len(raw) < expected:
            raw = raw + b"\x00" * (expected - len(raw))
        pixels = bytearray(w * h * 4)
        for i in range(w * h):
            val = struct.unpack_from("<H", raw, i * 2)[0]
            r = (val & 0x1F) << 3
            g = ((val >> 5) & 0x1F) << 3
            b = ((val >> 10) & 0x1F) << 3
            a = 0xFF if (val >> 15) & 1 else 0
            pixels[i * 4:i * 4 + 4] = bytes((r, g, b, a))
        img = Image.frombytes("RGBA", (w, h), bytes(pixels))
        return img

    # Indexed / Z-buffer formats – not directly decodable without CLUT
    return None


def save_upload(up, index, output_dir):
    """Save a single TEXTURE_UPLOAD event to output_dir.

    Saves a .png if the pixel format is directly decodable, otherwise
    saves the raw data as a .bin.
    """
    bb = up["bitbltbuf"]
    tr = up["trxreg"]
    w, h = tr["RRW"], tr["RRH"]
    base = f"upload_{index:03d}_DBP0x{bb['DBP']:04X}_{bb['DPSM_name']}_{w}x{h}"

    img = decode_upload_pixels(up)
    if img is not None:
        out_path = os.path.join(output_dir, base + ".png")
        img.save(out_path)
        print(f"    → saved {out_path}")
    else:
        out_path = os.path.join(output_dir, base + ".bin")
        with open(out_path, "wb") as f:
            f.write(bytes(up["data"]))
        print(f"    → saved raw {out_path}")


# ── PCSX2 new-format dump header (magic 0xFFFFFFFF) ──────────────────────────
#
# Layout from GSDump.h / GSLzma.cpp:
#   [0xFFFFFFFF/4]  [header_blob_size/4]  [header_blob/header_blob_size]
#   [state_data/header.state_size]  [regs/8192]  [packets...]
#
# GSDumpHeader (36 bytes, packed):
#   u32 state_version, state_size, serial_offset, serial_size, crc,
#       screenshot_width, screenshot_height, screenshot_offset, screenshot_size
#
# Old format (no 0xFFFFFFFF magic):
#   [crc/4]  [state_size/4]  [state_data/state_size]  [regs/8192]  [packets...]
#
# Packet types:
#   0 = Transfer: [path/1] [length/4] [gif_data/length]
#   1 = VSync:    [field/1]
#   2 = ReadFIFO2: (4 bytes)
#   3 = Registers: (8192 bytes)

_GSDUMP_HEADER_STRUCT = struct.Struct("<9I")  # 9 × u32 = 36 bytes


def _read_dump_header(data):
    """Parse a PCSX2 .gs dump and return (info_dict, packets_offset)."""
    magic = struct.unpack_from("<I", data, 0)[0]

    if magic == 0xFFFFFFFF:
        # ── New format ────────────────────────────────────────────
        header_blob_size = struct.unpack_from("<I", data, 4)[0]
        blob = data[8 : 8 + header_blob_size]
        fields = _GSDUMP_HEADER_STRUCT.unpack_from(blob, 0)
        (
            state_version, state_size,
            serial_off, serial_size,
            crc,
            ss_w, ss_h, ss_off, ss_size,
        ) = fields

        serial = blob[serial_off : serial_off + serial_size].decode("ascii", errors="replace")

        after_blob = 8 + header_blob_size
        packets_off = after_blob + state_size + 8192  # state + PMODE regs

        info = {
            "format": "new",
            "state_version": state_version,
            "state_size": state_size,
            "serial": serial,
            "crc": crc,
            "screenshot_size": (ss_w, ss_h),
        }
        return info, packets_off

    # ── Old format (crc + state_size) ─────────────────────────────
    crc = magic
    state_size = struct.unpack_from("<I", data, 4)[0]
    packets_off = 8 + state_size + 8192
    info = {
        "format": "old",
        "crc": crc,
        "state_size": state_size,
    }
    return info, packets_off


def _iter_packets(data, packets_off):
    """Yield (type_id, payload_bytes) for each command packet."""
    pos = packets_off
    end = len(data)
    while pos < end:
        pkt_id = data[pos]; pos += 1
        if pkt_id == 0:    # Transfer
            if pos + 5 > end:
                break
            path = data[pos]; pos += 1
            length = struct.unpack_from("<I", data, pos)[0]; pos += 4
            payload = data[pos : pos + length]; pos += length
            yield (0, path, payload)
        elif pkt_id == 1:  # VSync
            if pos >= end:
                break
            field = data[pos]; pos += 1
            yield (1, field, b"")
        elif pkt_id == 2:  # ReadFIFO2
            pos += 4
            yield (2, 0, b"")
        elif pkt_id == 3:  # Registers
            pos += 8192
            yield (3, 0, b"")
        else:
            print(f"  Warning: unknown packet id {pkt_id} at offset 0x{pos-1:X}, stopping")
            break


def parse_gs_dump(path, output_dir=None):
    """Parse a PCSX2 .gs dump file and print texture info."""
    print(f"Parsing GS dump: {path}")
    print(f"File size: {os.path.getsize(path)} bytes")
    print()

    with open(path, "rb") as f:
        data = f.read()

    info, packets_off = _read_dump_header(data)
    fmt = info["format"]
    print(f"Format: {fmt}")
    if "serial" in info:
        print(f"Serial: {info['serial']}  CRC: 0x{info['crc']:08X}")
    print(f"Packets start at: 0x{packets_off:X}")
    print(f"Packet data: {len(data) - packets_off} bytes")
    print()

    # Parse each GIF transfer packet independently, carrying state across
    # packets so that BITBLTBUF→IMAGE sequences that span packets still work.
    transfer_count = 0
    total_gif = 0
    events = []
    current_xfer = None
    for pkt_id, meta, payload in _iter_packets(data, packets_off):
        if pkt_id == 0:  # Transfer
            transfer_count += 1
            total_gif += len(payload)
            new_events, current_xfer = parse_gif_packets(
                payload, verbose=True, current_xfer=current_xfer,
            )
            events.extend(new_events)

    # Finalize any remaining in-progress upload
    if current_xfer and len(current_xfer["data"]) > 0:
        events.append(current_xfer)

    print(f"Transfer packets: {transfer_count} ({total_gif} bytes of GIF data)")

    # Summary
    print()
    print("=" * 60)
    print("TEXTURE UPLOADS FOUND:")
    print("=" * 60)

    uploads = [e for e in events if e["type"] == "TEXTURE_UPLOAD" and e.get("trxreg")]
    for i, up in enumerate(uploads):
        bb = up["bitbltbuf"]
        tr = up["trxreg"]
        tp = up["trxpos"]
        data_sz = len(up["data"])
        print(f"\nUpload #{i+1}:")
        print(f"  Destination: DBP=0x{bb['DBP']:04X}  DBW={bb['DBW']}  PSM={bb['DPSM_name']}")
        if tp:
            print(f"  Position: DSAX={tp['DSAX']} DSAY={tp['DSAY']}")
        if tr:
            print(f"  Size: {tr['RRW']}x{tr['RRH']} pixels")
        print(f"  Data: {data_sz} bytes")
        if output_dir:
            save_upload(up, i + 1, output_dir)

    print()
    print("=" * 60)
    print("TEX0 REGISTER WRITES (textures used for drawing):")
    print("=" * 60)
    tex0_events = [e for e in events if e["type"] == "TEX0"]
    seen = set()
    for e in tex0_events:
        key = (e["TBP0"], e["TBW"], e["PSM"])
        if key not in seen:
            seen.add(key)
            print(f"  TBP0=0x{e['TBP0']:04X}  TBW={e['TBW']}  PSM={e['PSM_name']}  "
                  f"size={e['tex_width']}x{e['tex_height']}  CBP=0x{e['CBP']:04X}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse a PCSX2 GS dump file (.gs) to extract texture upload information.",
        epilog=(
            "To capture a GS dump in PCSX2:\n"
            "  1. Navigate to the title screen (menu buttons visible)\n"
            "  2. Press Shift+F8\n"
            "  3. Find the .gs file in your PCSX2 folder\n"
            "  4. Run: python3 parse_gs_dump.py path/to/dump.gs"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("dump", help="Path to the PCSX2 .gs dump file")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Directory to write extracted textures to")
    args = parser.parse_args()

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    parse_gs_dump(args.dump, output_dir=args.output_dir)
