"""Experiment 5, part 1: read the reference fields where they SIT.

Experiment 4's scan looked for 64-bit words that RESEMBLED a GraphId and failed its own negative
control — 1 690 chance matches against 1 423 claimed hits. The fix is not a better heuristic but
a structural read, so a reference is identified by its offset in the tile.

From `GraphTile::Initialize` at 3.6.3, the layout is:

    0                                    GraphTileHeader, 272 bytes (static_assert)
    272                                  NodeInfo       x nodecount
    272 + N*32                           NodeTransition x transitioncount
    272 + N*32 + T*8                     DirectedEdge   x directededgecount
    ...                                  access restrictions, transit, signs, turn lanes, admins
    complex_restriction_forward_offset   preceded by the edge bins (GraphId array)

`sizeof(NodeInfo)` is 32: four 64-bit words, and the bitfields sum to exactly 64 in each.
`sizeof(NodeTransition)` is 8, and the whole value is a GraphId in its low 46 bits.
`sizeof(DirectedEdge)` is NOT asserted anywhere and its bitfields are easy to miscount, so it is
determined here by EXPERIMENT and checked: only the true size makes every node's edge range hold
endnodes that decode to tiles that exist, with ids inside those tiles' node counts.

The three kinds of cross-tile reference that exist in a road tile:

    DirectedEdge.endnode_    low 46 bits of the edge's FIRST word — points at a node
    NodeTransition.endnode_  the whole 8-byte record — points at a node on another level
    edge bins                an array of GraphIds naming edges, for spatial lookup
"""
import json
import os
import pathlib
import struct
import sys

ROOT = pathlib.Path("/data")
HEADER = 272
NODEINFO = 32
TRANSITION = 8
SIZES = {0: 4.0, 1: 1.0, 2: 0.25}


def hdr(d):
    counts = struct.unpack_from("<Q", d, 40)[0]
    w48 = struct.unpack_from("<I", d, 48)[0]
    bins = struct.unpack_from("<25I", d, 116)
    return {
        "nodecount": counts & 0x1FFFFF,
        "directededgecount": (counts >> 21) & 0x1FFFFF,
        "transitioncount": w48 & 0x3FFFFF,
        "complex_fwd": struct.unpack_from("<I", d, 96)[0],
        "edgeinfo": struct.unpack_from("<I", d, 104)[0],
        "textlist": struct.unpack_from("<I", d, 108)[0],
        "tile_size": struct.unpack_from("<I", d, 224)[0],
        "bin_last": bins[24],
    }


def gid(v):
    return v & 7, (v >> 3) & 0x3FFFFF, (v >> 25) & 0x1FFFFF


def tiles_of(label):
    base = ROOT / label / "tiles"
    return {str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}


def key_of(name):
    parts = name.split("/")
    lvl = int(parts[0])
    tid = int("".join(parts[1:]).removesuffix(".gph"))
    return lvl | (tid << 3)


# ── how big is a DirectedEdge? Try every plausible size and let the data decide. ─────────────
T0 = tiles_of("T0")
nodecounts = {}
for name, p in T0.items():
    nodecounts[key_of(name)] = hdr(p.read_bytes())["nodecount"]

sample = [p for n, p in sorted(T0.items()) if p.stat().st_size > 200_000][:25]
print("determining sizeof(DirectedEdge) by what the data validates\n")
print(f"{'size':>5}  {'tiles ok':>9}  {'endnodes checked':>17}  {'valid':>8}  {'ratio':>7}")
best = None
for size in range(32, 129, 8):
    ok_tiles = checked = valid = 0
    for p in sample:
        d = p.read_bytes()
        h = hdr(d)
        base = HEADER + h["nodecount"] * NODEINFO + h["transitioncount"] * TRANSITION
        end = base + h["directededgecount"] * size
        if end > h["complex_fwd"] or end > len(d):
            continue
        good = tot = 0
        for i in range(0, min(h["directededgecount"], 400)):
            v = struct.unpack_from("<Q", d, base + i * size)[0] & 0x3FFFFFFFFFFF
            lvl, tid, nid = gid(v)
            tot += 1
            k = lvl | (tid << 3)
            if lvl <= 2 and k in nodecounts and nid < nodecounts[k]:
                good += 1
        checked += tot
        valid += good
        if tot and good == tot:
            ok_tiles += 1
    ratio = valid / checked if checked else 0
    print(f"{size:>5}  {ok_tiles:>9}  {checked:>17}  {valid:>8}  {ratio:>7.3f}")
    if ratio > (best[1] if best else 0):
        best = (size, ratio, ok_tiles)

print(f"\nchosen sizeof(DirectedEdge) = {best[0]}  "
      f"({best[2]} of {len(sample)} sample tiles fully valid, ratio {best[1]:.4f})")
if best[1] < 0.999 or best[2] < len(sample):
    print("REFUSING: the size does not validate cleanly on every sampled tile.")
    sys.exit(1)

DIRECTEDEDGE = best[0]

# ── a second, independent check: the layout equation ────────────────────────────────────────
print("\nindependent check — do the sections fit inside the tile?")
bad = 0
for name, p in list(T0.items())[:400]:
    d = p.read_bytes()
    h = hdr(d)
    end_of_edges = (HEADER + h["nodecount"] * NODEINFO + h["transitioncount"] * TRANSITION
                    + h["directededgecount"] * DIRECTEDEDGE)
    bins_start = h["complex_fwd"] - h["bin_last"] * 8
    if not (end_of_edges <= bins_start <= h["complex_fwd"] <= h["edgeinfo"] <= h["textlist"]
            <= h["tile_size"] == len(d)):
        bad += 1
print(f"   {400 - bad} of 400 tiles satisfy "
      f"edges <= bins <= restrictions <= edgeinfo <= textlist == file size")
if bad:
    print("REFUSING: the layout does not hold.")
    sys.exit(1)

json.dump({"HEADER": HEADER, "NODEINFO": NODEINFO, "TRANSITION": TRANSITION,
           "DIRECTEDEDGE": DIRECTEDEDGE}, open(ROOT / "layout.json", "w"))
print(f"\nlayout written: header {HEADER}, NodeInfo {NODEINFO}, "
      f"NodeTransition {TRANSITION}, DirectedEdge {DIRECTEDEDGE}")
