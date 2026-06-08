#!/usr/bin/env python3
import struct, glob, os, itertools
from ulz_exact import chunks, decode

CAP = 96

def search_pruned(chunk, target, cap=CAP):
    n = len(chunk); best = (0, None)
    tgt = target[:cap]
    t0 = target[0]
    for a in range(0, n + 1, 4):
        for b in range(a, n + 1, 2):
            parts = [(0, a), (a, b), (b, n)]
            for perm in itertools.permutations(range(3)):
                fr = parts[perm[0]]; sr = parts[perm[1]]; lr = parts[perm[2]]
                if fr[1] - fr[0] < 4 or (fr[1] - fr[0]) % 4 != 0:
                    continue
                if sr[1] <= sr[0] or chunk[sr[0]] != t0:   # sym[0] must equal target[0]
                    continue
                if not (chunk[fr[0]+3] & 0x80):            # token0 literal => MSB(first flagword)=1 (SET)
                    continue
                for ob in (10, 11, 12, 13, 14, 15):
                    m = decode(chunk, fr[0], fr[1], sr[0], sr[1], lr[0], lr[1], ob, 2, tgt)
                    if m > best[0]:
                        best = (m, (fr, sr, lr, ob, 2))
    return best

if __name__ == '__main__':
    ups = sorted(glob.glob('scratch/gs_uploads/up*.bin'))
    ups = [u for u in ups if os.path.getsize(u) == 8192]
    print('chunk0 vs %d uploads (pruned, type2, cap=%d):' % (len(ups), CAP))
    res = []
    for u in ups:
        t = open(u, 'rb').read()
        m, p = search_pruned(chunks[0], t)
        res.append((m, os.path.basename(u), p))
    res.sort(reverse=True)
    for m, name, p in res[:10]:
        print('  %-22s match=%3d  %s' % (name, m, p))
