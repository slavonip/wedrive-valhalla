"""WeDrive patch 2 and 3: a tile that knows its region, and a reader that holds several tile dirs.

Region 0 is the default everywhere, and `with_region(0)` is the identity, so a single-region setup
behaves EXACTLY as stock. That is deliberate: the patch must be invisible until someone registers
a second region, or every existing measurement in this project would need redoing.
"""
import io
import os

SRC = os.path.expanduser("~/vhbuild/src")
edits = 0


def patch(path, old, new, why, count=1):
    global edits
    p = os.path.join(SRC, path)
    s = io.open(p, encoding="utf-8").read()
    if new.strip() and "WEDRIVE" in new and new.split("WEDRIVE", 1)[1][:40] in s:
        print(f"   already applied: {path} — {why}")
        return
    assert s.count(old) == count, \
        f"{path}: {why}\n  wanted {count} match(es), found {s.count(old)} for:\n{old[:220]}"
    io.open(p, "w", encoding="utf-8").write(s.replace(old, new))
    edits += 1
    print(f"   {path}: {why}")


# ── 2. GraphTile remembers which region it was loaded for ───────────────────────────────────
patch("valhalla/baldr/graphtile.h",
      """  GraphId id() const {
    return header_->graphid();
  }""",
      """  GraphId id() const {
    // WEDRIVE: the header knows nothing of regions — it was written by a Mjolnir run that had
    // only one. The reader compares `tile->id() != graphid.tile_base()` to decide a cache hit,
    // so a tile must answer with the region it was loaded FOR. region 0 is the identity, which
    // is why a single-region setup is bit-for-bit the stock behaviour.
    return header_->graphid().with_region(wedrive_region_);
  }

  /** WEDRIVE: which independently built region this tile was loaded for. */
  uint32_t wedrive_region() const {
    return wedrive_region_;
  }""",
      "GraphTile::id() carries the region")

patch("valhalla/baldr/graphtile.h",
      "  std::unique_ptr<const GraphMemory> memory_;",
      """  std::unique_ptr<const GraphMemory> memory_;

  // WEDRIVE: set from the GraphId this tile was requested with, so the tile can report an id
  // that matches what the reader asked for. Zero unless several regions are registered.
  uint32_t wedrive_region_{0};""",
      "region member on GraphTile")

patch("src/baldr/graphtile.cc",
      """    : header_(nullptr), traffic_tile(std::move(traffic_memory)) {
  // Initialize the internal tile data structures using a pointer to the
  // tile and the tile size
  memory_ = std::move(memory);""",
      """    : header_(nullptr), traffic_tile(std::move(traffic_memory)) {
  // WEDRIVE: remember the region the caller asked for, before anything else touches graphid.
  wedrive_region_ = graphid.region();
  // Initialize the internal tile data structures using a pointer to the
  // tile and the tile size
  memory_ = std::move(memory);""",
      "constructor records the region")

# ── 3. GraphReader: a directory per region ──────────────────────────────────────────────────
patch("valhalla/baldr/graphreader.h",
      "  virtual graph_tile_ptr GetGraphTile(const GraphId& graphid);",
      """  virtual graph_tile_ptr GetGraphTile(const GraphId& graphid);

  /**
   * WEDRIVE: register an independently built region.
   *
   * Each region is a Mjolnir run that knew nothing of the others, so two regions may hold the
   * same tile FILENAME with different contents — measured on Moldova and Romania: 35 shared
   * paths, none byte-identical. The region id rides in the spare high bits of a GraphId, which
   * never reach a file, so nothing about the tile format changes.
   *
   * Region 0 is the unregistered default and reads from the ordinary tile_dir.
   */
  void AddRegion(const uint32_t region, const std::string& tile_dir) {
    wedrive_region_dirs_[region] = tile_dir;
  }

  /** WEDRIVE: the directory a region's tiles live in; the stock tile_dir for region 0. */
  const std::string& TileDirForRegion(const uint32_t region) const {
    auto found = wedrive_region_dirs_.find(region);
    return found == wedrive_region_dirs_.end() ? tile_dir_ : found->second;
  }

  /** WEDRIVE: how many independently built regions are registered. */
  size_t RegionCount() const {
    return wedrive_region_dirs_.size();
  }""",
      "AddRegion / TileDirForRegion")

patch("src/baldr/graphreader.cc",
      "  graph_tile_ptr tile = GraphTile::Create(tile_dir_, base, std::move(traffic_memory));",
      """  // WEDRIVE: pick the directory by the region carried in the id's spare bits. With no region
  // registered this is tile_dir_ and the line behaves exactly as it did.
  graph_tile_ptr tile =
      GraphTile::Create(TileDirForRegion(base.region()), base, std::move(traffic_memory));""",
      "GetGraphTile reads from the region's directory")

print(f"\n{edits} edits applied")
