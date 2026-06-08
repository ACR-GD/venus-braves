#!/usr/bin/env python3
"""
Venus & Braves Translation Toolkit (vb_toolkit.py)

A unified command-line tool to assist the ROM translation community in extracting,
analyzing, and preparing translation catalogs for Venus & Braves (PS2).

Commands:
  1. unpack   - Unpack game archives (CDIMAGE.BIN, BGMIMAGE.BIN, MOVIMAGE.BIN)
  2. extract  - Extract all game strings from unpacked files and SLPS ELF into categorized, annotated CSVs.
"""

import os
import sys
import csv
import struct
import re
import argparse
import shutil
from pathlib import Path

ALIGNMENT = 0x800

# --- Helper Functions for Unpacking ---
def align_up(value, alignment=ALIGNMENT):
    return (value + (alignment - 1)) & ~(alignment - 1)

def parse_filelist_names(filelist_blob):
    names = []
    # Test if it's text-based (newline separated) or binary (NUL separated)
    if b'\x00' in filelist_blob:
        for part in filelist_blob.split(b"\x00"):
            if len(part) < 4:
                continue
            try:
                text = part.decode("ascii")
                if "/" in text and "." in text:
                    names.append(text)
            except UnicodeDecodeError:
                continue
    else:
        # Newline separated
        lines = filelist_blob.decode('utf-8', errors='ignore').splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            names.append(line)
    return names

def sanitize_relative_path(path_str):
    clean = path_str.replace("\\", "/").strip("/")
    # Strip common developer directories for cleaner local workspace unpacking
    prefixes_to_strip = ["home/tsuyoshi/venus/", "seven_data_link/"]
    for prefix in prefixes_to_strip:
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
    rel = Path(clean)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe path in file list: {path_str!r}")
    return rel

def cmd_unpack(args):
    archive_path = Path(args.archive)
    output_dir = Path(args.output)
    
    if not archive_path.exists():
        print(f"[-] Error: Archive '{archive_path}' not found.")
        sys.exit(1)
        
    file_size = archive_path.stat().st_size
    print(f"[+] Reading archive: {archive_path} ({file_size} bytes)...")

    # Read first 64KB to parse the index table
    with open(archive_path, 'rb') as f:
        header_data = f.read(65536)
        
    dword_count = len(header_data) // 4
    dwords = struct.unpack(f"<{dword_count}I", header_data[: dword_count * 4])
    
    name_offsets = list(dwords[0::2])
    sizes = list(dwords[1::2])
    
    # Extract unique index table entries
    entry_count = 1
    for i in range(1, len(name_offsets)):
        if name_offsets[i] < name_offsets[i - 1] and i > 1:
            # We verify if we reached padding/repeat marker
            break
        entry_count += 1
        
    name_offsets = name_offsets[:entry_count]
    sizes = sizes[:entry_count]
    
    payload_size = sum(align_up(size) for size in sizes)
    data_start = file_size - payload_size
    
    if data_start < 0 or data_start >= file_size:
        print("[-] Error: Invalid index table or computed offsets.")
        sys.exit(1)
        
    print(f"[+] Found {entry_count} archive entries.")
    
    # Read entry 0 which contains filelist names
    first_size = sizes[0]
    with open(archive_path, 'rb') as f:
        f.seek(data_start)
        filelist_blob = f.read(first_size)
        
    parsed_names = parse_filelist_names(filelist_blob)
    expected_paths = max(0, entry_count - 1)
    
    names = ["filelist.bin"]
    for i in range(1, entry_count):
        idx = i - 1
        if idx < len(parsed_names):
            names.append(parsed_names[idx])
        else:
            names.append(f"unknown/{i:05d}.bin")
            
    # Unpack file by file
    output_dir.mkdir(parents=True, exist_ok=True)
    cursor = data_start
    with open(archive_path, 'rb') as f_in:
        for i, (name, size) in enumerate(zip(names, sizes)):
            rel_path = sanitize_relative_path(name)
            out_path = output_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"  [{i+1}/{entry_count}] Unpacking {rel_path} ({size} bytes)...")
            f_in.seek(cursor)
            
            remaining = size
            with open(out_path, 'wb') as f_out:
                while remaining > 0:
                    chunk_size = min(1024 * 1024, remaining)
                    chunk = f_in.read(chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    remaining -= len(chunk)
                    
            cursor += align_up(size)
            
    print(f"[+] Unpacking archive complete. Saved to: {output_dir}")

# --- Helper Functions for Extraction & Encoding Detection ---
def swap_bits(idx):
    return (((idx & 0x55555555) << 1) | ((idx & 0xAAAAAAAA) >> 1)) & 0xFF

def decrypt_data(data):
    decrypted = bytearray()
    for i in range(len(data)):
        block_idx = i // 4
        key = swap_bits(block_idx)
        decrypted.append(data[i] ^ key)
    return bytes(decrypted)

def get_null_terminated_bytes(data, offset):
    str_bytes = bytearray()
    curr = offset
    while curr < len(data) and data[curr] != 0:
        str_bytes.append(data[curr])
        curr += 1
    return bytes(str_bytes)

def escape_control_chars(text_bytes, encoding='cp932'):
    res_parts = bytearray()
    i = 0
    n = len(text_bytes)
    while i < n:
        b = text_bytes[i]
        if b < 0x20 and b not in (0x0A, 0x0D, 0x09):
            res_parts.extend(f"\\x{b:02X}".encode('ascii'))
            i += 1
        elif (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < n:
            b2 = text_bytes[i+1]
            if 0x40 <= b2 <= 0xFC and b2 != 0x7F:
                res_parts.extend(text_bytes[i:i+2])
                i += 2
            else:
                res_parts.extend(f"\\x{b:02X}".encode('ascii'))
                i += 1
        else:
            res_parts.append(b)
            i += 1
    try:
        return res_parts.decode(encoding)
    except Exception:
        return res_parts.decode(encoding, errors='replace')

def get_valid_pool_bytes_len(data, start, encoding='cp932'):
    curr = start
    n = len(data)
    consecutive_nulls = 0
    while curr < n:
        if data[curr] == 0:
            consecutive_nulls += 1
            if consecutive_nulls >= 4:
                break
            curr += 1
            continue
        consecutive_nulls = 0
        b1 = data[curr]
        char_len = 1
        is_valid = False
        if 0x20 <= b1 <= 0x7E or 0xA1 <= b1 <= 0xDF or b1 in (0x0A, 0x0D, 0x09):
            is_valid = True
            char_len = 1
        elif (0x81 <= b1 <= 0x9F or 0xE0 <= b1 <= 0xFC) and curr + 1 < n:
            b2 = data[curr+1]
            if 0x40 <= b2 <= 0xFC and b2 != 0x7F:
                is_valid = True
                char_len = 2
        if not is_valid:
            break
        curr += char_len
    return curr - start

def find_pool_start_and_count(data, table_off, encoding='cp932'):
    max_records = (len(data) - table_off) // 16
    lens = []
    for N in range(max_records + 1):
        table_end = table_off + N * 16
        lens.append(get_valid_pool_bytes_len(data, table_end, encoding))
        
    best_N = None
    for N in range(1, max_records + 1):
        table_end = table_off + N * 16
        rem_size = len(data) - table_end
        threshold = min(30, rem_size)
        if lens[N] >= threshold and (lens[N] - lens[N-1] > 10 or lens[N-1] < 10):
            best_N = N
            break
            
    if best_N is not None:
        return table_off + best_N * 16, best_N
    return None, None

def split_fhm_payload(payload):
    i = 0
    n = len(payload)
    while i < n:
        b1 = payload[i]
        is_sjis = False
        if 0x20 <= b1 <= 0x7E or 0xA1 <= b1 <= 0xDF:
            is_sjis = True
        elif (0x81 <= b1 <= 0x9F or 0xE0 <= b1 <= 0xFC) and i + 1 < n:
            b2 = payload[i+1]
            if 0x40 <= b2 <= 0xFC and b2 != 0x7F:
                is_sjis = True
        if is_sjis:
            break
        i += 1
    if i == n:
        return payload, b"", b""
    prefix = payload[:i]
    text_end = i
    while text_end < n and payload[text_end] != 0:
        text_end += 1
    text_bytes = payload[i:text_end]
    suffix = payload[text_end:]
    return prefix, text_bytes, suffix

def get_cp932_char_boundaries(b_data):
    boundaries = [0]
    i = 0
    n = len(b_data)
    while i < n:
        b = b_data[i]
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < n:
            i += 2
        else:
            i += 1
        boundaries.append(i)
    return set(boundaries)

def is_really_clean(text):
    if len(text) < 4:
        return False
    if any(c in text for c in ('$', '%', '&', '*', '#', '<', '>', '_', '|', '\\', '/', '-', '+', '=')):
        return False
    jp_count = 0
    en_count = 0
    for c in text:
        o = ord(c)
        if 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F:
            jp_count += 1
        elif 32 <= o < 127:
            en_count += 1
    if jp_count > 0 and en_count > 0:
        words = re.findall(r'[a-zA-Z]+', text)
        for w in words:
            if not (w.isupper() or len(w) <= 2):
                return False
    return True

def contains_japanese_kana(text):
    for c in text:
        o = ord(c)
        if 0x3040 <= o <= 0x309F or 0x30A0 <= o <= 0x30FF or 0xFF65 <= o <= 0xFF9F:
            return True
    return False

def extract_elf_strings(data, min_len=4, encoding='cp932'):
    strings = []
    n = len(data)
    i = 0
    curr_str = bytearray()
    while i < n:
        b1 = data[i]
        char_len = 1
        is_sjis = False
        if 0x20 <= b1 <= 0x7E or 0xA1 <= b1 <= 0xDF or b1 in (0x0A, 0x0D, 0x09):
            is_sjis = True
            char_len = 1
        elif (0x81 <= b1 <= 0x9F or 0xE0 <= b1 <= 0xFC) and i + 1 < n:
            b2 = data[i+1]
            if 0x40 <= b2 <= 0xFC and b2 != 0x7F:
                is_sjis = True
                char_len = 2
        if is_sjis:
            curr_str.extend(data[i:i+char_len])
            i += char_len
        else:
            if len(curr_str) >= min_len:
                try:
                    text = curr_str.decode(encoding)
                    if is_really_clean(text) and contains_japanese_kana(text):
                        strings.append((i - len(curr_str), text.strip()))
                except Exception:
                    pass
            curr_str = bytearray()
            i += 1
    return strings

def classify_string(text, category):
    if '%' in text:
        return "Variable (Format Specifier)"
    if any(joke in text for joke in ["オマエモナー", "氏刑", "ナムコ社員"]):
        return "Developer Test String"
    if category.startswith("UI/"):
        has_hiragana = any(0x3040 <= ord(c) <= 0x309F for c in text)
        has_katakana = any(0x30A0 <= ord(c) <= 0x30FF for c in text)
        has_kanji = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
        has_english_word = bool(re.search(r'[a-zA-Z]{3,}', text))
        if (has_kanji or has_katakana) and not has_hiragana and not has_english_word:
            is_pure_katakana = all(0x30A0 <= ord(c) <= 0x30FF or c == 'ー' for c in text)
            if not is_pure_katakana:
                has_half_width = any(0xFF61 <= ord(c) <= 0xFF9F for c in text)
                has_rare_chars = any(c in text for c in ['鞅', '啓', 'ｦ', 'ｧ', 'ﾄ', '!(', '･'])
                if has_half_width or has_rare_chars or len(text) < 4:
                    return "Suspected Binary Data (False Positive)"
        if re.search(r'[鞅啓]+', text):
            return "Suspected Binary Data (False Positive)"
        if len(text) <= 3 and not any(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF or c.isalnum() for c in text):
            return "Suspected Binary Data (False Positive)"
    return "Standard Text"

def get_scenario_context(filename):
    if filename.startswith('bt'):
        m = re.match(r'bt(\d+)_(\d+)', filename)
        if m:
            return f"Battle Tutorial (Set {int(m.group(1))}, Step {int(m.group(2))})"
        return "Battle Tutorial / Combat Setup"
    elif filename.startswith('ms'):
        m = re.match(r'ms(\d+)_(\d+)', filename)
        if m:
            return f"Main Scenario Storyline (Chapter {int(m.group(1))}, Scene {int(m.group(2))})"
        return "Main Scenario Storyline Dialogue"
    elif filename.startswith('sys'):
        return "System Interface Event or Narrative Prompt"
    elif filename.startswith('renai'):
        return "Character Relationship Event (Romance Dialogues)"
    elif filename.startswith('w_map') or filename.startswith('wm'):
        return "World Map Navigation / Travel Dialogue"
    return "Event / Story Dialogue Scene"

def cmd_extract(args):
    unpacked_dir = Path(args.unpacked)
    elf_path = Path(args.elf) if args.elf else None
    output_dir = Path(args.output)
    encoding = args.encoding
    
    if not unpacked_dir.exists():
        print(f"[-] Error: Unpacked CDIMAGE folder '{unpacked_dir}' not found.")
        sys.exit(1)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    records_by_category = {}
    
    # Combined trackers
    spl_combined_records = []  # list of (file_val, record_idx, val_0, speaker_orig, val_2, dialogue_orig)
    nht_combined_records = []  # list of (file_val, block_idx, title, body)
    
    # Suffix map for SPL files
    spl_file_pools = {} # maps rel_path -> offset_map of {offset: (text_val, bytes_val, label)}

    def add_other_record(category, rel_path, index_off, text, context):
        if category not in records_by_category:
            records_by_category[category] = []
        records_by_category[category].append([str(rel_path), index_off, text, text, "", context])

    # 1. Extract SPL Dialogues
    spl_root = unpacked_dir / "scrdata/output"
    if not spl_root.exists():
        spl_root = unpacked_dir / "seven_data_link/scrdata/output"
    if spl_root.exists():
        spl_files = sorted([f for f in os.listdir(spl_root) if f.endswith('.spl')])
        print(f"[+] Found {len(spl_files)} .spl dialogue files. Processing...")
        for filename in spl_files:
            path = spl_root / filename
            rel_path = path.relative_to(unpacked_dir)
            with open(path, 'rb') as f:
                data = f.read()
            if len(data) < 64:
                continue
            h = struct.unpack('<16I', data[:64])
            table_off = h[2]
            p_start, num_recs = find_pool_start_and_count(data, table_off, encoding)
            if p_start is None:
                continue
            pool_size = get_valid_pool_bytes_len(data, p_start, encoding)
            
            offset_map = {}
            for i in range(num_recs):
                rec_off = table_off + i * 16
                val_0 = struct.unpack_from('<I', data, rec_off)[0]
                val_2 = struct.unpack_from('<I', data, rec_off + 8)[0]
                
                speaker_orig = ""
                dialogue_orig = ""
                
                if val_0 < pool_size:
                    name_bytes = get_null_terminated_bytes(data, p_start + val_0)
                    if name_bytes:
                        speaker_orig = escape_control_chars(name_bytes, encoding)
                        offset_map[val_0] = (speaker_orig, name_bytes, f"Speaker (Record {i})")
                
                if val_2 < pool_size:
                    text_bytes = get_null_terminated_bytes(data, p_start + val_2)
                    if text_bytes:
                        dialogue_orig = escape_control_chars(text_bytes, encoding)
                        offset_map[val_2] = (dialogue_orig, text_bytes, f"Dialogue (Record {i})")
                
                if speaker_orig.strip() or dialogue_orig.strip():
                    spl_combined_records.append((str(rel_path), f"Record {i}", val_0, speaker_orig, val_2, dialogue_orig))
            
            spl_file_pools[str(rel_path)] = (p_start, pool_size, offset_map)

    # 2. Extract NHT Help Files
    nht_root = unpacked_dir / "futa/help"
    if not nht_root.exists():
        nht_root = unpacked_dir / "seven_data_link/futa/help"
    if nht_root.exists():
        nht_files = sorted([f for f in os.listdir(nht_root) if f.endswith('.nht')])
        print(f"[+] Found {len(nht_files)} .nht help pages. Processing...")
        for filename in nht_files:
            path = nht_root / filename
            rel_path = path.relative_to(unpacked_dir)
            with open(path, 'rb') as f:
                data = f.read()
            if len(data) < 4:
                continue
            num_offsets = struct.unpack_from('<I', data, 0)[0]
            offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(num_offsets)]
            offsets.append(len(data))
            
            for i in range(num_offsets):
                start, end = offsets[i], offsets[i+1]
                block = data[start:end]
                if len(block) < 64:
                    continue
                title_bytes = block[:64].split(b'\x00')[0]
                body_bytes = block[64:].split(b'\x00')[0]
                title = escape_control_chars(title_bytes, encoding)
                body = escape_control_chars(body_bytes, encoding)
                
                nht_combined_records.append((str(rel_path), f"Block {i}", title, body))

    # 3. Extract FHM Tutorial Files
    fhm_tut = unpacked_dir / "scrdata/message/info/finfomes.fhm"
    if not fhm_tut.exists():
        fhm_tut = unpacked_dir / "seven_data_link/scrdata/message/info/finfomes.fhm"
    if fhm_tut.exists():
        print(f"[+] Processing {fhm_tut.name} tutorials...")
        rel_path = fhm_tut.relative_to(unpacked_dir)
        with open(fhm_tut, 'rb') as f:
            data = f.read()
        num_entries = struct.unpack_from('<I', data, 0)[0]
        offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(num_entries)]
        offsets.append(len(data))
        visited = set()
        for i in range(num_entries):
            if i < 2 or i > 166:
                continue
            start = offsets[i]
            if start == 708 or start in visited:
                continue
            visited.add(start)
            end = min(off for off in offsets[i+1:] if off > start) if any(off > start for off in offsets[i+1:]) else len(data)
            chunk = data[start:end]
            prefix, text_bytes, suffix = split_fhm_payload(chunk)
            if text_bytes:
                text_val = escape_control_chars(text_bytes, encoding)
                if text_val.strip():
                    add_other_record("Tutorial/FHMText", rel_path, f"Entry {i} (Offset {start})", text_val, f"FHM finfomes.fhm entry {i} (Pop-up tutorial instruction card)")

    # 4. Extract FHM Prophecy File
    fhm_prophecy = unpacked_dir / "scrdata/message/info/predict.fhm"
    if not fhm_prophecy.exists():
        fhm_prophecy = unpacked_dir / "seven_data_link/scrdata/message/info/predict.fhm"
    if fhm_prophecy.exists():
        print(f"[+] Processing {fhm_prophecy.name} prophecies...")
        rel_path = fhm_prophecy.relative_to(unpacked_dir)
        with open(fhm_prophecy, 'rb') as f:
            data = f.read()
        num_entries = struct.unpack_from('<I', data, 0)[0]
        offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(num_entries)]
        offsets.append(len(data))
        if num_entries > 18:
            start = offsets[18]
            end = min(off for off in offsets[19:] if off > start) if any(off > start for off in offsets[19:]) else len(data)
            chunk = data[start:end]
            decrypted = decrypt_data(chunk)
            text_val = escape_control_chars(decrypted.rstrip(b'\x00'), encoding)
            if text_val.strip():
                add_other_record("Story/Prophecy", rel_path, f"Entry 18 (Offset {start})", text_val, "FHM Prophecies (Obfuscated, Decrypted)")

    # 5. Extract ELF strings
    if elf_path and elf_path.exists():
        print(f"[+] Processing ELF executable: {elf_path}...")
        rel_path = elf_path.name
        with open(elf_path, 'rb') as f:
            elf_data = f.read()
        elf_strs = extract_elf_strings(elf_data, min_len=4, encoding=encoding)
        for offset, text in elf_strs:
            category = "UI/SystemMessage"
            if 0x366600 <= offset <= 0x371000:
                category = "UI/ItemName"
                ctx = f"ELF address 0x{offset:08X} (Inventory/Shop UI - Weapons, shields, accessories, or unit class names)"
            elif (0x363200 <= offset <= 0x364000) or (0x42A600 <= offset <= 0x42B000) or (0x421E00 <= offset <= 0x421FE0):
                category = "UI/LocationName"
                ctx = f"ELF address 0x{offset:08X} (World Map Navigation - Towns, regions, dungeons, or map locations)"
            else:
                ctx = f"ELF address 0x{offset:08X} (System UI - Combat stats, settings, options, or system prompts)"
            add_other_record(category, rel_path, f"Address 0x{offset:08X}", text, ctx)

    # --- Write Combined Scenario Dialogue CSV ---
    print("[+] Writing combined scenario dialogues...")
    combined_spl_rows = []
    for file_val, rec_idx, val_0, speaker, val_2, dialogue in spl_combined_records:
        speaker_note = ""
        dialogue_note = ""
        
        # Check suffixes
        p_start, pool_size, offset_map = spl_file_pools[file_val]
        if speaker.strip() and val_0 < pool_size:
            for other_offset, (other_orig, other_bytes, other_lbl) in offset_map.items():
                if other_offset < val_0:
                    diff = val_0 - other_offset
                    if diff < len(other_bytes):
                        suffix_bytes = other_bytes[diff:]
                        try:
                            decoded = suffix_bytes.split(b'\x00')[0].decode(encoding)
                        except Exception:
                            decoded = ""
                        if decoded == speaker:
                            boundaries = get_cp932_char_boundaries(other_bytes)
                            align = "exact" if diff in boundaries else "mid-byte (distorted)"
                            speaker_note = f"Speaker Suffix ({align} of '{other_orig}' at {other_lbl})"
                            break
                            
        if dialogue.strip() and val_2 < pool_size:
            for other_offset, (other_orig, other_bytes, other_lbl) in offset_map.items():
                if other_offset < val_2:
                    diff = val_2 - other_offset
                    if diff < len(other_bytes):
                        suffix_bytes = other_bytes[diff:]
                        try:
                            decoded = suffix_bytes.split(b'\x00')[0].decode(encoding)
                        except Exception:
                            decoded = ""
                        if decoded == dialogue:
                            boundaries = get_cp932_char_boundaries(other_bytes)
                            align = "exact" if diff in boundaries else "mid-byte (distorted)"
                            dialogue_note = f"Dialogue Suffix ({align} of '{other_orig}' at {other_lbl})"
                            break
                            
        notes_list = []
        if speaker_note: notes_list.append(speaker_note)
        if dialogue_note: notes_list.append(dialogue_note)
        notes_str = "; ".join(notes_list) if notes_list else "Standard Dialogue Line"
        
        if "%" in speaker or "%" in dialogue:
            notes_str = f"Contains Variables; {notes_str}"
        if any(joke in speaker or joke in dialogue for joke in ["オマエモナー", "氏刑", "ナムコ社員"]):
            notes_str = f"Developer Test String; {notes_str}"
            
        filename = os.path.basename(file_val)
        scene_context = get_scenario_context(filename)
        context_str = f"Scene Type: {scene_context}. Dialogue block in {filename} ({rec_idx})"
        
        combined_spl_rows.append([file_val, rec_idx, speaker, speaker, dialogue, dialogue, notes_str, context_str])
        
    out_spl_path = output_dir / "Story_Dialogue_Combined.csv"
    spl_header = ["File", "Record Index", "Speaker (Original)", "Speaker (Translation)", "Dialogue (Original)", "Dialogue (Translation)", "Notes", "Context"]
    with open(out_spl_path, 'w', encoding='utf-8', newline='') as f_out:
        writer = csv.writer(f_out)
        writer.writerow(spl_header)
        writer.writerows(combined_spl_rows)
    print(f"  - Wrote {len(combined_spl_rows)} scenario dialogue pairs to Story_Dialogue_Combined.csv")

    # --- Write Combined NHT Help Cards CSV ---
    print("[+] Writing combined help cards...")
    combined_nht_rows = []
    for file_val, block_idx, title, body in nht_combined_records:
        notes_str = "Standard Help Card"
        if "\\" in body:
            notes_str = "Contains inline formatting links"
        combined_nht_rows.append([file_val, block_idx, title, title, body, body, notes_str, f"NHT help card in deck '{os.path.basename(file_val)}', {block_idx} (Title: '{title}')"])
        
    out_nht_path = output_dir / "Tutorial_Help_Combined.csv"
    nht_header = ["File", "Block Index", "Title (Original)", "Title (Translation)", "Body (Original)", "Body (Translation)", "Notes", "Context"]
    with open(out_nht_path, 'w', encoding='utf-8', newline='') as f_out:
        writer = csv.writer(f_out)
        writer.writerow(nht_header)
        writer.writerows(combined_nht_rows)
    print(f"  - Wrote {len(combined_nht_rows)} help card pairs to Tutorial_Help_Combined.csv")

    # --- Write Other Category CSVs ---
    category_files_mapping = {
        "Story/Prophecy": "Story_Prophecy.csv",
        "Tutorial/FHMText": "Tutorial_FHMText.csv",
        "UI/ItemName": "UI_ItemName.csv",
        "UI/LocationName": "UI_LocationName.csv",
        "UI/SystemMessage": "UI_SystemMessage.csv"
    }

    print("[+] Writing other CSV catalogs...")
    other_header = ["File", "Index/Offset", "OriginalText", "EnglishTranslation", "Notes", "Context"]
    for category, filename in category_files_mapping.items():
        rows = records_by_category.get(category, [])
        out_path = output_dir / filename
        
        out_rows = []
        for file_val, idx_off, orig, eng, _, context in rows:
            note = classify_string(orig, category)
            out_rows.append([file_val, idx_off, orig, eng, note, context])
            
        with open(out_path, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.writer(f_out)
            writer.writerow(other_header)
            writer.writerows(out_rows)
        print(f"  - Wrote {len(out_rows)} rows to {filename}")
        
    print(f"[+] Text extraction and splitting complete. Files saved to: {output_dir}")

def cmd_context(args):
    manual = """================================================================================
                    Venus & Braves Translation Context Manual
================================================================================

This guide provides critical binary structures, formatting codes, and naming 
conventions used to coordinate translation work for Venus & Braves (PS2).

--------------------------------------------------------------------------------
1. Scenario File Naming Conventions (.spl)
--------------------------------------------------------------------------------
Scenario dialogue scripts are named with prefixes describing where/when they play:

  * btXX_XX.spl (Battle Tutorials):
    Examples: bt01_01.spl -> Battle Tutorial (Set 1, Step 1).
    Context: Explanations of unit roles, board rotations, and combat mechanics.

  * msXX_XX.spl (Main Scenario):
    Examples: ms02_03.spl -> Main Scenario Storyline (Chapter 2, Scene 3).
    Context: Main story cutscenes and critical dialogue lines.

  * sysXX_XX.spl (System Interface Events):
    Context: Narration prompts, UI choices, save/load checks, or world event triggers.

  * renai_XX.spl (Romance / Relationship Events):
    Context: Dialogues for character relationship growth, bonding, and subplots.

  * w_map_XX.spl / wmXX_XX.spl (World Map Navigation):
    Context: Party travel banter, travel instructions, and map-location dialogue.

--------------------------------------------------------------------------------
2. Help & Tutorial Formatting Tags (.nht)
--------------------------------------------------------------------------------
Help card description blocks contain inline binary control codes for layout 
and navigation. Preserve these codes or map them properly during translation:

  * \\x11 : Start highlighted term or hyperlink (colored yellow in-game).
  * \\x10 : End highlighted term or hyperlink.
  * \\x14\\xXX : Hyperlink destination. References help block index (hex \\xXX).
          Example: '\\x11Basic Controls\\x10\\x14\\x00' highlights 'Basic Controls'
          and links to block index 0x00 when clicked.
  * \\x15\\xXX (or \\x15\\xXX\\x03) : Page navigation reference pointing to block index \\xXX.

--------------------------------------------------------------------------------
3. FHM Containers & Encryption (.fhm)
--------------------------------------------------------------------------------
FHM files are simple archive containers holding game assets and system texts.

  * finfomes.fhm:
    Contains the tutorial dialogue boxes shown as pop-up messages.
  * predict.fhm:
    Contains the story prophecies. Entry 18 is encrypted using a bit-swap XOR.
    Decryption/Encryption key swap function:
      def swap_bits(idx):
          return (((idx & 0x55555555) << 1) | ((idx & 0xAAAAAAAA) >> 1)) & 0xFF

--------------------------------------------------------------------------------
4. Executable String Memory Addresses (SLPS_251.96)
--------------------------------------------------------------------------------
Hardcoded strings in the main executable are grouped by address ranges:

  * 0x366600 to 0x371000 (Inventory & Shop UI):
    Weapons, shields, accessories, unit class names, and shopping prompts.
    Length Constraint: Item names are structured at 116-byte offsets. English
    translations must fit within their original bounds (usually 32/40 bytes)
    unless relocated via assembly address redirections.

  * 0x363200 to 0x364000 & 0x42A600 to 0x42B000 (World Map Places):
    Town names, dungeon names, and region labels.

  * Other Ranges (System UI & Battle Prompts):
    Combat status labels (HP, AP), option menus, save screen warnings, etc.

--------------------------------------------------------------------------------
5. Dialogue Suffix Sharing (Mid-Byte Alignment Distortion)
--------------------------------------------------------------------------------
To optimize space, the game compiler reuses suffixes of strings in .spl pools:

  * Suffix Glitch: A pointer pointing to the middle of a double-byte CP932
    character cuts off the first byte, causing the second byte to merge with
    the next character and render as a distorted glyph (e.g. ｨまえは instead of おまえは).
  * Rebuilding Rule: English strings do not share suffixes. When rebuild/insertion
    is implemented, the compiler must split shared suffixes into unique strings
    and update pointers, rather than performing mid-byte referencing.
================================================================================"""
    print(manual)

def main():
    parser = argparse.ArgumentParser(
        description="Venus & Braves ROM Translation Utility Toolkit"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-commands")
    
    # Unpack Subparser
    parser_unpack = subparsers.add_parser("unpack", help="Unpack BIN archives (CDIMAGE.BIN, BGMIMAGE.BIN, etc.)")
    parser_unpack.add_argument("archive", type=str, help="Path to the archive file (e.g. CDIMAGE.BIN)")
    parser_unpack.add_argument("-o", "--output", type=str, required=True, help="Output directory for unpacked assets")
    
    # Extract Subparser
    parser_extract = subparsers.add_parser("extract", help="Extract game text to annotated CSVs")
    parser_extract.add_argument("unpacked", type=str, help="Directory containing unpacked CDIMAGE.BIN contents")
    parser_extract.add_argument("-e", "--elf", type=str, help="Optional path to SLPS_251.96 executable")
    parser_extract.add_argument("-o", "--output", type=str, default="translation_catalog_split", help="Output directory for CSVs")
    parser_extract.add_argument("--encoding", type=str, default="cp932", help="Encoding to use (default: cp932/Shift-JIS)")
    
    # Context Subparser
    subparsers.add_parser("context", help="Display translation and hacking context reference manual")
    
    args = parser.parse_args()
    
    if args.command == "unpack":
        cmd_unpack(args)
    elif args.command == "extract":
        cmd_extract(args)
    elif args.command == "context":
        cmd_context(args)

if __name__ == '__main__':
    main()

