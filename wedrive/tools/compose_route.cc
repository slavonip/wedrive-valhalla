// WeDrive: one routing search across two independently built Valhalla graphs.
//
// This is the proof, not the product. It does NOT touch Thor. It runs a single A* over a graph
// composed of two tile directories plus an external portal table, to answer one question:
//
//     can a search cross from one namespace into another without changing the .gph format?
//
// The negative control is the whole point. With the portal table empty the same binary, the same
// search and the same costing must fail -- otherwise a success proves nothing but that Geofabrik's
// extracts overlap at the border, which they demonstrably do.
//
// THE ONE RULE THAT MAKES THIS WORK: a GraphId read out of tile bytes carries no region. Every
// endnode taken from a DirectedEdge or a NodeTransition is re-tagged with the region of the node
// it was reached from, because a tile cannot know which namespace it was loaded into.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <queue>
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

// The external transition table. Deliberately as primitive as the design asks for: no tile edits,
// no synthetic DirectedEdge, nothing inside the .gph.
struct Portal {
  GraphId from;
  GraphId to;
  float distance; // metres of real road between the endpoints; 0 when they are one junction
};

struct Snap {
  GraphId node;
  PointLL ll;
  double metres;
};

// Nearest node carrying at least one edge, across every level, in the regions we were given.
Snap NearestNode(GraphReader& reader, const std::vector<uint32_t>& regions, const PointLL& p) {
  Snap best{GraphId(), PointLL(), 1e18};
  for (uint32_t region : regions) {
    for (uint8_t level = 0; level <= 2; ++level) {
      const auto& tiles = TileHierarchy::levels()[level].tiles;
      const int32_t centre = tiles.TileId(p);
      const int32_t cols = tiles.ncolumns();
      for (int32_t dr = -1; dr <= 1; ++dr) {
        for (int32_t dc = -1; dc <= 1; ++dc) {
          const int32_t tid = centre + dr * cols + dc;
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
            if (n->edge_count() == 0) {
              continue;
            }
            // The nearest node is not necessarily a node a CAR can stand on. Snapping to the
            // closest thing with any edge at all put Ungheni on a footpath and reported NO ROUTE
            // for a journey wholly inside one country -- a harness failure wearing the exact
            // costume of the defect this harness exists to detect.
            bool drivable = false;
            for (uint32_t e = 0; e < n->edge_count() && !drivable; ++e) {
              const auto* de = tile->directededge(n->edge_index() + e);
              drivable = !de->is_shortcut() && (de->forwardaccess() & kAutoAccess);
            }
            if (!drivable) {
              continue;
            }
            const PointLL ll = n->latlng(base);
            const double d = ll.Distance(p);
            if (d < best.metres) {
              best = {GraphId(tile_id.tileid(), level, i).with_region(region), ll, d};
            }
          }
        }
      }
    }
  }
  return best;
}

struct Step {
  uint64_t from;
  enum Kind { kEdge, kTransition, kPortal } kind;
};

struct QItem {
  double f; // cost so far plus the straight line still to run
  double g; // cost so far, metres
  uint64_t node;
  bool operator>(const QItem& o) const {
    return f > o.f;
  }
};

} // namespace

int main(int argc, char** argv) {
  if (argc < 8) {
    std::cerr << "usage: " << argv[0]
              << " <md-dir> <ro-dir> <olat> <olon> <dlat> <dlon> <md|ro|both|both+portal>\n";
    return 2;
  }
  const std::string md_dir = argv[1], ro_dir = argv[2];
  const PointLL origin(std::stod(argv[4]), std::stod(argv[3]));
  const PointLL dest(std::stod(argv[6]), std::stod(argv[5]));
  const std::string mode = argv[7];

  std::vector<uint32_t> regions;
  bool use_portals = false;
  if (mode == "md") {
    regions = {1};
  } else if (mode == "ro") {
    regions = {2};
  } else if (mode == "both") {
    regions = {1, 2};
  } else if (mode == "both+portal") {
    regions = {1, 2};
    use_portals = true;
  } else {
    std::cerr << "unknown mode " << mode << "\n";
    return 2;
  }

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", md_dir);
  conf.put("mjolnir.max_cache_size", 3ull * 1024 * 1024 * 1024);
  GraphReader reader(conf.get_child("mjolnir"));
  reader.AddRegion(1, md_dir);
  reader.AddRegion(2, ro_dir);

  // The portal table. Either the one hand-picked crossing, or a file written by portal_find --
  // the table is external either way, and nothing about it lives inside a .gph.
  std::vector<Portal> portals;
  if (use_portals) {
    if (argc > 8) {
      std::ifstream in(argv[8]);
      if (!in) {
        std::cerr << "cannot read portal table " << argv[8] << "\n";
        return 2;
      }
      std::string line;
      while (std::getline(in, line)) {
        const auto hash = line.find('#');
        if (hash != std::string::npos) {
          line.erase(hash);
        }
        std::istringstream ls(line);
        uint64_t from = 0, to = 0;
        double d = 0.0;
        if (ls >> from >> to >> d) {
          portals.push_back({GraphId(from), GraphId(to), static_cast<float>(d)});
        }
      }
    } else {
      // Two copies of the Leuseni/Albita junction on the E581, one in each independently built
      // graph, at the identical coordinate. Located by asking the graphs, never typed from memory.
      const GraphId md_side(70384118415618ULL);
      const GraphId ro_side(140758264856834ULL);
      portals.push_back({md_side, ro_side, 0.0f});
      portals.push_back({ro_side, md_side, 0.0f}); // bidirectional: two entries, as specified
    }
  }
  std::unordered_map<uint64_t, std::vector<const Portal*>> portal_index;
  for (const auto& p : portals) {
    portal_index[p.from.value].push_back(&p);
  }

  std::cout << "mode " << mode << "   regions";
  for (auto r : regions) {
    std::cout << " " << r;
  }
  std::cout << "   portals " << portals.size() << "\n";

  const Snap start = NearestNode(reader, regions, origin);
  const Snap target = NearestNode(reader, regions, dest);
  if (!start.node.is_valid() || start.metres > 2000.0) {
    std::cout << "NO ROUTE: origin does not snap (nearest node " << int(start.metres)
              << " m away)\n";
    return 1;
  }
  if (!target.node.is_valid() || target.metres > 2000.0) {
    std::cout << "NO ROUTE: destination does not snap (nearest node " << int(target.metres)
              << " m away)\n";
    return 1;
  }
  std::cout << "  origin      region " << start.node.region() << "  node " << start.node.value
            << "  " << int(start.metres) << " m off\n"
            << "  destination region " << target.node.region() << "  node " << target.node.value
            << "  " << int(target.metres) << " m off\n";

  std::priority_queue<QItem, std::vector<QItem>, std::greater<QItem>> open;
  std::unordered_map<uint64_t, double> g;
  std::unordered_map<uint64_t, Step> came;
  g[start.node.value] = 0.0;
  open.push({start.ll.Distance(dest), 0.0, start.node.value});

  size_t settled = 0, portal_crossings = 0;
  bool found = false;
  const size_t kCap = 4000000;

  while (!open.empty()) {
    QItem cur = open.top();
    open.pop();
    auto it = g.find(cur.node);
    if (it == g.end() || cur.g > it->second) {
      continue; // a better path to this node was already settled
    }
    if (cur.node == target.node.value) {
      found = true;
      break;
    }
    if (++settled > kCap) {
      std::cout << "  search capped at " << kCap << " nodes\n";
      break;
    }

    const GraphId node(cur.node);
    auto tile = reader.GetGraphTile(node);
    if (!tile) {
      continue;
    }
    const auto* ni = tile->node(node.id());

    auto relax = [&](GraphId next, double weight, Step::Kind kind) {
      const double ng = cur.g + weight;
      auto f = g.find(next.value);
      if (f != g.end() && f->second <= ng) {
        return;
      }
      g[next.value] = ng;
      came[next.value] = {cur.node, kind};
      // The heuristic needs the successor's position, which lives in ITS tile, not this one.
      auto ntile = reader.GetGraphTile(next);
      double h = 0.0;
      if (ntile) {
        h = ntile->node(next.id())->latlng(ntile->header()->base_ll()).Distance(dest);
      }
      open.push({ng + h, ng, next.value});
    };

    for (uint32_t i = 0; i < ni->edge_count(); ++i) {
      const auto* de = tile->directededge(ni->edge_index() + i);
      if (de->is_shortcut()) {
        continue;
      }
      if (!(de->forwardaccess() & kAutoAccess)) {
        continue;
      }
      // Re-tag: an endnode in the tile bytes has no idea which namespace it was loaded into.
      relax(de->endnode().with_region(node.region()), de->length(), Step::kEdge);
    }
    for (uint32_t i = 0; i < ni->transition_count(); ++i) {
      const auto* tr = tile->transition(ni->transition_index() + i);
      relax(tr->endnode().with_region(node.region()), 0.0, Step::kTransition);
    }
    auto pit = portal_index.find(cur.node);
    if (pit != portal_index.end()) {
      for (const Portal* p : pit->second) {
        relax(p->to, p->distance, Step::kPortal);
      }
    }
  }

  if (!found) {
    std::cout << "NO ROUTE  (settled " << settled << " nodes)\n";
    return 1;
  }

  // Walk the path back, counting what it is made of and where it changed namespace.
  std::vector<uint64_t> path;
  for (uint64_t n = target.node.value;;) {
    path.push_back(n);
    auto it = came.find(n);
    if (it == came.end()) {
      break;
    }
    if (it->second.kind == Step::kPortal) {
      ++portal_crossings;
    }
    n = it->second.from;
  }
  std::reverse(path.begin(), path.end());

  std::cout << "ROUTE FOUND   " << (g[target.node.value] / 1000.0) << " km   " << path.size()
            << " nodes   settled " << settled << "   portal crossings " << portal_crossings
            << "\n";

  // Where, exactly, the search changed namespace -- the line that distinguishes a composed search
  // from a lucky overlap.
  for (size_t i = 1; i < path.size(); ++i) {
    const GraphId a(path[i - 1]), b(path[i]);
    if (a.region() != b.region()) {
      auto ta = reader.GetGraphTile(a);
      auto tb = reader.GetGraphTile(b);
      const PointLL pa = ta->node(a.id())->latlng(ta->header()->base_ll());
      const PointLL pb = tb->node(b.id())->latlng(tb->header()->base_ll());
      std::cout << "   crossed region " << a.region() << " -> " << b.region() << " at " << pa.lat()
                << ", " << pa.lng() << "  ->  " << pb.lat() << ", " << pb.lng() << "\n";
    }
  }
  return 0;
}
