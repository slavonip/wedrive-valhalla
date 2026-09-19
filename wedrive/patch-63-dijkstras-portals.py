"""WeDrive patch 63: порталы и регион в обходе Dijkstras (изолинии).

Изолиния — четвёртая самостоятельная реализация обхода после Thor, Meili и CostMatrix. Внутри
региона она уже совпадала с монолитом точка в точку (2988 против 2988), а у границы контур
обрезался по Пруту: от самого перехода монолит давал долготы 27.932..28.656, композит —
28.140..28.656. Чистейший симптом отсутствия портала.

Три правки, все уже знакомого вида:

1. РЕГИОН на сборке идентификатора из составляющих:

       GraphId edgeid = {node.tileid(), node.level(), nodeinfo->edge_index()};

2. РЕГИОН на переходе между уровнями: trans->endnode() уходит рекурсивным вызовом как узел.

3. ПОРТАЛ, и здесь повторяется урок патча 53. Порталы лежат на уровне 0 (14 пар) и уровне 2
   (2 пары), а на уровень 0 обход попадает ТОЛЬКО через NodeTransition. Закрыть блок порталов
   тем же флагом from_transition означало бы снова спрятать все четырнадцать пар. Запретов два
   и они независимы, значит и флагов два.

Новый параметр объявлен со значением по умолчанию, поэтому существующие места вызова остаются
нетронутыми; явные инстанцирования шаблона перечисляют типы и правятся вместе с объявлением.
"""
import io
import os

SRC = "/src/valhalla"
H = os.path.join(SRC, "valhalla/thor/dijkstras.h")
C = os.path.join(SRC, "src/thor/dijkstras.cc")

NAME = "WEDRIVE dijkstras portals"

h = io.open(H, encoding="utf-8").read()
c = io.open(C, encoding="utf-8").read()

# --- объявление -----------------------------------------------------------------------------
H_OLD = (
    "                   const baldr::DirectedEdge* opp_pred_edge,\n"
    "                   const bool from_transition,\n"
    "                   const baldr::TimeInfo& time_info);\n"
)
H_NEW = (
    "                   const baldr::DirectedEdge* opp_pred_edge,\n"
    "                   const bool from_transition,\n"
    "                   const baldr::TimeInfo& time_info,\n"
    "                   // WEDRIVE dijkstras portals: второй запрет, независимый от первого —\n"
    "                   // порталы уровня 0 достижимы ТОЛЬКО через переход между уровнями.\n"
    "                   const bool from_portal = false);\n"
)

# --- определение ----------------------------------------------------------------------------
DEF_OLD = (
    "                            const bool from_transition,\n"
    "                            const baldr::TimeInfo& time_info) {\n"
)
DEF_NEW = (
    "                            const bool from_transition,\n"
    "                            const baldr::TimeInfo& time_info,\n"
    "                            const bool from_portal) {\n"
)

# --- явные инстанцирования ------------------------------------------------------------------
INST_OLD = (
    "    const baldr::DirectedEdge* opp_pred_edge,\n"
    "    const bool from_transition,\n"
    "    const baldr::TimeInfo& time_info);\n"
)
INST_NEW = (
    "    const baldr::DirectedEdge* opp_pred_edge,\n"
    "    const bool from_transition,\n"
    "    const baldr::TimeInfo& time_info,\n"
    "    const bool from_portal);\n"
)

# --- регион на сборке id --------------------------------------------------------------------
EID_OLD = "  GraphId edgeid = {node.tileid(), node.level(), nodeinfo->edge_index()};\n"
EID_NEW = (
    "  // WEDRIVE dijkstras region: сборка из составляющих теряет namespace, а edgeid здесь\n"
    "  // выбирает тайл и уходит в метки.\n"
    "  GraphId edgeid =\n"
    "      GraphId(node.tileid(), node.level(), nodeinfo->edge_index()).with_region(node.region());\n"
)

# --- переход и портал -----------------------------------------------------------------------
TR_OLD = (
    "  if (!from_transition && nodeinfo->transition_count() > 0) {\n"
    "    const baldr::NodeTransition* trans = tile->transition(nodeinfo->transition_index());\n"
    "    for (uint32_t i = 0; i < nodeinfo->transition_count(); ++i, ++trans) {\n"
    "      ExpandInner<expansion_direction>(graphreader, trans->endnode(), pred, pred_idx, opp_pred_edge,\n"
    "                                       true, offset_time);\n"
    "    }\n"
    "  }\n"
)
TR_NEW = (
    "  if (!from_transition && nodeinfo->transition_count() > 0) {\n"
    "    const baldr::NodeTransition* trans = tile->transition(nodeinfo->transition_index());\n"
    "    for (uint32_t i = 0; i < nodeinfo->transition_count(); ++i, ++trans) {\n"
    "      // WEDRIVE dijkstras region: переход между уровнями region не меняет — это тот же\n"
    "      // граф, — но endnode прочитан из тайла и namespace не несёт.\n"
    "      ExpandInner<expansion_direction>(graphreader,\n"
    "                                       trans->endnode().with_region(node.region()), pred,\n"
    "                                       pred_idx, opp_pred_edge, true, offset_time, from_portal);\n"
    "    }\n"
    "  }\n"
    "\n"
    "  // WEDRIVE dijkstras portals: единственный способ сменить регион. Флаг from_portal, а не\n"
    "  // from_transition: порталы уровня 0 достижимы только через переход, и общий флаг спрятал\n"
    "  // бы их все.\n"
    "  if (!from_portal) {\n"
    "    if (const auto* wd_portals = graphreader.PortalsAt(node)) {\n"
    "      for (const auto& wd_portal : *wd_portals) {\n"
    "        ExpandInner<expansion_direction>(graphreader, wd_portal.to, pred, pred_idx,\n"
    "                                         opp_pred_edge, false, offset_time, true);\n"
    "      }\n"
    "    }\n"
    "  }\n"
)

if NAME in c:
    print("      ok   уже применено: %s" % NAME)
else:
    assert h.count(H_OLD) == 1, "не нашёл объявление ExpandInner"
    assert c.count(DEF_OLD) == 1, "не нашёл определение ExpandInner"
    assert c.count(INST_OLD) == 2, "ожидал два явных инстанцирования, нашёл %d" % c.count(INST_OLD)
    assert c.count(EID_OLD) == 1, "не нашёл сборку edgeid"
    assert c.count(TR_OLD) == 1, "не нашёл блок переходов"
    io.open(H, "w", encoding="utf-8").write(h.replace(H_OLD, H_NEW))
    c = (c.replace(DEF_OLD, DEF_NEW)
          .replace(INST_OLD, INST_NEW)
          .replace(EID_OLD, EID_NEW)
          .replace(TR_OLD, TR_NEW))
    io.open(C, "w", encoding="utf-8").write(c)
    print("      +    %s" % NAME)

h = io.open(H, encoding="utf-8").read()
c = io.open(C, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    (h, "параметр объявлен со значением по умолчанию", "const bool from_portal = false);", True),
    (c, "определение принимает параметр", "const bool from_portal) {", True),
    (c, "оба инстанцирования обновлены", "    const bool from_portal);", True),
    (c, "регион на edgeid", ".with_region(node.region());", True),
    (c, "регион на переходе", "trans->endnode().with_region(node.region())", True),
    (c, "раскрытие порталов", "graphreader.PortalsAt(node)", True),
    # Проверка нарочно узкая: ExpandForwardMultiModal — отдельная функция транзита, её
    # нетегированный переход остаётся и это НЕ упущение. Мультимодальный обход в multi-region
    # не переносился вовсе, о чём сказано и в самом файле.
    (c, "нетегированного перехода в ExpandInner не осталось",
     "ExpandInner<expansion_direction>(graphreader, trans->endnode(), pred", False),
    (c, "мультимодальный переход не тронут", "ExpandForwardMultiModal(graphreader, trans->endnode()", True),
)
for text, label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in text) == want else "MISSING", label))
print("      %s инстанцирований с новым параметром: %d"
      % ("ok     " if c.count("    const bool from_portal);") == 2 else "MISSING",
         c.count("    const bool from_portal);")))
