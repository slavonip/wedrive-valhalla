"""WeDrive patch 4: make the DEFAULT cache region-aware.

The first run of the test failed in exactly the place it was written to watch. Everything about
the region tag worked — level(), tileid(), tile_base(), is_valid() — and yet the two tiles came
back as ONE object, with Romania's copy calling itself region 1. The cause:

    FlatTileCache::get_offset(graphid)
        -> index_offsets_[graphid.level()] + graphid.tileid()

Level and tileid only. The region never reaches it, so both regions' copies of a cell land on one
slot and the second ask returns the first's bytes — a router reading another country's roads
under the right filename, which is the silent failure this whole branch exists to prevent.

Switching the test to SimpleTileCache proved the design (438 nodes against 11734 for the same
path). But the flat cache is the DEFAULT, so leaving it region-blind means the correct behaviour
depends on a config flag nobody would know to set.

THE FIX KEEPS STOCK BEHAVIOUR EXACTLY. Region 0 — every single-region setup — still takes the
flat array with its O(1) offset and unchanged memory. Only tiles carrying a region fall through
to a small map keyed on the whole GraphId value. Sizing the flat array for (regions x tiles)
was rejected: the region count is not known when the cache is constructed, and it would multiply
the index array for every user who has only one region.
"""
import io
import os

SRC = os.path.expanduser("~/vhbuild/src")
edits = 0


def patch(path, old, new, why, count=1):
    global edits
    p = os.path.join(SRC, path)
    s = io.open(p, encoding="utf-8").read()
    if "WEDRIVE" in new and new.split("WEDRIVE", 1)[1][:40] in s:
        print(f"   already applied: {path} — {why}")
        return
    assert s.count(old) == count, \
        f"{path}: {why}\n  wanted {count}, found {s.count(old)} for:\n{old[:200]}"
    io.open(p, "w", encoding="utf-8").write(s.replace(old, new))
    edits += 1
    print(f"   {path}: {why}")


patch("valhalla/baldr/graphreader.h",
      """  // The actual cached GraphTile objects
  std::vector<graph_tile_ptr> cache_;""",
      """  // WEDRIVE: tiles from a registered region, keyed on the WHOLE GraphId value so the region
  // bits are part of the key. The flat array below is indexed by level and tileid alone and
  // cannot tell two regions' copies of a cell apart; rather than resize it for a region count
  // that is unknown at construction, region 0 keeps the fast path untouched and anything tagged
  // comes through here.
  std::unordered_map<uint64_t, graph_tile_ptr> wedrive_region_cache_;

  // The actual cached GraphTile objects
  std::vector<graph_tile_ptr> cache_;""",
      "an overflow map for tagged tiles")

# Get / Put / Contains / Clear all have to consult it.
patch("src/baldr/graphreader.cc",
      """graph_tile_ptr FlatTileCache::Get(const GraphId& graphid) const {""",
      """graph_tile_ptr FlatTileCache::Get(const GraphId& graphid) const {
  // WEDRIVE: a tagged tile is not in the flat array — its slot would collide with every other
  // region's copy of the same cell.
  if (graphid.region() != 0) {
    auto found = wedrive_region_cache_.find(graphid.value);
    return found == wedrive_region_cache_.end() ? nullptr : found->second;
  }""",
      "Get consults the region map")

patch("src/baldr/graphreader.cc",
      """graph_tile_ptr FlatTileCache::Put(const GraphId& graphid, graph_tile_ptr tile, size_t size) {""",
      """graph_tile_ptr FlatTileCache::Put(const GraphId& graphid, graph_tile_ptr tile, size_t size) {
  // WEDRIVE: see Get.
  if (graphid.region() != 0) {
    cache_size_ += size;
    return wedrive_region_cache_.emplace(graphid.value, std::move(tile)).first->second;
  }""",
      "Put stores tagged tiles apart")

patch("src/baldr/graphreader.cc",
      """bool FlatTileCache::Contains(const GraphId& graphid) const {""",
      """bool FlatTileCache::Contains(const GraphId& graphid) const {
  // WEDRIVE: see Get.
  if (graphid.region() != 0) {
    return wedrive_region_cache_.find(graphid.value) != wedrive_region_cache_.end();
  }""",
      "Contains consults the region map")

patch("src/baldr/graphreader.cc",
      """void FlatTileCache::Clear() {""",
      """void FlatTileCache::Clear() {
  // WEDRIVE: the region map is part of this cache and is emptied with it.
  wedrive_region_cache_.clear();""",
      "Clear empties the region map too")

print(f"\n{edits} edits applied")
