#!/usr/bin/env python3
import os
import csv
import struct
import re

def csv_to_python(s):
    def repl(m):
        return chr(int(m.group(1), 16))
    return re.sub(r"\\x([0-9A-Fa-f]{2})", repl, s)

def main():
    workspace = "/Users/acr/Develop/venus-braves"
    csv_path = os.path.join(workspace, "translation_catalog_split/Tutorial_Help_Combined.csv")
    unpacked_dir = os.path.join(workspace, "cdimage_unpacked")
    
    if not os.path.exists(csv_path):
        print(f"[!] Error: {csv_path} not found.")
        return

    # Load CSV
    print("[+] Loading help card translations...")
    files_data = {} # rel_file -> list of (block_idx, title, body)
    
    block_index_regex = re.compile(r'Block\s+(\d+)')
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            rel_file, block_idx_str, _, title_trans, _, body_trans, _, _ = row
            m = block_index_regex.match(block_idx_str)
            if m:
                block_idx = int(m.group(1))
            else:
                block_idx = 0
            
            # Unescape hex control codes (like \x11, \x10, etc.)
            title_clean = csv_to_python(title_trans)
            body_clean = csv_to_python(body_trans)
            
            if rel_file not in files_data:
                files_data[rel_file] = []
            files_data[rel_file].append((block_idx, title_clean, body_clean))
            
    print(f"[+] Found {len(files_data)} NHT help deck files in CSV.")
    
    for rel_file, blocks in files_data.items():
        abs_path = os.path.join(unpacked_dir, rel_file)
        if not os.path.exists(abs_path):
            print(f"[!] Warning: Help file {abs_path} does not exist. Skipping.")
            continue
            
        print(f"[+] Reconstructing help deck: {rel_file}")
        
        # Sort blocks by index to ensure proper order
        blocks.sort(key=lambda x: x[0])
        num_offsets = len(blocks)
        
        # Build block payloads
        block_payloads = []
        for block_idx, title, body in blocks:
            # Encode Title (exactly 64 bytes padded with \x00)
            title_bytes = title.encode('cp932')
            if len(title_bytes) > 63:
                title_bytes = title_bytes[:63]
            title_padded = title_bytes.ljust(64, b'\x00')
            
            # Encode Body (null-terminated)
            body_bytes = body.encode('cp932') + b'\x00'
            
            block_payloads.append(title_padded + body_bytes)
            
        # Calculate offsets
        offsets = []
        curr_offset = 4 + num_offsets * 4
        for payload in block_payloads:
            offsets.append(curr_offset)
            curr_offset += len(payload)
            
        # Rebuild file data
        new_data = bytearray()
        new_data.extend(struct.pack('<I', num_offsets))
        for off in offsets:
            new_data.extend(struct.pack('<I', off))
        for payload in block_payloads:
            new_data.extend(payload)
            
        # Write file back
        with open(abs_path, 'wb') as f_out:
            f_out.write(new_data)
            
        print(f"  - Rebuilt {rel_file} with {num_offsets} pages. Total size: {len(new_data)} bytes.")
        
    print("[+] Help card re-insertion complete!")

if __name__ == '__main__':
    main()
