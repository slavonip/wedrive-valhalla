"""WeDrive patch 47: порталы и регион в собственном поиске Meili.

Сопоставление трассы (map matching) не пользуется Thor. У Meili свой расширитель в
src/meili/routing.cc, и все патчи Thor его не касались вовсе. Измерено на трассе Кишинёв -> Яссы
в 770 точек, снятой с монолита:

    монолит    рёбер 1221, точек 770, все сопоставлены,            150.059 км
    composite  рёбер  761, сопоставлено 638, НЕ сопоставлено 132,  126.626 км
               первая несопоставленная точка #633: 47.31478,27.60826 — сам переход через Прут

Последняя точка сопоставлена, значит Loki кандидатов в Румынии находит. Ломается именно
маршрутизация между кандидатом MD и кандидатом RO: пути нет, цепочка Витерби рвётся, и точки
между ними отбрасываются.

Две правки в одном месте, обе того же вида, что уже сделаны в Thor:

1. РЕГИОН. Идентификатор ребра собирается из составляющих:

       baldr::GraphId edgeid = {node.tileid(), node.level(), nodeinfo->edge_index()};

   Такая сборка теряет namespace. То же с directededge->endnode(): он выбирает тайл и кладётся
   в labelset как узел для дальнейшего расширения — оба раза region обязателен. Третье
   использование, get_node_ll, индексирует уже выбранный тайл, и там тег безразличен.

2. ПОРТАЛ. Блок рядом с NodeTransition, ровно как в Thor: из узла раскрываются ещё и его
   порталы. Флаг from_transition у рекурсивного вызова не даёт уйти по порталам дальше одного
   прыжка, и это то же правило, по которому portal раскрывается в Thor — один переход, затем
   обычные рёбра.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/routing.cc")
s = io.open(P, encoding="utf-8").read()

# --- 1. region на edgeid -------------------------------------------------------------------
EDGEID_OLD = (
    "    baldr::GraphId edgeid = {node.tileid(), node.level(), nodeinfo->edge_index()};\n"
)
EDGEID_NEW = (
    "    // WEDRIVE meili region: сборка из составляющих теряет namespace, а edgeid здесь и\n"
    "    // выбирает тайл, и сверяется с ключами edge_dests, пришедшими из Loki с тегом.\n"
    "    baldr::GraphId edgeid =\n"
    "        baldr::GraphId(node.tileid(), node.level(), nodeinfo->edge_index())\n"
    "            .with_region(node.region());\n"
)

# --- 2. region на endnode ------------------------------------------------------------------
ENDTILE_OLD = (
    "      baldr::graph_tile_ptr endtile =\n"
    "          directededge->leaves_tile() ? reader.GetGraphTile(directededge->endnode()) : tile;\n"
)
ENDTILE_NEW = (
    "      // WEDRIVE meili region: endnode выбирает тайл и уходит в labelset как узел для\n"
    "      // следующего расширения, поэтому обязан нести регион своего ребра.\n"
    "      const baldr::GraphId wd_endnode = directededge->endnode().with_region(edgeid.region());\n"
    "      baldr::graph_tile_ptr endtile =\n"
    "          directededge->leaves_tile() ? reader.GetGraphTile(wd_endnode) : tile;\n"
)

PUT_OLD = (
    "          float sortcost = cost.cost + heuristic(endtile->get_node_ll(directededge->endnode()));\n"
    "          labelset->put(directededge->endnode(), edgeid, 0.0f, 1.0f, cost, turn_cost, sortcost,\n"
    "                        label_idx, directededge, travelmode, restriction_idx);\n"
)
PUT_NEW = (
    "          float sortcost = cost.cost + heuristic(endtile->get_node_ll(wd_endnode));\n"
    "          labelset->put(wd_endnode, edgeid, 0.0f, 1.0f, cost, turn_cost, sortcost,\n"
    "                        label_idx, directededge, travelmode, restriction_idx);\n"
)

# --- 3. раскрытие порталов -----------------------------------------------------------------
TRANS_OLD = (
    "    // Handle transitions - expand from the end node each transition\n"
    "    if (!from_transition && nodeinfo->transition_count() > 0) {\n"
    "      const baldr::NodeTransition* trans = tile->transition(nodeinfo->transition_index());\n"
    "      for (uint32_t i = 0; i < nodeinfo->transition_count(); ++i, ++trans) {\n"
    "        expand(trans->endnode(), label_idx, true);\n"
    "      }\n"
    "    }\n"
)
TRANS_NEW = TRANS_OLD + (
    "\n"
    "    // WEDRIVE meili portals: единственный способ сменить регион, тот же, что в Thor.\n"
    "    // from_transition у рекурсивного вызова ограничивает переход одним прыжком: дальше\n"
    "    // раскрываются обычные рёбра узла-близнеца, а не его собственные порталы.\n"
    "    if (!from_transition) {\n"
    "      if (const auto* portals = reader.PortalsAt(node)) {\n"
    "        for (const auto& portal : *portals) {\n"
    "          expand(portal.to, label_idx, true);\n"
    "        }\n"
    "      }\n"
    "    }\n"
)

NAME = "WEDRIVE meili portals"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("edgeid", EDGEID_OLD), ("endtile", ENDTILE_OLD), ("put", PUT_OLD),
                       ("transitions", TRANS_OLD)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    s = (s.replace(EDGEID_OLD, EDGEID_NEW)
          .replace(ENDTILE_OLD, ENDTILE_NEW)
          .replace(PUT_OLD, PUT_NEW)
          .replace(TRANS_OLD, TRANS_NEW))
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
for label, needle in (
        ("регион на edgeid", ".with_region(node.region());"),
        ("регион на endnode", "wd_endnode = directededge->endnode().with_region"),
        ("endnode в labelset", "labelset->put(wd_endnode, edgeid"),
        ("раскрытие порталов", "reader.PortalsAt(node)"),
        ("порталы ограничены одним прыжком", "expand(portal.to, label_idx, true);")):
    print("      %s %s" % ("ok     " if needle in s else "MISSING", label))
print("      %s старое нетегированное endnode не осталось в labelset"
      % ("ok     " if "labelset->put(directededge->endnode()" not in s else "MISSING"))
