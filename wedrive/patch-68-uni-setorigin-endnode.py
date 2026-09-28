"""WeDrive patch 68: SetOrigin однонаправленного A* — endnode без региона (то, что патч 11 сделал
для двунаправленного).

UnidirectionalAStar::SetOrigin (FORWARD) брал тайл конечного узла исходного ребра так:

    const auto endtile = graphreader.GetGraphTile(directededge->endnode());
    if (endtile == nullptr) continue;

directededge->endnode() прочитан из байтов тайла, у него нет региона. Без региона GraphReader идёт в
каталог ПО УМОЛЧАНИЮ (mjolnir.tile_dir), а фабрика ставит туда первую страну набора по алфавиту.

Найдено 2026-09-28 на прогоне всей Европы (regional-factory 36347575798): «AT внутри: Вена (Пенцинг) -
Вена (Фаворитен)» — нет маршрута, REGION LOST x6, при 14512 принятых порталах. Доказательство на одном
наборе AT+CZ+HU+SI+SK, меняя только mjolnir.tile_dir: AT -> 15.468 км; CZ -> 0; HU -> 0. Стек
детектора: UnidirectionalAStar<Forward, true>::GetBestPath (SetOrigin встроен), алгоритм
time_dependent_forward_a*. Первое расхождение: тайл уровня 2 795665 (Вена) ищется в каталоге по
умолчанию; есть он только у AT, в наборе из пяти стран первой по алфавиту была AT (совпадение), в
наборе из 32 — AL, тайла нет, все исходные рёбра пропускаются, пути нет.

Исправление — то же, что в патче 11: регион берётся у edgeid, полученного из корреляции Location.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/unidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE uni SetOrigin endnode region"
OLD = ("      const auto endtile = graphreader.GetGraphTile(directededge->endnode());\n"
       "      if (endtile == nullptr) {\n"
       "        continue;\n"
       "      }\n"
       "      endpoint = endtile->get_node_ll(directededge->endnode());\n")
NEW = ("      // " + NAME + ": endnode из байтов тайла, регион у edgeid (patch 68, как patch 11).\n"
       "      const GraphId endnode = directededge->endnode().with_region(edgeid.region());\n"
       "      const auto endtile = graphreader.GetGraphTile(endnode);\n"
       "      if (endtile == nullptr) {\n"
       "        continue;\n"
       "      }\n"
       "      endpoint = endtile->get_node_ll(endnode);\n")

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    if n != 1:
        raise SystemExit("patch 68: ожидал 1 совпадение, нашёл %d" % n)
    s = s.replace(OLD, NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      ok   %s" % NAME)
