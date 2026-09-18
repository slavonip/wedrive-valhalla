"""Experiment 5, part 3: build EXACT_MIXED and test it two ways.

SUFFICIENCY   does the computed closure make the assembly behave exactly like the coherent
              reference? Compared by geometry SHA, so "the same" means the same points.

MINIMALITY    is any of it wasted? Remove single closure tiles, one at a time, and see whether a
              defect returns. A closure that is merely sufficient says nothing about how much of
              it was needed — and experiment 4 has already shown that an absent failure is not an
              absent defect, so the tiles chosen for removal are the ones whose stale references
              the eight routes plausibly traverse, not an arbitrary sample.
"""
import json
import os
import pathlib
import shutil

ROOT = pathlib.Path("/data")
E = json.load(open(ROOT / "exact.json"))
COUNTRIES = ["RO", "HU", "RS", "BG", "MD", "UA"]


def cut_of(label, c):
    base = ROOT / label / "cuts" / c
    return ({str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}
            if base.is_dir() else {})


def tiles_of(label):
    base = ROOT / label / "tiles"
    return {str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}


REF = tiles_of("REF")
installed = {}
for c in COUNTRIES:
    installed.update(cut_of("T0", c))

take = set(E["ro_from_ref"]) | set(E["exact"])


def assemble(name, take_ref):
    out = ROOT / name / "tiles"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    n = 0
    for tile, src in installed.items():
        chosen = REF[tile] if (tile in take_ref and tile in REF) else src
        dst = out / tile
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chosen, dst)
        n += 1
    for tile in E["ro_from_ref"]:
        if tile not in installed and tile in take_ref and tile in REF:
            dst = out / tile
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REF[tile], dst)
            n += 1
    return n


print(f"EXACT_MIXED: {assemble('EXACT_MIXED', take)} tiles "
      f"(Romania {len(E['ro_from_ref'])} + closure {len(E['exact'])})")

# For the minimality test, drop ONE closure tile at a time. Pick the largest, which carry the
# most references, and a few at random so the choice is not only the easy cases.
import random
random.seed(7)
by_size = sorted(E["exact"], key=lambda n: -REF[n].stat().st_size)
picks = by_size[:4] + random.sample(E["exact"], min(4, len(E["exact"])))
picks = list(dict.fromkeys(picks))[:6]
json.dump(picks, open(ROOT / "picks.json", "w"))
for i, tile in enumerate(picks):
    n = assemble(f"MINUS_{i}", take - {tile})
    print(f"MINUS_{i}: {n} tiles — closure minus {tile} "
          f"({REF[tile].stat().st_size/1048576:.1f} MB)")
