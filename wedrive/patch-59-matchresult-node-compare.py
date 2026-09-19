"""WeDrive patch 59: сравнение узлов в привязке результата к кандидату.

Зонд стадий снял с маршрутизации все подозрения разом: 653 поиска между состояниями, НОЛЬ пустых,
и ровно те же числа во всех трёх режимах — один регион, два региона с тегом, два региона без
тега. Маршруты находятся всегда; теряется привязка найденного маршрута к кандидату.

В FindMatchResult, в ветке «кандидат стоит на перекрёстке», сравниваются два узла из разных
пространств имён:

    auto candidate_nodes = graph_reader.GetDirectedEdgeNodes(edge.id, tile);  // С РЕГИОНОМ
    ...
    const auto* prev_de = graph_reader.directededge(prev_edge, tile);
    if (prev_de && prev_de->endnode() == candidate_node) {                    // БЕЗ РЕГИОНА

GetDirectedEdgeNodes регион сохраняет ещё с патчей 12 и 28, а endnode() читается из тайла как
есть. При одном регионе оба нуля и равенство работает; при двух кандидат помечен единицей, а
endnode остаётся нулём — равенство не наступает НИКОГДА. Кандидат на перекрёстке не опознаётся,
и точка уходит в несопоставленные.

Отсюда и характер поломки, который сбивал с толку: отказы рассыпаны по всему маршруту в местах,
где привязка попадает на узел, а не в середину ребра, и к границе отношения не имеют вовсе.

Сравнивать надо в одном пространстве имён. Встречное ребро живёт в том же графе, что и прямое,
поэтому его endnode берёт регион своего ребра.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/map_matcher.cc")
s = io.open(P, encoding="utf-8").read()

PREV_OLD = (
    "    const auto* prev_de = graph_reader.directededge(prev_edge, tile);\n"
    "    if (prev_de && prev_de->endnode() == candidate_node) {\n"
)
PREV_NEW = (
    "    // WEDRIVE matchresult region: candidate_node пришёл из GetDirectedEdgeNodes с тегом,\n"
    "    // а endnode() читается из тайла без него. Сравнивать их можно только в одном\n"
    "    // пространстве имён, иначе при двух регионах равенство не наступает никогда.\n"
    "    const auto* prev_de = graph_reader.directededge(prev_edge, tile);\n"
    "    if (prev_de && prev_de->endnode().with_region(prev_edge.region()) == candidate_node) {\n"
)

NEXT_OLD = (
    "    const auto* next_opp_de = graph_reader.GetOpposingEdge(next_edge, tile);\n"
    "    if (next_opp_de && next_opp_de->endnode() == candidate_node) {\n"
)
NEXT_NEW = (
    "    // WEDRIVE matchresult region: то же самое со стороны следующего ребра. Встречное\n"
    "    // ребро лежит в том же графе, поэтому регион берётся у next_edge.\n"
    "    const auto* next_opp_de = graph_reader.GetOpposingEdge(next_edge, tile);\n"
    "    if (next_opp_de && next_opp_de->endnode().with_region(next_edge.region()) == candidate_node) {\n"
)

NAME = "WEDRIVE matchresult region"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("предыдущее ребро", PREV_OLD), ("следующее ребро", NEXT_OLD)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    io.open(P, "w", encoding="utf-8").write(s.replace(PREV_OLD, PREV_NEW).replace(NEXT_OLD, NEXT_NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("маркер", NAME, True),
    ("сравнение со стороны предыдущего", "prev_de->endnode().with_region(prev_edge.region()) == candidate_node", True),
    ("сравнение со стороны следующего", "next_opp_de->endnode().with_region(next_edge.region()) == candidate_node", True),
    ("нетегированных сравнений не осталось", "prev_de->endnode() == candidate_node", False),
    ("нетегированных сравнений не осталось 2", "next_opp_de->endnode() == candidate_node", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
