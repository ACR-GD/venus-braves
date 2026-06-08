#!/usr/bin/env python3
import os
import csv
import re

def get_null_terminated_len(f, offset):
    f.seek(offset)
    length = 0
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
            break
        length += 1
    return length

def main():
    workspace = "/Users/acr/Develop/venus-braves"
    elf_path = os.path.join(workspace, "extracted_iso/SLPS_251.96")
    
    csvs = [
        os.path.join(workspace, "translation_catalog_split/UI_ItemName.csv"),
        os.path.join(workspace, "translation_catalog_split/UI_LocationName.csv"),
        os.path.join(workspace, "translation_catalog_split/UI_SystemMessage.csv")
    ]
    
    if not os.path.exists(elf_path):
        print(f"[!] Error: Executable {elf_path} not found.")
        return

    # Count real strings first
    all_rows = []
    for cp in csvs:
        if not os.path.exists(cp):
            print(f"[!] Warning: CSV file {cp} does not exist. Skipping.")
            continue
        with open(cp, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                # Store row and source CSV name
                all_rows.append((row, os.path.basename(cp)))

    print(f"[+] Loaded {len(all_rows)} rows across ELF UI CSVs.")
    
    patched_count = 0
    skipped_fp_count = 0
    truncated_count = 0
    
    address_regex = re.compile(r'Address\s+0x([0-9A-Fa-f]+)')
    
    with open(elf_path, 'r+b') as f:
        for row, source_csv in all_rows:
            index_off_str = row[1]
            orig_text = row[2]
            trans_text = row[3]
            notes = row[4]
            
            # Skip if it is a suspected binary false positive
            if "False Positive" in notes:
                skipped_fp_count += 1
                continue
                
            m = address_regex.search(index_off_str)
            if not m:
                continue
                
            offset = int(m.group(1), 16)
            
            # Read original length of null-terminated string at this offset
            orig_len = get_null_terminated_len(f, offset)
            
            # Encode translation to cp932 (Shift-JIS)
            try:
                trans_bytes = trans_text.encode('cp932')
            except Exception as e:
                print(f"[!] Error encoding string at 0x{offset:08X} in {source_csv}: {e}")
                # Fallback: remove non-ascii characters or use original text
                trans_bytes = trans_text.encode('ascii', errors='ignore')
                
            # Check length constraint
            # Total available space including the null terminator is orig_len + 1 bytes.
            available_space = orig_len
            
            if len(trans_bytes) > available_space:
                # Must truncate to fit, leaving room for at least one null terminator
                truncated_bytes = trans_bytes[:available_space]
                print(f"[!] Warning: String at 0x{offset:08X} too long. Truncated {trans_text!r} ({len(trans_bytes)}B) -> {truncated_bytes.decode('cp932', errors='ignore')!r} ({len(truncated_bytes)}B). Original space: {orig_len}B.")
                trans_bytes = truncated_bytes
                truncated_count += 1
                
            # Pad to the original length + 1 (the final null byte)
            padded_bytes = trans_bytes.ljust(orig_len + 1, b'\x00')
            
            # Write back to executable
            f.seek(offset)
            f.write(padded_bytes)
            patched_count += 1
            
    print(f"\n[+] Executable patching complete:")
    print(f"  - Successfully patched {patched_count} UI strings.")
    print(f"  - Skipped {skipped_fp_count} binary false positives.")
    print(f"  - Truncated {truncated_count} strings to fit memory limits.")

if __name__ == '__main__':
    main()
