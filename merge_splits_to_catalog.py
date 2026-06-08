#!/usr/bin/env python3
import os
import csv
import re

def main():
    workspace = "/Users/acr/Develop/venus-braves"
    catalog_path = os.path.join(workspace, "translation_catalog.csv")
    
    dialogue_csv = os.path.join(workspace, "translation_catalog_split/Story_Dialogue_Combined.csv")
    prophecy_csv = os.path.join(workspace, "translation_catalog_split/Story_Prophecy.csv")
    fhm_csv = os.path.join(workspace, "translation_catalog_split/Tutorial_FHMText.csv")
    
    if not os.path.exists(catalog_path):
        print(f"[!] Error: {catalog_path} not found.")
        return

    # 1. Load Dialogue translations
    print("[+] Loading Dialogue translations...")
    dialogue_map = {} # (file, record_idx) -> (speaker_trans, dialogue_trans)
    if os.path.exists(dialogue_csv):
        with open(dialogue_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                rel_file, rec_idx, _, speaker_trans, _, dialogue_trans, _, _ = row
                # Normalize rec_idx (e.g. "Record 0")
                dialogue_map[(rel_file, rec_idx.strip())] = (speaker_trans, dialogue_trans)
        print(f"  - Loaded {len(dialogue_map)} dialogue records.")
    else:
        print(f"[-] Warning: {dialogue_csv} not found.")

    # 2. Load Prophecy translations
    print("[+] Loading Prophecy translations...")
    prophecy_map = {} # (file, index_off) -> trans
    if os.path.exists(prophecy_csv):
        with open(prophecy_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                rel_file, index_off, _, trans, _, _ = row
                prophecy_map[(rel_file, index_off.strip())] = trans
        print(f"  - Loaded {len(prophecy_map)} prophecy records.")
    else:
        print(f"[-] Warning: {prophecy_csv} not found.")

    # 3. Load FHM Text translations
    print("[+] Loading FHM Text translations...")
    fhm_map = {} # (file, index_off) -> trans
    if os.path.exists(fhm_csv):
        with open(fhm_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                rel_file, index_off, _, trans, _, _ = row
                fhm_map[(rel_file, index_off.strip())] = trans
        print(f"  - Loaded {len(fhm_map)} FHM tutorial records.")
    else:
        print(f"[-] Warning: {fhm_csv} not found.")

    # 4. Process and update translation_catalog.csv
    print("[+] Updating translation_catalog.csv...")
    updated_rows = []
    headers = []
    
    record_regex = re.compile(r'Record\s+(\d+)')
    
    updated_dialogue_count = 0
    updated_prophecy_count = 0
    updated_fhm_count = 0
    
    with open(catalog_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            file_val, category, index_off, orig, eng, context = row
            new_eng = eng
            
            if category in ("Story/SpeakerName", "Story/Dialogue"):
                m = record_regex.match(index_off)
                if m:
                    rec_num = m.group(1)
                    key = (file_val, f"Record {rec_num}")
                    if key in dialogue_map:
                        speaker_trans, dialogue_trans = dialogue_map[key]
                        if category == "Story/SpeakerName":
                            new_eng = speaker_trans
                        else:
                            new_eng = dialogue_trans
                        updated_dialogue_count += 1
            
            elif category == "Story/Prophecy":
                key = (file_val, index_off.strip())
                if key in prophecy_map:
                    new_eng = prophecy_map[key]
                    updated_prophecy_count += 1
                    
            elif category == "Tutorial/FHMText":
                key = (file_val, index_off.strip())
                if key in fhm_map:
                    new_eng = fhm_map[key]
                    updated_fhm_count += 1
            
            updated_rows.append([file_val, category, index_off, orig, new_eng, context])

    # Save back
    with open(catalog_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(updated_rows)
        
    print(f"[+] Successfully merged translations into {catalog_path}:")
    print(f"  - Updated {updated_dialogue_count} speaker/dialogue entries.")
    print(f"  - Updated {updated_prophecy_count} prophecy entries.")
    print(f"  - Updated {updated_fhm_count} FHM tutorial entries.")

if __name__ == '__main__':
    main()
