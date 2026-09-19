// WeDrive: маршрут через НАСТОЯЩИЙ Thor (BidirectionalAStar) + настоящий Sif (auto costing)
// по нескольким независимо собранным графам, соединённым внешней таблицей порталов.
//
// Отличие от compose_route.cc принципиальное: там был собственный A* по расстоянию, здесь —
// штатный двунаправленный поиск Valhalla со штатной стоимостью по времени, поворотными
// штрафами, ограничениями и иерархией уровней. Если это работает, значит работает не игрушка.
//
// Программа также печатает счётчик GraphReader::WeDriveRegionLost(): сколько раз тайл
// запрашивался по id, у которого регион потерян. Ноль — обязательное условие зелёного теста.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <boost/property_tree/ptree.hpp>
#include <valhalla/baldr/graphconstants.h>
#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/baldr/graphtile.h>
#include <valhalla/baldr/tilehierarchy.h>
#include <valhalla/midgard/pointll.h>
#include <valhalla/proto/api.pb.h>
#include <valhalla/sif/costfactory.h>
#include <valhalla/thor/bidirectional_astar.h>
#include <valhalla/worker.h>

using namespace valhalla;
using namespace valhalla::baldr;
using namespace valhalla::midgard;

namespace {

struct Snap {
  GraphId node;
  PointLL ll;
  double metres;
};

// Ближайший узел, на котором может стоять АВТОМОБИЛЬ. Узел с любым ребром не годится: в Унгенах
// это оказалась пешеходная дорожка, и маршрут внутри одной страны отчитался как NO ROUTE.
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
          auto tile = reader.GetGraphTile(GraphId(static_cast<uint32_t>(tid), level, 0)
                                              .with_region(region));
          if (!tile) {
            continue;
          }
          const auto base = tile->header()->base_ll();
          for (uint32_t i = 0; i < tile->header()->nodecount(); ++i) {
            const auto* n = tile->node(i);
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
              best = {GraphId(static_cast<uint32_t>(tid), level, i).with_region(region), ll, d};
            }
          }
        }
      }
    }
  }
  return best;
}

// Location с уже готовой корреляцией. Loki мы не трогаем — он про регионы не знает, и учить его
// это отдельная работа; здесь кандидаты строятся прямо из найденного узла, с ТЕГНУТЫМИ id.
// Кандидаты как их отдаёт loki для точки посреди улицы: percent_along = 0.5 на ребре И на
// противоположном ему. Первые две версии ставили точку НА УЗЕЛ (percent_along 0 или 1) — и
// обратное дерево двунаправленного поиска исчерпывалось на восьмом узле даже на цельной
// одно-региональной Молдове. Это был дефект стенда, а не рантайма, и он в точности изображал
// из себя тот дефект, который стенд обязан ловить.
valhalla::Location MakeLoc(GraphReader& reader, const Snap& s) {
  valhalla::Location loc;
  loc.mutable_ll()->set_lat(static_cast<float>(s.ll.lat()));
  loc.mutable_ll()->set_lng(static_cast<float>(s.ll.lng()));
  auto tile = reader.GetGraphTile(s.node);
  const auto* ni = tile->node(s.node);
  auto add = [&](const GraphId& id, const DirectedEdge* de) {
    if (de->is_shortcut() || !(de->forwardaccess() & kAutoAccess)) {
      return;
    }
    auto* pe = loc.mutable_correlation()->add_edges();
    pe->set_graph_id(id.value);
    pe->set_percent_along(0.5);
    pe->mutable_ll()->set_lat(static_cast<float>(s.ll.lat()));
    pe->mutable_ll()->set_lng(static_cast<float>(s.ll.lng()));
    pe->set_distance(0.0);
    pe->set_outbound_reach(100);
    pe->set_inbound_reach(100);
  };
  for (uint32_t i = 0; i < ni->edge_count(); ++i) {
    const GraphId eid =
        GraphId(s.node.tileid(), s.node.level(), ni->edge_index() + i).with_region(s.node.region());
    const auto* de = tile->directededge(ni->edge_index() + i);
    if (de->is_shortcut()) {
      continue;
    }
    add(eid, de);
    graph_tile_ptr opp_tile;
    const GraphId opp = reader.GetOpposingEdgeId(eid, opp_tile);
    if (opp.is_valid() && opp_tile) {
      add(opp, opp_tile->directededge(opp));
    }
  }
  return loc;
}

size_t LoadPortals(GraphReader& reader, const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    std::cerr << "не могу прочитать таблицу порталов " << path << "\n";
    return 0;
  }
  std::string line;
  size_t n = 0;
  while (std::getline(in, line)) {
    const auto hash = line.find('#');
    if (hash != std::string::npos) {
      line.erase(hash);
    }
    std::istringstream ls(line);
    uint64_t from = 0, to = 0;
    double d = 0.0;
    if (ls >> from >> to >> d) {
      reader.AddPortal(GraphId(from), GraphId(to), static_cast<float>(d));
      ++n;
    }
  }
  return n;
}

} // namespace

int main(int argc, char** argv) {
  if (argc < 8) {
    std::cerr << "usage: " << argv[0]
              << " <dir1> <dir2> <olat> <olon> <dlat> <dlon> <r1|r2|both|both+portal>"
                 " [portal-table]\n";
    return 2;
  }
  // Без этого abort() съедает буфер и падение выглядит так, будто программа не стартовала.
  std::cout << std::unitbuf;
  const std::string dir1 = argv[1], dir2 = argv[2];
  const PointLL origin_ll(std::stod(argv[4]), std::stod(argv[3]));
  const PointLL dest_ll(std::stod(argv[6]), std::stod(argv[5]));
  const std::string mode = argv[7];

  std::vector<uint32_t> regions;
  bool want_portals = false;
  bool two = true;
  if (mode == "r1") {
    regions = {1};
    two = false;
  } else if (mode == "r2") {
    regions = {2};
    two = false;
  } else if (mode == "both") {
    regions = {1, 2};
  } else if (mode == "both+portal") {
    regions = {1, 2};
    want_portals = true;
  } else {
    std::cerr << "неизвестный режим " << mode << "\n";
    return 2;
  }

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", dir1);
  conf.put("mjolnir.max_cache_size", 3ull * 1024 * 1024 * 1024);
  GraphReader reader(conf.get_child("mjolnir"));
  // В одно-региональном режиме регистрируем ровно один регион, иначе детектор потери региона
  // ругался бы на совершенно законный stock-путь.
  if (two) {
    reader.AddRegion(1, dir1);
    reader.AddRegion(2, dir2);
  } else {
    reader.AddRegion(regions.front(), regions.front() == 1 ? dir1 : dir2);
  }
  GraphReader::WeDriveResetRegionLost();

  size_t portals = 0;
  if (want_portals) {
    if (argc > 8) {
      portals = LoadPortals(reader, argv[8]);
    } else {
      // Два экземпляра одного и того же перекрёстка Leuseni/Albita на E581.
      reader.AddPortal(GraphId(70384118415618ULL), GraphId(140758264856834ULL), 0.0f);
      reader.AddPortal(GraphId(140758264856834ULL), GraphId(70384118415618ULL), 0.0f);
      portals = 2;
    }
  }

  std::cout << "режим " << mode << "   регионов " << reader.RegionCount() << "   порталов "
            << reader.PortalCount() << " (в файле " << portals << ", отвергнуто " << reader.PortalsRejected() << ")\n";

  const Snap so = NearestNode(reader, regions, origin_ll);
  const Snap sd = NearestNode(reader, regions, dest_ll);
  if (!so.node.is_valid() || so.metres > 2000.0) {
    std::cout << "NO ROUTE: origin не привязался (ближайший узел " << int(so.metres) << " м)\n";
    return 1;
  }
  if (!sd.node.is_valid() || sd.metres > 2000.0) {
    std::cout << "NO ROUTE: destination не привязался (ближайший узел " << int(sd.metres)
              << " м)\n";
    return 1;
  }
  std::cout << "  origin      регион " << so.node.region() << "  " << int(so.metres) << " м\n"
            << "  destination регион " << sd.node.region() << "  " << int(sd.metres) << " м\n";

  // Costing строим ЧЕРЕЗ ParseApi, а не руками. Первая версия делала
  //     options.set_costing_type(auto); factory.Create(options);
  // и получала костинг БЕЗ дефолтных опций Sif: скорости, факторы и штрафы оставались
  // нулевыми. Маршрут при этом находился, что и делало ошибку опасной — он просто был
  // ДРУГОЙ: 137.8 км вместо 109.3 на Кишинёв-Унгены и 1.56e+07 секунд на четыре километра.
  // Цифры, полученные так, нельзя было бы сравнивать ни с upstream, ни между собой.
  Api api;
  valhalla::ParseApi(
      R"({"locations":[{"lat":47.0,"lon":28.0},{"lat":47.1,"lon":28.1}],"costing":"auto"})",
      Options::route, api);
  Options& options = *api.mutable_options();
  sif::CostFactory factory;
  sif::TravelMode travel_mode;
  sif::mode_costing_t mode_costing = factory.CreateModeCosting(options, travel_mode);

  valhalla::Location origin = MakeLoc(reader, so);
  valhalla::Location dest = MakeLoc(reader, sd);
  std::cout << "  кандидатов: origin " << origin.correlation().edges_size()
            << ", destination " << dest.correlation().edges_size() << std::endl;

  thor::BidirectionalAStar astar;
  auto paths = astar.GetBestPath(origin, dest, reader, mode_costing, travel_mode, options);

  const uint64_t lost = GraphReader::WeDriveRegionLost();
  if (paths.empty() || paths.front().empty()) {
    std::cout << "NO ROUTE   (region lost: " << lost << ")\n";
    return 1;
  }

  const auto& path = paths.front();
  size_t switches = 0;
  uint32_t prev_region = GraphId(path.front().edgeid).region();
  for (const auto& p : path) {
    const uint32_t r = GraphId(p.edgeid).region();
    if (r != prev_region) {
      ++switches;
      prev_region = r;
    }
  }

  // НЕПРЕРЫВНОСТЬ через портал: конец ребра ДО перехода и начало ребра ПОСЛЕ должны быть
  // одной и той же физической точкой. Если это не так, «маршрут» склеен из двух кусков,
  // которые нигде не встречаются — то есть телепорт, а не дорога.
  auto node_ll = [&](const GraphId& id) {
    auto t = reader.GetGraphTile(id);
    return t ? t->node(id)->latlng(t->header()->base_ll()) : PointLL();
  };
  double worst_gap = 0.0;
  for (size_t i = 1; i < path.size(); ++i) {
    const GraphId prev(path[i - 1].edgeid), cur(path[i].edgeid);
    if (prev.region() == cur.region()) {
      continue;
    }
    auto tprev = reader.GetGraphTile(prev);
    const PointLL a =
        node_ll(tprev->directededge(prev)->endnode().with_region(prev.region()));
    graph_tile_ptr opp_tile;
    const GraphId opp = reader.GetOpposingEdgeId(cur, opp_tile);
    PointLL b;
    if (opp.is_valid() && opp_tile) {
      b = node_ll(opp_tile->directededge(opp)->endnode().with_region(opp.region()));
    }
    const double gap = a.Distance(b);
    worst_gap = std::max(worst_gap, gap);
    std::cout << "   переход регион " << prev.region() << " -> " << cur.region() << " в "
              << a.lat() << ", " << a.lng() << "  разрыв " << gap << " м" << std::endl;
  }
  if (switches > 0) {
    std::cout << "   НЕПРЕРЫВНОСТЬ: худший разрыв " << worst_gap << " м"
              << (worst_gap < 1.0 ? "   OK" : "   <<< РАЗРЫВ") << std::endl;
  }

  std::cout << "МАРШРУТ НАЙДЕН   " << (path.back().path_distance / 1000.0) << " км   "
            << path.back().elapsed_cost.secs << " с   " << path.size() << " рёбер   смен региона "
            << switches << "\n"
            << "   region lost: " << lost << (lost == 0 ? "   OK" : "   <<< ПОТЕРЯ РЕГИОНА")
            << "\n";
  return 0;
}
