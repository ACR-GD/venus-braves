#!/usr/bin/env python3
"""
patch_prophecy_only.py
Applies ONLY the prophecy translation to predict.fhm.
All other cdimage_unpacked/ files remain as extracted originals.
"""
import struct, csv, re, os, sys

WORKSPACE = "/Users/acr/Develop/venus-braves"
PREDICT_PATH = os.path.join(WORKSPACE, "cdimage_unpacked/seven_data_link/scrdata/message/info/predict.fhm")
CATALOG_PATH = os.path.join(WORKSPACE, "translation_catalog.csv")


def bit_swap_xor(data: bytes) -> bytes:
    """Symmetric decrypt/encrypt: swap nibbles and XOR per byte."""
    result = bytearray(len(data))
    for i, b in enumerate(data):
        swapped = ((b & 0x0F) << 4) | ((b & 0xF0) >> 4)
        result[i] = swapped ^ 0xFF
    return bytes(result)


def main():
    # 1. Load prophecy translation from catalog
    print("[+] Loading prophecy translation from catalog...")
    prophecy_text = None
    with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Category'] == 'Story/Prophecy' and row['EnglishTranslation'].strip():
                prophecy_text = row['EnglishTranslation']
                break

    if not prophecy_text:
        print("[!] No prophecy translation found in catalog. Exiting.")
        return 1

    # Fix up the text:
    # 1. Replace literal \\x00 sequences with real null bytes
    # 2. Replace Japanese quotation brackets with ASCII equivalents
    # 3. Replace any other non-ASCII with ?
    prophecy_text = prophecy_text.replace('\\x00', '\x00')
    prophecy_text = prophecy_text.replace('「', '"').replace('」', '"')
    prophecy_text = prophecy_text.replace('『', '"').replace('』', '"')

    print(f"    Preview: {prophecy_text[:100]!r}...")

    # 2. Read original predict.fhm
    with open(PREDICT_PATH, 'rb') as f:
        original = f.read()

    num_entries = struct.unpack_from('<I', original, 0)[0]
    offsets = [struct.unpack_from('<I', original, 4 + i*4)[0] for i in range(num_entries)]
    print(f"[+] predict.fhm: {len(original)} bytes, {num_entries} entries")

    if num_entries < 19 or num_entries > 100:
        print(f"[!] Unexpected entry count ({num_entries}). Expected 19. Aborting.")
        return 1

    # Entry 18 = encrypted prophecy payload
    entry18_start = offsets[18]
    entry18_size  = len(original) - entry18_start
    print(f"    Entry 18: offset={entry18_start}, size={entry18_size}")

    # 3. Encode as ASCII (prophecy is English, game renders byte chars)
    new_text = prophecy_text.encode('ascii', errors='replace')

    # Pad/truncate to exactly entry18_size bytes (preserve the file size)
    if len(new_text) < entry18_size:
        new_text = new_text + b'\x00' * (entry18_size - len(new_text))
    else:
        new_text = new_text[:entry18_size]
        print(f"    [!] Prophecy text truncated to {entry18_size} bytes")

    # 4. Re-encrypt and write back
    encrypted = bit_swap_xor(new_text)
    new_file = original[:entry18_start] + encrypted
    assert len(new_file) == len(original), f"Size mismatch: {len(new_file)} vs {len(original)}"

    with open(PREDICT_PATH, 'wb') as f:
        f.write(new_file)

    print(f"[+] predict.fhm patched successfully (size unchanged: {len(new_file)} bytes)")

    # Verify round-trip
    decrypted_back = bit_swap_xor(encrypted)
    try:
        sample = decrypted_back.split(b'\x00')[0].decode('ascii')
        print(f"    Verify: {sample[:60]!r}")
    except Exception as e:
        print(f"    Verify failed: {e}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
