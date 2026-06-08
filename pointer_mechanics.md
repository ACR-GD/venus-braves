# Venus & Braves Hacking Guide: Pointer & Offset Mechanics

When translating the Japanese text of *Venus & Braves* into English, strings will naturally change in size. This document describes the binary file structures, offset tables, pointer rules, and formatting codes that must be adjusted during text re-insertion.

---

## 1. SPL Files (Dialogue & Story Scripts)
SPL files (`seven_data_link/scrdata/output/*.spl`) contain the main story scenarios and event dialogues.

### File Structure
An SPL file is structured as follows:
1. **Header (64 bytes)**: Consists of 16 32-bit little-endian integers (dwords).
   - `Dword 2` contains `table_off`, which specifies the start offset of the record table in the file.
2. **Record Table**: Starts at `table_off` and contains `num_records` 16-byte records.
   - Each record contains four dwords:
     - **Dword 0**: Speaker name pointer (relative to the start of the string pool).
     - **Dword 1**: Control flags.
     - **Dword 2**: Dialogue text pointer (relative to the start of the string pool).
     - **Dword 3**: Control flags.
3. **String Pool**: Starts at `pool_start` = `table_off + (num_records * 16)`.
   - Contains null-terminated Shift-JIS strings. The size of this pool in bytes is `pool_size`.
4. **Bytecode/Trailing Data**: Starts immediately after the string pool at `pool_start + pool_size` and continues to the end of the file.

### Pointer Shifting Rules
When translating strings to English, the size of the string pool will change from `old_pool_size` to `new_pool_size`. Let the size difference be:
$$\text{size\_diff} = \text{new\_pool\_size} - \text{old\_pool\_size}$$

Every pointer (Dword 0 or Dword 2) in the record table must be processed as follows:
- **Null Pointers**: If the value is `0xFFFFFFFF`, leave it as `0xFFFFFFFF`.
- **String Pool Pointers**: If the value is $< \text{old\_pool\_size}$, it points to a string. When rebuilding the string pool, write the translated string to the new pool and update the pointer with its new relative offset from the start of the new string pool.
- **Trailing Bytecode Pointers**: If the value is $\ge \text{old\_pool\_size}$, it is not a string pointer. Instead, it points to bytecode instructions or control structures in the trailing data. Because the trailing data is shifted by `size_diff` bytes due to the changed pool size, these pointers **must** be adjusted:
  $$\text{new\_value} = \text{old\_value} + \text{size\_diff}$$

Failure to adjust trailing bytecode pointers will cause the game engine to execute garbage data or crash.

### Suffix-Sharing & Mid-Byte Distortion
To minimize storage, the compiler reuses suffixes of strings in the string pool. Multiple record pointers can point to different offsets within the same string block.
- **Mid-byte Suffixing**: When a pointer references the middle of a double-byte CP932 character, the second byte of that character combines with subsequent bytes. This distorts the first decoded character of the suffix (e.g. `おまえは` becoming `ｨまえは`).
- **Translation Rebuilding Rule**: When translating to English, suffix sharing will usually break because English translations do not share suffixes in the same way. During reconstruction, it is recommended to split shared suffixes into unique string entries and update their respective record pointers. If any pointers are left pointing to the middle of an English string, they will display cut-off/corrupted English characters.

---

## 2. NHT Files (Help & Tutorials)
NHT files (`seven_data_link/futa/help/*.nht`) contain the help reference pages and tutorial screens.

### File Structure
An NHT file is structured as follows:
1. **Offset Table**:
   - The first 4 bytes (`uint32`) contain `num_offsets` (the number of help pages).
   - This is followed by `num_offsets` 32-bit absolute offsets (relative to the start of the file) pointing to each page block.
2. **Help Blocks**: Each block contains a single help page.
   - **Title (64 bytes)**: A fixed-size block starting at the block offset. It contains a null-terminated Shift-JIS title string padded with zeros.
   - **Body (variable size)**: Starts at offset `0x40` within the block. It contains a null-terminated Shift-JIS description string.

### Inline Control Codes
Help bodies contain layout formatting and referencing tags:
- `\x11`: Start highlighted term / link.
- `\x10`: End highlighted term / link.
- `\x14\xXX`: Hyperlink reference pointing to block index `\xXX`. For example, `\x14\x28` references block `0x28` (40).
- `\x15\xXX` or `\x15\xXX\x03`: Page navigation target pointing to block index `\xXX`.

### Offset Table Mechanics
There are no internal pointers inside NHT blocks. When translating a block's body text:
1. The title must remain padded to exactly 64 bytes (`0x40`).
2. The body text can be of arbitrary length (null-terminated).
3. The new size of the block `i` is $64 + \text{len(new\_body\_bytes)} + 1$.
4. Recalculate the absolute offsets for the header table sequentially:
   - $\text{offset}[0] = 4 + (\text{num\_offsets} \times 4)$
   - $\text{offset}[i] = \text{offset}[i-1] + \text{size}(\text{block}[i-1])$
5. Update the offset table at the beginning of the file.

---

## 3. FHM Files (Container Archives)
FHM files (e.g. `finfomes.fhm`, `predict.fhm`) are archives containing game assets or message logs.

### File Structure
1. **Header**:
   - First 4 bytes: `num_entries` (number of files inside the archive).
   - Next `num_entries * 4` bytes: 32-bit offsets pointing to the entries.
2. **Entry Payload**:
   - Each entry contains a binary prefix (which often describes formatting or size constraints) followed by Shift-JIS text.

### Prophecy Decryption (predict.fhm Entry 18)
Entry 18 in `predict.fhm` contains the game prophecies and is obfuscated.
- **Decryption/Encryption Algorithm**: Bit-swap XOR.
- For each byte `i` in the entry, the XOR key is derived by swapping the adjacent bits of the block index (`block_idx = i // 4`):
  ```python
  def swap_bits(idx):
      return (((idx & 0x55555555) << 1) | ((idx & 0xAAAAAAAA) >> 1)) & 0xFF
  
  def crypt_byte(b, i):
      return b ^ swap_bits(i // 4)
  ```
- Re-insertion requires encrypting the translated English string using this same algorithm.

---

## 4. ELF Executable (SLPS_251.96)
The main executable contains hardcoded string tables for jobs, item names, region names, and system prompts.

### Struct Boundaries & Length Constraints
ELF strings are stored in fixed-size structs or contiguous data blocks.
- **Item Names**: Stored in a structure at interval of 116 bytes. The string itself must be null-terminated and cannot exceed the size allocated for it (usually 32 or 40 bytes).
- **Location Names**: Stored in structures at intervals of 82 bytes.
- **In-place Replacement**: If translating in-place (without relocating pointers), the English string **must** fit within the original boundaries (terminated by a null byte `\x00`). If the English string exceeds the original length, it will overwrite adjacent struct fields (such as stats, prices, or IDs), causing memory corruption or gameplay bugs.
- **Relocation**: If longer text is required, MIPS assembly hacking is necessary:
  1. Relocate the strings to a blank/unused memory segment of the ELF.
  2. Locate the MIPS instruction loading the original address (e.g., `lui`/`addiu` pointer loads).
  3. Relocate these pointer references to the new address in RAM.
