"""Is the blast radius geographic, or is it the LEVEL-0 CELL?

The ring-6 level-2 tile that changed is ~120 km from the edit. No level-2 edge reaches that far,
so a horizontal explanation is already in trouble. The alternative: a level-2 tile carries
NodeTransitions into the level-0 tile above it, the level-0 tile's node ids moved, and every
level-2 tile inside that 4-degree cell therefore had to be rewritten.

If that is the mechanism, then the set of changed tiles should be *exactly* the tiles lying
inside the changed level-0 cells — not a ring around the edit.
"""
import os
import pathlib

SIZES = {0: 4.0, 1: 1.0, 2: 0.25}
ROOT = pathlib.Path(os.environ["HOME"]) / "det"
MASK = [(32, 40), (88, 96)]


def masked(p):
    d = bytearray(p.read_bytes())
    for s, e in MASK:
        d[s:e] = b"\0" * (e - s)
    return bytes(d)


def parse(name):
    parts = name.split("/")
    return int(parts[0]), int("".join(parts[1:]).removesuffix(".gph"))


def bbox(tid, level):
    s = SIZES[level]
    row, col = divmod(tid, int(360 / s))
    return col * s - 180, row * s - 90, col * s - 180 + s, row * s - 90 + s


base = ROOT / "A" / "tiles"
names = sorted(str(p.relative_to(base)).replace("\\", "/") for p in base.rglob("*.gph"))

changed = set()
for n in names:
    pb = ROOT / "M2" / "tiles" / n
    if pb.exists() and masked(base / n) != masked(pb):
        changed.add(n)

l0_changed = [parse(n)[1] for n in changed if n.startswith("0/")]
cells = [bbox(t, 0) for t in l0_changed]
print(f"level-0 tiles changed: {l0_changed}")
for t, c in zip(l0_changed, cells):
    print(f"   {t}: lon {c[0]}..{c[2]}  lat {c[1]}..{c[3]}")
print()


def inside_any(name):
    lvl, tid = parse(name)
    w, s, e, n = bbox(tid, lvl)
    clat, clon = (s + n) / 2, (w + e) / 2
    return any(cw <= clon < ce and cs <= clat < cn for cw, cs, ce, cn in cells)


rows = []
for n in names:
    if n.startswith("0/"):
        continue
    rows.append((n, n in changed, inside_any(n)))

both = sum(1 for _, c, i in rows if c and i)
changed_outside = [n for n, c, i in rows if c and not i]
unchanged_inside = [n for n, c, i in rows if not c and i]

print(f"non-level-0 tiles: {len(rows)}")
print(f"   changed AND inside a changed L0 cell   {both}")
print(f"   changed but OUTSIDE                    {len(changed_outside)}  {changed_outside[:6]}")
print(f"   inside but UNCHANGED                   {len(unchanged_inside)}")
if unchanged_inside:
    for n in unchanged_inside[:10]:
        lvl, tid = parse(n)
        w, s, e, nn = bbox(tid, lvl)
        sz = (base / n).stat().st_size
        print(f"        {n:<22} L{lvl}  lon {w:.2f}..{e:.2f} lat {s:.2f}..{nn:.2f}  {sz:>9} B")
    if len(unchanged_inside) > 10:
        print(f"        ... and {len(unchanged_inside)-10} more")
