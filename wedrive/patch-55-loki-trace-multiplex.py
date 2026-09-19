"""WeDrive patch 55: концы трассы тоже надо искать во всех регионах.

Детектор потери региона указал место сам — и не там, где я его искал. Стек первого же срабатывания:

    bin_handler_t::search
    valhalla::loki::Search::search
    valhalla::loki::loki_worker_t::locations_from_shape
    valhalla::loki::loki_worker_t::trace
    valhalla::tyr::actor_t::trace_route

То есть теряет регион не Meili, а Loki — на отдельном пути, который патч 23 не затронул. Патч 23
размножил по регионам `search_.search` в route_action.cc; у trace свой вызов в
trace_route_action.cc, и он остался одно-региональным:

    auto projections = search_.search(locations, costing);

Концы трассы — это origin и destination будущего маршрута. Для Кишинёв -> Яссы конец лежит в
Румынии, одно-региональный Loki его не находит, и запрос падает с 442 «No path could be found»,
сколько бы порталов ни было в таблице.

Тот же приём и та же форма, что в патче 23, чтобы не заводить второй диалект одного решения.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/loki/trace_route_action.cc")
s = io.open(P, encoding="utf-8").read()

OLD = "    auto projections = search_.search(locations, costing);\n"

NEW = """    // WEDRIVE loki trace multiplex: по разу на регион, как в route_action.cc. Регион в
    // перекрытии не выбирается заранее — концы трассы могут лежать в разных графах.
    auto wedrive_correlate = [&]() {
      if (reader->RegionCount() < 2) {
        return search_.search(locations, costing);
      }
      std::unordered_map<baldr::Location, baldr::PathLocation> merged;
      for (const uint32_t region : reader->RegionIds()) {
        baldr::GraphReader::RegionScope scope(region);
        loki::Search regional(*reader);
        std::unordered_map<baldr::Location, baldr::PathLocation> found;
        try {
          found = regional.search(locations, costing);
        } catch (...) {
          continue; // регион не покрывает точку — обычный ответ, а не ошибка
        }
        for (auto& kv : found) {
          auto it = merged.find(kv.first);
          if (it == merged.end()) {
            it = merged.emplace(kv.first, baldr::PathLocation(kv.first)).first;
          }
          // Тег: Loki отдаёт id без региона, он о нём не знает.
          for (auto& e : kv.second.edges) {
            e.id = e.id.with_region(region);
            it->second.edges.push_back(e);
          }
          for (auto& e : kv.second.filtered_edges) {
            e.id = e.id.with_region(region);
            it->second.filtered_edges.push_back(e);
          }
        }
      }
      // Ближе к точке — раньше, как это делает и сам Loki.
      for (auto& kv : merged) {
        std::stable_sort(kv.second.edges.begin(), kv.second.edges.end(),
                         [](const baldr::PathLocation::PathEdge& a,
                            const baldr::PathLocation::PathEdge& b) {
                           return a.distance < b.distance;
                         });
      }
      return merged;
    };
    auto projections = wedrive_correlate();
"""

NAME = "WEDRIVE loki trace multiplex"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл search_.search в locations_from_shape"
    s = s.replace(OLD, NEW)
    if "#include <algorithm>" not in s:
        first = s.index("#include")
        s = s[:first] + "#include <algorithm> // WEDRIVE loki trace multiplex\n" + s[first:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("RegionScope используется", "baldr::GraphReader::RegionScope scope(region);", True),
    ("кандидаты тегируются", "e.id = e.id.with_region(region);", True),
    ("стоковая ветка при одном регионе", "return search_.search(locations, costing);", True),
    ("прежний одиночный вызов убран", "auto projections = search_.search(locations, costing);", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
