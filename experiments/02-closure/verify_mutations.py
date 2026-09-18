"""Did the mutations reach the PBF, and did they reach the GRAPH?

M1 renamed a street and its own tile did not change beyond the header, which is exactly what a
mutation that never applied would look like. Before reading anything into the blast radius, check
that the edit is present in both the input and the output.
"""
import os
import pathlib
import subprocess

DET = pathlib.Path(os.environ["HOME"]) / "det"


def grep_pbf(pbf, needle):
    """Is the string in the file at all? PBF string tables store names verbatim (uncompressed
    blocks may be zlib-deflated, so absence here is not proof)."""
    out = subprocess.run(["osmium", "cat", str(DET / "src" / pbf), "-f", "osm"],
                         capture_output=True)
    return out.stdout.count(needle.encode())


def grep_tiles(label, needle):
    n = 0
    hits = []
    base = DET / label / "tiles"
    for p in sorted(base.rglob("*.gph")):
        c = p.read_bytes().count(needle.encode())
        if c:
            n += c
            hits.append(str(p.relative_to(base)))
    return n, hits


print("=== is the edit in the INPUT? ===")
for pbf, needle in (("moldova.osm.pbf", "WEDRIVE-M1"),
                    ("moldova-m1.osm.pbf", "WEDRIVE-M1"),
                    ("moldova.osm.pbf", "WEDRIVE-M2"),
                    ("moldova-m2.osm.pbf", "WEDRIVE-M2")):
    print(f"   {pbf:<24} '{needle}' x{grep_pbf(pbf, needle)}")

print("\n=== is the edit in the GRAPH? ===")
for label, needle in (("A", "WEDRIVE-M1"), ("M1", "WEDRIVE-M1"),
                      ("A", "WEDRIVE-M2"), ("M2", "WEDRIVE-M2")):
    n, hits = grep_tiles(label, needle)
    print(f"   build {label:<3} '{needle}' x{n}  {hits[:4]}")

print("\n=== and the ORIGINAL name, for contrast ===")
for label in ("A", "M1"):
    n, hits = grep_tiles(label, "Strada Na")
    print(f"   build {label:<3} 'Strada Na' x{n} in {len(hits)} tiles")

print("\n=== header stamp: what is at offsets 32 and 88? ===")
for label in ("A", "B", "M1", "M2"):
    p = DET / label / "tiles" / "2" / "000" / "792" / "834.gph"
    if p.exists():
        d = p.read_bytes()
        print(f"   {label:<3} [32:40]={d[32:40].hex()}   [88:96]={d[88:96].hex()}")

print("\n=== did the mutated PBFs keep their replication timestamp? ===")
for pbf in ("moldova.osm.pbf", "moldova-m1.osm.pbf", "moldova-m2.osm.pbf"):
    r = subprocess.run(["osmium", "fileinfo", str(DET / "src" / pbf)],
                       capture_output=True, text=True)
    stamp = [l.strip() for l in r.stdout.splitlines() if "replication" in l.lower()]
    print(f"   {pbf:<24} {stamp or ['(none)']}")
