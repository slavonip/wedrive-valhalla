"""WeDrive patch 32: трассировка момента встречи деревьев в BidirectionalAStar.

Патч 31 показал ЧТО происходит (первое соединение, порог, размеры деревьев). Теперь нужно
понять ПОЧЕМУ оптимальная ветка не побеждает, хотя её существование доказано: timedep_forward на
тех же графах и той же таблице порталов даёт монолитные 456.458 км.

Логируется при WEDRIVE_DEBUG_BIDIR=1:

  * КАЖДОЕ соединение, а не только первое: стоимость, ребро с регионом, координата точки встречи.
    Если композит и монолит встречаются в разных местах, это видно сразу.
  * достижение «наблюдаемого» узла, задаваемого через WEDRIVE_WATCH_NODE=<graphid>: settle-ится
    ли вообще ребро, выходящее из точки расхождения, и с каким sortcost. Это отвечает на главный
    вопрос — ветка рассматривалась и проиграла или её вовсе не было в очереди.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()


def edit(name, old, new, count=1):
    global s
    if name in s:
        print("      ok   уже применено: %s" % name)
        return
    n = s.count(old)
    assert n >= count, "не нашёл %s (совпадений %d)" % (name, n)
    s = s.replace(old, new)
    print("      +    %s" % name)


# 1. Наблюдаемый узел и счётчик соединений.
edit(
    "WEDRIVE watch node",
    "thread_local bool wedrive_first_conn = true;",
    "thread_local bool wedrive_first_conn = true;\n"
    "thread_local size_t wedrive_conn_count = 0;\n"
    "// WEDRIVE watch node: какой узел отслеживать. 0 — не отслеживать.\n"
    "uint64_t wedrive_watch_node() {\n"
    "  static const uint64_t v = [] {\n"
    "    const char* e = std::getenv(\"WEDRIVE_WATCH_NODE\");\n"
    "    return e ? std::strtoull(e, nullptr, 10) : 0ull;\n"
    "  }();\n"
    "  return v;\n"
    "}",
)

# 2. Каждое соединение — со стоимостью, ребром и координатой.
edit(
    "WEDRIVE trace connection",
    "  // WEDRIVE report first connection: что известно поиску в момент, когда он решает,\n"
    "  // насколько ещё продолжать.\n"
    "  if (wedrive_debug_bidir() && wedrive_first_conn) {",
    "  // WEDRIVE trace connection: каждое соединение, а не только первое. Место встречи и его\n"
    "  // стоимость — это и есть ответ на вопрос, почему выбран один путь, а не другой.\n"
    "  if (wedrive_debug_bidir() && ++wedrive_conn_count <= 12) {\n"
    "    auto t = graphreader.GetGraphTile(pred.edgeid());\n"
    "    midgard::PointLL ll;\n"
    "    if (t) {\n"
    "      ll = t->get_node_ll(pred.endnode());\n"
    "    }\n"
    "    std::cerr << \"WEDRIVE CONN #\" << wedrive_conn_count << \"  cost=\" << c\n"
    "              << \"  ребро=\" << pred.edgeid().value << \" регион=\" << pred.edgeid().region()\n"
    "              << \"  в \" << ll.lat() << \",\" << ll.lng()\n"
    "              << \"  порог=\" << cost_threshold_ << std::endl;\n"
    "  }\n"
    "  // WEDRIVE report first connection: что известно поиску в момент, когда он решает,\n"
    "  // насколько ещё продолжать.\n"
    "  if (wedrive_debug_bidir() && wedrive_first_conn) {",
)

# 3. Достигает ли forward-дерево наблюдаемого узла.
edit(
    "WEDRIVE watch hit",
    "        // Forward path to this edge can't be improved, so we can settle it right now.\n"
    "        edgestatus_forward_.Update(fwd_pred.edgeid(), EdgeSet::kPermanent);",
    "        // Forward path to this edge can't be improved, so we can settle it right now.\n"
    "        edgestatus_forward_.Update(fwd_pred.edgeid(), EdgeSet::kPermanent);\n"
    "        // WEDRIVE watch hit: дошло ли forward-дерево до интересующего узла и с какой оценкой.\n"
    "        if (wedrive_debug_bidir() && wedrive_watch_node() != 0 &&\n"
    "            fwd_pred.endnode().value == wedrive_watch_node()) {\n"
    "          std::cerr << \"WEDRIVE WATCH достигнут: sortcost=\" << fwd_pred.sortcost()\n"
    "                    << \" cost=\" << fwd_pred.cost().cost << \" порог=\" << cost_threshold_\n"
    "                    << \" дерево fwd=\" << edgelabels_forward_.size() << std::endl;\n"
    "        }",
)

# 4. Сброс счётчика соединений вместе с остальными.
edit(
    "WEDRIVE reset conn count",
    "  wedrive_portal_fwd = wedrive_portal_rev = 0;\n  wedrive_first_conn = true;",
    "  wedrive_portal_fwd = wedrive_portal_rev = 0;\n"
    "  wedrive_first_conn = true;\n"
    "  wedrive_conn_count = 0; // WEDRIVE reset conn count",
)

io.open(P, "w", encoding="utf-8").write(s)

print("\n   проверка:")
s = io.open(P, encoding="utf-8").read()
for m in ("WEDRIVE watch node", "WEDRIVE trace connection", "WEDRIVE watch hit",
          "WEDRIVE reset conn count"):
    print("      %s %s" % ("ok     " if m in s else "MISSING", m))
