"""The blast radius of one OSM edit, with the header stamp masked out.

Two confounds had to be removed before any of this could be read:

  1. `osmium apply-changes` drops the osmosis replication timestamp, so the mutated builds get a
     different `dataset_id`. That is bytes 32..40, plus a build-level value at 88..96 derived
     from it -- identical in A and B, different in M1 and M2, and present in EVERY tile. Left in,
     it reports 100% of tiles changed, which is this repository's oldest measurement trap.
  2. The first sampling picked the wrong level-1 tile: 1/049/888 sits over latitude 48-49 while
     the edit is at 47.57. The tile above the edit is 1/049/528.

MASK covers both header fields. Everything outside it is the graph.
"""
import os
import pathlib

SIZES = {0: 4.0, 1: 1.0, 2: 0.25}
EDIT_LAT, EDIT_LON = 47.57479, 28.56396
ROOT = pathlib.Path(os.environ["HOME"]) / "det"
MASK = [(32, 40), (88, 96)]


def masked(p: pathlib.Path) -> bytes:
    d = bytearray(p.read_bytes())
    for s, e in MASK:
        d[s:e] = b"\0" * (e - s)
    return bytes(d)


def parse(path):
    parts = path.split("/")
    return int(parts[0]), int("".join(parts[1:]).removesuffix(".gph"))


def ring(tid, level):
    ncols = int(360 / SIZES[level])
    row, col = divmod(tid, ncols)
    s = SIZES[level]
    return max(abs(row - int((EDIT_LAT + 90) / s)), abs(col - int((EDIT_LON + 180) / s)))


def tiles(label):
    base = ROOT / label / "tiles"
    return {str(p.relative_to(base)).replace("\\", "/"): p for p in sorted(base.rglob("*.gph"))}


A = tiles("A")
print("the edit is inside:")
for lvl in (2, 1, 0):
    s = SIZES[lvl]
    tid = int((EDIT_LAT + 90) / s) * int(360 / s) + int((EDIT_LON + 180) / s)
    w = ((len(str(int(360 / s) * int(180 / s) - 1)) + 2) // 3) * 3
    d = f"{tid:0{w}d}"
    print(f"   level {lvl}: {lvl}/" + "/".join(d[i:i + 3] for i in range(0, w, 3)) + ".gph")

for label in ("M1", "M2"):
    B = tiles(label)
    print()
    print("=" * 76)
    print(f"{label}: " + ("one TAG changed on one primary way" if label == "M1"
                          else "one NEW way + two NEW nodes"))
    print("=" * 76)
    changed = []
    for name, pa in A.items():
        pb = B.get(name)
        if pb is None:
            continue
        a, b = masked(pa), masked(pb)
        if a != b:
            nbytes = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
            changed.append((name, nbytes, len(a), len(b)))

    print(f"  tiles compared {len(A)}   CHANGED {len(changed)}   unchanged {len(A)-len(changed)}")
    for lvl in (0, 1, 2):
        tot = sum(1 for n in A if n.startswith(f"{lvl}/"))
        ch = sum(1 for n, *_ in changed if n.startswith(f"{lvl}/"))
        print(f"     level {lvl}: {ch:>3} of {tot:>3}")
    print()
    for name, nbytes, la, lb in sorted(changed, key=lambda r: (parse(r[0])[0], -r[1])):
        lvl, tid = parse(name)
        pct = 100.0 * nbytes / max(la, 1)
        grew = f"{lb-la:+d}" if lb != la else "same size"
        print(f"     {name:<22} L{lvl} ring {ring(tid,lvl)}  "
              f"{nbytes:>9} bytes differ of {la:>9} ({pct:5.1f} %)  {grew}")
