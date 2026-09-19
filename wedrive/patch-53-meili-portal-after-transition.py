"""WeDrive patch 53: портал должен раскрываться и после перехода между уровнями.

Счётчик патча 48 упрямо показывал ноль непустых ответов PortalsAt даже после того, как регион
перестал теряться: 65391 узел региона 1, и ни одного портального. Причина не в теге и не в
таблице, а в том, ЧЕМ я загородил блок.

Порталы лежат на двух уровнях:

    уровень 0   14 пар   (магистральный)
    уровень 2    2 пары  (локальный)

Кандидаты Meili ищутся на самом подробном уровне, и на уровень 0 расширение попадает ТОЛЬКО
через NodeTransition. А блок порталов был закрыт условием !from_transition — тем самым флагом,
который для переходов означает «дальше по переходам не ходить». В результате порталы
спрашивались исключительно на уровне кандидатов, где на всю границу приходится одна пара, и
переход через Прут в Скулень, лежащий на уровне 0, не был виден никогда.

Флага нужно два, потому что запретов два и они независимы:

    from_transition   не уходить по переходам дальше одного шага
    from_portal       не уходить по порталам дальше одного прыжка

Тогда узел, до которого дошли переходом, всё ещё может раскрыть свой портал, а узел-близнец за
порталом раскрывает рёбра и переходы, но не следующий портал. Рекурсия остаётся ограниченной.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/meili/routing.cc")
s = io.open(P, encoding="utf-8").read()

DECL_OLD = (
    "  std::function<void(const baldr::GraphId&, const uint32_t, const bool)> expand;\n"
    "  expand = [&](const baldr::GraphId& node, const uint32_t label_idx, const bool from_transition) {\n"
)
DECL_NEW = (
    "  // WEDRIVE meili portal flag: запретов два и они независимы — по переходам не ходить\n"
    "  // дальше одного шага, по порталам не прыгать дальше одного раза. Одним флагом их\n"
    "  // объединить нельзя: порталы уровня 0 достижимы ТОЛЬКО через переход.\n"
    "  std::function<void(const baldr::GraphId&, const uint32_t, const bool, const bool)> expand;\n"
    "  expand = [&](const baldr::GraphId& node, const uint32_t label_idx, const bool from_transition,\n"
    "               const bool from_portal) {\n"
)

TRANS_OLD = "        expand(trans->endnode().with_region(node.region()), label_idx, true);\n"
TRANS_NEW = (
    "        expand(trans->endnode().with_region(node.region()), label_idx, true, from_portal);\n"
)

PORT_OLD = (
    "    if (!from_transition) {\n"
    "      ++wedrive_meili_asked;\n"
)
PORT_NEW = (
    "    if (!from_portal) {\n"
    "      ++wedrive_meili_asked;\n"
)

HOP_OLD = "          expand(portal.to, label_idx, true);\n"
HOP_NEW = (
    "          // Узел-близнец раскрывает свои рёбра и переходы, но не следующий портал.\n"
    "          expand(portal.to, label_idx, false, true);\n"
)

ROOT_OLD = "      expand(label.nodeid(), label_idx, false);\n"
ROOT_NEW = "      expand(label.nodeid(), label_idx, false, false);\n"

NAME = "WEDRIVE meili portal flag"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("объявление", DECL_OLD), ("переход", TRANS_OLD), ("блок порталов", PORT_OLD),
                       ("прыжок", HOP_OLD), ("корневой вызов", ROOT_OLD)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    s = (s.replace(DECL_OLD, DECL_NEW)
          .replace(TRANS_OLD, TRANS_NEW)
          .replace(PORT_OLD, PORT_NEW)
          .replace(HOP_OLD, HOP_NEW)
          .replace(ROOT_OLD, ROOT_NEW))
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("два флага в объявлении", "const bool from_transition,\n               const bool from_portal", True),
    ("порталы больше не закрыты переходом", "if (!from_portal) {\n      ++wedrive_meili_asked;", True),
    ("переход несёт флаг портала", "label_idx, true, from_portal);", True),
    ("прыжок ограничен", "expand(portal.to, label_idx, false, true);", True),
    ("корневой вызов обновлён", "expand(label.nodeid(), label_idx, false, false);", True),
    ("трёхаргументных вызовов не осталось", "label_idx, true);", False),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
