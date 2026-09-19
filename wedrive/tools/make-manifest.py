"""Манифест региональных пакетов: что лежит на раздаче и что качать при обновлении.

Схема родилась не из общих соображений, а из измерения. Обновление Румынии 2026-09-01 ->
2026-09-18 показало:

    тайлов различается побайтово   636 из 636
    пар идентификаторов в таблице   20 из 32 сменились

То есть таблица порталов принадлежит не границе, а КОНКРЕТНОЙ ПАРЕ ВЕРСИЙ двух графов. Поэтому
у каждой записи portals стоят обе версии, а не одна, и поэтому же при обновлении одной страны
скачиваются ОБЕ её таблицы, а не только граница с тем соседом, который тоже обновился:
идентификаторы обновлённой страны входят в каждую её таблицу.

Манифест описывает то, что реально лежит в каталогах, и ничего не выдумывает: версия графа
берётся из отметки времени исходного экстракта OSM, контрольная сумма — из самих файлов.

  usage:
    make-manifest.py build   <regions.json> [> index.json]
    make-manifest.py plan    <index.json> <код-страны>   — что качать при обновлении страны
"""
import hashlib
import json
import os
import subprocess
import sys


def osm_date(pbf):
    """Дата данных OSM из заголовка экстракта. Это и есть версия графа: два пакета,
    собранные из одного экстракта, взаимозаменяемы, из разных — нет."""
    try:
        out = subprocess.run(
            ["osmium", "fileinfo", "-g", "header.option.osmosis_replication_timestamp", pbf],
            capture_output=True, text=True, check=True).stdout.strip()
        return out[:10] if out else "неизвестна"
    except Exception:
        return "неизвестна"


def digest(path):
    """Контрольная сумма дерева файлов: имена и содержимое. Нужна, чтобы устройство могло
    отличить «тот же пакет» от «того же размера»."""
    h = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            h.update(os.path.relpath(full, path).encode())
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def build(spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    regions = {}
    for r in spec["regions"]:
        tiles = r["tiles"]
        if not os.path.isdir(tiles):
            continue
        regions[r["code"]] = {
            "region_id": r["id"],
            "graph_version": osm_date(r["pbf"]),
            "package": r.get("package", "%s.tar" % r["code"].lower()),
            "checksum": digest(tiles),
            "source": os.path.basename(r["pbf"]),
        }

    portals = {}
    for p in spec["portals"]:
        a, b = p["between"]
        if a not in regions or b not in regions:
            continue
        if not os.path.isfile(p["file"]):
            continue
        portals["%s-%s" % (a, b)] = {
            # Обе версии, а не одна: таблица годна ровно для этой пары сборок.
            "versions": ["%s-%s" % (a, regions[a]["graph_version"]),
                         "%s-%s" % (b, regions[b]["graph_version"])],
            "file": os.path.basename(p["file"]),
            "checksum": digest(p["file"]),
            "rows": sum(1 for l in open(p["file"], encoding="utf-8")
                        if l.strip() and not l.startswith("#")),
        }

    return {"engine": {"version": spec.get("engine", "multi-region-runtime-v2")},
            "regions": regions, "portals": portals}


def plan(index_path, code):
    """Что устройство обязано скачать, когда обновилась одна страна.

    Ответ не «страна плюс граница с обновившимся соседом», а страна плюс ВСЕ её таблицы:
    идентификаторы пересобранного графа меняются целиком, и каждая его таблица становится
    негодной. Измерено: 20 из 32 пар сменились при обновлении Румынии.
    """
    idx = json.load(open(index_path, encoding="utf-8"))
    if code not in idx["regions"]:
        print("нет такой страны в манифесте: %s" % code)
        return 1
    need_tables = [name for name in idx["portals"] if code in name.split("-")]
    keep = [c for c in idx["regions"] if c != code]
    print("обновилась страна: %s (версия %s)" % (code, idx["regions"][code]["graph_version"]))
    print()
    print("СКАЧАТЬ:")
    print("   пакет   %-10s %s" % (code, idx["regions"][code]["package"]))
    for t in need_tables:
        print("   таблица %-10s %s  (версии %s)"
              % (t, idx["portals"][t]["file"], ", ".join(idx["portals"][t]["versions"])))
    print()
    print("НЕ СКАЧИВАТЬ (не изменились):")
    for c in keep:
        print("   пакет   %-10s %s" % (c, idx["regions"][c]["package"]))
    for t in idx["portals"]:
        if t not in need_tables:
            print("   таблица %-10s %s" % (t, idx["portals"][t]["file"]))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "build":
        print(json.dumps(build(sys.argv[2]), ensure_ascii=False, indent=2))
    elif sys.argv[1] == "plan":
        sys.exit(plan(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
        sys.exit(2)
