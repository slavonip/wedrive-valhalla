"""Experiment 3: the closure of a clean local topology edit, measured two ways.

Byte level  — which tiles moved, in which section, inside which level-0 cell.
OBJECT level — which OSM ways changed the GraphIds they own, read out of Valhalla's own index.

The second is the one that answers the architectural question, because a tile whose bytes moved
might merely have been re-serialised, while an OSM way whose GraphId moved is an object that
every other tile referring to it now points at wrongly.
"""
import os
import pathlib

SIZES = {0: 4.0, 1: 1.0, 2: 0.25}
ROOT = pathlib.Path(os.environ["HOME"]) / "det"
MASK = [(32, 40), (88, 96)]
ANCHORS = {"M3": (47.64054, 28.64065), "M4": (47.74999, 28.60431)}


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


def tile_of(lat, lon, level):
    s = SIZES[level]
    return int((lat + 90) / s) * int(360 / s) + int((lon + 180) / s)


def ways(label):
    out = {}
    with open(ROOT / label / "tiles" / "way_edges.txt") as fh:
        for line in fh:
            bits = line.strip().split(",")
            out[bits[0]] = tuple(bits[1:])
    return out


base_dir = ROOT / "A" / "tiles"
names = sorted(str(p.relative_to(base_dir)).replace("\\", "/")
               for p in base_dir.rglob("*.gph"))
A_ways = ways("A")

for label in ("M3", "M4"):
    lat, lon = ANCHORS[label]
    print("=" * 78)
    print(f"{label}   anchor {lat},{lon}   "
          f"L2 {tile_of(lat,lon,2)}  L1 {tile_of(lat,lon,1)}  L0 {tile_of(lat,lon,0)}")
    print("=" * 78)

    # ── tiles ───────────────────────────────────────────────────────────────────────────────
    changed = []
    for n in names:
        pb = ROOT / label / "tiles" / n
        if not pb.exists():
            continue
        a, b = masked(base_dir / n), masked(pb)
        if a != b:
            nb = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
            changed.append((n, nb, len(a), len(b)))

    by_lvl = {0: [], 1: [], 2: []}
    for n, nb, la, lb in changed:
        by_lvl[parse(n)[0]].append((n, nb, la, lb))
    print(f"  tiles changed {len(changed)} of {len(names)}   "
          + "   ".join(f"L{l}: {len(by_lvl[l])}/"
                       f"{sum(1 for n in names if n.startswith(str(l)+'/'))}" for l in (0, 1, 2)))

    l0 = [parse(n)[1] for n, *_ in changed if n.startswith("0/")]
    cells = [bbox(t, 0) for t in l0]
    outside = []
    for n, *_ in changed:
        lvl, tid = parse(n)
        if lvl == 0:
            continue
        w, s, e, nn = bbox(tid, lvl)
        clat, clon = (s + nn) / 2, (w + e) / 2
        if not any(cw <= clon < ce and cs <= clat < cn for cw, cs, ce, cn in cells):
            outside.append(n)
    print(f"  level-0 cells touched: {l0 or 'none'}")
    print(f"  changed tiles OUTSIDE those cells: {len(outside)} {outside[:5]}")
    print()
    for lvl in (0, 1, 2):
        for n, nb, la, lb in sorted(by_lvl[lvl], key=lambda r: -r[1])[:8]:
            tid = parse(n)[1]
            s = SIZES[lvl]
            d = max(abs(divmod(tid, int(360 / s))[0] - int((lat + 90) / s)),
                    abs(divmod(tid, int(360 / s))[1] - int((lon + 180) / s)))
            print(f"     {n:<22} L{lvl} ring {d}  {nb:>9} of {la:>9} bytes "
                  f"({100.0*nb/max(la,1):5.2f} %)  {'+%d' % (lb-la) if lb != la else 'same size'}")
        if len(by_lvl[lvl]) > 8:
            print(f"     ... and {len(by_lvl[lvl])-8} more at level {lvl}")

    # ── objects ─────────────────────────────────────────────────────────────────────────────
    B_ways = ways(label)
    shared = set(A_ways) & set(B_ways)
    moved = [w for w in shared if A_ways[w] != B_ways[w]]
    added = sorted(set(B_ways) - set(A_ways))
    print()
    print(f"  OSM WAYS: {len(shared)} in both.  GraphIds MOVED for {len(moved)} "
          f"({100.0*len(moved)/len(shared):.3f} %).  new ways: {len(added)}")
    for w in added:
        print(f"     added way {w} -> {B_ways[w]}")
    for w in moved[:6]:
        a, b = A_ways[w], B_ways[w]
        print(f"     way {w}")
        print(f"        A {a[:6]}")
        print(f"        B {b[:6]}")
    if len(moved) > 6:
        print(f"     ... and {len(moved)-6} more ways whose GraphIds moved")
    print()
