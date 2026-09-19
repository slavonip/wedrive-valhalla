"""WeDrive patch 62: ExpandInner матрицы выбирал тайл по нетегированному endnode.

Патчи 60 и 61 починили кандидатов и раскрытие, но матрица через границу стала падать:

    GraphTile NodeInfo index out of bounds: 3111,0,23826 nodecount= 3330

Индекс узла за пределами тайла — классический признак того, что идентификатор одного графа
применён к тайлу другого: тайл 3111 уровня 0 существует в ОБОИХ регионах и содержит разное
число узлов.

Детектор назвал место по стеку, и это лямбда внутри ExpandInner:

    t2 = meta.edge->leaves_tile() ? graphreader.GetGraphTile(meta.edge->endnode()) : tile;
    opp_edge_id = t2->GetOpposingEdgeId(meta.edge);

endnode прочитан из тайла и namespace не несёт, а здесь он ВЫБИРАЕТ тайл — и следом по
чужому тайлу берётся встречное ребро. Регион берётся у ребра, которому endnode принадлежит:
ребро целиком лежит в своём графе, сменить граф может только портал.

Соседнее использование того же endnode в get_node_ll НЕ трогается: там он индексирует уже
выбранный тайл, а внутри выбранного тайла тег не нужен — ровно то различие, ради которого
инвариант и сформулирован.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/costmatrix.cc")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "    t2 = meta.edge->leaves_tile() ? graphreader.GetGraphTile(meta.edge->endnode()) : tile;\n"
)
NEW = (
    "    // WEDRIVE costmatrix region: endnode здесь ВЫБИРАЕТ тайл, значит обязан нести регион\n"
    "    // своего ребра. Без этого встречное ребро берётся по чужому тайлу и индекс узла\n"
    "    // уходит за его границы.\n"
    "    t2 = meta.edge->leaves_tile()\n"
    "             ? graphreader.GetGraphTile(\n"
    "                   meta.edge->endnode().with_region(meta.edge_id.region()))\n"
    "             : tile;\n"
)

NAME = "WEDRIVE costmatrix region: endnode здесь ВЫБИРАЕТ тайл"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл выбор тайла в лямбде"
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("выбор тайла тегирован", "meta.edge->endnode().with_region(meta.edge_id.region())", True),
    ("нетегированного выбора не осталось",
     "graphreader.GetGraphTile(meta.edge->endnode()) : tile;", False),
    ("индексация внутри тайла не тронута", "t2->get_node_ll(meta.edge->endnode())", True),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
