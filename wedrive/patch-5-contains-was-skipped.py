"""WeDrive patch 5: the one FlatTileCache method patch 4 silently skipped.

Patch 4 reported "already applied" for `Contains` and moved on. It had not been applied. The
idempotency check compared the first 40 characters after the WEDRIVE marker, and for `Put` and
`Contains` those characters are identical:

    ": see Get.\\n  if (graphid.region() != 0) {"

So once `Put` was in, `Contains` looked done. The test passed regardless, because it never calls
`Contains` — a green result over a function that had not changed, which is precisely the failure
this project keeps meeting from the other side.

The marker is now the METHOD NAME, which cannot collide.
"""
import io
import os

SRC = os.path.expanduser("~/vhbuild/src")
P = os.path.join(SRC, "src/baldr/graphreader.cc")
s = io.open(P, encoding="utf-8").read()

OLD = """bool FlatTileCache::Contains(const GraphId& graphid) const {
  return is_valid(get_index(graphid));
}"""
NEW = """bool FlatTileCache::Contains(const GraphId& graphid) const {
  // WEDRIVE Contains: a tagged tile lives in the region map, not the flat array — its slot there
  // would be shared with every other region's copy of the same cell.
  if (graphid.region() != 0) {
    return wedrive_region_cache_.find(graphid.value) != wedrive_region_cache_.end();
  }
  return is_valid(get_index(graphid));
}"""

if "WEDRIVE Contains" in s:
    print("   already applied (checked by method name, which cannot collide)")
else:
    assert s.count(OLD) == 1, f"wanted 1 match, found {s.count(OLD)}"
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("   src/baldr/graphreader.cc: Contains consults the region map — FOR REAL this time")

# Prove each of the four is present, by its own unique marker.
s = io.open(P, encoding="utf-8").read()
h = io.open(os.path.join(SRC, "valhalla/baldr/graphreader.h"), encoding="utf-8").read()
print("\n   verification, each by a marker that cannot be confused with another:")
for what, hay, needle in (
    ("the region map member", h, "wedrive_region_cache_;"),
    ("Get", s, "graph_tile_ptr FlatTileCache::Get(const GraphId& graphid) const {\n  // WEDRIVE"),
    ("Put", s, "size_t size) {\n  // WEDRIVE: see Get."),
    ("Contains", s, "WEDRIVE Contains"),
    ("Clear", s, "void FlatTileCache::Clear() {\n  // WEDRIVE"),
):
    print(f"      {'ok  ' if needle in hay else 'MISSING'} {what}")
