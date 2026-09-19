"""WeDrive patch 29: НАЧАЛЬНЫЙ startnode в TripLegBuilder::Build.

Патч 24 протегировал startnode там, где он переносится из итерации в итерацию:

    startnode = directededge->endnode().with_region(graphtile->id().region());

но его ПЕРВОЕ значение вычисляется раньше и отдельно:

    GraphId startnode =
        first_tile->directededge(first_node->edge_index() + first_edge->opp_index())->endnode();

и региона не несло. Дальше по нему выбирается тайл — берётся каталог по умолчанию, а индекс
приходит из другого графа. Поэтому падали ровно те маршруты, у которых origin в НЕ-дефолтном
регионе: «внутри Румынии» и «Яссы -> Кишинёв», тогда как «Кишинёв -> Яссы» уже проходил.

Это третья по счёту ошибка одного вида в моих же патчах: протегировано место, где переменная
обновляется, и пропущено место, где она рождается.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/triplegbuilder.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE initial startnode keeps region"
OLD = """  GraphId startnode =
      first_tile->directededge(first_node->edge_index() + first_edge->opp_index())->endnode();"""
NEW = """  // WEDRIVE initial startnode keeps region: первое значение startnode, по которому дальше
  // выбирается тайл. Патч 24 протегировал только его обновление в цикле.
  GraphId startnode = first_tile->directededge(first_node->edge_index() + first_edge->opp_index())
                          ->endnode()
                          .with_region(first_tile->id().region());"""

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
print("      %s оба места startnode тегированы"
      % ("ok     " if s.count("startnode") >= 2 and "with_region(first_tile->id().region())" in s
                      and "with_region(graphtile->id().region())" in s else "MISSING"))
