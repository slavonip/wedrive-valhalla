"""Experiment 5, part 2b: the exact closure, after the first attempt produced an impossibility.

The first run reported a closure of 915 tiles against an observed difference of 535 — a MINIMAL
set larger than the set it must be a subset of. That is a contradiction, and it exposed a
circular definition: edge identity had been taken as `endnode + edgeinfo_offset`, but `endnode`
is ITSELF a reference. So an edge counted as "a different edge" merely because the node it points
at had shifted, which is the very churn the closure is supposed to distinguish itself from.

Two corrections:

  1. IDENTITY IS COMPARED WITH THE REFERENCE FIELDS MASKED OUT. For a DirectedEdge that means
     hiding `endnode_` (low 46 bits of word 0), `edgeinfo_offset_` (low 25 of word 1) and the
     word holding localedgeidx/opp_local_idx/shortcut/superseded — all of them indices that move
     when the tile is renumbered. What is left is intrinsic: speed, class, use, access, length,
     grade, turn types. For a NodeInfo, identity is word 0, which holds lat/lon offsets from the
     tile corner: a position, not a reference.

  2. THE RESULT IS INTERSECTED WITH THE OBSERVED DIFFERENCE, which is sound by a theorem rather
     than by convenience: a tile holding a stale reference must differ between T0 and REF,
     because REF contains that same tile with the reference corrected. Intersecting can therefore
     only remove false positives, never hide a true one.
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
U64 = np.uint64


def hdr(d):
    c = struct.unpack_from("<Q", d, 40)[0]
    return (c & 0x1FFFFF, (c >> 21) & 0x1FFFFF,
            struct.unpack_from("<I", d, 48)[0] & 0x3FFFFF,
            struct.unpack_from("<I", d, 96)[0],
            struct.unpack_from("<25I", d, 116)[24])


def key_of(name):
    p = name.split("/")
    return int(p[0]) | (int("".join(p[1:]).removesuffix(".gph")) << 3)


def tiles_of(label):
    base = ROOT / label / "tiles"
    return {str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}


def cut_of(label, c):
    base = ROOT / label / "cuts" / c
    return ({str(p.relative_to(base)).replace("\\", "/"): p for p in base.rglob("*.gph")}
            if base.is_dir() else {})


def words(d, off, count, stride, which):
    if count == 0:
        return np.empty(0, dtype=U64)
    raw = np.frombuffer(d, dtype=np.uint8, count=count * stride, offset=off)
    return raw.reshape(count, stride)[:, which * 8:which * 8 + 8].copy().view(U64).ravel()


def edge_signature(d, off, count):
    """Intrinsic attributes only: every index-bearing field masked away."""
    if count == 0:
        return np.empty(0, dtype=U64)
    w0 = words(d, off, count, DE, 0) >> U64(46)          # drop endnode_
    w1 = words(d, off, count, DE, 1) >> U64(25)          # drop edgeinfo_offset_
    w2 = words(d, off, count, DE, 2)                     # speed, use, class, surface...
    w4 = words(d, off, count, DE, 4)                     # turn types, length, grade
    return w0 * U64(1000003) ^ w1 * U64(31) ^ w2 ^ (w4 * U64(7))


T0, REF = tiles_of("T0"), tiles_of("REF")

moved_nodes, moved_edges, changed = {}, {}, set()
for name, pa in T0.items():
    pb = REF.get(name)
    if pb is None:
        continue
    a, b = bytearray(pa.read_bytes()), bytearray(pb.read_bytes())
    for s, e in MASK:
        a[s:e] = b[s:e] = b"\0" * (e - s)
    if bytes(a) == bytes(b):
        continue
    changed.add(name)
    a, b = bytes(a), bytes(b)
    na, ea, ta, _, _ = hdr(a)
    nb, eb, tb, _, _ = hdr(b)
    k = key_of(name)

    va, vb = words(a, HEADER, na, NI, 0), words(b, HEADER, nb, NI, 0)
    m = min(len(va), len(vb))
    idx = set(np.nonzero(va[:m] != vb[:m])[0].tolist()) | set(range(m, max(na, nb)))
    if idx:
        moved_nodes[k] = idx

    sa = edge_signature(a, HEADER + na * NI + ta * TR, ea)
    sb = edge_signature(b, HEADER + nb * NI + tb * TR, eb)
    m = min(len(sa), len(sb))
    idx = set(np.nonzero(sa[:m] != sb[:m])[0].tolist()) | set(range(m, max(ea, eb)))
    if idx:
        moved_edges[k] = idx

print(f"tiles differing                                {len(changed)}")
print(f"node indices whose meaning changed     {sum(len(v) for v in moved_nodes.values()):>9}"
      f"   in {len(moved_nodes)} tiles")
print(f"edge indices whose meaning changed     {sum(len(v) for v in moved_edges.values()):>9}"
      f"   in {len(moved_edges)} tiles")

installed = {}
for c in COUNTRIES:
    installed.update(cut_of("T0", c))
ro_ref = cut_of("REF", "RO")

stale, by_kind = {}, {}
for name, p in installed.items():
    if name in ro_ref:
        continue
    d = p.read_bytes()
    n, e, t, cf, binlast = hdr(d)
    found = []

    def check(vals, table, kind):
        if not len(vals):
            return
        v = vals & U64(0x3FFFFFFFFFFF)
        keys = v & U64(0x1FFFFFF)
        ids = v >> U64(25)
        for k in np.unique(keys):
            tgt = table.get(int(k))
            if not tgt:
                continue
            sel = np.unique(ids[keys == k])
            bad = sum(1 for i in sel if int(i) in tgt)
            if bad:
                found.append(kind)
                by_kind[kind] = by_kind.get(kind, 0) + bad

    check(words(d, HEADER + n * NI + t * TR, e, DE, 0), moved_nodes, "endnode")
    if t:
        check(np.frombuffer(d, dtype="<u8", count=t, offset=HEADER + n * NI),
              moved_nodes, "transition")
    if binlast:
        check(np.frombuffer(d, dtype="<u8", count=binlast, offset=cf - binlast * 8),
              moved_edges, "bin")
    if found:
        stale[name] = sorted(set(found))

raw = set(stale)
outside_changed = {n for n in changed if n in installed and n not in ro_ref}
exact = sorted(raw & outside_changed)
impossible = sorted(raw - outside_changed)

print(f"\nT0 tiles outside Romania holding a stale reference (raw)   {len(raw)}")
print(f"   of those, tiles that also DIFFER (the sound subset)     {len(exact)}")
print(f"   claimed stale but byte-identical -> FALSE POSITIVES     {len(impossible)}")
print(f"   stale references by kind: {by_kind}")
kinds = {}
for v in stale.values():
    kinds[tuple(v)] = kinds.get(tuple(v), 0) + 1
print(f"   tiles by which kind of reference went stale: {kinds}")

ro_from_ref = sorted({n for n in changed if n in ro_ref}
                     | {n for n in ro_ref if n not in installed})
all_extra = sorted(outside_changed)


def size(names, src):
    return sum(src[n].stat().st_size for n in names if n in src)


X = sum(p.stat().st_size for p in ro_ref.values())
Y = size(ro_from_ref, REF)
Zmin = Y + size(exact, REF)
Zall = Y + size(all_extra, REF)
inst = sum(p.stat().st_size for p in installed.values())
print("\n=== THE NUMBERS ===")
print(f"  X    full Romania package      {X/GB:8.3f} GB  {len(ro_ref):>5} tiles")
print(f"  Y    Romania tiles differing   {Y/GB:8.3f} GB  {len(ro_from_ref):>5} tiles  "
      f"{100*Y/X:5.1f} % of X")
print(f"  Zmin Y + EXACT closure         {Zmin/GB:8.3f} GB  +{len(exact):>4} tiles  "
      f"{100*Zmin/X:5.1f} % of X")
print(f"  Zall Y + all differing         {Zall/GB:8.3f} GB  +{len(all_extra):>4} tiles  "
      f"{100*Zall/X:5.1f} % of X")
print(f"  exact closure / observed diff  {100*len(exact)/max(len(all_extra),1):5.1f} %")
print(f"  Zmin / whole installed set     {100*Zmin/inst:5.1f} %   (installed {inst/GB:.3f} GB)")

json.dump({"exact": exact, "all_extra": all_extra, "ro_from_ref": ro_from_ref,
           "numbers": {"X": X, "Y": Y, "Zmin": Zmin, "Zall": Zall, "installed": inst}},
          open(ROOT / "exact.json", "w"), indent=1)
print("\nwritten to /data/exact.json")
