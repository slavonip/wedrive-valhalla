// WeDrive: какие значения РЕАЛЬНО принимают поля, которые предлагается сузить.
//
// Для расширения region до 8 бит нужно пять бит внутри EdgeLabel, а он упакован без
// единого свободного. Кандидаты и основания:
//
//     opp_local_idx_ : 7   но kMaxLocalEdgeIndex = 7, то есть семантически хватает ТРЁХ бит
//     mode_          : 4   но TravelMode имеет пять значений (0..4), хватает трёх
//
// Первое — допущение о данных, и полагаться на константу из заголовка мало: важно, что
// лежит в тайлах. Программа обходит все рёбра всех уровней и печатает фактические максимумы.
// Если opp_local_idx хоть раз превысит 7, сужение до 3 бит недопустимо, и искать биты надо
// в другом месте.
#include <cstdint>
#include <cstdio>
#include <string>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <valhalla/baldr/graphconstants.h>
#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/baldr/graphtile.h>
#include <valhalla/baldr/tilehierarchy.h>

using namespace valhalla::baldr;

int main(int argc, char** argv) {
  if (argc < 2) {
    std::printf("usage: field_range <config.json>\n");
    return 1;
  }
  boost::property_tree::ptree cfg;
  boost::property_tree::read_json(argv[1], cfg);
  GraphReader reader(cfg.get_child("mjolnir"));

  uint32_t max_opp_local = 0, max_local = 0, max_opp_index = 0;
  uint64_t edges = 0, over7_opp_local = 0;

  for (const auto& level : TileHierarchy::levels()) {
    for (auto tile_id : reader.GetTileSet(level.level)) {
      if (reader.OverCommitted()) {
        reader.Trim();
      }
      auto tile = reader.GetGraphTile(tile_id);
      if (!tile) {
        continue;
      }
      const uint32_t n = tile->header()->directededgecount();
      for (uint32_t i = 0; i < n; ++i) {
        GraphId eid = tile->id();
        eid.set_id(i);
        const DirectedEdge* de = tile->directededge(eid);
        ++edges;
        const uint32_t o = de->opp_local_idx();
        const uint32_t l = de->localedgeidx();
        const uint32_t x = de->opp_index();
        if (o > max_opp_local) {
          max_opp_local = o;
        }
        if (l > max_local) {
          max_local = l;
        }
        if (x > max_opp_index) {
          max_opp_index = x;
        }
        if (o > 7) {
          ++over7_opp_local;
        }
      }
    }
  }

  std::printf("    рёбер обойдено: %llu\n", static_cast<unsigned long long>(edges));
  std::printf("    max opp_local_idx = %u   (kMaxLocalEdgeIndex = %u)\n", max_opp_local,
              kMaxLocalEdgeIndex);
  std::printf("    max localedgeidx  = %u\n", max_local);
  std::printf("    max opp_index     = %u   (kMaxEdgesPerNode = %u)\n", max_opp_index,
              kMaxEdgesPerNode);
  std::printf("    рёбер с opp_local_idx > 7: %llu\n",
              static_cast<unsigned long long>(over7_opp_local));
  std::printf("    вывод: три бита под opp_local_idx %s\n",
              (max_opp_local <= 7) ? "ДОСТАТОЧНО" : "НЕДОСТАТОЧНО");
  return (max_opp_local <= 7) ? 0 : 1;
}
