#!/usr/bin/env python3
import os
import csv
import struct
import sys
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

# --- CP932 / Shift-JIS Helpers ---
def get_null_terminated_bytes(data, offset):
    str_bytes = bytearray()
    curr = offset
    while curr < len(data) and data[curr] != 0:
        str_bytes.append(data[curr])
        curr += 1
    return bytes(str_bytes)

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

# --- FHM Helper for generic payload splitting ---
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

# --- SPL Reconstruction ---
def reconstruct_spl(original_data, file_records_csv, rel_path):
    header_dwords = struct.unpack('<16I', original_data[:64])
    table_off = header_dwords[2]
    
    pool_start, num_records = find_pool_start_and_count(original_data, table_off)
    if pool_start is None:
        print(f"[!] Warning: Failed to parse SPL structure for {rel_path}. Skipping modification.")
        return original_data
        
    pool_size = get_valid_pool_bytes_len(original_data, pool_start)
    
    prefix_bytes = original_data[:table_off]
    
    orig_records = []
    for i in range(num_records):
        rec_off = table_off + i * 16
        val_0, val_1, val_2, val_3 = struct.unpack_from('<4I', original_data, rec_off)
        orig_records.append([val_0, val_1, val_2, val_3])
        
    trailing_bytes = original_data[pool_start + pool_size:]
    
    new_pool = bytearray()
    string_to_offset = {}
    
    def add_to_pool(orig_offset, entry_type, record_idx):
        if orig_offset == 0xFFFFFFFF:
            return 0xFFFFFFFF
            
        if orig_offset < pool_size:
            key = (entry_type, record_idx, orig_offset)
            if key in file_records_csv:
                text = file_records_csv[key]
                s_bytes = text.encode('cp932')
            else:
                s_bytes = get_null_terminated_bytes(original_data, pool_start + orig_offset)
                
            if s_bytes not in string_to_offset:
                string_to_offset[s_bytes] = len(new_pool)
                new_pool.extend(s_bytes + b'\x00')
            return string_to_offset[s_bytes]
        else:
            return orig_offset
            
    new_records = []
    # We will build the new pool first, and track which pointers were in the pool and which were in the trailing bytes.
    # To do that, we check the original offsets *before* we lookup or add to the pool.
    new_records_temp = []
    for i in range(num_records):
        val_0, val_1, val_2, val_3 = orig_records[i]
        new_val_0 = add_to_pool(val_0, "Story/SpeakerName", i)
        new_val_2 = add_to_pool(val_2, "Story/Dialogue", i)
        new_records_temp.append([new_val_0, val_1, new_val_2, val_3])
        
    new_pool_size = len(new_pool)
    size_diff = new_pool_size - pool_size
    
    # Adjust trailing pointers (originally >= pool_size and != 0xFFFFFFFF, pointing inside the file)
    for i in range(num_records):
        val_0, val_1, val_2, val_3 = orig_records[i]
        new_val_0, _, new_val_2, _ = new_records_temp[i]
        
        # Only shift if it is a valid offset within the trailing section of the file
        if val_0 != 0xFFFFFFFF and pool_size <= val_0 < len(original_data) - pool_start:
            new_val_0 = val_0 + size_diff
            
        if val_2 != 0xFFFFFFFF and pool_size <= val_2 < len(original_data) - pool_start:
            new_val_2 = val_2 + size_diff
            
        new_records.append([new_val_0, val_1, new_val_2, val_3])
        
    table_bytes = bytearray()
    for r in new_records:
        table_bytes.extend(struct.pack('<4I', r[0], r[1], r[2], r[3]))
        
    return prefix_bytes + table_bytes + bytes(new_pool) + trailing_bytes

# --- FHM Reconstruction (finfomes.fhm) ---
def reconstruct_finfomes(original_data, file_records_csv):
    num_entries = struct.unpack_from('<I', original_data, 0)[0]
    offsets = [struct.unpack_from('<I', original_data, 4 + i*4)[0] for i in range(num_entries)]
    
    header_end = 4 + num_entries * 4
    
    # Build an index-keyed map from the catalog (catalog may have stale offsets)
    # Key: entry_index -> translated_text
    idx_to_text = {}
    for (cat, idx, off), text in file_records_csv.items():
        if cat == "Tutorial/FHMText":
            idx_to_text[idx] = text
    
    # Initialize the new payload container with the placeholder 4-byte padding at offset header_end
    new_payloads = bytearray(b'\x00\x00\x00\x00')
    new_offsets = [0] * num_entries
    orig_offset_to_new_offset = { header_end: header_end }
    
    for i in range(num_entries):
        orig_offset = offsets[i]
        if orig_offset in orig_offset_to_new_offset:
            new_offsets[i] = orig_offset_to_new_offset[orig_offset]
        else:
            end = min(off for off in offsets[i+1:] if off > orig_offset) if any(off > orig_offset for off in offsets[i+1:]) else len(original_data)
            chunk = original_data[orig_offset:end]
            prefix, text_bytes, suffix = split_fhm_payload(chunk)
            
            # Match by entry index (catalog offsets may be stale)
            if i in idx_to_text:
                text = idx_to_text[i]
                new_text_bytes = text.encode('ascii', errors='replace')
            else:
                new_text_bytes = text_bytes
                
            new_chunk = bytearray(prefix + new_text_bytes + suffix)
            while len(new_chunk) % 4 != 0:
                new_chunk.append(0)
                
            start_offset = header_end + len(new_payloads)
            new_offsets[i] = start_offset
            orig_offset_to_new_offset[orig_offset] = start_offset
            new_payloads.extend(new_chunk)
            
    new_data = bytearray(struct.pack('<I', num_entries))
    for off in new_offsets:
        new_data.extend(struct.pack('<I', off))
    new_data.extend(new_payloads)
    return bytes(new_data)

# --- FHM Reconstruction (predict.fhm) ---
def reconstruct_predict(original_data, file_records_csv):
    # predict.fhm may be a standard FHM with num_entries at byte 0,
    # or it may be a raw encrypted block. Guard against overflow.
    if len(original_data) < 4:
        return original_data
    
    num_entries = struct.unpack_from('<I', original_data, 0)[0]
    
    # If num_entries is unreasonably large, this is not a plain FHM header.
    # Fall back: the prophecy text occupies the LAST logical payload.
    # Based on original analysis, the encrypted text starts at offset[18] when
    # the file has >= 19 FHM entries. If it's not a valid FHM, skip modification.
    if num_entries > 10000 or 4 + num_entries * 4 > len(original_data):
        print(f"    [!] predict.fhm doesn't look like a standard FHM (num_entries={num_entries}). Skipping.")
        return original_data
    
    offsets = [struct.unpack_from('<I', original_data, 4 + i*4)[0] for i in range(num_entries)]
    
    if num_entries <= 18:
        return original_data
        
    start = offsets[18]
    if start >= len(original_data):
        return original_data
    
    # Match by category only (offset may be stale)
    prophecy_text = None
    for (cat, idx, off), text in file_records_csv.items():
        if cat == "Story/Prophecy" and text.strip():
            prophecy_text = text
            break
    
    if prophecy_text is None:
        return original_data
        
    new_text_bytes = prophecy_text.encode('ascii', errors='replace')
    
    target_size = len(original_data) - start
    if len(new_text_bytes) < target_size:
        new_text_bytes = new_text_bytes + b'\x00' * (target_size - len(new_text_bytes))
    else:
        new_text_bytes = new_text_bytes[:target_size]
        
    encrypted_entry_18 = decrypt_data(new_text_bytes)  # bit-swap XOR is symmetric
    
    return original_data[:start] + encrypted_entry_18


def main():
    workspace_dir = "/Users/acr/Develop/venus-braves"
    csv_path = os.path.join(workspace_dir, "translation_catalog.csv")
    
    if not os.path.exists(csv_path):
        print(f"[!] Error: CSV catalog not found at {csv_path}")
        sys.exit(1)
        
    # Read mode: 'english' (default) or 'japanese' (for dry-run verification)
    mode = 'english'
    if len(sys.argv) > 1 and sys.argv[1].lower() in ('english', 'japanese'):
        mode = sys.argv[1].lower()
        
    print(f"[+] Running in '{mode}' mode...")
    
    # Load translation CSV
    # Structure: file_path -> (entry_type, index, orig_offset) -> translated_text
    catalog = {}
    record_offset_regex = re.compile(r'(?:Record|Entry|Block)\s+(\d+)\s+\(Offset\s+(\d+)\)')
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rel_file = row['File']
            entry_type = row['Category']
            
            index_off_str = row['Index/Offset']
            m = record_offset_regex.match(index_off_str)
            if m:
                idx = int(m.group(1))
                orig_off = int(m.group(2))
            else:
                m2 = re.search(r'Offset\s+(\d+)', index_off_str)
                orig_off = int(m2.group(1)) if m2 else 0
                m3 = re.search(r'(?:Record|Entry|Block)\s+(\d+)', index_off_str)
                idx = int(m3.group(1)) if m3 else 0
                
            if mode == 'english':
                text = row['EnglishTranslation']
            else:
                text = row['OriginalText']
                
            if rel_file not in catalog:
                catalog[rel_file] = {}
            catalog[rel_file][(entry_type, idx, orig_off)] = text
            
    print(f"[+] Loaded translations for {len(catalog)} files.")
    
    # Reconstruct files
    for rel_file, file_records in catalog.items():
        if rel_file.startswith("extracted_iso"):
            abs_path = os.path.join(workspace_dir, rel_file)
        else:
            abs_path = os.path.join(workspace_dir, "cdimage_unpacked", rel_file)
        if not os.path.exists(abs_path):
            print(f"[!] Warning: File {abs_path} does not exist. Skipping.")
            continue
            
        with open(abs_path, 'rb') as f:
            original_data = f.read()
            
        print(f"[+] Reconstructing: {rel_file}")
        
        if rel_file.endswith('.spl'):
            new_data = reconstruct_spl(original_data, file_records, rel_file)
        elif rel_file.endswith('finfomes.fhm'):
            new_data = reconstruct_finfomes(original_data, file_records)
        elif rel_file.endswith('predict.fhm'):
            new_data = reconstruct_predict(original_data, file_records)
        else:
            print(f"[!] Warning: Unknown file type for {rel_file}. Skipping.")
            continue
            
        with open(abs_path, 'wb') as f:
            f.write(new_data)
            
    print("[+] Reconstruction complete!")

if __name__ == '__main__':
    main()
