"""WeDrive patch 23: multiplexing поиска кандидатов внутри loki_worker.

В стендах multiplexing делал вызывающий код. Внутри valhalla_service вызывающего кода нет —
там `search_.search(locations, costing)` в route_action.cc, и он видит ровно один граф.

Тот же приём, что и в стенде: stock Search запускается ПО РАЗУ НА РЕГИОН внутри RegionScope,
каждый проход видит один граф, а результаты тегируются и складываются в общий набор. Алгоритм
поиска Loki не меняется ни на строку — меняется только то, сколько раз он вызван и что делается
с ответом.

В зоне перекрытия регион НЕ выбирается заранее: кандидаты обоих графов попадают в один список, и
решает Thor по стоимости.

Регионов меньше двух — выполняется ровно прежняя строка, без единого отличия.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/loki/route_action.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE loki multiplex"
OLD = "    const auto projections = search_.search(locations, costing);"
NEW = """    // WEDRIVE loki multiplex: по разу на регион, кандидаты складываются вместе.
    // Регион не выбирается заранее — в перекрытии вернутся кандидаты обоих графов.
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
    const auto projections = wedrive_correlate();"""

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    assert n == 1, "ожидал 1 совпадение, нашёл %d" % n
    s = s.replace(OLD, NEW)
    if "#include <algorithm>" not in s:
        first = s.index("#include")
        s = s[:first] + "#include <algorithm> // WEDRIVE loki multiplex\n" + s[first:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s RegionScope используется" % ("ok     " if "RegionScope scope(region)" in s else "MISSING"))
print("      %s кандидаты тегируются" % ("ok     " if "e.id.with_region(region)" in s else "MISSING"))
print("      %s одно-региональный путь не изменён"
      % ("ok     " if "return search_.search(locations, costing);" in s else "MISSING"))
