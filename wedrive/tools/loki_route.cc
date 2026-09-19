// WeDrive: полная цепочка координаты -> Loki -> tagged PathEdges -> multi-region Thor -> path.
//
// До сих пор кандидаты строились вручную из ближайшего узла: это доказывало Thor, но обходило
// вопрос, умеет ли обычный запрос координатами вообще попасть в нужный регион. Здесь работает
// НАСТОЯЩИЙ loki::Search.
//
// Правило, которое здесь реализовано:
//
//     координата -> ВСЕ регионы, покрывающие точку -> кандидаты каждого -> tagged GraphId
//                -> общий набор -> Thor решает по стоимости
//
// В зоне перекрытия нельзя заранее объявить точку принадлежащей одному региону. Если её
// покрывают два графа, возвращаются кандидаты обоих, и выбор делает поиск, а не привязка.
//
// Loki при этом НЕ ПАТЧЕН ни на строку: он запускается по разу на регион внутри
// GraphReader::RegionScope, каждый проход видит ровно один граф, а тегирование результатов —
// забота этого файла.
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
#include <valhalla/baldr/location.h>
#include <valhalla/baldr/pathlocation.h>
#include <valhalla/loki/search.h>
#include <valhalla/midgard/pointll.h>
#include <valhalla/proto/api.pb.h>
#include <valhalla/sif/costfactory.h>
#include <valhalla/thor/bidirectional_astar.h>
#include <valhalla/worker.h>

using namespace valhalla;
using namespace valhalla::baldr;
using namespace valhalla::midgard;

namespace {

struct Cand {
  GraphId id;
  double percent_along;
  PointLL ll;
  double distance;
  bool begin_node;
  bool end_node;
  uint32_t region;
};

// Кандидаты ИЗ ВСЕХ регионов, покрывающих точку. Регион не выбирается заранее.
std::vector<Cand> SearchAllRegions(GraphReader& reader,
                                   const std::vector<uint32_t>& regions,
                                   const PointLL& p,
                                   const sif::cost_ptr_t& costing,
                                   std::vector<uint32_t>* regions_hit) {
  std::vector<Cand> out;
  for (uint32_t region : regions) {
    // Один проход = один граф. Внутри scope нетегнутые id, которые строит Loki, относятся
    // именно к этому региону.
    GraphReader::RegionScope scope(region);

    // loki::Search — КЛАСС, и работает он с baldr::Location, а не с protobuf-овским.
    const baldr::Location bl(p, baldr::Location::StopType::BREAK);
    const std::vector<baldr::Location> locs{bl};

    std::unordered_map<baldr::Location, baldr::PathLocation> found;
    try {
      loki::Search searcher(reader);
      found = searcher.search(locs, costing);
    } catch (const std::exception&) {
      continue; // регион не покрывает точку — нормальный ответ, а не ошибка
    }
    if (found.empty()) {
      continue;
    }
    const PathLocation& pl = found.begin()->second;
    if (pl.edges.empty()) {
      continue;
    }
    if (regions_hit) {
      regions_hit->push_back(region);
    }
    for (const auto& e : pl.edges) {
      // ТЕГ. Loki вернул id без региона — он его и не знает. Регион берётся из прохода.
      out.push_back({e.id.with_region(region), e.percent_along, e.projected, e.distance,
                     e.begin_node(), e.end_node(), region});
    }
  }
  // Ближе к точке — раньше в списке, как это делает и сам Loki.
  std::sort(out.begin(), out.end(),
            [](const Cand& a, const Cand& b) { return a.distance < b.distance; });
  return out;
}

valhalla::Location ToLocation(const PointLL& p, const std::vector<Cand>& cands) {
  valhalla::Location loc;
  loc.mutable_ll()->set_lat(static_cast<float>(p.lat()));
  loc.mutable_ll()->set_lng(static_cast<float>(p.lng()));
  for (const auto& c : cands) {
    auto* pe = loc.mutable_correlation()->add_edges();
    pe->set_graph_id(c.id.value); // весь 64-битный id, регион вместе с ним
    pe->set_percent_along(c.percent_along);
    pe->mutable_ll()->set_lat(static_cast<float>(c.ll.lat()));
    pe->mutable_ll()->set_lng(static_cast<float>(c.ll.lng()));
    pe->set_distance(c.distance);
    pe->set_begin_node(c.begin_node);
    pe->set_end_node(c.end_node);
    pe->set_outbound_reach(100);
    pe->set_inbound_reach(100);
  }
  return loc;
}

size_t LoadPortals(GraphReader& reader, const std::string& path) {
  std::ifstream in(path);
  if (!in) {
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

std::string RegionList(const std::vector<uint32_t>& v) {
  if (v.empty()) {
    return "нет";
  }
  std::ostringstream os;
  for (size_t i = 0; i < v.size(); ++i) {
    os << (i ? "+" : "") << v[i];
  }
  return os.str();
}

} // namespace

int main(int argc, char** argv) {
  if (argc < 7) {
    std::cerr << "usage: " << argv[0]
              << " <dir1> <dir2> <olat> <olon> <dlat> <dlon> [portal-table]\n";
    return 2;
  }
  std::cout << std::unitbuf;
  const std::string dir1 = argv[1], dir2 = argv[2];
  const PointLL origin_ll(std::stod(argv[4]), std::stod(argv[3]));
  const PointLL dest_ll(std::stod(argv[6]), std::stod(argv[5]));

  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", dir1);
  conf.put("mjolnir.max_cache_size", 3ull * 1024 * 1024 * 1024);
  GraphReader reader(conf.get_child("mjolnir"));
  reader.AddRegion(1, dir1);
  reader.AddRegion(2, dir2);
  GraphReader::WeDriveResetRegionLost();

  size_t portals = 0;
  if (argc > 7) {
    portals = LoadPortals(reader, argv[7]);
  }
  std::cout << "регионов " << reader.RegionCount() << "   порталов " << reader.PortalCount()
            << " (загружено " << portals << ")\n";

  Api api;
  valhalla::ParseApi(
      R"({"locations":[{"lat":47.0,"lon":28.0},{"lat":47.1,"lon":28.1}],"costing":"auto"})",
      Options::route, api);
  Options& options = *api.mutable_options();
  sif::CostFactory factory;
  sif::TravelMode travel_mode;
  sif::mode_costing_t mode_costing = factory.CreateModeCosting(options, travel_mode);
  const sif::cost_ptr_t costing = mode_costing[static_cast<size_t>(travel_mode)];

  const std::vector<uint32_t> regions{1, 2};
  std::vector<uint32_t> o_hit, d_hit;
  const auto o_cands = SearchAllRegions(reader, regions, origin_ll, costing, &o_hit);
  const auto d_cands = SearchAllRegions(reader, regions, dest_ll, costing, &d_hit);

  std::cout << "  origin      кандидатов " << o_cands.size() << "   из регионов "
            << RegionList(o_hit) << "\n"
            << "  destination кандидатов " << d_cands.size() << "   из регионов "
            << RegionList(d_hit) << "\n";

  if (o_cands.empty() || d_cands.empty()) {
    std::cout << "NO ROUTE: Loki не нашёл кандидатов\n";
    return 1;
  }

  valhalla::Location origin = ToLocation(origin_ll, o_cands);
  valhalla::Location dest = ToLocation(dest_ll, d_cands);

  thor::BidirectionalAStar astar;
  auto paths = astar.GetBestPath(origin, dest, reader, mode_costing, travel_mode, options);

  const uint64_t lost = GraphReader::WeDriveRegionLost();
  if (paths.empty() || paths.front().empty()) {
    std::cout << "NO ROUTE   (region lost: " << lost << ")\n";
    return 1;
  }

  const auto& path = paths.front();
  size_t switches = 0;
  uint32_t prev = GraphId(path.front().edgeid).region();
  for (const auto& p : path) {
    const uint32_t r = GraphId(p.edgeid).region();
    if (r != prev) {
      ++switches;
      prev = r;
    }
  }
  std::cout << "МАРШРУТ НАЙДЕН   " << (path.back().path_distance / 1000.0) << " км   "
            << path.back().elapsed_cost.secs << " с   " << path.size() << " рёбер   смен региона "
            << switches << "\n"
            << "   region lost: " << lost << (lost == 0 ? "   OK" : "   <<< ПОТЕРЯ") << "\n";
  return 0;
}
