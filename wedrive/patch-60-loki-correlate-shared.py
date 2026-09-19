"""WeDrive patch 60: один multiplex Loki вместо трёх копий.

Детектор снова назвал место сам, и это оказался ТРЕТИЙ отдельный вызов поиска кандидатов:

    (anonymous namespace)::bin_handler_t::search
    valhalla::loki::Search::search
    valhalla::loki::loki_worker_t::matrix

Патч 23 размножил по регионам route_action, патч 55 — trace_route_action, и вот matrix_action.
Это и объясняет неверную матрицу: Кишинёв -> Яссы давал 111.578 км вместо 150.1, а цель
приснапливалась на 27.7375 вместо 27.6014 — то есть на молдавскую дорогу, потому что румынских
кандидатов одно-региональный Loki не находил вовсе.

Третью копию одного и того же кода я заводить не стал: тридцать строк, размноженные трижды,
расходятся при первой же правке. Общая реализация кладётся в valhalla/loki/search.h — его уже
включают все три файла — и все вызовы переводятся на неё, включая два уже работающих.

Поведение при одном регионе не меняется: RegionCount() < 2 исполняет ровно прежнюю строку.
"""
import io
import os

SRC = "/src/valhalla"
H = os.path.join(SRC, "valhalla/loki/search.h")
NAME = "WEDRIVE loki correlate"

HELPER = '''
/**
 * WEDRIVE loki correlate: поиск кандидатов по ВСЕМ зарегистрированным регионам.
 *
 * Stock Search запускается по разу на регион внутри RegionScope — каждый проход видит один
 * граф, — а результаты тегируются регионом своего прохода и складываются в общий набор. Сам
 * алгоритм Loki не меняется ни на строку: меняется лишь то, сколько раз он вызван и что
 * делается с ответом.
 *
 * В зоне перекрытия регион НЕ выбирается заранее: кандидаты обоих графов попадают в один
 * список, и решает уже поиск пути — по стоимости.
 *
 * Регионов меньше двух — исполняется ровно прежний одиночный вызов, без единого отличия.
 */
inline std::unordered_map<baldr::Location, baldr::PathLocation>
WeDriveCorrelate(baldr::GraphReader& reader,
                 Search& stock_search,
                 const std::vector<baldr::Location>& locations,
                 const sif::cost_ptr_t& costing) {
  if (reader.RegionCount() < 2) {
    return stock_search.search(locations, costing);
  }
  std::unordered_map<baldr::Location, baldr::PathLocation> merged;
  for (const uint32_t region : reader.RegionIds()) {
    baldr::GraphReader::RegionScope scope(region);
    Search regional(reader);
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
}

'''

ANCHOR = "} // namespace loki\n"

h = io.open(H, encoding="utf-8").read()
if NAME in h:
    print("      ok   уже применено: общий helper")
else:
    assert h.count(ANCHOR) == 1, "не нашёл конец namespace loki"
    assert h.count("#include <valhalla/sif/dynamiccost.h>") == 1, "не нашёл включения"
    h = h.replace("#include <valhalla/sif/dynamiccost.h>",
                  "#include <valhalla/sif/dynamiccost.h>\n\n#include <algorithm>\n#include <unordered_map>\n#include <vector>")
    io.open(H, "w", encoding="utf-8").write(h.replace(ANCHOR, HELPER + ANCHOR))
    print("      +    общий helper в search.h")

# --- три места вызова -----------------------------------------------------------------------
# Две встроенные копии (патчи 23 и 55) вырезаются целиком: блок начинается своим комментарием и
# заканчивается вызовом лямбды, поэтому границы однозначны и искать их по длинному тексту не надо.
def replace_block(path, first_line, last_line, new_text):
    s = io.open(path, encoding="utf-8").read()
    if "WeDriveCorrelate" in s:
        return None
    a = s.index(first_line)
    b = s.index(last_line, a) + len(last_line)
    return s[:a] + new_text + s[b:]


BLOCKS = (
    ("src/loki/route_action.cc",
     "    // WEDRIVE loki multiplex: по разу на регион, кандидаты складываются вместе.\n",
     "    const auto projections = wedrive_correlate();\n",
     "    // WEDRIVE loki correlate: общая реализация, одна на все три места вызова.\n"
     "    const auto projections = loki::WeDriveCorrelate(*reader, search_, locations, costing);\n"),
    ("src/loki/trace_route_action.cc",
     "    // WEDRIVE loki trace multiplex: по разу на регион, как в route_action.cc. Регион в\n",
     "    auto projections = wedrive_correlate();\n",
     "    // WEDRIVE loki correlate: общая реализация, одна на все три места вызова.\n"
     "    auto projections = loki::WeDriveCorrelate(*reader, search_, locations, costing);\n"),
)

for rel, first, last, new in BLOCKS:
    P = os.path.join(SRC, rel)
    out = replace_block(P, first, last, new)
    if out is None:
        print("      ok   уже применено: %s" % rel)
    else:
        io.open(P, "w", encoding="utf-8").write(out)
        print("      +    %s (встроенная копия убрана)" % rel)

CALLS = (
    # файл, что было, что стало
    ("src/loki/matrix_action.cc",
     "    const auto searched = search_.search(sources_targets, costing);\n",
     "    // WEDRIVE loki correlate: третий отдельный вызов поиска кандидатов, из-за которого\n"
     "    // матрица через границу считалась по одному графу.\n"
     "    const auto searched = loki::WeDriveCorrelate(*reader, search_, sources_targets, costing);\n"),
)

for rel, old, new in CALLS:
    P = os.path.join(SRC, rel)
    s = io.open(P, encoding="utf-8").read()
    if "WeDriveCorrelate" in s:
        print("      ok   уже применено: %s" % rel)
        continue
    assert s.count(old) == 1, "не нашёл вызов в %s" % rel
    io.open(P, "w", encoding="utf-8").write(s.replace(old, new))
    print("      +    %s" % rel)

print("\n   проверка:")
h = io.open(H, encoding="utf-8").read()
m = io.open(os.path.join(SRC, "src/loki/matrix_action.cc"), encoding="utf-8").read()
r = io.open(os.path.join(SRC, "src/loki/route_action.cc"), encoding="utf-8").read()
tr = io.open(os.path.join(SRC, "src/loki/trace_route_action.cc"), encoding="utf-8").read()
CHECKS = (
    (h, "helper объявлен", "WeDriveCorrelate(baldr::GraphReader& reader", True),
    (h, "стоковая ветка", "if (reader.RegionCount() < 2) {", True),
    (h, "область видимости региона", "baldr::GraphReader::RegionScope scope(region);", True),
    (m, "матрица переведена на helper", "loki::WeDriveCorrelate(*reader, search_, sources_targets", True),
    (m, "прежний одиночный вызов убран", "search_.search(sources_targets, costing)", False),
    (r, "маршрут переведён на helper", "loki::WeDriveCorrelate(*reader, search_, locations, costing)", True),
    (tr, "трасса переведена на helper", "loki::WeDriveCorrelate(*reader, search_, locations, costing)", True),
    (r, "встроенной копии в маршруте нет", "wedrive_correlate", False),
    (tr, "встроенной копии в трассе нет", "wedrive_correlate", False),
)
for text, label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in text) == want else "MISSING", label))
