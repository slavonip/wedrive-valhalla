"""WeDrive patch 27: GetEndNode — единственный из inline-хелперов, который нужно тегировать.

Backtrace на полном valhalla_service привёл сюда: recover_shortcut -> GetEndNode ->
GetGraphTile(edge->endnode(), tile). Тайл выбирается по нетегнутому endnode, то есть берётся
каталог по умолчанию, а индекс приходит из другого графа.

ВАЖНО, ЧТО СОСЕДНИЕ ХЕЛПЕРЫ ТРОГАТЬ НЕЛЬЗЯ. Первая версия этого патча тегировала заодно
GetOpposingEdge, GetBeginNodeId и edge_startnode — и Loki перестал находить кандидатов вообще,
«No suitable edges near location» даже на маршруте внутри одной страны, который до этого работал.
Причина в том, что эти три ВОЗВРАЩАЮТ идентификатор наружу, где он сравнивается с нетегнутым, а
GetEndNode возвращает указатель на NodeInfo и наружу ничего не отдаёт.

Отсюда уточнение к общему правилу: тегировать безопасно там, где id используется ВНУТРИ функции
для выбора тайла. Как только id уходит наружу, тег становится частью контракта, и менять его в
одиночку нельзя.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/baldr/graphreader.h")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE GetEndNode keeps region"

OLD = """    return GetGraphTile(edge->endnode(), end_node_tile) ? end_node_tile->node(edge->endnode())
                                                        : nullptr;"""
NEW = """    // WEDRIVE GetEndNode keeps region: регион у тайла, из которого пришло ребро — на входе
    // end_node_tile указывает именно на него. Наружу id не отдаётся, поэтому тег безопасен.
    const GraphId wd_end =
        edge->endnode().with_region(end_node_tile ? end_node_tile->id().region() : 0);
    return GetGraphTile(wd_end, end_node_tile) ? end_node_tile->node(wd_end) : nullptr;"""

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    assert n == 1, "ожидал 1 совпадение, нашёл %d" % n
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s GetOpposingEdge НЕ тронут"
      % ("ok     " if "if (GetGraphTile(edge->endnode(), opp_tile)) {" in s else "ТРОНУТ"))
print("      %s GetBeginNodeId НЕ тронут"
      % ("ok     " if "if (!GetGraphTile(edge->endnode(), maybe_other_tile))" in s else "ТРОНУТ"))
print("      %s edge_startnode НЕ тронут"
      % ("ok     " if "return opp_edge->endnode();" in s else "ТРОНУТ"))
