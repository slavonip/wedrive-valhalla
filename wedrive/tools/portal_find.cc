// WeDrive: build the external portal table from the graphs themselves.
//
// Two independently built extracts overlap at the frontier, so the SAME physical junction exists
// in both, at the same coordinate, with different ids in different namespaces. Every such pair is
// a candidate portal. This finds them by coordinate coincidence rather than by anyone typing a
// border crossing from memory -- the failure mode that has already cost this project three probes.
//
// It emits the table compose_route reads, one line per direction:
//     <from_graphid> <to_graphid> <metres>   # lat, lon
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

#include <boost/property_tree/ptree.hpp>
#include <valhalla/baldr/graphconstants.h>
#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/baldr/graphtile.h>
#include <valhalla/baldr/tilehierarchy.h>
#include <valhalla/midgard/pointll.h>

using namespace valhalla::baldr;
using namespace valhalla::midgard;

namespace {

// A node's position quantised hard enough that the same OSM node encoded into two different tile
// builds lands in the same bucket, and tight enough (~1 cm) that two genuinely different junctions
// never do.
uint64_t Key(const PointLL& ll) {
  const int64_t lat = static_cast<int64_t>(std::llround(ll.lat() * 1e7));
  const int64_t lon = static_cast<int64_t>(std::llround(ll.lng() * 1e7));
  return (static_cast<uint64_t>(lat + 900000000) << 32) ^ static_cast<uint64_t>(lon + 1800000000);
}

bool Drivable(const graph_tile_ptr& tile, const NodeInfo* n) {
  for (uint32_t e = 0; e < n->edge_count(); ++e) {
    const auto* de = tile->directededge(n->edge_index() + e);
    if (!de->is_shortcut() && (de->forwardaccess() & kAutoAccess)) {
      return true;
    }
  }
  return false;
}

struct Cand {
  GraphId node;
  PointLL ll;
};

} // namespace

int main(int argc, char** argv) {
  if (argc < 8) {
    std::cerr << "usage: " << argv[0]
              << " <md-dir> <ro-dir> <minlat> <minlon> <maxlat> <maxlon> <level>\n";
    return 2;
  }
  const std::string md_dir = argv[1], ro_dir = argv[2];
  const double minlat = std::stod(argv[3]), minlon = std::stod(argv[4]);
  const double maxlat = std::stod(argv[5]), maxlon = std::stod(argv[6]);
  const uint8_t level = static_cast<uint8_t>(std::stoi(argv[7]));

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", md_dir);
  conf.put("mjolnir.max_cache_size", 3ull * 1024 * 1024 * 1024);
  GraphReader reader(conf.get_child("mjolnir"));
  reader.AddRegion(1, md_dir);
  reader.AddRegion(2, ro_dir);

  const auto& tiles = TileHierarchy::levels()[level].tiles;
  const int32_t lo = tiles.TileId(PointLL(minlon, minlat));
  const int32_t hi = tiles.TileId(PointLL(maxlon, maxlat));
  const int32_t cols = tiles.ncolumns();
  const int32_t r0 = lo / cols, r1 = hi / cols;
  const int32_t c0 = lo % cols, c1 = hi % cols;

  size_t pairs = 0, md_nodes = 0, ro_nodes = 0;
  std::vector<std::string> lines;

  for (int32_t r = r0; r <= r1; ++r) {
    for (int32_t c = c0; c <= c1; ++c) {
      const int32_t tid = r * cols + c;
      if (tid < 0) {
        continue;
      }
      GraphId base_id(static_cast<uint32_t>(tid), level, 0);
      auto md = reader.GetGraphTile(base_id.with_region(1));
      auto ro = reader.GetGraphTile(base_id.with_region(2));
      if (!md || !ro) {
        continue; // a portal needs the junction in BOTH namespaces
      }

      std::unordered_map<uint64_t, Cand> by_pos;
      const auto md_base = md->header()->base_ll();
      for (uint32_t i = 0; i < md->header()->nodecount(); ++i) {
        const auto* n = md->node(i);
        if (!Drivable(md, n)) {
          continue;
        }
        const PointLL ll = n->latlng(md_base);
        if (ll.lat() < minlat || ll.lat() > maxlat || ll.lng() < minlon || ll.lng() > maxlon) {
          continue;
        }
        ++md_nodes;
        by_pos[Key(ll)] = {GraphId(base_id.tileid(), level, i).with_region(1), ll};
      }

      const auto ro_base = ro->header()->base_ll();
      for (uint32_t i = 0; i < ro->header()->nodecount(); ++i) {
        const auto* n = ro->node(i);
        if (!Drivable(ro, n)) {
          continue;
        }
        const PointLL ll = n->latlng(ro_base);
        if (ll.lat() < minlat || ll.lat() > maxlat || ll.lng() < minlon || ll.lng() > maxlon) {
          continue;
        }
        ++ro_nodes;
        auto it = by_pos.find(Key(ll));
        if (it == by_pos.end()) {
          continue;
        }
        const GraphId ro_id = GraphId(base_id.tileid(), level, i).with_region(2);
        char buf[256];
        std::snprintf(buf, sizeof(buf), "%llu %llu 0   # %.6f, %.6f",
                      static_cast<unsigned long long>(it->second.node.value),
                      static_cast<unsigned long long>(ro_id.value), ll.lat(), ll.lng());
        lines.push_back(buf);
        std::snprintf(buf, sizeof(buf), "%llu %llu 0   # %.6f, %.6f",
                      static_cast<unsigned long long>(ro_id.value),
                      static_cast<unsigned long long>(it->second.node.value), ll.lat(), ll.lng());
        lines.push_back(buf);
        ++pairs;
      }
    }
  }

  std::cerr << "# level " << int(level) << "   drivable nodes in box: MD " << md_nodes << "  RO "
            << ro_nodes << "   coincident pairs " << pairs << "\n";
  for (const auto& l : lines) {
    std::cout << l << "\n";
  }
  return 0;
}
