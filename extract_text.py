#!/usr/bin/env python3
import os
import csv
import struct
import re

# --- Bit-Swap XOR Decryption for predict.fhm Entry 18 ---
def swap_bits(idx):
    return (((idx & 0x55555555) << 1) | ((idx & 0xAAAAAAAA) >> 1)) & 0xFF

def decrypt_data(data):
    decrypted = bytearray()
    for i in range(len(data)):
        block_idx = i // 4
        key = swap_bits(block_idx)
        decrypted.append(data[i] ^ key)
    return bytes(decrypted)

# --- Shift-JIS / CP932 Decoders with Control Characters Escaping ---
def get_null_terminated_bytes(data, offset):
    str_bytes = bytearray()
    curr = offset
    while curr < len(data) and data[curr] != 0:
        str_bytes.append(data[curr])
        curr += 1
    return bytes(str_bytes)

def escape_control_chars(text_bytes):
    """
    Decodes Shift-JIS (cp932) but escapes control bytes < 0x20 
    (except 0x0A, 0x0D, 0x09) as ASCII escape sequences like \\xXX.
    """
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
        return res_parts.decode('cp932')
    except Exception:
        return res_parts.decode('cp932', errors='replace')

# --- SPL-specific Heuristic Parser ---
def get_valid_pool_bytes_len(data, start):
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
        is_sjis = False
        if 0x20 <= b1 <= 0x7E or 0xA1 <= b1 <= 0xDF or b1 in (0x0A, 0x0D, 0x09):
            is_sjis = True
            char_len = 1
        elif (0x81 <= b1 <= 0x9F or 0xE0 <= b1 <= 0xFC) and curr + 1 < n:
            b2 = data[curr+1]
            if 0x40 <= b2 <= 0xFC and b2 != 0x7F:
                is_sjis = True
                char_len = 2
        if not is_sjis:
            break
        curr += char_len
    return curr - start

def find_pool_start_and_count(data, table_off):
    max_records = (len(data) - table_off) // 16
    lens = []
    for N in range(max_records + 1):
        table_end = table_off + N * 16
        lens.append(get_valid_pool_bytes_len(data, table_end))
        
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

# --- FHM Container Helper ---
def split_fhm_payload(payload):
    i = 0
    n = len(payload)
    while i < n:
        b1 = payload[i]
        is_sjis = False
        if 0x20 <= b1 <= 0x7E:
            is_sjis = True
        elif 0xA1 <= b1 <= 0xDF:
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

# --- ELF String Extraction Helpers ---
def contains_japanese_kana(text):
    for c in text:
        o = ord(c)
        if 0x3040 <= o <= 0x309F or 0x30A0 <= o <= 0x30FF or 0xFF65 <= o <= 0xFF9F:
            return True
    return False

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

def extract_elf_strings(data, min_len=4):
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
                    text = curr_str.decode('cp932')
                    if is_really_clean(text) and contains_japanese_kana(text):
                        strings.append((i - len(curr_str), text.strip()))
                except Exception:
                    pass
            curr_str = bytearray()
            i += 1
            
    if len(curr_str) >= min_len:
        try:
            text = curr_str.decode('cp932')
            if is_really_clean(text) and contains_japanese_kana(text):
                strings.append((n - len(curr_str), text.strip()))
        except Exception:
            pass
            
    return strings

def categorize_elf_string(offset):
    # Determine UI Category based on ELF Address
    if 0x366600 <= offset <= 0x371000:
        return "UI/ItemName"
    elif (0x363200 <= offset <= 0x364000) or (0x42A600 <= offset <= 0x42B000) or (0x421E00 <= offset <= 0x421FE0):
        return "UI/LocationName"
    else:
        return "UI/SystemMessage"

# --- Main Unified Extraction ---
def main():
    workspace_dir = "/Users/acr/Develop/venus-braves"
    unpacked_dir = os.path.join(workspace_dir, "cdimage_unpacked")
    elf_path = os.path.join(workspace_dir, "extracted_iso/SLPS_251.96")
    
    # Target columns: File, Category, Index/Offset, OriginalText, EnglishTranslation, Context
    records = []
    
    # 1. SPL Dialog/Story
    spl_root = os.path.join(unpacked_dir, "seven_data_link/scrdata/output")
    if os.path.exists(spl_root):
        spl_files = sorted([f for f in os.listdir(spl_root) if f.endswith('.spl')])
        print(f"[+] Found {len(spl_files)} .spl files. Extracting dialogue...")
        for filename in spl_files:
            path = os.path.join(spl_root, filename)
            rel_path = os.path.relpath(path, unpacked_dir)
            with open(path, 'rb') as f:
                data = f.read()
            if len(data) < 64:
                continue
            
            header_dwords = struct.unpack('<16I', data[:64])
            table_off = header_dwords[2]
            pool_start, num_records = find_pool_start_and_count(data, table_off)
            if pool_start is None:
                continue
                
            pool_size = get_valid_pool_bytes_len(data, pool_start)
            
            for i in range(num_records):
                rec_off = table_off + i * 16
                val_0 = struct.unpack_from('<I', data, rec_off)[0]
                val_2 = struct.unpack_from('<I', data, rec_off + 8)[0]
                
                # Speaker name
                if val_0 < pool_size:
                    name_bytes = get_null_terminated_bytes(data, pool_start + val_0)
                    if name_bytes:
                        name_text = escape_control_chars(name_bytes)
                        if name_text.strip():
                            records.append([
                                rel_path,
                                "Story/SpeakerName",
                                f"Record {i} (Offset {val_0})",
                                name_text,
                                name_text,
                                f"SPL dialogue file: {filename}, Record: {i}"
                            ])
                
                # Dialogue text
                if val_2 < pool_size:
                    text_bytes = get_null_terminated_bytes(data, pool_start + val_2)
                    if text_bytes:
                        text_val = escape_control_chars(text_bytes)
                        if text_val.strip():
                            records.append([
                                rel_path,
                                "Story/Dialogue",
                                f"Record {i} (Offset {val_2})",
                                text_val,
                                text_val,
                                f"SPL dialogue file: {filename}, Record: {i}"
                            ])

    # 2. NHT Help/Tutorial Pages
    nht_root = os.path.join(unpacked_dir, "seven_data_link/futa/help")
    if os.path.exists(nht_root):
        nht_files = sorted([f for f in os.listdir(nht_root) if f.endswith('.nht')])
        print(f"[+] Found {len(nht_files)} .nht files. Extracting help pages...")
        for filename in nht_files:
            path = os.path.join(nht_root, filename)
            rel_path = os.path.relpath(path, unpacked_dir)
            with open(path, 'rb') as f:
                data = f.read()
            if len(data) < 4:
                continue
                
            num_offsets = struct.unpack_from('<I', data, 0)[0]
            offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(num_offsets)]
            offsets.append(len(data))
            
            for i in range(num_offsets):
                start = offsets[i]
                end = offsets[i+1]
                block = data[start:end]
                if len(block) < 64:
                    continue
                
                title_bytes = block[:64].split(b'\x00')[0]
                body_bytes = block[64:].split(b'\x00')[0]
                
                title = escape_control_chars(title_bytes)
                body = escape_control_chars(body_bytes)
                
                # NHT Title
                records.append([
                    rel_path,
                    "Tutorial/HelpTitle",
                    f"Block {i} (TitleOffset 0x00)",
                    title,
                    title,
                    f"NHT help file: {filename}, Block: {i}"
                ])
                
                # NHT Body
                if body.strip():
                    records.append([
                        rel_path,
                        "Tutorial/HelpBody",
                        f"Block {i} (BodyOffset 0x40)",
                        body,
                        body,
                        f"NHT help file: {filename}, Block: {i} (Title: {title})"
                    ])

    # 3. FHM Tutorials (finfomes.fhm)
    finfomes_path = os.path.join(unpacked_dir, "seven_data_link/scrdata/message/info/finfomes.fhm")
    if os.path.exists(finfomes_path):
        print(f"[+] Extracting tutorial blocks from finfomes.fhm...")
        rel_path = os.path.relpath(finfomes_path, unpacked_dir)
        with open(finfomes_path, 'rb') as f:
            data = f.read()
        num_entries = struct.unpack_from('<I', data, 0)[0]
        offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(num_entries)]
        offsets.append(len(data))
        
        visited_offsets = set()
        
        for i in range(num_entries):
            # Extract Entries 2 to 166 (tutorials)
            if i < 2 or i > 166:
                continue
            start = offsets[i]
            if start == 708 or start in visited_offsets:
                continue
            visited_offsets.add(start)
            
            end = min(off for off in offsets[i+1:] if off > start) if any(off > start for off in offsets[i+1:]) else len(data)
            chunk = data[start:end]
            prefix, text_bytes, suffix = split_fhm_payload(chunk)
            if text_bytes:
                text_val = escape_control_chars(text_bytes)
                if text_val.strip():
                    records.append([
                        rel_path,
                        "Tutorial/FHMText",
                        f"Entry {i} (Offset {start})",
                        text_val,
                        text_val,
                        f"FHM message file: finfomes.fhm, Entry index: {i}"
                    ])

    # 4. FHM Prophecies (predict.fhm Entry 18)
    predict_path = os.path.join(unpacked_dir, "seven_data_link/scrdata/message/info/predict.fhm")
    if os.path.exists(predict_path):
        print(f"[+] Extracting decrypted prophecy from predict.fhm...")
        rel_path = os.path.relpath(predict_path, unpacked_dir)
        with open(predict_path, 'rb') as f:
            data = f.read()
        num_entries = struct.unpack_from('<I', data, 0)[0]
        offsets = [struct.unpack_from('<I', data, 4 + i*4)[0] for i in range(num_entries)]
        offsets.append(len(data))
        
        if num_entries > 18:
            start = offsets[18]
            end = min(off for off in offsets[19:] if off > start) if any(off > start for off in offsets[19:]) else len(data)
            chunk = data[start:end]
            decrypted = decrypt_data(chunk)
            dec_clean = decrypted.rstrip(b'\x00')
            text_val = escape_control_chars(dec_clean)
            if text_val.strip():
                records.append([
                    rel_path,
                    "Story/Prophecy",
                    f"Entry 18 (Offset {start})",
                    text_val,
                    text_val,
                    "FHM predict file, Decrypted Entry 18 (Obfuscated Story Prophecies)"
                ])

    # 5. ELF UI & Menus (SLPS_251.96)
    if os.path.exists(elf_path):
        print(f"[+] Extracting menu/UI strings from SLPS_251.96...")
        rel_path = os.path.relpath(elf_path, workspace_dir)
        with open(elf_path, 'rb') as f:
            elf_data = f.read()
        
        elf_strs = extract_elf_strings(elf_data)
        for offset, text in elf_strs:
            category = categorize_elf_string(offset)
            records.append([
                rel_path,
                category,
                f"Address 0x{offset:08X}",
                text,
                text,
                f"ELF executable string at address 0x{offset:08X}"
            ])

    # 6. Write to translation_catalog.csv
    csv_path = os.path.join(workspace_dir, "translation_catalog.csv")
    print(f"[+] Writing {len(records)} entries into {csv_path}...")
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["File", "Category", "Index/Offset", "OriginalText", "EnglishTranslation", "Context"])
        writer.writerows(records)
    print("[+] Unified extraction complete!")

if __name__ == '__main__':
    main()
