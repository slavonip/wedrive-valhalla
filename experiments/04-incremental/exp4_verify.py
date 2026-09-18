"""Before believing 1423, check the scanner against chance.

A GraphId's (level, tile) half is 25 bits. Scanning a tile as raw 64-bit words, any word matches
one of 185 targets with probability 185 / 2**25 = 5.5e-6. A one-megabyte tile holds 131 072
words, so roughly 0.7 FALSE hits are expected per tile per pass — over 2 642 tiles that is about
1 900 spurious "references", which is the order of the 1 423 reported.

So the raw scan cannot be trusted. Two checks:

  1. a NEGATIVE CONTROL — scan for the same number of tile keys that do NOT exist in this build.
     Whatever that finds is pure chance, and the real signal has to stand above it.
  2. the DEFENSIBLE SET — a tile that genuinely holds a reference whose target renumbered must
     also DIFFER between T0 and REF. Chance hits cannot satisfy both.
"""
import json
import pathlib
import struct

import numpy as np

ROOT = pathlib.Path("/data")
MASK = [(32, 40), (88, 96)]
GB = 1 << 30
SIZES = {0: 4.0, 1: 1.0, 2: 0.25}
COUNTRIES = ["RO", "HU", "RS", "BG", "MD", "UA"]


def masked(p):
    d = bytearray(p.read_bytes())
    for s, e in MASK:
        d[s:e] = b"\0" * (e - s)
    return bytes(d)


def parse(n):
    parts = n.split("/")
    return int(parts[0]), int("".join(parts[1:]).removesuffix(".gph"))


def tiles_of(label):
    base = ROOT / label / "tiles"
    return {str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}


def cut_of(label, c):
    base = ROOT / label / "cuts" / c
    return ({str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}
            if base.is_dir() else {})


blob = json.load(open(ROOT / "closure.json"))
renumbered = blob["renumbered"]
minimal_extra = blob["minimal_extra"]

T0, REF = tiles_of("T0"), tiles_of("REF")
installed = {}
for c in COUNTRIES:
    installed.update(cut_of("T0", c))
ro_ref = cut_of("REF", "RO")
outside = {n: p for n, p in installed.items() if n not in ro_ref}

real_keys = np.array(sorted({lvl | (tid << 3) for lvl, tid in (parse(n) for n in renumbered)}),
                     dtype=np.uint64)
# Keys of tiles that do not exist anywhere in this build: same count, same levels, shifted ids.
existing = {lvl | (tid << 3) for lvl, tid in (parse(n) for n in T0)}
fake = []
for k in real_keys:
    cand = int(k)
    while cand in existing or cand in fake:
        cand += 8 * 977            # step by whole tiles, staying on the same level
    fake.append(cand)
fake_keys = np.array(sorted(fake), dtype=np.uint64)

hits_real = hits_fake = 0
for name, p in outside.items():
    raw = p.read_bytes()
    arr = np.frombuffer(raw, dtype="<u8", count=len(raw) // 8)
    low = arr & np.uint64(0x1FFFFFF)
    if np.isin(low, real_keys).any():
        hits_real += 1
    if np.isin(low, fake_keys).any():
        hits_fake += 1

print("=== is the scan signal or chance? ===")
print(f"  tiles outside Romania                      {len(outside)}")
print(f"  matching a RENUMBERED tile's key           {hits_real}")
print(f"  matching a NON-EXISTENT tile's key         {hits_fake}   <- pure chance")
print(f"  => the raw scan is {'MOSTLY NOISE' if hits_fake > hits_real * 0.5 else 'signal'}")
print()
print("=== the defensible set: references AND actually differs ===")
print(f"  tiles outside Romania that differ T0 vs REF  "
      f"{sum(1 for n, p in outside.items() if n in REF and masked(p) != masked(REF[n]))}")
print(f"  of those, also matching a renumbered key     {len(minimal_extra)}")
print()

# ── where does the closure live? ────────────────────────────────────────────────────────────
print("=== the closure, by level and country ===")
by_level = {}
for n in minimal_extra:
    lvl, _ = parse(n)
    by_level.setdefault(lvl, []).append(n)
for lvl in sorted(by_level):
    b = sum(REF[n].stat().st_size for n in by_level[lvl])
    print(f"  level {lvl}: {len(by_level[lvl]):>4} tiles  {b/GB:7.3f} GB")
for c in COUNTRIES:
    cut = cut_of("T0", c)
    mine = [n for n in minimal_extra if n in cut]
    if mine:
        b = sum(REF[n].stat().st_size for n in mine)
        print(f"  {c}: {len(mine):>4} tiles  {b/GB:7.3f} GB")

print()
print("=== how much of each country's package had to move? ===")
for c in COUNTRIES:
    cut = cut_of("T0", c)
    ch = [n for n in cut if n in REF and masked(cut[n]) != masked(REF[n])]
    tot = sum(p.stat().st_size for p in cut.values())
    b = sum(REF[n].stat().st_size for n in ch)
    print(f"  {c}: {len(ch):>4} of {len(cut):>4} tiles changed   "
          f"{b/GB:7.3f} of {tot/GB:7.3f} GB  ({100*b/max(tot,1):5.1f} %)")
