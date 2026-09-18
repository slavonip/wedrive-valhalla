"""Experiment 5, part 2: the EXACT dependency closure.

"The target tile renumbered" is too coarse. A tile can gain a node at index 900 and leave indices
0..899 meaning exactly what they meant before, so a neighbour referring to index 12 is still
correct. The precise question is per-INDEX:

    a reference (tile T, id i) held in a T0 tile is STALE if and only if
    index i in T denotes a DIFFERENT OBJECT in REF than it did in T0

Node identity is its position: `NodeInfo`'s first word holds lat_offset_/lon_offset_ as offsets
from the tile's corner, so two NodeInfo records with the same first word are the same node. Edge
identity is taken as its endnode plus its edgeinfo offset — the first two words of DirectedEdge.

Three kinds of reference are enumerated, each read at its own offset rather than recognised by
resemblance:

    DirectedEdge.endnode_    low 46 bits of each edge's first word   -> a node
    NodeTransition           the whole 8-byte record                 -> a node on another level
    edge bins                a GraphId array before the restrictions -> an edge
"""
import json
import pathlib
import struct

import numpy as np

ROOT = pathlib.Path("/data")
L = json.load(open(ROOT / "layout.json"))
HEADER, NI, TR, DE = L["HEADER"], L["NODEINFO"], L["TRANSITION"], L["DIRECTEDEDGE"]
GB = 1 << 30
COUNTRIES = ["RO", "HU", "RS", "BG", "MD", "UA"]
MASK = [(32, 40), (88, 96)]


def hdr(d):
    c = struct.unpack_from("<Q", d, 40)[0]
    return (c & 0x1FFFFF, (c >> 21) & 0x1FFFFF,
            struct.unpack_from("<I", d, 48)[0] & 0x3FFFFF,
            struct.unpack_from("<I", d, 96)[0],
            struct.unpack_from("<25I", d, 116)[24])


def key_of(name):
    parts = name.split("/")
    return int(parts[0]) | (int("".join(parts[1:]).removesuffix(".gph")) << 3)


def tiles_of(label):
    base = ROOT / label / "tiles"
    return {str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}


def cut_of(label, c):
    base = ROOT / label / "cuts" / c
    return ({str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}
            if base.is_dir() else {})


def word0(d, off, count, stride):
    """The first 8 bytes of each fixed record, as uint64."""
    if count == 0:
        return np.empty(0, dtype=np.uint64)
    raw = np.frombuffer(d, dtype=np.uint8, count=count * stride, offset=off)
    return raw.reshape(count, stride)[:, :8].copy().view(np.uint64).ravel()


def word1(d, off, count, stride):
    if count == 0:
        return np.empty(0, dtype=np.uint64)
    raw = np.frombuffer(d, dtype=np.uint8, count=count * stride, offset=off)
    return raw.reshape(count, stride)[:, 8:16].copy().view(np.uint64).ravel()


T0, REF = tiles_of("T0"), tiles_of("REF")

# ── which INDEX in which tile changed meaning? ──────────────────────────────────────────────
moved_nodes, moved_edges = {}, {}
changed = []
for name, pa in T0.items():
    pb = REF.get(name)
    if pb is None:
        continue
    a, b = bytearray(pa.read_bytes()), bytearray(pb.read_bytes())
    for s, e in MASK:
        a[s:e] = b[s:e] = b"\0" * (e - s)
    if bytes(a) == bytes(b):
        continue
    changed.append(name)
    a, b = bytes(a), bytes(b)
    na, ea, ta, _, _ = hdr(a)
    nb, eb, tb, _, _ = hdr(b)
    k = key_of(name)

    # node identity = the first NodeInfo word (lat/lon offsets + access)
    va, vb = word0(a, HEADER, na, NI), word0(b, HEADER, nb, NI)
    m = min(len(va), len(vb))
    idx = set(np.nonzero(va[:m] != vb[:m])[0].tolist())
    idx.update(range(m, max(na, nb)))
    if idx:
        moved_nodes[k] = idx

    # edge identity = endnode + edgeinfo offset, i.e. the first two DirectedEdge words
    off_a = HEADER + na * NI + ta * TR
    off_b = HEADER + nb * NI + tb * TR
    ea0, eb0 = word0(a, off_a, ea, DE), word0(b, off_b, eb, DE)
    ea1, eb1 = word1(a, off_a, ea, DE), word1(b, off_b, eb, DE)
    m = min(len(ea0), len(eb0))
    idx = set(np.nonzero((ea0[:m] != eb0[:m]) | (ea1[:m] != eb1[:m]))[0].tolist())
    idx.update(range(m, max(ea, eb)))
    if idx:
        moved_edges[k] = idx

print(f"tiles differing            {len(changed)}")
print(f"tiles with a node index whose meaning changed  {len(moved_nodes)}")
print(f"tiles with an edge index whose meaning changed {len(moved_edges)}")
print(f"node indices that changed meaning, total  "
      f"{sum(len(v) for v in moved_nodes.values())}")
print(f"edge indices that changed meaning, total  "
      f"{sum(len(v) for v in moved_edges.values())}")

installed = {}
for c in COUNTRIES:
    installed.update(cut_of("T0", c))
ro_ref = cut_of("REF", "RO")

# ── which T0 tiles hold a reference that has gone stale? ────────────────────────────────────
stale = {}
for name, p in installed.items():
    if name in ro_ref:
        continue                       # Romania's own tiles come from REF anyway
    d = p.read_bytes()
    n, e, t, cf, binlast = hdr(d)
    hits = []

    def check(values, table, kind):
        if not len(values):
            return
        v = values & np.uint64(0x3FFFFFFFFFFF)
        keys = (v & np.uint64(0x1FFFFFF)).astype(np.uint64)
        ids = (v >> np.uint64(25)).astype(np.uint64)
        for k in np.unique(keys):
            tgt = table.get(int(k))
            if not tgt:
                continue
            sel = ids[keys == k]
            bad = [int(i) for i in sel if int(i) in tgt]
            if bad:
                hits.append((kind, int(k), len(bad)))

    check(word0(d, HEADER + n * NI + t * TR, e, DE), moved_nodes, "endnode")
    if t:
        check(np.frombuffer(d, dtype="<u8", count=t, offset=HEADER + n * NI),
              moved_nodes, "transition")
    bins_start = cf - binlast * 8
    if binlast:
        check(np.frombuffer(d, dtype="<u8", count=binlast, offset=bins_start),
              moved_edges, "bin")
    if hits:
        stale[name] = hits

print(f"\nT0 tiles outside Romania holding a STALE reference: {len(stale)}")
kinds = {}
for hs in stale.values():
    for kind, _, nbad in hs:
        kinds[kind] = kinds.get(kind, 0) + nbad
print(f"   stale references by kind: {kinds}")

ro_from_ref = sorted(set(n for n in changed if n in ro_ref)
                     | set(n for n in ro_ref if n not in installed))
exact_extra = sorted(stale)
all_extra = sorted(n for n in changed if n in installed and n not in ro_ref)


def size(names, src):
    return sum(src[n].stat().st_size for n in names if n in src)


X = sum(p.stat().st_size for p in ro_ref.values())
Y = size(ro_from_ref, REF)
Zmin = Y + size(exact_extra, REF)
Zall = Y + size(all_extra, REF)
print("\n=== THE NUMBERS ===")
print(f"  X    full Romania package        {X/GB:8.3f} GB  {len(ro_ref):>5} tiles")
print(f"  Y    Romania tiles differing     {Y/GB:8.3f} GB  {len(ro_from_ref):>5} tiles"
      f"   {100*Y/X:5.1f} % of X")
print(f"  Zmin Y + EXACT closure           {Zmin/GB:8.3f} GB  +{len(exact_extra):>4} tiles"
      f"   {100*Zmin/X:5.1f} % of X")
print(f"  Zall Y + every differing tile    {Zall/GB:8.3f} GB  +{len(all_extra):>4} tiles"
      f"   {100*Zall/X:5.1f} % of X")
print(f"  the exact closure is {100*len(exact_extra)/max(len(all_extra),1):.1f} % "
      f"of the observed difference")

json.dump({"exact_extra": exact_extra, "all_extra": all_extra, "ro_from_ref": ro_from_ref,
           "stale_sample": {k: v[:3] for k, v in list(stale.items())[:40]},
           "numbers": {"X": X, "Y": Y, "Zmin": Zmin, "Zall": Zall}},
          open(ROOT / "exact.json", "w"), indent=1)
print("\nwritten to /data/exact.json")
