"""WeDrive patch 18: EdgeStatus — второй namespace-неосознающий контейнер после FlatTileCache.

Это оказалось причиной всего, что осталось после того, как region lost дошёл до нуля.

EdgeStatus помнит, посещено ли ребро, и ключом служит

    edgeid.tile_value() | SHIFT_path_id(path_id)

где tile_value() возвращает uint32_t — 25 бит level+tileid, — а path_id занимает оставшиеся 7.
Ключ забит целиком, региону там места нет ФИЗИЧЕСКИ. Значит тайл региона 1 и тайл региона 2 с
одинаковым tileid делят один массив статусов.

Последствия ровно те, что наблюдались:

  * маршрут «находился» даже БЕЗ портала — forward-дерево в регионе 1 и reverse-дерево в
    регионе 2 встречались на общем слоте статуса, хотя это разные рёбра разных графов;
  * дальше recost шёл по пути, склеенному из рёбер двух регионов без реального перехода, и
    падал на NodeInfo index out of bounds — id из графа, где узлов больше, применялся к тайлу,
    где их меньше;
  * и всё это при region lost = 0, потому что регион не терялся: он просто не участвовал в
    ключе.

Урок того же класса, что FlatTileCache: ЛЮБОЙ контейнер, ключом которого является tileid,
обязан знать про регион. Стоит пройти по ним всем, а не чинить по одному.

При region == 0 ключ побитово совпадает со старым, поэтому одно-региональное поведение не
меняется — это важно для регрессии против upstream.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/thor/edgestatus.h")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE edgestatus region key"

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    # 1. path_id сдвигаем уже в 64 битах.
    old_macro = "#define SHIFT_path_id(x) (static_cast<uint32_t>(x) << 25u)"
    assert s.count(old_macro) == 1
    new_macro = (
        "#define SHIFT_path_id(x) (static_cast<uint64_t>(x) << 25u)\n"
        "// WEDRIVE edgestatus region key: ключ расширен до 64 бит, регион лёг выше path_id.\n"
        "// В 32-битном ключе места не было вовсе: 25 бит tile_value + 7 бит path_id = все 32,\n"
        "// поэтому два региона делили один слот и деревья «встречались» без портала.\n"
        "// При region == 0 ключ побитово совпадает со старым.\n"
        "#define WEDRIVE_ES_KEY(edgeid, path_id)                                                    \\\n"
        "  (static_cast<uint64_t>((edgeid).tile_value()) | SHIFT_path_id(path_id) |                 \\\n"
        "   (static_cast<uint64_t>((edgeid).region()) << 32u))"
    )
    s = s.replace(old_macro, new_macro)

    # 2. Все обращения — через новый ключ.
    old_key = "edgeid.tile_value() | SHIFT_path_id(path_id)"
    n = s.count(old_key)
    assert n == 6, "ожидал 6 обращений к ключу, нашёл %d" % n
    s = s.replace(old_key, "WEDRIVE_ES_KEY(edgeid, path_id)")

    # 3. Тип контейнера.
    old_map = "std::unordered_map<uint32_t, EdgeStatusInfo*> edgestatus_;"
    assert s.count(old_map) == 1
    s = s.replace(old_map, "std::unordered_map<uint64_t, EdgeStatusInfo*> edgestatus_;")

    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s (%d обращений к ключу)" % (NAME, n))

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s макрос ключа объявлен" % ("ok     " if "WEDRIVE_ES_KEY" in s else "MISSING"))
print("      %d обращений используют его" % s.count("WEDRIVE_ES_KEY(edgeid, path_id)"))
print("      %s не осталось старой формы ключа"
      % ("ok     " if "edgeid.tile_value() | SHIFT_path_id" not in s else "MISSING"))
print("      %s контейнер на uint64" % ("ok     " if "unordered_map<uint64_t, EdgeStatusInfo*>" in s else "MISSING"))

print("\n   ревизия: ВСЕ места, где tile_value() используется как ключ")
import subprocess

out = subprocess.run(
    ["grep", "-rn", "tile_value()", os.path.join(SRC, "valhalla"), os.path.join(SRC, "src")],
    capture_output=True, text=True).stdout
for line in out.strip().split("\n"):
    if line:
        print("      " + line.replace(SRC + "/", "")[:110])
