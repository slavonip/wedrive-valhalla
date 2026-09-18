"""Experiment 4, part 2: four assemblies, and a closure computed rather than observed.

  REF             one coherent master: neighbours @ T0, Romania @ T1. The correct answer.
  BROKEN_MIXED    neighbours @ T0 + Romania's cut from REF. Nothing else. The control.
  MIXED           neighbours @ T0 + EVERY differing tile from REF. An upper bound: a tile can
                  differ because it holds fresher Romanian roads rather than because it holds a
                  stale reference, so this replaces more than correctness requires.
  MINIMAL_MIXED   neighbours @ T0 + Romania's cut + exactly the tiles a DEPENDENCY-CLOSURE
                  ALGORITHM says must come too. This is the number a server would compute, and
                  the only one that answers "what must the car download".

THE PREDICTOR, stated before any route is run and worded carefully.

Experiment 3 established that a tile's ids shift exactly when its node/edge counts change. So the
tiles the car keeps at T0 are unsafe precisely when they hold a reference into a tile whose counts
moved. Finding such references does NOT entitle anyone to say "BROKEN must fail": eight chosen
routes may simply never traverse them. The honest claim is narrower —

    BROKEN_MIXED contains PROVABLY STALE REFERENCES, and at least one test that actually
    traverses one of them must differ from REF or refuse.

— which is why stale references are turned into TARGETED probes below instead of hoping the
general route set happens to cross one. Absence of an observed failure is not absence of a
defect; this project learned that from a coordinate in Vienna.
"""
import json
import os
import pathlib
import shutil
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


def counts(p):
    v = struct.unpack_from("<Q", p.read_bytes(), 40)[0]
    return v & 0x1FFFFF, (v >> 21) & 0x1FFFFF


def parse(name):
    parts = name.split("/")
    return int(parts[0]), int("".join(parts[1:]).removesuffix(".gph"))


def bbox(tid, level):
    s = SIZES[level]
    row, col = divmod(tid, int(360 / s))
    return col * s - 180, row * s - 90, col * s - 180 + s, row * s - 90 + s


def centre(tid, level):
    w, s, e, n = bbox(tid, level)
    return (s + n) / 2, (w + e) / 2


def tiles_of(label, sub="tiles"):
    base = ROOT / label / sub
    return {str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}


def cut_of(label, c):
    base = ROOT / label / "cuts" / c
    return ({str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}
            if base.is_dir() else {})


T0, REF = tiles_of("T0"), tiles_of("REF")
print(f"master tiles   T0 {len(T0)}   REF {len(REF)}")

shared = sorted(set(T0) & set(REF))
changed, renumbered = [], []
for n in shared:
    if masked(T0[n]) != masked(REF[n]):
        changed.append(n)
        if counts(T0[n]) != counts(REF[n]):
            renumbered.append(n)
print(f"  added {len(set(REF)-set(T0))}  removed {len(set(T0)-set(REF))}  shared {len(shared)}")
print(f"  CHANGED {len(changed)}   RENUMBERED (counts moved) {len(renumbered)}")
print(f"  changed only by references {len(changed)-len(renumbered)}")

installed = {}
for c in COUNTRIES:
    installed.update(cut_of("T0", c))
ro_ref = cut_of("REF", "RO")
print(f"installed (six T0 cuts) {len(installed)} tiles "
      f"{sum(p.stat().st_size for p in installed.values())/GB:.3f} GB")
print(f"Romania REF cut         {len(ro_ref)} tiles "
      f"{sum(p.stat().st_size for p in ro_ref.values())/GB:.3f} GB")

# ── THE ALGORITHMIC CLOSURE ─────────────────────────────────────────────────────────────────
# A GraphId is level:3 | tileid:22 | id:21, so (value & 0x1FFFFFF) names (level, tile) alone.
# Scan every tile the car holds for 64-bit words pointing into a RENUMBERED tile.
S_keys = np.array(sorted({lvl | (tid << 3) for lvl, tid in (parse(n) for n in renumbered)}),
                  dtype=np.uint64)
print(f"\nscanning {len(installed)} installed tiles for references into "
      f"{len(S_keys)} renumbered tiles...")

referencing = []
for name, p in installed.items():
    if name in ro_ref:
        continue                       # Romania's own tiles arrive from REF regardless
    raw = p.read_bytes()
    arr = np.frombuffer(raw, dtype="<u8", count=len(raw) // 8)
    if np.isin(arr & np.uint64(0x1FFFFFF), S_keys).any():
        hits = arr[np.isin(arr & np.uint64(0x1FFFFFF), S_keys)]
        targets = sorted({int(h) & 0x1FFFFFF for h in hits[:4000]})
        referencing.append((name, len(hits), targets[:4]))

print(f"  tiles holding references into a renumbered tile: {len(referencing)}")

ref_names = {n for n, _, _ in referencing}
ro_changed = [n for n in changed if n in ro_ref]
new_in_ro = sorted(n for n in ro_ref if n not in installed)
update_all = sorted(n for n in installed if n in REF and masked(installed[n]) != masked(REF[n]))
outside_ro_all = [n for n in update_all if n not in ro_ref]
minimal_extra = sorted(ref_names & set(update_all))


def size(names, src):
    return sum(src[n].stat().st_size for n in names if n in src)


whole_ro = sum(p.stat().st_size for p in ro_ref.values())
ro_part = size([n for n in update_all if n in ro_ref], REF) + size(new_in_ro, REF)

print("\n=== THE THREE NUMBERS ===")
print(f"  X  full Romania package                    {whole_ro/GB:8.3f} GB  "
      f"({len(ro_ref)} tiles)")
print(f"  Y  Romania tiles that actually changed     {ro_part/GB:8.3f} GB  "
      f"({len([n for n in update_all if n in ro_ref])+len(new_in_ro)} tiles)")
print(f"  Zmin  + ALGORITHMIC closure                "
      f"{(ro_part+size(minimal_extra, REF))/GB:8.3f} GB  (+{len(minimal_extra)} tiles)")
print(f"  Zall  + every differing tile (upper bound) "
      f"{(ro_part+size(outside_ro_all, REF))/GB:8.3f} GB  (+{len(outside_ro_all)} tiles)")
print(f"  ---")
print(f"  Y  / X = {100*ro_part/whole_ro:5.1f} %")
print(f"  Zmin/X = {100*(ro_part+size(minimal_extra, REF))/whole_ro:5.1f} %")
print(f"  Zall/X = {100*(ro_part+size(outside_ro_all, REF))/whole_ro:5.1f} %")

print("\n=== the predictor, before any route is run ===")
ren_installed = [n for n in renumbered if n in installed and n not in ro_ref]
print(f"  renumbered tiles among those the car keeps at T0: {len(ren_installed)}")
print(f"  T0 tiles provably holding stale references:       {len(referencing)}")
if referencing:
    print("  => BROKEN_MIXED contains PROVABLY STALE REFERENCES. That is not yet a prediction")
    print("     that any of the eight general routes fails; targeted probes below are built")
    print("     from the stale references themselves so the claim can be tested directly.")
else:
    print("  => nothing the car keeps references a renumbered tile. BROKEN_MIXED is then")
    print("     CORRECT, not merely lucky, and the closure is about freshness, not safety.")

# ── assemble ────────────────────────────────────────────────────────────────────────────────
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
    for tile in new_in_ro:
        if tile in take_ref:
            dst = out / tile
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REF[tile], dst)
            n += 1
    print(f"  {name:<14} {n} tiles  {sum(f.stat().st_size for f in out.rglob('*.gph'))/GB:.3f} GB")


print("\n=== assemblies ===")
ro_from_ref = set(n for n in update_all if n in ro_ref) | set(new_in_ro)
assemble("BROKEN_MIXED", ro_from_ref)
assemble("MINIMAL_MIXED", ro_from_ref | set(minimal_extra))
assemble("MIXED", set(update_all) | set(new_in_ro))

# ── targeted probes, built FROM the stale references ────────────────────────────────────────
probes = []
for name, nhits, targets in sorted(referencing, key=lambda r: -r[1])[:12]:
    lvl, tid = parse(name)
    for key in targets[:1]:
        tlvl, ttid = key & 7, key >> 3
        probes.append({
            "from_tile": name, "to_key": key, "hits": nhits,
            "from": list(centre(tid, lvl)), "to": list(centre(ttid, tlvl)),
            "label": f"{name} -> L{tlvl} t{ttid} ({nhits} stale refs)",
        })
json.dump({"probes": probes, "referencing": [(n, h, t) for n, h, t in referencing[:200]],
           "renumbered": renumbered, "minimal_extra": minimal_extra,
           "numbers": {"X": whole_ro, "Y": ro_part,
                       "Zmin": ro_part + size(minimal_extra, REF),
                       "Zall": ro_part + size(outside_ro_all, REF)}},
          open(ROOT / "closure.json", "w"), indent=1)
print(f"\n{len(probes)} targeted probes written to /data/closure.json")
