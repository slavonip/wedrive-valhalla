"""WeDrive patch 31: диагностика двунаправленного поиска, включаемая переменной окружения.

Вопрос стоит так: не завершает ли bidirectional поиск, найдя первое межрегиональное соединение,
до того как раскроется оптимальная ветка. Угадывать по коду дорого — дешевле напечатать, что
происходит в момент первого соединения и на выходе.

Печатается при WEDRIVE_DEBUG_BIDIR=1:
  * сколько раз раскрыт портал в прямом и обратном деревьях;
  * стоимость первого соединения, назначенный порог и размеры деревьев в этот момент;
  * причина выхода: порог, исчерпание или число итераций.

В обычном режиме не стоит ничего, кроме проверки одного bool, прочитанного один раз.
"""
import io
import os

SRC = "/src/valhalla"


def patch(relpath, edits):
    p = os.path.join(SRC, relpath)
    s = io.open(p, encoding="utf-8").read()
    changed = False
    for name, old, new in edits:
        if name in s:
            print("      ok   уже применено: %s" % name)
            continue
        n = s.count(old)
        # «Set thresholds» встречается и в SetForwardConnection, и в SetReverseConnection —
        # диагностика нужна в обеих, а от повторной печати защищает wedrive_first_conn.
        assert n >= 1, "%s: не нашёл %s" % (relpath, name)
        s = s.replace(old, new)
        changed = True
        print("      +    %s" % name)
    if changed:
        io.open(p, "w", encoding="utf-8").write(s)


print("   src/thor/bidirectional_astar.cc")
patch(
    "src/thor/bidirectional_astar.cc",
    [
        (
            "WEDRIVE bidir counters",
            "namespace valhalla {\nnamespace thor {",
            "namespace {\n"
            "// WEDRIVE bidir counters: включаются переменной окружения, по умолчанию молчат.\n"
            "bool wedrive_debug_bidir() {\n"
            "  static const bool on = std::getenv(\"WEDRIVE_DEBUG_BIDIR\") != nullptr;\n"
            "  return on;\n"
            "}\n"
            "thread_local size_t wedrive_portal_fwd = 0;\n"
            "thread_local size_t wedrive_portal_rev = 0;\n"
            "thread_local bool wedrive_first_conn = true;\n"
            "} // namespace\n\n"
            "namespace valhalla {\nnamespace thor {",
        ),
        (
            "WEDRIVE count portal expansion",
            "  if (const auto* portals = graphreader.PortalsAt(node)) {\n"
            "    for (const auto& portal : *portals) {",
            "  if (const auto* portals = graphreader.PortalsAt(node)) {\n"
            "    // WEDRIVE count portal expansion\n"
            "    if (FORWARD) {\n"
            "      ++wedrive_portal_fwd;\n"
            "    } else {\n"
            "      ++wedrive_portal_rev;\n"
            "    }\n"
            "    for (const auto& portal : *portals) {",
        ),
        (
            "WEDRIVE report first connection",
            "  // Set thresholds to extend search\n"
            "  if (cost_threshold_ == std::numeric_limits<float>::max() || c < best_connections_.front().cost) {",
            "  // WEDRIVE report first connection: что известно поиску в момент, когда он решает,\n"
            "  // насколько ещё продолжать.\n"
            "  if (wedrive_debug_bidir() && wedrive_first_conn) {\n"
            "    wedrive_first_conn = false;\n"
            "    std::cerr << \"WEDRIVE BIDIR первое соединение: cost=\" << c\n"
            "              << \"  порог был=\" << cost_threshold_ << \"  деревья fwd=\"\n"
            "              << edgelabels_forward_.size() << \" rev=\" << edgelabels_reverse_.size()\n"
            "              << \"  раскрытий портала fwd=\" << wedrive_portal_fwd\n"
            "              << \" rev=\" << wedrive_portal_rev << std::endl;\n"
            "  }\n"
            "  // Set thresholds to extend search\n"
            "  if (cost_threshold_ == std::numeric_limits<float>::max() || c < best_connections_.front().cost) {",
        ),
        (
            "WEDRIVE BIDIR выход по порогу",
            "        if (fwd_pred.sortcost() + cost_diff_ > cost_threshold_) {\n"
            "          return FormPath(graphreader, options, origin, destination, forward_time_info);",
            "        if (fwd_pred.sortcost() + cost_diff_ > cost_threshold_) {\n"
            "          if (wedrive_debug_bidir()) {\n"
            "            std::cerr << \"WEDRIVE BIDIR выход по порогу: sortcost=\" << fwd_pred.sortcost()\n"
            "                      << \" + cost_diff=\" << cost_diff_ << \" > порог=\" << cost_threshold_\n"
            "                      << \"  деревья fwd=\" << edgelabels_forward_.size()\n"
            "                      << \" rev=\" << edgelabels_reverse_.size()\n"
            "                      << \"  раскрытий портала fwd=\" << wedrive_portal_fwd\n"
            "                      << \" rev=\" << wedrive_portal_rev << std::endl;\n"
            "          }\n"
            "          return FormPath(graphreader, options, origin, destination, forward_time_info);",
        ),
        (
            "WEDRIVE reset counters",
            "  cost_threshold_ = std::numeric_limits<float>::max();\n"
            "  iterations_threshold_ = std::numeric_limits<uint32_t>::max();",
            "  cost_threshold_ = std::numeric_limits<float>::max();\n"
            "  iterations_threshold_ = std::numeric_limits<uint32_t>::max();\n"
            "  // WEDRIVE reset counters\n"
            "  wedrive_portal_fwd = wedrive_portal_rev = 0;\n"
            "  wedrive_first_conn = true;",
        ),
    ],
)

# cstdlib для getenv, iostream для cerr
p = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(p, encoding="utf-8").read()
for inc in ("#include <cstdlib>", "#include <iostream>"):
    if inc not in s:
        first = s.index("#include")
        s = s[:first] + inc + " // WEDRIVE bidir counters\n" + s[first:]
io.open(p, "w", encoding="utf-8").write(s)

print("\n   проверка:")
s = io.open(p, encoding="utf-8").read()
for m in ("WEDRIVE bidir counters", "WEDRIVE count portal expansion",
          "WEDRIVE report first connection", "WEDRIVE BIDIR выход по порогу",
          "WEDRIVE reset counters", "#include <cstdlib>", "#include <iostream>"):
    print("      %s %s" % ("ok     " if m in s else "MISSING", m))
