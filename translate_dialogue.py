#!/usr/bin/env python3
import os
import csv
import re
import urllib.request
import urllib.parse
import json
import time
import socket

# Force IPv4 to prevent connection hangs on IPv6 (SYN_SENT issues)
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(*args, **kwargs):
    responses = orig_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = getaddrinfo_ipv4

CACHE_PATH = "translation_dialogue_cache.json"
CSV_PATH = "translation_catalog_split/Story_Dialogue_Combined.csv"

# Dual Engine & Official API state
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
    USE_MYMEMORY = False
else:
    print("[!] No Google API key found. Falling back to MyMemory API.")
    USE_MYMEMORY = True

EMAIL_INDEX = 1

def get_mymemory_email():
    global EMAIL_INDEX
    return f"acr_trans_braves_proj_{EMAIL_INDEX}@gmail.com"

def rotate_mymemory_email():
    global EMAIL_INDEX
    EMAIL_INDEX += 1
    print(f"[!] Rotated MyMemory email to index {EMAIL_INDEX}: {get_mymemory_email()}")

def needs_translation(text):
    if not text:
        return False
    # Japanese character ranges:
    # Hiragana: 3040-309F
    # Katakana: 30A0-30FF
    # Kanji: 4E00-9FBF
    # Half-width Katakana: FF65-FF9F
    # Full-width punctuation: 3000-303F, FF01-FF0F
    jp_regex = re.compile(r"[\u3040-\u30ff\u4e00-\u9faf\uff66-\uff9f\u3000-\u303f]")
    return bool(jp_regex.search(text))

def translate_single_api(q, retries=7):
    global USE_MYMEMORY
    if not q.strip():
        return q
        
    if USE_MYMEMORY:
        # If the query is too long for MyMemory, return None immediately so fallback is triggered
        if len(q) > 450:
            return None
        return translate_mymemory_api(q, retries)
        
    # Google Translate (POST request)
    url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl=en&dt=t"
    data = urllib.parse.urlencode({"q": q}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0"})
    
    delay = 1.0
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                translated = "".join([item[0] for item in data[0] if item[0]])
                return translated
        except Exception as e:
            is_429 = "429" in str(e)
            if is_429:
                print(f"[!] Google Translate rate limited (429). Switching translation engine to MyMemory.")
                USE_MYMEMORY = True
                return None
                
            current_delay = delay
            print(f"[-] Google Translate error: {e}. Retrying in {current_delay}s...")
            time.sleep(current_delay)
            delay *= 2
    return None

def translate_mymemory_api(q, retries=7):
    if not q.strip():
        return q
        
    delay = 2.0
    for attempt in range(retries):
        email = get_mymemory_email()
        url = "https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(q) + f"&langpair=ja|en&de={email}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                status = data.get("responseStatus")
                if status == 200:
                    translated = data["responseData"]["translatedText"]
                    return translated
                elif status in (403, 429) or "quota" in str(data.get("responseDetails")).lower():
                    print(f"[-] MyMemory limit reached for {email}: {data.get('responseDetails')}")
                    rotate_mymemory_email()
                    # Retry immediately with the new email
                    continue
                else:
                    print(f"[-] MyMemory status error: {status} - {data.get('responseDetails')}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
        except Exception as e:
            if "403" in str(e) or "429" in str(e):
                print(f"[-] MyMemory connection limit/error: {e}")
                rotate_mymemory_email()
                continue
                
            print(f"[-] MyMemory connection error: {e}. Retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2
    return None

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

def translate_batch(batch):
    if GOOGLE_API_KEY:
        res = translate_official_google_api(batch, GOOGLE_API_KEY)
        if res is not None:
            return res
        print("[-] Official Google API batch translation failed. Falling back to free translation paths...")

    # Replace internal newlines in each string with a placeholder
    processed_batch = []
    for s in batch:
        processed_batch.append(s.replace("\n", "__NL__"))
        
    # Join batch with newline
    query = "\n".join(processed_batch)
    
    # Translate the joined query
    translated_query = translate_single_api(query)
    if translated_query is None:
        print("[-] Batch translation query failed. Falling back to individual translation.")
        results = []
        for s in batch:
            res = translate_single_api(s.replace("\n", "__NL__"))
            if res is None:
                return None
            results.append(res.replace("__NL__", "\n").replace("__NL__", "\n"))
            time.sleep(0.5)
        return results
        
    # Split translated query back into lines
    translated_lines = translated_query.split("\n")
    
    # Clean up line count mismatch if any
    if len(translated_lines) != len(batch):
        print(f"[-] Batch size mismatch: expected {len(batch)}, got {len(translated_lines)}. Falling back to individual translation.")
        results = []
        for s in batch:
            res = translate_single_api(s.replace("\n", "__NL__"))
            if res is None:
                return None
            results.append(res.replace("__NL__", "\n").replace("__NL__", "\n"))
            time.sleep(0.5)
        return results
        
    # Restore newlines
    results = [line.replace("__NL__", "\n").replace("__NL__", "\n") for line in translated_lines]
    return results

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

    # Read CSV to collect strings needing translation
    rows = []
    headers = []
    unique_to_translate = set()
    
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            rows.append(row)
            # row[2] = Speaker (Original), row[4] = Dialogue (Original)
            speaker = row[2]
            dialogue = row[4]
            if speaker and needs_translation(speaker) and speaker not in cache:
                unique_to_translate.add(speaker)
            if dialogue and needs_translation(dialogue) and dialogue not in cache:
                unique_to_translate.add(dialogue)

    to_translate_list = sorted(list(unique_to_translate))
    total_to_translate = len(to_translate_list)
    print(f"[+] Found {total_to_translate} unique strings that need translation.")

    if total_to_translate > 0:
        idx = 0
        batch_count = 0
        
        print(f"[+] Translating remaining unique strings...")
        
        while idx < len(to_translate_list):
            batch_count += 1
            # Determine batch parameters based on the current engine
            if GOOGLE_API_KEY:
                max_chars = 6000
                max_items = 80
                engine_name = "OfficialGoogle"
            else:
                max_chars = 450 if USE_MYMEMORY else 4500
                max_items = 15 if USE_MYMEMORY else 40
                engine_name = "MyMemory" if USE_MYMEMORY else "Google"
            
            # Form next batch
            batch = []
            current_chars = 0
            while idx < len(to_translate_list) and len(batch) < max_items:
                item = to_translate_list[idx]
                item_len = len(item)
                if current_chars + item_len + len(batch) > max_chars:
                    if not batch: # Single extremely long item
                        batch.append(item)
                        idx += 1
                    break
                batch.append(item)
                current_chars += item_len
                idx += 1
                
            pct = (idx / total_to_translate) * 100
            print(f"[*] Batch {batch_count} ({engine_name}): translating {len(batch)} items ({current_chars} chars)... Progress: {idx}/{total_to_translate} ({pct:.2f}%)")
            
            results = translate_batch(batch)
            if results is None:
                print("[-] Fatal: Translation failed. Saving cache and exiting.")
                break
                
            # Add to cache
            for orig, trans in zip(batch, results):
                cache[orig] = trans
                
            # Periodic cache save
            try:
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[-] Error saving cache: {e}")
                
            if GOOGLE_API_KEY:
                sleep_time = 0.5
            else:
                sleep_time = 2.0 if USE_MYMEMORY else 1.5
            time.sleep(sleep_time)

    # Update CSV rows
    print("[+] Mapping translations back to CSV...")
    translated_speakers = 0
    translated_dialogues = 0
    
    for row in rows:
        speaker = row[2]
        dialogue = row[4]
        
        if speaker:
            if speaker in cache:
                row[3] = cache[speaker]
                translated_speakers += 1
            else:
                row[3] = speaker
        else:
            row[3] = ""
            
        if dialogue:
            if dialogue in cache:
                row[5] = cache[dialogue]
                translated_dialogues += 1
            else:
                row[5] = dialogue
        else:
            row[5] = ""

    # Write CSV back
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"[+] Successfully wrote translations to {CSV_PATH}.")
    print(f"    - Updated {translated_speakers} speaker rows.")
    print(f"    - Updated {translated_dialogues} dialogue rows.")

if __name__ == "__main__":
    main()
