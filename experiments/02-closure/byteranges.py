"""WHICH bytes actually differ — before trusting any count of changed tiles.

Every tile reported as changed, every one the same size, every one first differing at byte 32.
That is the signature of a header stamp, not of a graph that moved, and this repository has met
it before: "four bytes of build stamp at offset 32 that made the first run report 100%".

So: enumerate the differing RANGES for tiles at increasing distance from the edit. If a distant
tile differs only inside the header, it did not really change.
"""
import hashlib
import os
import pathlib

ROOT = pathlib.Path(os.environ["HOME"]) / "det"


def ranges(a: bytes, b: bytes, gap=8):
    """Contiguous differing regions, merging runs closer together than `gap`."""
    out = []
    start = None
    last = None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            if start is None:
                start = i
            elif i - last > gap:
                out.append((start, last))
                start = i
            last = i
    if start is not None:
        out.append((start, last))
    return out


def show(label, name):
    a = (ROOT / "A" / "tiles" / name).read_bytes()
    b = (ROOT / label / "tiles" / name).read_bytes()
    rs = ranges(a, b)
    total = sum(e - s + 1 for s, e in rs)
    print(f"   {name:<22} {len(rs):>4} differing regions, {total:>9} bytes of {len(a)}")
    for s, e in rs[:6]:
        print(f"        bytes {s:>9}..{e:<9} ({e-s+1}) "
              f"A={a[s:min(e+1,s+12)].hex()} B={b[s:min(e+1,s+12)].hex()}")
    if len(rs) > 6:
        print(f"        ... and {len(rs)-6} more regions")


SAMPLES = [
    ("the edited tile",   "2/000/792/834.gph"),
    ("ring 1",            "2/000/791/394.gph"),
    ("ring 4",            "2/000/787/074.gph"),
    ("far away (Chisinau)", "2/000/789/955.gph"),
    ("level 1 above it",  "1/049/888.gph"),
    ("level 0",           "0/003/112.gph"),
]

for label in ("M1", "M2"):
    print("=" * 78)
    print(label)
    print("=" * 78)
    for what, name in SAMPLES:
        p = ROOT / label / "tiles" / name
        if not p.exists():
            print(f"   {name}: absent in {label}")
            continue
        print(f"  {what}:")
        show(label, name)
    print()

# Now the honest count: identical once the header's first 64 bytes are excluded.
print("=" * 78)
print("changed tiles, IGNORING the first N bytes of each tile")
print("=" * 78)
base = {str(p.relative_to(ROOT / "A" / "tiles")).replace("\\", "/"): p
        for p in (ROOT / "A" / "tiles").rglob("*.gph")}
for skip in (0, 32, 36, 40, 48, 64, 128):
    line = f"   skip {skip:>4}: "
    for label in ("M1", "M2"):
        changed = 0
        for name, pa in base.items():
            pb = ROOT / label / "tiles" / name
            if not pb.exists():
                changed += 1
                continue
            a, b = pa.read_bytes(), pb.read_bytes()
            if hashlib.sha256(a[skip:]).digest() != hashlib.sha256(b[skip:]).digest():
                changed += 1
        line += f"{label} {changed:>4}/{len(base)}   "
    print(line)
