"""WeDrive patch 10: регион нужен ТОЛЬКО при выборе тайла.

Патч 9 сделал ассерты строгими и они тут же начали падать на законных обращениях — потому что
требовали región там, где он не нужен. Разделение, которое всё расставляет по местам:

    выбор тайла  (GetGraphTile)      -> регион ОБЯЗАТЕЛЕН, иначе возьмём файл чужой страны
    индексация внутри тайла (node(), directededge(), get_node_ll())
                                     -> регион НЕ нужен: тайл уже правильный, а id() внутри него
                                        считается по 21 биту

Поэтому проверка принадлежности сравнивает tile_base БЕЗ региона, но отдельно требует, чтобы
тегнутый id не принадлежал ДРУГОМУ региону. Нетегнутый (region 0) означает «не знаю, доверяю
тайлу» и проходит; тегнутый чужим регионом падает немедленно.

Это резко сокращает список мест, которые вообще нужно править: только те, где endnode уходит
в GetGraphTile.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/baldr/graphtile.h")
s = io.open(P, encoding="utf-8").read()

if "wedrive_id_ok" in s:
    print("      ok   уже применено: wedrive_id_ok")
else:
    # 1. Хелпер рядом с id().
    anchor = "  /** WEDRIVE: which independently built region this tile was loaded for. */"
    assert s.count(anchor) == 1
    helper = (
        "  /**\n"
        "   * WEDRIVE: принадлежит ли id этому тайлу.\n"
        "   *\n"
        "   * Сравнение идёт БЕЗ региона, потому что внутри тайла индекс считается по младшим\n"
        "   * битам и регион там не участвует. Но если регион в id всё-таки проставлен и он\n"
        "   * ЧУЖОЙ — это обращение к узлу другой страны через тайл этой, то есть ровно та тихая\n"
        "   * ошибка, ради которой затевался весь multi-region. Такое падает сразу.\n"
        "   */\n"
        "  bool wedrive_id_ok(const GraphId& other) const {\n"
        "    return other.tile_base().without_region() == id().tile_base().without_region() &&\n"
        "           (other.region() == 0 || other.region() == wedrive_region_);\n"
        "  }\n\n"
    )
    s = s.replace(anchor, helper + anchor)

    # 2. Четыре ассерта переводим на него.
    old_forms = [
        "assert(node.tile_base() == id().tile_base());",
        "assert(nodeid.tile_base() == id().tile_base());",
        "assert(edge.tile_base() == id().tile_base());",
    ]
    total = 0
    for f in old_forms:
        var = f.split("(")[1].split(".")[0]
        n = s.count(f)
        assert n >= 1, "не нашёл ассерт для %s" % var
        s = s.replace(f, "assert(wedrive_id_ok(%s));" % var)
        total += n
    assert total == 4, "ожидал 4 ассерта, заменил %d" % total
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    wedrive_id_ok + %d ассерта переведены на него" % total)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s хелпер объявлен" % ("ok     " if "bool wedrive_id_ok" in s else "MISSING"))
print("      %d ассерта используют его" % s.count("assert(wedrive_id_ok("))
print("      %s не осталось прямых сравнений tile_base с id()"
      % ("ok     " if ".tile_base() == id().tile_base()" not in s else "MISSING"))
