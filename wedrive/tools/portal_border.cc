// WeDrive: порталы на ФАКТИЧЕСКИХ пересечениях государственной границы.
//
// Таблица «все совпадающие узлы в зоне перекрытия» даёт корректные маршруты, но отвратительную
// топологию: Кишинёв -> Яссы переключался между графами 63 раза. Каждая копия одного и того же
// перекрёстка существует в обоих namespace, переход бесплатен, и поиску незачем оставаться на
// месте. Для production нужна одна физическая граница = обычно одна смена региона.
//
// КРИТЕРИЙ ИЗ ДАННЫХ, а не из внешнего полигона. Тайлы несут admin-информацию, и каждый граф
// видит ТОЛЬКО свою страну: при сборке Молдовы admin-база покрывала Молдову, поэтому узлы за
// Прутом получили admin_index 0 — «страна не определена». Измерено на тайле 788512:
//
//     молдавский граф   2893 узла: 2805 MD, 88 без страны
//     румынский граф    1278 узлов: 1013 RO, 265 без страны
//
// Значит ребро, у которого один конец имеет СВОЮ страну, а другой — нет, буквально пересекает
// государственную границу. Никакой геометрии границы искать не нужно.
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

std::string Country(const graph_tile_ptr& tile, const NodeInfo* n) {
  const uint32_t idx = n->admin_index();
  if (idx >= tile->header()->admincount()) {
    return std::string();
  }
  return tile->admininfo(idx).country_iso();
}

struct Cand {
  GraphId node;
  PointLL ll;
};

// Узлы региона, инцидентные ребру, которое пересекает границу СВОЕЙ страны.
std::unordered_map<uint64_t, Cand> BorderNodes(GraphReader& reader,
                                               uint32_t region,
                                               uint8_t level,
                                               double minlat,
                                               double minlon,
                                               double maxlat,
                                               double maxlon,
                                               size_t* edges_seen) {
  std::unordered_map<uint64_t, Cand> out;
  const auto& tiles = TileHierarchy::levels()[level].tiles;
  const int32_t lo = tiles.TileId(PointLL(minlon, minlat));
  const int32_t hi = tiles.TileId(PointLL(maxlon, maxlat));
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
        const std::string here = Country(tile, n);
        const PointLL ll = n->latlng(tbase);
        if (ll.lat() < minlat || ll.lat() > maxlat || ll.lng() < minlon || ll.lng() > maxlon) {
          continue;
        }
        for (uint32_t e = 0; e < n->edge_count(); ++e) {
          const auto* de = tile->directededge(n->edge_index() + e);
          if (de->is_shortcut() || !(de->forwardaccess() & kAutoAccess)) {
            continue;
          }
          const GraphId end = de->endnode().with_region(region);
          auto etile = reader.GetGraphTile(end);
          if (!etile || end.id() >= etile->header()->nodecount()) {
            continue;
          }
          const std::string there = Country(etile, etile->node(end.id()));
          // Страна меняется — включая переход в «страна не определена», который в этом графе
          // и означает «за пределами собранной страны».
          if (here != there) {
            ++(*edges_seen);
            out[Key(ll)] = {GraphId(static_cast<uint32_t>(tid), level, i).with_region(region), ll};
            break;
          }
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
              << " <dirA> <dirB> <minlat> <minlon> <maxlat> <maxlon> <level>"
              << " [regionA=1] [regionB=2]\n";
    return 2;
  }
  const std::string dira = argv[1], dirb = argv[2];
  const double minlat = std::stod(argv[3]), minlon = std::stod(argv[4]);
  const double maxlat = std::stod(argv[5]), maxlon = std::stod(argv[6]);
  const uint8_t level = static_cast<uint8_t>(std::stoi(argv[7]));
  // Номера регионов — у каждой границы свои. MD=1, RO=2, HU=3: таблица RO-HU
  // строится с парой 2 и 3, и зашитые 1/2 пометили бы венгерские узлы чужим
  // namespace.
  const uint32_t region_a = (argc > 8) ? std::stoul(argv[8]) : 1u;
  const uint32_t region_b = (argc > 9) ? std::stoul(argv[9]) : 2u;

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", dira);
  conf.put("mjolnir.max_cache_size", 3ull * 1024 * 1024 * 1024);
  GraphReader reader(conf.get_child("mjolnir"));
  reader.AddRegion(region_a, dira);
  reader.AddRegion(region_b, dirb);

  size_t ea = 0, eb = 0;
  const auto a = BorderNodes(reader, region_a, level, minlat, minlon, maxlat, maxlon, &ea);
  const auto b = BorderNodes(reader, region_b, level, minlat, minlon, maxlat, maxlon, &eb);

  size_t pairs = 0;
  for (const auto& [k, ca] : a) {
    auto f = b.find(k);
    if (f == b.end()) {
      continue; // граница видна одному графу, но второй этого узла не знает
    }
    std::printf("%llu %llu 0   # %.6f, %.6f\n",
                static_cast<unsigned long long>(ca.node.value),
                static_cast<unsigned long long>(f->second.node.value), ca.ll.lat(), ca.ll.lng());
    std::printf("%llu %llu 0   # %.6f, %.6f\n",
                static_cast<unsigned long long>(f->second.node.value),
                static_cast<unsigned long long>(ca.node.value), ca.ll.lat(), ca.ll.lng());
    ++pairs;
  }
  std::cerr << "# level " << int(level) << "  регионы " << region_a << "/" << region_b
            << "   пограничных узлов: A " << a.size() << "  B "
            << b.size() << "   парных порталов " << pairs << "\n";
  return 0;
}
