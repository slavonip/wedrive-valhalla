"""WeDrive patch 71: a region knows which of its tiles exist, so a missing one costs no syscall.

MEASURED 2026-10-02, desktop and emulator, same four country graphs (MD RO HU AT). One snap of a
two-point jam in Chisinau on a warm engine: MD alone 31 ms; MD+RO 3.9 s; +HU 9.1 s; +AT 11.8 s,
with an identical answer every time. CPU for the 11.8 s was 0.85 s. Every one of 40 stack samples
of the busy thread sat in open(): loki::Search::search -> GetGraphTile -> GraphTile::Create ->
fopen. The multi-region search asks EVERY region for the tile of each bin it walks, a region that
has no tile there answers ENOENT, and nothing remembers it: RO/2/000/789/955.gph was opened 52
times in one request, 1278 failed opens in all. On the device an open on the SD card goes through
FUSE at ~25-30 ms, which is where 21 s per snap and 318 s per 150 km route trace came from
(12 212 failed opens in that trace).

THE FIX IS AN INDEX, NOT A NEGATIVE CACHE. A cache learns a missing tile by failing to open it
once per (region, tile), so with 50 countries installed the first query in every new area would
still pay ~49 x 16 x 30 ms. The index is read once when the region is registered: one directory
walk, the relative path of every tile file (".gz" stripped, since Create accepts either). The
lookup key is GraphTile::FileSuffix(base) — the very string Create appends to the directory to
open the file — so the check and the open cannot disagree about which file is meant.

WHAT DOES NOT CHANGE. Only the filesystem probe is skipped: an absent tile leaves `tile` null and
everything after it (the URL getter, its 404 record) runs exactly as before. A region whose walk
found nothing — an empty or unreadable directory — keeps no index and is probed as it always was.
The index is built in AddRegion, before any request, and never written again, so readers need no
lock. A reopened engine builds a fresh reader and with it a fresh index.
"""
import io
import os
SRC = "/src/valhalla"
edits = 0


def patch(path, old, new, why, count=1):
    global edits
    p = os.path.join(SRC, path)
    s = io.open(p, encoding="utf-8").read()
    if new in s:
        print(f"   already applied: {path} — {why}")
        return
    assert s.count(old) == count, \
        f"{path}: {why}\n  wanted {count}, found {s.count(old)} for:\n{old[:200]}"
    io.open(p, "w", encoding="utf-8").write(s.replace(old, new))
    edits += 1
    print(f"   {path}: {why}")


patch("valhalla/baldr/graphreader.h",
      """    wedrive_region_dirs_[region] = tile_dir;
  }
""",
      """    wedrive_region_dirs_[region] = tile_dir;
    WeDriveIndexRegion(region, tile_dir); // WEDRIVE tile presence: walk the directory once
  }

  /** WEDRIVE tile presence: true when [region] keeps an index and the tile is NOT in it. */
  bool WeDriveTileAbsent(const GraphId& base) const {
    auto found = wedrive_region_tiles_.find(base.region());
    if (found == wedrive_region_tiles_.end()) {
      return false; // no index for this region: probe the filesystem as before
    }
    return found->second.find(GraphTile::FileSuffix(base)) == found->second.end();
  }
""",
      "AddRegion builds the presence index; a lookup helper")

patch("valhalla/baldr/graphreader.h",
      """  std::unordered_map<uint32_t, std::string> wedrive_region_dirs_;
""",
      """  std::unordered_map<uint32_t, std::string> wedrive_region_dirs_;

  // WEDRIVE tile presence: per region, the relative path of every tile file that existed when the
  // region was registered. Written only in AddRegion, before any request; read-only afterwards.
  std::unordered_map<uint32_t, std::unordered_set<std::string>> wedrive_region_tiles_;
  void WeDriveIndexRegion(uint32_t region, const std::string& tile_dir);
""",
      "the index member")

patch("valhalla/baldr/graphreader.h",
      """#include <unordered_map>
""",
      """#include <unordered_map>
#include <unordered_set> // WEDRIVE tile presence
""",
      "unordered_set include")

patch("src/baldr/graphreader.cc",
      """  graph_tile_ptr tile =
      GraphTile::Create(TileDirForRegion(base.region()), base, std::move(traffic_memory));
""",
      """  // WEDRIVE tile presence: a region that indexed its directory and has no such tile is not asked
  // to open it. Only the filesystem probe is skipped; a null tile takes the same path below.
  graph_tile_ptr tile =
      WeDriveTileAbsent(base)
          ? nullptr
          : GraphTile::Create(TileDirForRegion(base.region()), base, std::move(traffic_memory));
""",
      "GetGraphTile skips the open of an absent tile")

patch("src/baldr/graphreader.cc",
      """bool GraphReader::DoesTileExist(const GraphId& graphid) const {""",
      """// WEDRIVE tile presence: one directory walk per region, at registration.
void GraphReader::WeDriveIndexRegion(uint32_t region, const std::string& tile_dir) {
  std::unordered_set<std::string> tiles;
  std::error_code ec;
  const std::filesystem::path root{tile_dir};
  // The relative path is cut off the iterator's own string, not computed with
  // std::filesystem::relative(): that canonicalises both paths and stats every component of every
  // file, which on a slow mount made a 50-region open take 69 s. The directory entry's type comes
  // from readdir, so the walk itself costs one getdents per directory and no stat per file.
  const std::string prefix = (root / "").string();
  for (std::filesystem::recursive_directory_iterator it(root, ec), end; !ec && it != end;
       it.increment(ec)) {
    std::error_code type_ec;
    if (!it->is_regular_file(type_ec)) {
      continue;
    }
    const std::string& full = it->path().native();
    if (full.compare(0, prefix.size(), prefix) != 0) {
      continue;
    }
    std::string rel = full.substr(prefix.size());
    if (rel.size() > 3 && rel.compare(rel.size() - 3, 3, ".gz") == 0) {
      rel.resize(rel.size() - 3);
    }
    if (rel.size() > 4 && rel.compare(rel.size() - 4, 4, ".gph") == 0) {
      tiles.insert(std::move(rel));
    }
  }
  if (ec || tiles.empty()) {
    // Unreadable or empty: keep no index, so this region is probed exactly as before.
    wedrive_region_tiles_.erase(region);
    LOG_WARN("WEDRIVE tile presence: region " + std::to_string(region) + " not indexed (" +
             (ec ? ec.message() : std::string("no tiles")) + "), probing the filesystem");
    return;
  }
  LOG_INFO("WEDRIVE tile presence: region " + std::to_string(region) + " has " +
           std::to_string(tiles.size()) + " tiles");
  wedrive_region_tiles_[region] = std::move(tiles);
}

bool GraphReader::DoesTileExist(const GraphId& graphid) const {""",
      "the directory walk")

print(f"\n{edits} edits applied")
