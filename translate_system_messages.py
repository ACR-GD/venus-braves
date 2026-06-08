#!/usr/bin/env python3
import os
import csv
import re
import urllib.request
import urllib.parse
import json
import time

CACHE_PATH = "translation_system_cache.json"
CSV_PATH = "translation_catalog_split/UI_SystemMessage.csv"

# Load official API key
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY and os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as env_file:
            for line in env_file:
                if line.strip().startswith("GOOGLE_API_KEY="):
                    GOOGLE_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except Exception as e:
        print(f"[-] Error reading .env file: {e}")

if GOOGLE_API_KEY:
    print("[+] Using official Google Translate API key.")
else:
    print("[!] Error: No Google API key found in environment or .env file.")
    exit(1)

def parse_addr(addr_str):
    parts = addr_str.replace('Address', '').strip().split()
    for p in parts:
        if p.startswith('0x'):
            return int(p, 16)
    return 0

def is_real_string(s):
    # Skip if it contains half-width katakana (indicates random binary data decode)
    if re.search(r'[\uff61-\uff9f]', s):
        return False
        
    # Skip character glyph sheets and font tests
    if len(s) > 15 and all(c in "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽぁぃぅぇぉっゃゅょー、。゛゜アィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモヤユヨラリルレロワヲンヴヵヶ" or c in ".,])}、。．・｝」）』】ー～ゃゅょャュョっッ" or c in "★☆´｀¨＾ヽヾゝゞ〃―‐‘’“”°′″" for c in s):
        return False

    hiragana_regex = re.compile(r'[\u3040-\u309f]')
    katakana_regex = re.compile(r'[\u30a0-\u30ff]')
    kanji_regex = re.compile(r'[\u4e00-\u9faf]')

    h_count = len(hiragana_regex.findall(s))
    k_count = len(katakana_regex.findall(s))
    kanji_count = len(kanji_regex.findall(s))
    
    is_real = (h_count >= 2) or (k_count >= 2) or (kanji_count >= 1 and (h_count >= 1 or k_count >= 1)) or any(w in s for w in ['決定', '戻る', 'はい', 'いいえ', 'セーブ', 'ロード', 'クリア'])
    return is_real

def translate_official_google_api(batch, api_key, retries=5):
    if not batch:
        return []
    url = f"https://translation.googleapis.com/language/translate/v2?key={api_key}"
    payload = {
        "q": batch,
        "source": "ja",
        "target": "en",
        "format": "text"
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    delay = 1.0
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                translations = [item["translatedText"] for item in resp_data["data"]["translations"]]
                return translations
        except Exception as e:
            print(f"[-] Official Google Translate error: {e}. Retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2
    return None

def main():
    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.")
        return

    # Load cache
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[+] Loaded {len(cache)} translated strings from cache.")
        except Exception as e:
            print(f"[-] Error loading cache: {e}")

    # Read CSV
    rows = []
    unique_to_translate = set()
    
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            rows.append(row)
            addr = parse_addr(row[1])
            text = row[2]
            
            # If it's a real string at address >= 0x00420000, collect for translation
            if addr >= 0x00420000 and is_real_string(text):
                if text not in cache:
                    unique_to_translate.add(text)

    to_translate_list = sorted(list(unique_to_translate))
    total_to_translate = len(to_translate_list)
    print(f"[+] Found {total_to_translate} unique system UI strings to translate.")

    if total_to_translate > 0:
        idx = 0
        batch_count = 0
        max_items = 80
        
        while idx < len(to_translate_list):
            batch_count += 1
            batch = to_translate_list[idx : idx + max_items]
            idx += len(batch)
            
            pct = (idx / total_to_translate) * 100
            print(f"[*] Batch {batch_count}: translating {len(batch)} items... Progress: {idx}/{total_to_translate} ({pct:.2f}%)")
            
            results = translate_official_google_api(batch, GOOGLE_API_KEY)
            if results is None:
                print("[-] Fatal: Translation failed. Exiting.")
                return
                
            for orig, trans in zip(batch, results):
                cache[orig] = trans
                
            try:
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[-] Error saving cache: {e}")
                
            time.sleep(0.5)

    # Map back to CSV rows
    print("[+] Mapping translations back to CSV...")
    translated_count = 0
    fp_count = 0
    
    for row in rows:
        addr = parse_addr(row[1])
        text = row[2]
        
        # If it is below 0x00420000 or is not a real string:
        # copy exactly, mark as False Positive
        if addr < 0x00420000 or not is_real_string(text):
            row[3] = text
            row[4] = "Suspected Binary Data (False Positive)"
            fp_count += 1
        else:
            # It's a real string
            if text in cache:
                row[3] = cache[text]
                row[4] = "Standard Text"
                translated_count += 1
            else:
                row[3] = text
                row[4] = "Standard Text"

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"[+] Successfully wrote translations to {CSV_PATH}.")
    print(f"    - Cleaned and copied {fp_count} false positive rows.")
    print(f"    - Updated {translated_count} real text rows.")

if __name__ == "__main__":
    main()
