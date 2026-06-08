#!/usr/bin/env python3
import os
import csv
import re

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

def classify_string(text, category):
    # 1. Variable / Format Specifier check
    if '%' in text:
        return "Variable (Format Specifier)"
        
    # 2. Developer Test / Joke Strings check
    if any(joke in text for joke in ["オマエモナー", "氏刑", "ナムコ社員"]):
        return "Developer Test String"
        
    # 3. Suspected Binary Data (False Positive) check for UI elements
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

def main():
    workspace_dir = "/Users/acr/Develop/venus-braves"
    input_csv = os.path.join(workspace_dir, "translation_catalog.csv")
    output_dir = os.path.join(workspace_dir, "translation_catalog_split")
    os.makedirs(output_dir, exist_ok=True)
    
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return
        
    print(f"Reading {input_csv}...")
    
    # Group rows by Category, and also by File (for suffix analysis)
    rows_by_category = {}
    files_data = {}
    
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            file_val, category, index_off, orig, eng, context = row
            if category not in rows_by_category:
                rows_by_category[category] = []
            rows_by_category[category].append(row)
            
            if file_val not in files_data:
                files_data[file_val] = []
            files_data[file_val].append(row)
            
    # Step 1: Detect overlapping suffixes per file
    offset_re = re.compile(r'Offset (\d+)')
    suffixes_notes = {} # maps (file_val, index_off, orig) -> notes
    
    print("Analyzing files for overlapping suffixes...")
    for file_val, rows in files_data.items():
        offsets_map = {}
        for row in rows:
            f_val, category, index_off, orig, eng, context = row
            m = offset_re.search(index_off)
            if m:
                offset_val = int(m.group(1))
                try:
                    b = orig.encode('cp932')
                except Exception:
                    b = orig.encode('utf-8')
                offsets_map[offset_val] = (orig, b, index_off)
                
        for row in rows:
            f_val, category, index_off, orig, eng, context = row
            m = offset_re.search(index_off)
            if m:
                offset_val = int(m.group(1))
                is_suffix = False
                parent_info = None
                
                # Check against other strings in same file
                for other_offset, (other_orig, other_bytes, other_index) in offsets_map.items():
                    if other_offset < offset_val:
                        diff = offset_val - other_offset
                        if diff < len(other_bytes):
                            suffix_bytes = other_bytes[diff:]
                            try:
                                decoded_suffix = suffix_bytes.split(b'\x00')[0].decode('cp932')
                            except Exception:
                                decoded_suffix = ""
                                
                            if decoded_suffix == orig:
                                is_suffix = True
                                # Check character alignment
                                boundaries = get_cp932_char_boundaries(other_bytes)
                                alignment = "exact alignment" if diff in boundaries else "mid-byte alignment (distorts lead char)"
                                parent_info = (other_orig, other_index, alignment)
                                break
                                
                if is_suffix:
                    parent_text, parent_idx, alignment = parent_info
                    suffixes_notes[(file_val, index_off, orig)] = (
                        f"Overlapping Suffix ({alignment}) - suffix of '{parent_text}' at {parent_idx}"
                    )

    # Step 2: Separate and write to category CSVs
    category_files_mapping = {
        "Story/Dialogue": "Story_Dialogue.csv",
        "Story/SpeakerName": "Story_SpeakerName.csv",
        "Story/Prophecy": "Story_Prophecy.csv",
        "Tutorial/FHMText": "Tutorial_FHMText.csv",
        "Tutorial/HelpBody": "Tutorial_HelpBody.csv",
        "Tutorial/HelpTitle": "Tutorial_HelpTitle.csv",
        "UI/ItemName": "UI_ItemName.csv",
        "UI/LocationName": "UI_LocationName.csv",
        "UI/SystemMessage": "UI_SystemMessage.csv"
    }
    
    new_header = ["File", "Index/Offset", "OriginalText", "EnglishTranslation", "Notes", "Context"]
    
    print("Writing split CSVs with notes...")
    for category, filename in category_files_mapping.items():
        rows = rows_by_category.get(category, [])
        out_path = os.path.join(output_dir, filename)
        
        out_rows = []
        for row in rows:
            file_val, cat, index_off, orig, eng, context = row
            
            # Base classification
            note = classify_string(orig, cat)
            
            # Overwrite if it's a suffix
            key = (file_val, index_off, orig)
            if key in suffixes_notes:
                suffix_note = suffixes_notes[key]
                if note != "Standard Text":
                    note = f"{note}; {suffix_note}"
                else:
                    note = suffix_note
                    
            out_rows.append([file_val, index_off, orig, eng, note, context])
            
        with open(out_path, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.writer(f_out)
            writer.writerow(new_header)
            writer.writerows(out_rows)
            
        print(f"  - Wrote {len(out_rows)} rows to {os.path.basename(out_path)}")
        
    print("[+] Splitting and annotation complete!")

if __name__ == '__main__':
    main()
