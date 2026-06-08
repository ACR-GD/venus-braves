#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#define N 2048

void *memmem(const void *haystack, size_t haystacklen,
             const void *needle, size_t needlelen) {
    if (!needlelen) return (void *)haystack;
    if (needlelen > haystacklen) return NULL;
    const char *h = haystack;
    const char *n = needle;
    for (size_t i = 0; i <= haystacklen - needlelen; i++) {
        if (h[i] == n[0] && memcmp(h + i, n, needlelen) == 0) {
            return (void *)(h + i);
        }
    }
    return NULL;
}

int try_lzss(uint8_t *data, size_t data_len, int F, int T, int start_pos, int flag_inv, int flag_msb, int pack_type, int init_byte, uint8_t *out) {
    uint8_t text_buf[N];
    memset(text_buf, init_byte, N);
    int r = start_pos;
    int out_len = 0;
    int pos = 0;
    
    while (pos < data_len && out_len < 64) {
        uint8_t flags = data[pos++];
        if (flag_inv) flags = ~flags & 0xFF;
        
        for (int i = 0; i < 8; i++) {
            if (pos >= data_len || out_len >= 64) break;
            
            int bit = flag_msb ? ((flags >> (7-i)) & 1) : ((flags >> i) & 1);
            
            if (bit == 1) {
                uint8_t c = data[pos++];
                out[out_len++] = c;
                text_buf[r] = c;
                r = (r + 1) & (N - 1);
            } else {
                if (pos + 1 >= data_len) break;
                uint8_t lo = data[pos++];
                uint8_t hi = data[pos++];
                
                int match_offset = 0;
                int match_len = 0;
                
                if (pack_type == 0) {
                    match_offset = lo | ((hi & 0x0F) << 8);
                    match_len = (hi >> 4) + T;
                } else if (pack_type == 1) {
                    match_offset = (hi << 4) | (lo >> 4);
                    match_len = (lo & 0x0F) + T;
                } else if (pack_type == 2) {
                    match_offset = lo | ((hi & 0xF0) << 4);
                    match_len = (hi & 0x0F) + T;
                } else if (pack_type == 3) {
                    match_offset = (lo << 4) | (hi >> 4);
                    match_len = (hi & 0x0F) + T;
                }
                
                for (int k = 0; k < match_len; k++) {
                    if (out_len >= 64) break;
                    uint8_t c = text_buf[(match_offset + k) & (N - 1)];
                    out[out_len++] = c;
                    text_buf[r] = c;
                    r = (r + 1) & (N - 1);
                }
            }
        }
    }
    return out_len;
}

int main() {
    FILE *f_ram = fopen("scratch/options_savestate/eeMemory.bin", "rb");
    if (!f_ram) { printf("Failed to open eeMemory.bin\n"); return 1; }
    
    fseek(f_ram, 0, SEEK_END);
    size_t ram_size = ftell(f_ram);
    fseek(f_ram, 0, SEEK_SET);
    
    uint8_t *ee_ram = malloc(ram_size);
    fread(ee_ram, 1, ram_size, f_ram);
    fclose(f_ram);
    
    FILE *f_opt = fopen("cdimage_unpacked/seven_data_link/futa/screen/option.fhm", "rb");
    if (!f_opt) { printf("Failed to open option.fhm\n"); return 1; }
    
    fseek(f_opt, 0, SEEK_END);
    size_t fhm_size = ftell(f_opt);
    fseek(f_opt, 0, SEEK_SET);
    uint8_t *fhm_data = malloc(fhm_size);
    fread(fhm_data, 1, fhm_size, f_opt);
    fclose(f_opt);
    
    uint32_t offset3 = *(uint32_t*)(fhm_data + 4 + 3*4);
    uint32_t offset4 = *(uint32_t*)(fhm_data + 4 + 4*4);
    
    uint8_t *entry3 = fhm_data + offset3;
    uint32_t chunk_offsets[9];
    for (int k=0; k<8; k++) chunk_offsets[k] = *(uint32_t*)(entry3 + 0x10 + k*4);
    chunk_offsets[8] = offset4 - offset3;
    
    int F_vals[] = {18, 16, 17, 34};
    int T_vals[] = {2, 3, 1};
    int flag_inv_vals[] = {0, 1};
    int flag_msb_vals[] = {0, 1};
    int pack_type_vals[] = {0, 1, 2, 3};
    int init_byte_vals[] = {0, 0x20, 0xFF};
    
    printf("Starting brute force in C...\n");
    int found = 0;
    uint8_t out[256];
    
    for (int chunk_idx = 0; chunk_idx < 4; chunk_idx++) {
        uint8_t *chunk = entry3 + chunk_offsets[chunk_idx];
        size_t chunk_len = chunk_offsets[chunk_idx+1] - chunk_offsets[chunk_idx];
        
        for (int iF = 0; iF < 4 && !found; iF++) {
            int F = F_vals[iF];
            for (int iT = 0; iT < 3 && !found; iT++) {
                int T = T_vals[iT];
                int start_pos_vals[] = {2048 - F, 2048 - F - T, 0, 2048 - 16, 2048 - 18, 2048 - 1};
                
                for (int iSP = 0; iSP < 6 && !found; iSP++) {
                    int start_pos = start_pos_vals[iSP];
                    for (int iFI = 0; iFI < 2 && !found; iFI++) {
                        int flag_inv = flag_inv_vals[iFI];
                        for (int iFM = 0; iFM < 2 && !found; iFM++) {
                            int flag_msb = flag_msb_vals[iFM];
                            for (int iPT = 0; iPT < 4 && !found; iPT++) {
                                int pack_type = pack_type_vals[iPT];
                                for (int iIB = 0; iIB < 3 && !found; iIB++) {
                                    int init_byte = init_byte_vals[iIB];
                                    
                                    int out_len = try_lzss(chunk, chunk_len, F, T, start_pos, flag_inv, flag_msb, pack_type, init_byte, out);
                                    if (out_len >= 32) {
                                        void *match = memmem(ee_ram, ram_size, out, 32);
                                        if (match) {
                                            size_t idx = (uint8_t*)match - ee_ram;
                                            printf("MATCH FOUND at RAM offset 0x%zx for chunk %d!\n", idx, chunk_idx);
                                            printf("Parameters: F=%d, T=%d, start_pos=%d, flag_inv=%d, flag_msb=%d, pack_type=%d, init_byte=0x%x\n",
                                                F, T, start_pos, flag_inv, flag_msb, pack_type, init_byte);
                                                
                                            if (out_len >= 64 && memmem(ee_ram, ram_size, out, 64)) {
                                                printf("64-byte match VERIFIED!\n");
                                                found = 1;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    if (!found) printf("No match found.\n");
    
    free(ee_ram);
    free(fhm_data);
    return 0;
}
