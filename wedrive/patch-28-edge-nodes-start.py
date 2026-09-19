"""WeDrive patch 28: start_node в GetDirectedEdgeNodes. Исправляет ошибку патча 12.

В патче 12 я протегировал end_node и оставил рядом комментарий:

    start_node внутри t2 не тегируем: индексация внутри уже правильного тайла

Это неверно. `start_node` не остаётся внутри функции — он ВОЗВРАЩАЕТСЯ наружу, и вызывающий по
нему выбирает тайл. Скажем, GetTimezoneFromEdge делает ровно это:

    auto nodes = GetDirectedEdgeNodes(edge, tile);
    if (const auto* node = nodeinfo(nodes.first, tile))   // <- выбор тайла по start_node

Без региона брался каталог по умолчанию с индексом из другого графа, и весь маршрут падал на
этапе определения часового пояса — даже маршрут целиком внутри Румынии.

Уточнение к правилу, которое стоило двух ошибок подряд (эта и патч 27):

    id остаётся ВНУТРИ функции   -> тегировать безопасно и нужно, если по нему выбирается тайл
    id УХОДИТ НАРУЖУ             -> тег становится частью контракта; тегировать нужно, только
                                    если наружу он тоже используется для выбора тайла, и НЕ
                                    нужно, если его сравнивают с нетегнутыми (патч 27)

Здесь именно первый случай второго рода: наружу и для выбора тайла.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/baldr/graphreader.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE start node keeps region"
OLD = "    start_node = t2->directededge(edge_idx)->endnode();"
NEW = ("    // WEDRIVE start node keeps region: возвращается НАРУЖУ, и вызывающий выбирает по нему\n"
       "    // тайл (например GetTimezoneFromEdge). Патч 12 ошибочно счёл его внутренним.\n"
       "    start_node = t2->directededge(edge_idx)->endnode().with_region(t2->id().region());")

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
print("      %s оба узла пары тегированы"
      % ("ok     " if "edge->endnode().with_region(wedrive_region)" in s
                      and "endnode().with_region(t2->id().region())" in s else "MISSING"))
