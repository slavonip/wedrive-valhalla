"""WHERE inside each tile did the bytes move? Section-level classification.

Offsets come from `valhalla/baldr/graphtileheader.h` at 3.6.3, and are anchored empirically: the
value at byte 216 equals the file size on an unchanged tile, which pins the tail of the offsets
block and therefore the rest of it.

    32   dataset_id_        (changes with any edit to the PBF -- masked)
    40   nodecount:21 | directededgecount:21 | predictedspeeds_count:21
    88   checksum_          ("hashed md5 of the OSM PBFs" -- masked)
    96   complex_restriction_forward_offset_
   100   complex_restriction_reverse_offset_
   104   edgeinfo_offset_
   108   textlist_offset_
   112   date_created_
   116   bins, 25 x uint32
   216   lane_connectivity_offset_
   220   predictedspeeds_offset_
   224   tile_size_

What each section means for the question we are asking:

  FIXED RECORDS   NodeInfo, DirectedEdge, NodeTransition, signs, restrictions, admins. GraphIds
                  and endnode references live here, so ID CHURN shows up in this section.
  EDGEINFO        per-edge shape and name indices.
  TEXTLIST        the strings themselves. A pure rename should land here and nowhere else.
"""
import os
import pathlib
import struct

ROOT = pathlib.Path(os.environ["HOME"]) / "det"
MASK = [(32, 40), (88, 96)]


def header(d: bytes):
    counts = struct.unpack_from("<Q", d, 40)[0]
    return {
        "nodecount": counts & 0x1FFFFF,
        "directededgecount": (counts >> 21) & 0x1FFFFF,
        "complex_fwd": struct.unpack_from("<I", d, 96)[0],
        "complex_rev": struct.unpack_from("<I", d, 100)[0],
        "edgeinfo": struct.unpack_from("<I", d, 104)[0],
        "textlist": struct.unpack_from("<I", d, 108)[0],
        "tile_size": struct.unpack_from("<I", d, 224)[0],
    }


def sections(h, total):
    return [
        ("header+fixed records", 0, h["complex_fwd"]),
        ("complex restrictions", h["complex_fwd"], h["edgeinfo"]),
        ("edgeinfo", h["edgeinfo"], h["textlist"]),
        ("textlist", h["textlist"], total),
    ]


def classify(pa, pb):
    a, b = bytearray(pa.read_bytes()), bytearray(pb.read_bytes())
    ha, hb = header(bytes(a)), header(bytes(b))
    for s, e in MASK:
        a[s:e] = b[s:e] = b"\0" * (e - s)
    out = []
    for name, s, e in sections(ha, len(a)):
        n = sum(1 for i in range(s, min(e, len(a), len(b))) if a[i] != b[i])
        if e > len(b):
            n += e - len(b)
        out.append((name, n, e - s))
    return ha, hb, out


CASES = {
    "M1": [("2/000/792/834.gph", "the L2 tile under the edit"),
           ("1/049/528.gph", "the L1 tile above it"),
           ("0/003/112.gph", "the L0 tile holding the primary road")],
    "M2": [("2/000/792/834.gph", "the edited tile"),
           ("0/003/112.gph", "the L0 tile above it"),
           ("1/049/528.gph", "the L1 tile above it"),
           ("2/000/791/394.gph", "a level-2 neighbour, ring 1"),
           ("2/000/787/074.gph", "a level-2 tile four rings away"),
           ("2/000/785/640.gph", "a level-2 tile six rings away")],
}

for label, cases in CASES.items():
    print("=" * 78)
    print(label)
    print("=" * 78)
    for name, what in cases:
        pa, pb = ROOT / "A" / "tiles" / name, ROOT / label / "tiles" / name
        if not pb.exists():
            print(f"  {name}: absent")
            continue
        ha, hb, secs = classify(pa, pb)
        total = sum(n for _, n, _ in secs)
        dn = hb["nodecount"] - ha["nodecount"]
        de = hb["directededgecount"] - ha["directededgecount"]
        print(f"  {name}  — {what}")
        print(f"     nodes {ha['nodecount']:>7} -> {hb['nodecount']:<7} ({dn:+d})    "
              f"directed edges {ha['directededgecount']:>7} -> {hb['directededgecount']:<7} ({de:+d})")
        if total == 0:
            print("     UNCHANGED outside the header stamp")
        else:
            for sname, n, size in secs:
                if n:
                    print(f"     {sname:<22} {n:>9} of {size:>9} bytes differ "
                          f"({100.0*n/max(size,1):5.1f} %)")
        print()
