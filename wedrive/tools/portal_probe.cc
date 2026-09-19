// WeDrive: find the real nodes on each side of a border crossing, from the graphs themselves.
//
// Probe coordinates typed from memory have cost this project three separate failures, so the two
// ends of the first portal are located by asking each region's graph what it actually has near
// the crossing — and by reporting how far away that is, so a node in the wrong village cannot
// pass unnoticed.
//
// It also answers the question the portal exists to fix: does either graph already reach the
// other side? Moldova's build knows nothing of Romania, so its westernmost edges should simply
// stop at the Prut.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include <boost/property_tree/ptree.hpp>
#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/baldr/graphtile.h>
#include <valhalla/baldr/tilehierarchy.h>
#include <valhalla/midgard/pointll.h>

using namespace valhalla::baldr;
using namespace valhalla::midgard;

namespace {

struct Found {
  GraphId node;
  PointLL ll;
  double metres;
  uint32_t edges;
};

// Every node in the tiles covering a small box around `centre`, nearest first.
std::vector<Found> NearestNodes(GraphReader& reader,
                                uint32_t region,
                                const PointLL& centre,
                                uint8_t level,
                                size_t want) {
  std::vector<Found> found;
  // The tile the point is in, plus its eight neighbours — a crossing sits on a tile edge as often
  // as not, and looking only at the containing tile is how a node two hundred metres away goes
  // missing.
  const auto& tiles = TileHierarchy::levels()[level].tiles;
  const auto centre_id = tiles.TileId(centre);
  const int32_t cols = tiles.ncolumns();
  for (int32_t dr = -1; dr <= 1; ++dr) {
    for (int32_t dc = -1; dc <= 1; ++dc) {
      const int32_t tid = centre_id + dr * cols + dc;
      if (tid < 0) {
        continue;
      }
      GraphId tile_id(static_cast<uint32_t>(tid), level, 0);
      auto tile = reader.GetGraphTile(tile_id.with_region(region));
      if (!tile) {
        continue;
      }
      const auto base = tile->header()->base_ll();
      for (uint32_t i = 0; i < tile->header()->nodecount(); ++i) {
        const auto* n = tile->node(i);
        const PointLL ll = n->latlng(base);
        const double d = ll.Distance(centre);
        if (d < 25000.0) {
          found.push_back({GraphId(tile_id.tileid(), level, i).with_region(region), ll, d,
                           n->edge_count()});
        }
      }
    }
  }
  std::sort(found.begin(), found.end(),
            [](const Found& a, const Found& b) { return a.metres < b.metres; });
  if (found.size() > want) {
    found.resize(want);
  }
  return found;
}

} // namespace

int main(int argc, char** argv) {
  if (argc < 5) {
    std::cerr << "usage: " << argv[0] << " <md-dir> <ro-dir> <lat> <lon> [level]\n";
    return 2;
  }
  const std::string md_dir = argv[1], ro_dir = argv[2];
  const PointLL centre(std::stod(argv[4]), std::stod(argv[3]));
  const uint8_t level = argc > 5 ? static_cast<uint8_t>(std::stoi(argv[5])) : 2;

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", md_dir);
  conf.put("mjolnir.max_cache_size", 1024ull * 1024 * 1024);

  GraphReader reader(conf.get_child("mjolnir"));
  reader.AddRegion(1, md_dir);
  reader.AddRegion(2, ro_dir);

  std::cout << "looking around " << centre.lat() << ", " << centre.lng() << " at level "
            << int(level) << "\n\n";

  for (auto [region, name] : {std::pair<uint32_t, const char*>{1, "MOLDOVA"},
                              std::pair<uint32_t, const char*>{2, "ROMANIA"}}) {
    std::cout << name << " (region " << region << ")\n";
    auto near = NearestNodes(reader, region, centre, level, 6);
    if (near.empty()) {
      std::cout << "   nothing within 25 km — this region has no graph here\n\n";
      continue;
    }
    for (const auto& f : near) {
      std::cout << "   node " << f.node.value << "  tile " << f.node.tileid() << " id "
                << f.node.id() << "   " << f.ll.lat() << ", " << f.ll.lng() << "   "
                << int(f.metres) << " m   " << f.edges << " edges\n";
    }
    std::cout << "\n";
  }
  return 0;
}
