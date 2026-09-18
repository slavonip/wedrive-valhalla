"""Decode the bytes that actually moved, and test the NodeTransition hypothesis.

The hypothesis from experiment 2: a level-2 tile carries NodeTransitions into the level-0 tile
above it, so when level-0 node ids shift, every level-2 tile in that 4-degree cell holding such a
transition must be rewritten. It explains a tile changing six rings away, and it has never been
demonstrated.

No full struct layout is needed to test it. A GraphId is a 64-bit value laid out as

    level : 3   |   tileid : 22   |   id : 21   |   spare : 18

so `value & 0x1FFFFFF` identifies (level, tile) on its own. Read the changed regions as aligned
64-bit words and ask what they point AT. If the words that moved in a distant level-2 tile
resolve to level-0 tile 3112, the hypothesis holds; if they resolve to the neighbouring level-2
tile, the propagation is horizontal instead.
"""
import os
import pathlib
import struct

ROOT = pathlib.Path(os.environ["HOME"]) / "det"
MASK = [(32, 40), (88, 96)]


def graphid(v):
    return v & 7, (v >> 3) & 0x3FFFFF, (v >> 25) & 0x1FFFFF


def name_of(level, tid):
    return f"L{level} tile {tid}"


# ── sanity: does the decoder agree with valhalla_ways_to_edges? ──────────────────────────────
print("decoder check — the primary way 44278477 should live in L0 tile 3112")
with open(ROOT / "A" / "tiles" / "way_edges.txt") as fh:
    for line in fh:
        if line.startswith("44278477,"):
            vals = line.strip().split(",")[1:]
            for v in vals[1:8:2]:
                lvl, tid, i = graphid(int(v))
                print(f"   {v:>14} -> level {lvl}  tile {tid:>7}  id {i}")
            break
print()


def changed_words(pa, pb):
    """Aligned 64-bit words that differ, with their before/after values."""
    a, b = bytearray(pa.read_bytes()), bytearray(pb.read_bytes())
    for s, e in MASK:
        a[s:e] = b[s:e] = b"\0" * (e - s)
    n = min(len(a), len(b))
    out = []
    for off in range(0, n - 8, 8):
        wa = struct.unpack_from("<Q", a, off)[0]
        wb = struct.unpack_from("<Q", b, off)[0]
        if wa != wb:
            out.append((off, wa, wb))
    return out


CASES = [
    ("M2", "2/000/785/640.gph", "six rings away — the tile that motivated the hypothesis"),
    ("M2", "2/000/787/074.gph", "four rings away"),
    ("M2", "1/049/528.gph", "the L1 tile above the edit"),
    ("M3", "2/000/792/833.gph", "M3: a ring-1 neighbour of a CLEAN local edit"),
    ("M3", "0/003/112.gph", "M3: the L0 tile"),
    ("M4", "2/000/794/273.gph", "M4: a ring-1 neighbour of a boundary edit"),
]

for label, tile, what in CASES:
    pa, pb = ROOT / "A" / "tiles" / tile, ROOT / label / "tiles" / tile
    if not pb.exists():
        continue
    words = changed_words(pa, pb)
    print("=" * 76)
    print(f"{label}  {tile}  — {what}")
    print(f"   {len(words)} aligned 64-bit words changed")
    targets = {}
    for off, wa, wb in words:
        la, ta, ia = graphid(wa)
        lb, tb, ib = graphid(wb)
        # a plausible GraphId reference: the (level, tile) half is unchanged and the id moved
        if (la, ta) == (lb, tb) and ia != ib and ta != 0:
            targets[(la, ta)] = targets.get((la, ta), 0) + 1
    for (lvl, tid), n in sorted(targets.items(), key=lambda kv: -kv[1]):
        print(f"      {n:>4} words look like references into {name_of(lvl, tid)} "
              f"with the id shifted")
    if not targets:
        print("      no word looks like a (level,tile)-stable GraphId with a moved id")
    for off, wa, wb in words[:4]:
        la, ta, ia = graphid(wa)
        lb, tb, ib = graphid(wb)
        print(f"      @{off:<9} A={wa:<20} -> L{la} t{ta} id{ia}")
        print(f"       {'':<10} B={wb:<20} -> L{lb} t{tb} id{ib}")
    print()
