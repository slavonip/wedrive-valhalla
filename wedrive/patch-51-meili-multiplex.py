"""WeDrive patch 51: кандидаты Meili собираются по всем регионам.

Тот же приём, что уже применён к loki::Search в патче 23, и по той же причине: алгоритм поиска
не меняется ни на строку — меняется лишь то, сколько раз он вызван и что делается с ответом.

    for (region : RegionIds())
        RegionScope scope(region);
        candidatequery_.Query(...)      // стоковый вызов, видит один граф
        кандидаты складываются в общий список

Регион в перекрытии НЕ выбирается заранее: обе стороны границы попадают в один набор состояний,
и решает Витерби по стоимости — ровно как Thor решает по стоимости на маршруте.

Патч 50 обязателен до этого: сетка кандидатов кэшировалась по чистому bin_id, и multiplex поверх
неё возвращал бы сетку первого региона второму.

Регионов меньше двух — исполняется ровно прежняя строка, без единого отличия.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/map_matcher.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "  const auto& candidates =\n"
    "      candidatequery_.Query(measurement.lnglat(), measurement.stop_type(), sq_radius, costing());\n"
)

NEW = (
    "  // WEDRIVE meili multiplex: по разу на регион, кандидаты складываются вместе. Регион в\n"
    "  // перекрытии не выбирается заранее — обе стороны границы становятся состояниями, и\n"
    "  // выбирает Витерби по стоимости.\n"
    "  auto wedrive_query = [&]() {\n"
    "    if (graphreader_.RegionCount() < 2) {\n"
    "      return candidatequery_.Query(measurement.lnglat(), measurement.stop_type(), sq_radius,\n"
    "                                   costing());\n"
    "    }\n"
    "    std::vector<baldr::PathLocation> merged;\n"
    "    for (const uint32_t region : graphreader_.RegionIds()) {\n"
    "      baldr::GraphReader::RegionScope scope(region);\n"
    "      std::vector<baldr::PathLocation> found;\n"
    "      try {\n"
    "        found = candidatequery_.Query(measurement.lnglat(), measurement.stop_type(), sq_radius,\n"
    "                                      costing());\n"
    "      } catch (...) {\n"
    "        continue; // регион не покрывает точку — обычный ответ, а не ошибка\n"
    "      }\n"
    "      for (auto& pl : found) {\n"
    "        merged.push_back(std::move(pl));\n"
    "      }\n"
    "    }\n"
    "    return merged;\n"
    "  };\n"
    "  const auto candidates = wedrive_query();\n"
)

NAME = "WEDRIVE meili multiplex"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл вызов candidatequery_.Query"
    s = s.replace(OLD, NEW)
    if "#include <vector>" not in s:
        first = s.index("#include")
        s = s[:first] + "#include <vector> // WEDRIVE meili multiplex\n" + s[first:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("обход регионов", "for (const uint32_t region : graphreader_.RegionIds())", True),
    ("область видимости региона", "baldr::GraphReader::RegionScope scope(region);", True),
    ("стоковая ветка при одном регионе", "if (graphreader_.RegionCount() < 2)", True),
    ("прежний одиночный вызов убран", "const auto& candidates =\n      candidatequery_.Query", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
