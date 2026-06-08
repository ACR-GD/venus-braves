#!/usr/bin/env python3
"""
insert_prophecy.py
==================
Inserts translated English prophecy text into predict.fhm

CRITICAL: The file MUST stay the same size as the original.
Growing the file shifts all subsequent files in CDIMAGE.BIN,
breaking the game's internal file offset table and causing freezes.

Strategy: fit each EN segment into its corresponding JP segment's byte
budget (with minimum 16 bytes per segment), truncating at word/sentence
boundaries if needed.

Structure of predict.fhm:
  Bytes 0-3:    num_entries (19)
  Bytes 4-79:   19 x uint32 offsets to each entry
  Bytes 80+:    entry data payloads
  Entry 18 (last): XOR-encrypted block of null-terminated Shift-JIS strings
"""
import struct, shutil, csv, re, os, sys

ORIG    = "cdimage_temp_unpacked/seven_data_link/scrdata/message/info/predict.fhm"
TARGET  = "cdimage_unpacked/seven_data_link/scrdata/message/info/predict.fhm"
CATALOG = "translation_catalog.csv"

# ── Crypto ────────────────────────────────────────────────────────────────────

def swap_bits(idx):
    return (((idx & 0x55555555) << 1) | ((idx & 0xAAAAAAAA) >> 1)) & 0xFF

def xor_crypt(data):
    """Symmetric XOR encrypt/decrypt with bit-swap key."""
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ swap_bits(i // 4)
    return bytes(out)

# ── Helpers ───────────────────────────────────────────────────────────────────

def unescape(s):
    """Convert literal \\x00, \\n, etc. back to real characters."""
    s = re.sub(r'\\x([0-9A-Fa-f]{2})',
               lambda m: chr(int(m.group(1), 16)), s)
    return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')

def clean_for_ascii(s):
    """Convert JP-only punctuation to ASCII equivalents."""
    s = unescape(s)
    for jp, en in [('「','"'),('」','"'),('『','"'),('』','"'),
                   ('…','...'),('―','-'),('–','-'),('　',' ')]:
        s = s.replace(jp, en)
    return s

def fit_to_budget(text, budget):
    """
    Encode text as Latin-1 and truncate to budget-1 bytes (leaving 1 for null).
    Truncates at sentence then word boundary.
    """
    encoded = text.encode('latin-1', errors='replace')
    if len(encoded) <= budget - 1:
        return encoded

    limit = budget - 1
    truncated = encoded[:limit]

    # Try sentence boundary
    for punct in (b'.\n', b'!\n', b'?\n', b'. ', b'! ', b'? '):
        idx = truncated.rfind(punct)
        if idx > limit // 2:
            return truncated[:idx + 1]

    # Try word boundary
    idx = truncated.rfind(b' ')
    if idx > limit // 2:
        return truncated[:idx]

    return truncated  # hard cut

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Load the clean original as structural template
    if not os.path.exists(ORIG):
        print(f"ERROR: Original not found: {ORIG}")
        sys.exit(1)
    orig_data = open(ORIG, 'rb').read()
    print(f"[+] Original: {len(orig_data):,} bytes")

    num_entries = struct.unpack_from('<I', orig_data, 0)[0]
    offsets = [struct.unpack_from('<I', orig_data, 4 + i*4)[0]
               for i in range(num_entries)]
    e18_start = offsets[18]
    e18_raw   = orig_data[e18_start:]
    e18_dec   = xor_crypt(e18_raw)
    BUDGET    = len(e18_dec)  # MUST stay exactly this size

    # Parse original JP segments to get per-segment byte budgets
    jp_segs = []
    pos = 0
    while pos < len(e18_dec):
        end = e18_dec.find(b'\x00', pos)
        if end == -1: end = len(e18_dec)
        jp_segs.append(e18_dec[pos:end])
        pos = end + 1
    print(f"    {num_entries} entries, Entry 18 at offset {e18_start}")
    print(f"    {len(jp_segs)} JP strings, BUDGET={BUDGET:,} bytes (FIXED — cannot change)")

    # 2. Load translation
    blob = None
    with open(CATALOG, newline='', encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            if 'predict.fhm' in row.get('File','') and row.get('EnglishTranslation','').strip():
                blob = row['EnglishTranslation']
                break
    if blob is None:
        print("ERROR: No prophecy translation in catalog")
        sys.exit(1)

    # 3. Split and clean
    en_segs = [clean_for_ascii(s) for s in blob.split('\\x00')]
    print(f"[+] {len(en_segs)} EN segments loaded")

    # 4. Fit each segment into its JP byte budget
    assembled = bytearray()
    truncated_count = 0
    for i, en_text in enumerate(en_segs):
        jp_size   = len(jp_segs[i]) if i < len(jp_segs) else 16
        seg_budget = max(jp_size + 1, 16)  # allow 1 extra byte minimum, min 16

        fitted = fit_to_budget(en_text, seg_budget)
        en_bytes = en_text.encode('latin-1', errors='replace')
        if len(fitted) < len(en_bytes):
            truncated_count += 1
        assembled.extend(fitted)
        assembled.append(0)  # null terminator

    # Trim or pad to exactly BUDGET bytes (file size must not change)
    if len(assembled) > BUDGET:
        assembled = bytearray(assembled[:BUDGET])
        assembled[-1] = 0
    elif len(assembled) < BUDGET:
        assembled.extend(b'\x00' * (BUDGET - len(assembled)))

    assert len(assembled) == BUDGET

    print(f"[+] Assembled: {BUDGET:,} bytes ({truncated_count}/{len(en_segs)} segments truncated to fit)")

    # 5. XOR-encrypt
    new_enc = xor_crypt(bytes(assembled))

    # 6. Rebuild file — SAME size as original
    new_file = orig_data[:e18_start] + new_enc
    assert len(new_file) == len(orig_data), \
        f"BUG: file size changed {len(new_file)} != {len(orig_data)}"
    print(f"[+] File size: {len(new_file):,} bytes (unchanged ✓)")

    # 7. Verify
    verify = xor_crypt(new_enc)
    first_null = verify.find(b'\x00')
    first_str  = verify[:first_null].decode('latin-1', 'replace')
    print(f"\n[+] First string: {repr(first_str[:80])}")
    # Last string logic would go here if needed, but original used non-existent variable

    # ── 8. Write ───────────────────────────────────────────────────────────
    backup = TARGET + '.bak'
    if not os.path.exists(backup):
        shutil.copy2(TARGET, backup)
        print(f"\n[+] Backup saved: {backup}")

    open(TARGET, 'wb').write(new_file)
    print(f"[+] Written: {TARGET}")
    print(f"\n✓ predict.fhm patched! Next:")
    print(f"  python3 repack_cdimage.py && python3 patch_iso.py")


if __name__ == '__main__':
    main()
