// WeDrive: шорткаты, проложенные СКВОЗЬ пограничный пост.
//
// Расследование +2.8 % на Кишинёв -> Бухарест сошлось сюда. Штраф за пересечение границы
// начисляется не ребру, а УЗЛУ:
//
//     c += country_crossing_cost_ * (node->type() == kBorderControl);   // dynamiccost.h
//
// Стоимость шортката — это стоимость его рёбер; переходы во внутренних узлах в неё не входят
// никогда. Значит шорткат, накрывающий пограничный пост, прячет от поиска 600 секунд, и recost
// предъявляет их только на уже выбранном пути.
//
// Почему монолит этим не страдает, видно в mjolnir/shortcutbuilder.cc, CanContract:
//
//     // ISO country codes at the end nodes must equal this node
//     if (e1_iso != iso || e2_iso != iso) return false;
//
// В когерентной сборке по обе стороны поста лежат РАЗНЫЕ страны, и стяжка запрещена. В сборке
// одной страны соседа в admin-базе нет вовсе, и этот запрет не срабатывает.
//
// Программа считает это напрямую: для каждого шортката тайла восстанавливает его рёбра и
// смотрит тип каждого внутреннего узла. Печатает, сколько шорткатов накрывают пост.
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <valhalla/baldr/graphconstants.h>
#include <valhalla/baldr/graphid.h>
#include <valhalla/baldr/graphreader.h>
#include <valhalla/baldr/graphtile.h>
#include <valhalla/baldr/tilehierarchy.h>

using namespace valhalla::baldr;

int main(int argc, char** argv) {
  if (argc < 2) {
    std::printf("usage: border_shortcut <config.json> [level]\n");
    return 1;
  }
  boost::property_tree::ptree cfg;
  boost::property_tree::read_json(argv[1], cfg);
  GraphReader reader(cfg.get_child("mjolnir"));

  const uint32_t want_level = (argc > 2) ? std::stoul(argv[2]) : 1u;

  // Окно вокруг перехода Леушень-Албица: сравниваем графы по одному и тому же месту.
  const double lo_lat = (argc > 3) ? std::stod(argv[3]) : 46.7;
  const double hi_lat = (argc > 4) ? std::stod(argv[4]) : 46.95;
  const double lo_lon = (argc > 5) ? std::stod(argv[5]) : 28.0;
  const double hi_lon = (argc > 6) ? std::stod(argv[6]) : 28.3;

  size_t shortcuts = 0, spanning = 0, unrecovered = 0, posts_total = 0;
  size_t nodes_border = 0;

  for (const auto& level : TileHierarchy::levels()) {
    if (level.level != want_level) {
      continue;
    }
    for (auto tile_id : reader.GetTileSet(level.level)) {
      auto tile = reader.GetGraphTile(tile_id);
      if (!tile) {
        continue;
      }
      const uint32_t n = tile->header()->directededgecount();
      for (uint32_t i = 0; i < n; ++i) {
        GraphId eid = tile->id();
        eid.set_id(i);
        const DirectedEdge* de = tile->directededge(eid);
        if (!de->is_shortcut()) {
          continue;
        }
        ++shortcuts;
        auto rec = reader.RecoverShortcut(eid);
        if (rec.size() == 1 && rec.front() == eid) {
          ++unrecovered;
          continue;
        }
        // Внутренние узлы шортката: конец каждого восстановленного ребра, кроме последнего.
        size_t posts = 0;
        for (size_t k = 0; k + 1 < rec.size(); ++k) {
          graph_tile_ptr t = tile;
          const DirectedEdge* inner = reader.directededge(rec[k], t);
          if (!inner) {
            continue;
          }
          graph_tile_ptr nt = t;
          const NodeInfo* ni = reader.GetEndNode(inner, nt);
          if (ni && ni->type() == NodeType::kBorderControl) {
            ++posts;
          }
        }
        if (posts) {
          ++spanning;
          posts_total += posts;
          // Координата поста нужна, чтобы сравнивать графы по МЕСТУ, а не по счётчику.
          for (size_t k = 0; k + 1 < rec.size(); ++k) {
            graph_tile_ptr t = tile;
            const DirectedEdge* inner = reader.directededge(rec[k], t);
            if (!inner) {
              continue;
            }
            graph_tile_ptr nt = t;
            const NodeInfo* ni = reader.GetEndNode(inner, nt);
            if (ni && ni->type() == NodeType::kBorderControl && nt) {
              const auto ll = ni->latlng(nt->header()->base_ll());
              if (ll.lat() > lo_lat && ll.lat() < hi_lat && ll.lng() > lo_lon &&
                  ll.lng() < hi_lon) {
                std::printf("  пост НАКРЫТ шорткатом: %.5f,%.5f  шорткат id=%u длина=%u рёбер=%zu\n",
                            ll.lat(), ll.lng(), eid.id(), de->length(), rec.size());
              }
            }
          }
        }
      }
    }
  }

  // Сколько пограничных постов вообще есть на этом уровне — иначе ноль накрытых ничего не значит.
  for (const auto& level : TileHierarchy::levels()) {
    if (level.level != want_level) {
      continue;
    }
    for (auto tile_id : reader.GetTileSet(level.level)) {
      auto tile = reader.GetGraphTile(tile_id);
      if (!tile) {
        continue;
      }
      const uint32_t nn = tile->header()->nodecount();
      for (uint32_t i = 0; i < nn; ++i) {
        const NodeInfo* ni = tile->node(i);
        if (ni->type() != NodeType::kBorderControl) {
          continue;
        }
        ++nodes_border;
        const auto ll = ni->latlng(tile->header()->base_ll());
        if (ll.lat() > lo_lat && ll.lat() < hi_lat && ll.lng() > lo_lon && ll.lng() < hi_lon) {
          std::printf("  пост в окне: %.5f,%.5f  рёбер у узла %u\n", ll.lat(), ll.lng(),
                      ni->edge_count());
        }
      }
    }
  }

  std::printf("уровень %u: шорткатов %zu, не восстановлено %zu\n", want_level, shortcuts,
              unrecovered);
  std::printf("  пограничных постов на уровне: %zu\n", nodes_border);
  std::printf("  шорткатов СКВОЗЬ пост: %zu (постов накрыто %zu)\n", spanning, posts_total);
  return 0;
}
