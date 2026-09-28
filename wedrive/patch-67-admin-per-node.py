"""WeDrive patch 67: страна узла — по полигону, а не «единственный полигон тайла».

GraphBuilder (src/mjolnir/graphbuilder.cc) присваивал admin так:

    admin_index = (admin_polys.size() == 1) ? admin_polys.begin()->first
                                            : GetMultiPolyId(admin_polys, node_ll, graphtile);

то есть если тайл пересекается РОВНО С ОДНИМ полигоном, страну этого полигона получают ВСЕ узлы
тайла без проверки, лежит ли узел внутри. Для планеты это экономия. Для нашей схемы это ошибка:
граф страны собирается с admin-базой, знающей только эту страну, и у пограничного тайла полигон
почти всегда один — поэтому узлы ЗА границей (полоса экстракта Geofabrik) тоже становятся
«своими», у рёбер через границу концы не расходятся по стране, и frontier_dump их не видит.

Измерено 2026-09-28 на прогоне всей Европы (regional-factory 36347575798): пустой frontier у LU,
NL, NO, RU, MK, AD, LI, MC; частичный у ME (2 узла), SI (6), XK (12), AL (17). Локально на LU:
admin-полигон точный (5.736..6.531 / 49.448..50.183), а valhalla_build_statistics видит ВСЕ рёбра
графа, включая полосу в DE/FR/BE, как LU; frontier_dump: nodes 213809, frontier 0.

Исправление общее, без исключений по странам: узел всегда проверяется по полигону
(GetMultiPolyId возвращает 0 = «без страны», если узел вне всех полигонов). Критерий frontier_dump
не меняется — у ребра концы расходятся по стране, и теперь это действительно так на границе.
Маршрутизацию не затрагивает: только построение тайлов.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/mjolnir/graphbuilder.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE admin per node"
OLD = ("          admin_index = (admin_polys.size() == 1) ? admin_polys.begin()->first\n"
       "                                                  : GetMultiPolyId(admin_polys, node_ll, graphtile);\n")
NEW = ("          // " + NAME + ": always by polygon (patch 67); a lone polygon of the tile no longer\n"
       "          // claims the nodes beyond the border, which is what hid every frontier node there\n"
       "          admin_index = GetMultiPolyId(admin_polys, node_ll, graphtile);\n")

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    if n != 1:
        raise SystemExit("patch 67: ожидал 1 совпадение, нашёл %d" % n)
    s = s.replace(OLD, NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      ok   %s" % NAME)
