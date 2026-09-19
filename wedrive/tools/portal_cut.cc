// WeDrive: production-таблица порталов по ЛИНИИ РАЗРЕЗА, а не по полосе перекрытия.
//
// Эксперимент показал, почему «все совпадающие узлы в полосе» — неверная модель границы:
// в километровой полосе 5158 совпадающих пар на level 2, и почти все они ВНУТРЕННИЕ узлы,
// у которых обе копии эквивалентны. Переход в таком узле не добавляет связности, он только
// удваивает состояние поиска — отсюда 5 смен региона подряд на одном участке дороги и
// 297 км вместо 279.
//
// Портал нужен ровно там, где дорожная связь ПЕРЕСЕКАЕТ линию раздела: узел по одну сторону,
// его сосед по другую. Таких мест на порядки меньше, и каждое из них — настоящий переход.
//
// Здесь линия задана широтой, потому что искусственный разрез Молдовы сделан по широте. Для
// государственной границы линия берётся из admin-полигона; критерий тот же и код тот же.
#include <algorithm>
#include <cmath>
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

// Узлы региона, у которых ЕСТЬ ребро через линию разреза.
std::unordered_map<uint64_t, Cand> CrossingNodes(GraphReader& reader,
                                                 uint32_t region,
                                                 uint8_t level,
                                                 double cut_lat,
                                                 double band,
                                                 double minlon,
                                                 double maxlon) {
  std::unordered_map<uint64_t, Cand> out;
  const auto& tiles = TileHierarchy::levels()[level].tiles;
  const int32_t lo = tiles.TileId(PointLL(minlon, cut_lat - band));
  const int32_t hi = tiles.TileId(PointLL(maxlon, cut_lat + band));
  const int32_t cols = tiles.ncolumns();
  for (int32_t r = lo / cols; r <= hi / cols; ++r) {
    for (int32_t c = lo % cols; c <= hi % cols; ++c) {
      const int32_t tid = r * cols + c;
      if (tid < 0) {
        continue;
      }
      GraphId base(static_cast<uint32_t>(tid), level, 0);
      auto tile = reader.GetGraphTile(base.with_region(region));
      if (!tile) {
        continue;
      }
      const auto tbase = tile->header()->base_ll();
      for (uint32_t i = 0; i < tile->header()->nodecount(); ++i) {
        const auto* n = tile->node(i);
        if (!Drivable(tile, n)) {
          continue;
        }
        const PointLL ll = n->latlng(tbase);
        if (std::fabs(ll.lat() - cut_lat) > band) {
          continue;
        }
        // Есть ли у узла сосед по ДРУГУЮ сторону линии?
        bool crosses = false;
        for (uint32_t e = 0; e < n->edge_count() && !crosses; ++e) {
          const auto* de = tile->directededge(n->edge_index() + e);
          if (de->is_shortcut() || !(de->forwardaccess() & kAutoAccess)) {
            continue;
          }
          const GraphId end = de->endnode().with_region(region);
          auto etile = reader.GetGraphTile(end);
          if (!etile) {
            continue;
          }
          const PointLL ell = etile->node(end)->latlng(etile->header()->base_ll());
          crosses = (ll.lat() - cut_lat) * (ell.lat() - cut_lat) < 0.0;
        }
        if (crosses) {
          out[Key(ll)] = {GraphId(static_cast<uint32_t>(tid), level, i).with_region(region), ll};
        }
      }
    }
  }
  return out;
}

} // namespace

int main(int argc, char** argv) {
  if (argc < 8) {
    std::cerr << "usage: " << argv[0]
              << " <dirA> <dirB> <cut_lat> <band_deg> <minlon> <maxlon> <level>\n";
    return 2;
  }
  const std::string dira = argv[1], dirb = argv[2];
  const double cut_lat = std::stod(argv[3]);
  const double band = std::stod(argv[4]);
  const double minlon = std::stod(argv[5]), maxlon = std::stod(argv[6]);
  const uint8_t level = static_cast<uint8_t>(std::stoi(argv[7]));

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", dira);
  conf.put("mjolnir.max_cache_size", 3ull * 1024 * 1024 * 1024);
  GraphReader reader(conf.get_child("mjolnir"));
  reader.AddRegion(1, dira);
  reader.AddRegion(2, dirb);

  const auto a = CrossingNodes(reader, 1, level, cut_lat, band, minlon, maxlon);
  const auto b = CrossingNodes(reader, 2, level, cut_lat, band, minlon, maxlon);

  size_t pairs = 0;
  for (const auto& [k, ca] : a) {
    auto f = b.find(k);
    if (f == b.end()) {
      continue; // связь пересекает линию, но второй граф этого узла не знает
    }
    std::printf("%llu %llu 0   # %.6f, %.6f\n",
                static_cast<unsigned long long>(ca.node.value),
                static_cast<unsigned long long>(f->second.node.value), ca.ll.lat(), ca.ll.lng());
    std::printf("%llu %llu 0   # %.6f, %.6f\n",
                static_cast<unsigned long long>(f->second.node.value),
                static_cast<unsigned long long>(ca.node.value), ca.ll.lat(), ca.ll.lng());
    ++pairs;
  }
  std::cerr << "# level " << int(level) << "   узлов со связью через разрез: A " << a.size()
            << "  B " << b.size() << "   парных порталов " << pairs << "\n";
  return 0;
}
