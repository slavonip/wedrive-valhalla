"""WeDrive patch 26: восстановление шорткатов — ТРЕТИЙ namespace-неосознающий контейнер.

После FlatTileCache и EdgeStatus это третий случай одной болезни, и он же — последнее место,
куда указал backtrace детектора на полном valhalla_service:

    shortcut_recovery_t::recover_shortcut(...)
    GraphReader::RecoverShortcut(...)
    BidirectionalAStar::FormPath(...)

Внутри `recover_shortcut` новые идентификаторы собираются так:

    edges.push_back(tile->header()->graphid());
    edges.back().set_id(&de - tile->directededge(0));

`header()->graphid()` — это id, КАК ЕГО ЗАПИСАЛ MJOLNIR, то есть без региона: заголовок тайла о
регионах не знает и знать не может. А `tile->id()` (патч 2) отдаёт тот же id, тегнутый регионом,
для которого тайл был загружен. Разница в одну функцию, и из-за неё все восстановленные рёбра
шортката теряли namespace, а дальше по ним выбирался тайл каталога по умолчанию.

Ровно та же подмена уже чинилась в ассертах graphtile.h (патч 9): сравнивать и строить нужно от
`id()`, а не от заголовка.

Отдельно стоит знать про кеш: `shortcut_recovery_t` — СИНГЛТОН, и его таблица предзаполняется
обходом только каталога по умолчанию. Ключ — полное 64-битное значение, поэтому регионы в нём не
сталкиваются; записи для прочих регионов просто считаются на лету. Это корректно, хотя и не
бесплатно.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/baldr/shortcut_recovery.h")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE shortcut ids keep region"
OLD = "tile->header()->graphid()"
NEW = "tile->id()"

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    n = s.count(OLD)
    assert n >= 1, "не нашёл ни одного tile->header()->graphid()"
    s = s.replace(OLD, NEW)
    anchor = "struct shortcut_recovery_t {"
    assert s.count(anchor) == 1
    s = s.replace(
        anchor,
        "// WEDRIVE shortcut ids keep region: восстановленные рёбра строятся от tile->id(), а не\n"
        "// от header()->graphid(). Заголовок хранит id так, как его записал Mjolnir — без региона,\n"
        "// — и все восстановленные идентификаторы теряли namespace.\n" + anchor,
    )
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s (%d вхождений)" % (NAME, n))

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s не осталось header()->graphid()" % ("ok     " if OLD not in s else "MISSING"))
print("      %d использований tile->id()" % s.count("tile->id()"))
