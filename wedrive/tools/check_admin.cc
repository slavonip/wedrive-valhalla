// Знают ли наши тайлы, в какой стране лежит узел?
//
// Если да, то настоящий погранпереход определяется буквально: ребро, соединяющее узлы РАЗНЫХ
// стран. Это и есть «фактическое пересечение государственной границы», и никакой геометрии
// границы искать не нужно. Если нет — придётся опираться на что-то другое.
#include <cstdint>
#include <iostream>
#include <map>
#include <string>

#include <boost/property_tree/ptree.hpp>
#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/baldr/graphtile.h>
#include <valhalla/baldr/tilehierarchy.h>
#include <valhalla/midgard/pointll.h>

using namespace valhalla::baldr;
using namespace valhalla::midgard;

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "usage: " << argv[0] << " <tile-dir> [lat lon]\n";
    return 2;
  }
  boost::property_tree::ptree conf;
  conf.put("mjolnir.tile_dir", argv[1]);
  conf.put("mjolnir.max_cache_size", 1024ull * 1024 * 1024);
  GraphReader reader(conf.get_child("mjolnir"));

  // Тайл вокруг перекрёстка Leuseni/Albita, где граница проходит заведомо.
  const double lat = argc > 3 ? std::stod(argv[2]) : 46.8233;
  const double lon = argc > 3 ? std::stod(argv[3]) : 28.1407;
  const auto& tiles = TileHierarchy::levels()[2].tiles;
  GraphId tid(static_cast<uint32_t>(tiles.TileId(PointLL(lon, lat))), 2, 0);
  auto tile = reader.GetGraphTile(tid);
  if (!tile) {
    std::cout << "тайла нет\n";
    return 1;
  }

  const auto* h = tile->header();
  std::cout << "тайл " << tid.tileid() << "   узлов " << h->nodecount() << "   admins "
            << h->admincount() << "\n";
  if (h->admincount() == 0) {
    std::cout << "AДМИНОВ НЕТ — тайлы собраны без admin-базы, страну узла не спросить\n";
    return 0;
  }

  for (uint32_t i = 0; i < h->admincount(); ++i) {
    const auto* a = tile->admin(i);
    std::cout << "   admin " << i << "  страна '" << tile->admininfo(i).country_iso() << "'  '"
              << tile->admininfo(i).state_iso() << "'\n";
    (void)a;
  }

  std::map<uint32_t, size_t> by_admin;
  for (uint32_t i = 0; i < h->nodecount(); ++i) {
    ++by_admin[tile->node(i)->admin_index()];
  }
  std::cout << "\nузлы по admin_index:\n";
  for (const auto& [idx, n] : by_admin) {
    std::cout << "   admin_index " << idx << "  узлов " << n << "  страна '"
              << (idx < h->admincount() ? tile->admininfo(idx).country_iso() : std::string("?"))
              << "'\n";
  }
  return 0;
}
