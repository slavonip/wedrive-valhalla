"""WeDrive patch 58: встречное ребро-кандидат оставалось без региона.

Контроли сузили это до одной строки, и по дороге стенд дважды соврал — оба раза моими руками.

    один регион                       рёбер 702, несопоставлено 0
    два региона, второй ПУСТОЙ        рёбер 479, несопоставлено 76
    два региона, оба Молдова          рёбер 479, несопоставлено 76
    два региона, тег снят с кандидатов рёбер 702, несопоставлено 0

Пустой второй регион не даёт ни одного кандидата, а сопоставление всё равно портится. Значит
дело не во втором графе, а в том, что кандидаты стали ТЕГИРОВАННЫМИ. Снятие тега чинит.

Причина — половинчатость. Патч 50 пометил регионом рёбра, попадающие в сетку, а встречное ребро
добавляется в кандидаты отдельной строкой и приходит из GetOpposingEdgeId, который регион НЕ
ставит намеренно: патч 27 показал, что тег на нём ломает Loki целиком.

    correlated.edges.emplace_back(edgeid, dist, point, sq_distance);       // с регионом
    correlated.edges.emplace_back(opp_edgeid, dist, point, sq_distance);   // без региона

В результате edge_dests получает ключи обоих видов на одни и те же физические рёбра, а
расширение строит edgeid всегда с регионом и находит только половину. Назначение, записанное
под нетегированным ключом, не находится никогда — точка остаётся несопоставленной.

Встречное ребро лежит в ТОМ ЖЕ графе, что и прямое: сменить граф может только портал. Поэтому
тег берётся у edgeid, и это не противоречит патчу 27 — там речь о самом GetOpposingEdgeId,
который остаётся нетронутым, здесь же помечается локальная копия перед укладкой в кандидаты.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/candidate_search.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "    const auto opp_edgeid = reader_.GetOpposingEdgeId(edgeid, opp_edge, opp_tile);\n"
    "    if (!opp_edgeid.is_valid()) {\n"
    "      continue;\n"
    "    }\n"
)

NEW = (
    "    // WEDRIVE meili opposing candidate: встречное ребро лежит в ТОМ ЖЕ графе — сменить\n"
    "    // граф может только портал. GetOpposingEdgeId регион не ставит намеренно (патч 27:\n"
    "    // тег на нём ломает Loki), поэтому помечается локальная копия перед укладкой в\n"
    "    // кандидаты. Иначе половина кандидатов уходит без namespace, edge_dests получает\n"
    "    // ключи обоих видов, и расширение находит только половину назначений.\n"
    "    const auto opp_edgeid =\n"
    "        reader_.GetOpposingEdgeId(edgeid, opp_edge, opp_tile).with_region(edgeid.region());\n"
    "    if (!opp_edgeid.is_valid()) {\n"
    "      continue;\n"
    "    }\n"
)

NAME = "WEDRIVE meili opposing candidate"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл получение встречного ребра"
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("тег от прямого ребра", "GetOpposingEdgeId(edgeid, opp_edge, opp_tile).with_region(edgeid.region())", True),
    ("нетегированного получения не осталось",
     "const auto opp_edgeid = reader_.GetOpposingEdgeId(edgeid, opp_edge, opp_tile);", False),
    ("сам GetOpposingEdgeId не тронут", "reader_.GetOpposingEdgeId(", True),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
