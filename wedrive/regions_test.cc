// WeDrive: does one reader hold two independently built graphs at once?
//
// The test is the collision. Moldova and Romania, built by separate Mjolnir runs that knew nothing
// of each other, share 35 tile FILENAMES and none of them byte-identical. Stock Valhalla keys its
// cache on (level, tileid), so asking for that tile twice would hand back whichever copy was
// loaded first — the second region would silently read the first region's roads.
//
// Passing means: the same GraphId, tagged for two different regions, yields two different tiles,
// each with the node and edge counts its own build wrote.
#include <cstdint>
#include <iostream>
#include <string>

#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/baldr/graphtile.h>
#include <boost/property_tree/ptree.hpp>

using namespace valhalla::baldr;

namespace {

// A tile path like "2/000/779/872.gph" back into the id Valhalla would use for it.
GraphId FromPath(uint32_t level, uint64_t tileid) {
  GraphId id;
  id.value = level | (tileid << 3);
  return id;
}

int failures = 0;

void check(bool ok, const std::string& what) {
  std::cout << (ok ? "  ok   " : "  FAIL ") << what << "\n";
  if (!ok) {
    ++failures;
  }
}

} // namespace

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: " << argv[0] << " <moldova-tile-dir> <romania-tile-dir>\n";
    return 2;
  }
  const std::string md_dir = argv[1];
  const std::string ro_dir = argv[2];

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", md_dir); // region 0 falls back to this
  conf.put("mjolnir.max_cache_size", 512 * 1024 * 1024);
  // FlatTileCache, the default, keys on level and tileid alone — `get_offset` never sees the
  // region, so both regions' copies of a tile land on one slot and the second ask returns the
  // first's bytes. SimpleTileCache keys on the whole GraphId value, region bits included.
  // Set here to establish that the DESIGN is sound; the flat cache is fixed separately.
  conf.put("mjolnir.use_simple_mem_cache", true);

  GraphReader reader(conf.get_child("mjolnir"));
  reader.AddRegion(1, md_dir);
  reader.AddRegion(2, ro_dir);
  std::cout << "regions registered: " << reader.RegionCount() << "\n";
  check(reader.RegionCount() == 2, "two regions registered");

  // 2/000/779/872.gph — one of the 35 paths present in BOTH builds.
  const GraphId plain = FromPath(2, 779872);
  const GraphId in_md = plain.with_region(1);
  const GraphId in_ro = plain.with_region(2);

  std::cout << "\nthe same tile, asked for twice:\n";
  std::cout << "  plain  value=" << plain.value << " level=" << plain.level()
            << " tileid=" << plain.tileid() << " region=" << plain.region() << "\n";
  std::cout << "  as MD  value=" << in_md.value << " level=" << in_md.level()
            << " tileid=" << in_md.tileid() << " region=" << in_md.region() << "\n";
  std::cout << "  as RO  value=" << in_ro.value << " level=" << in_ro.level()
            << " tileid=" << in_ro.tileid() << " region=" << in_ro.region() << "\n\n";

  check(in_md.level() == 2 && in_ro.level() == 2, "the region does not disturb level()");
  check(in_md.tileid() == 779872 && in_ro.tileid() == 779872, "nor tileid()");
  check(in_md.tile_base().region() == 1, "tile_base() keeps the region");
  check(in_md.without_region().value == plain.value, "without_region() undoes the tag");
  check(in_md.is_valid() && in_ro.is_valid(), "a tagged id is still valid");

  auto md = reader.GetGraphTile(in_md);
  auto ro = reader.GetGraphTile(in_ro);
  check(md != nullptr, "moldova's copy loaded");
  check(ro != nullptr, "romania's copy loaded");
  if (!md || !ro) {
    std::cout << "\ncannot continue without both tiles\n";
    return 1;
  }

  const auto mn = md->header()->nodecount(), me = md->header()->directededgecount();
  const auto rn = ro->header()->nodecount(), re = ro->header()->directededgecount();
  std::cout << "\n  moldova's tile : " << mn << " nodes, " << me << " directed edges\n";
  std::cout << "  romania's tile : " << rn << " nodes, " << re << " directed edges\n\n";

  check(md.get() != ro.get(), "they are two DIFFERENT tiles, not one served twice");
  check(mn != rn || me != re,
        "their contents differ, as two independent builds of the same cell must");
  check(md->id().region() == 1, "moldova's tile reports region 1");
  check(ro->id().region() == 2, "romania's tile reports region 2");

  // Ask again: the cache must keep them apart rather than collapsing them.
  auto md2 = reader.GetGraphTile(in_md);
  check(md2.get() == md.get(), "the second ask for moldova hits the same cached tile");
  auto ro2 = reader.GetGraphTile(in_ro);
  check(ro2.get() == ro.get(), "and romania's stays its own");

  std::cout << "\n" << (failures ? "FAILURES: " + std::to_string(failures) : "all checks passed")
            << "\n";
  return failures ? 1 : 0;
}
