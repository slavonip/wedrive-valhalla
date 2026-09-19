"""WeDrive patch 35: измерить вклад шорткатов, ничего не исправляя.

Зацепка «993 ребра против 1800» указывает на шорткаты, но сама по себе ничего не доказывает:
shortcut_recovery работает уже при восстановлении пути, а недосчёт 1234.44 существует РАНЬШЕ,
внутри накопленных стоимостей лейблов.

Два измерения, оба под переменными окружения, без единой правки логики:

  WEDRIVE_DEBUG_BIDIR=1   к строке RECOST добавляется, сколько шорткатов было в пути ДО
                          восстановления и сколько рёбер стало ПОСЛЕ.

  WEDRIVE_NO_SHORTCUTS=1  двунаправленный поиск не берёт шорткат-рёбра вовсе. Контрольный прогон:
                          если маршрут станет монолитным и недосчёт вернётся к обычным ~150,
                          гипотеза подтверждается независимо; если результат не изменится,
                          шорткаты невиновны.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()

FLAG_OLD = "thread_local size_t wedrive_conn_count = 0;"
FLAG_NEW = (
    "thread_local size_t wedrive_conn_count = 0;\n"
    "// WEDRIVE no shortcuts flag: контрольный прогон без шорткат-рёбер.\n"
    "bool wedrive_no_shortcuts() {\n"
    "  static const bool on = std::getenv(\"WEDRIVE_NO_SHORTCUTS\") != nullptr;\n"
    "  return on;\n"
    "}"
)

# Якорь — самое начало ExpandInner, до любых наших правок.
SKIP_OLD = (
    "  // Skip if this is a regular edge superseded by a shortcut.\n"
    "  if (shortcuts & meta.edge->superseded()) {\n"
    "    return false;\n"
    "  }"
)
SKIP_NEW = (
    "  // WEDRIVE skip shortcuts: контрольный прогон, чтобы проверить их вклад независимо.\n"
    "  if (wedrive_no_shortcuts() && meta.edge->is_shortcut()) {\n"
    "    return false;\n"
    "  }\n"
) + SKIP_OLD

COUNT_OLD = (
    "      if (wedrive_debug_bidir() && !path.empty()) {\n"
    "        std::cerr << \"WEDRIVE RECOST: оценка=\" << best_connection->cost"
)
COUNT_NEW = (
    "      if (wedrive_debug_bidir() && !path.empty()) {\n"
    "        // WEDRIVE shortcut count: сколько рёбер исходного пути были шорткатами. Разрыв\n"
    "        // между размером пути до и после восстановления — это их разворачивание.\n"
    "        size_t wd_sc = 0;\n"
    "        for (const auto& wd_e : path_edges) {\n"
    "          graph_tile_ptr wd_t;\n"
    "          if (graphreader.GetGraphTile(wd_e, wd_t) && wd_t->directededge(wd_e)->is_shortcut()) {\n"
    "            ++wd_sc;\n"
    "          }\n"
    "        }\n"
    "        std::cerr << \"WEDRIVE SHORTCUTS: в исходном пути \" << wd_sc << \" из \"\n"
    "                  << path_edges.size() << \" рёбер, после восстановления \" << path.size()\n"
    "                  << std::endl;\n"
    "        std::cerr << \"WEDRIVE RECOST: оценка=\" << best_connection->cost"
)


def edit(name, old, new):
    global s
    if name in s:
        print("      ok   уже применено: %s" % name)
        return
    n = s.count(old)
    assert n == 1, "%s: ожидал 1 совпадение, нашёл %d" % (name, n)
    s = s.replace(old, new)
    print("      +    %s" % name)


edit("WEDRIVE no shortcuts flag", FLAG_OLD, FLAG_NEW)
edit("WEDRIVE skip shortcuts", SKIP_OLD, SKIP_NEW)
edit("WEDRIVE shortcut count", COUNT_OLD, COUNT_NEW)

io.open(P, "w", encoding="utf-8").write(s)

print("\n   проверка:")
s = io.open(P, encoding="utf-8").read()
for m in ("WEDRIVE no shortcuts flag", "WEDRIVE skip shortcuts", "WEDRIVE shortcut count"):
    print("      %s %s" % ("ok     " if m in s else "MISSING", m))
