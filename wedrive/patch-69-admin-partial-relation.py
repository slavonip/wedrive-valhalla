"""WeDrive patch 69: admin-отношение с недостающими членами не выбрасывается целиком.

AdminBuilder (src/mjolnir/adminbuilder.cc, to_segments) при ОДНОМ отсутствующем way- или
node-члене отношения возвращал false, и BuildAdminFromPBF пропускал всё отношение
(«is degenerate and will be skipped»). Для планеты это редкость. Для нашей схемы — норма:
страна строится из экстракта Geofabrik, а у государства бывают части вне экстракта.

Измерено 2026-09-28 на NL после patch 67: frontier_dump nodes 4404533, frontier 0. admins.sqlite
содержит только 12 провинций уровня 4; отношение Королевства r2323309 (admin_level=2,
ISO3166-1=NL) пропущено, потому что в экстракте нет way 993740650 (Карибская часть). Без
полигона страны у узлов нет страны, и граница не видна.

Исправление общее, без исключений по странам: отсутствующий way пропускается, way с отсутствующим
узлом пропускается целиком (его геометрия неполна). Кольца собирает to_rings, который уже
отбрасывает незамкнутые и вырожденные кольца, — поэтому остаются только те части страны, чья
граница в экстракте есть полностью (европейская часть NL), а незамкнутый хвост отбрасывается
как и раньше. Если не замкнулось ни одно внешнее кольцо, отношение по-прежнему пропускается.
Только построение admins.sqlite; маршрутизацию не затрагивает.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/mjolnir/adminbuilder.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE admin partial relation"
EDITS = [
    ("      LOG_WARN(name + \" (\" + std::to_string(admin.id) + \") is missing way member \" +\n"
     "               std::to_string(memberid));\n"
     "      return false;\n",
     "      LOG_WARN(name + \" (\" + std::to_string(admin.id) + \") is missing way member \" +\n"
     "               std::to_string(memberid));\n"
     "      // " + NAME + " (patch 69): skip the member, keep the rings that still close\n"
     "      continue;\n"),
    ("    bg::ring_ll_t coords;\n"
     "    for (const auto node_id : w_itr->second) {\n",
     "    bg::ring_ll_t coords;\n"
     "    bool whole = true; // " + NAME + ": a way missing a node is skipped whole\n"
     "    for (const auto node_id : w_itr->second) {\n"),
    ("                 std::to_string(memberid) + \" is missing node \" + std::to_string(node_id));\n"
     "        return false;\n"
     "      }\n",
     "                 std::to_string(memberid) + \" is missing node \" + std::to_string(node_id));\n"
     "        whole = false;\n"
     "        break;\n"
     "      }\n"),
    ("    // remember how to find this line\n"
     "    if (!coords.empty()) {\n",
     "    // remember how to find this line\n"
     "    if (whole && !coords.empty()) {\n"),
]

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for old, new in EDITS:
        n = s.count(old)
        if n != 1:
            raise SystemExit("patch 69: ожидал 1 совпадение, нашёл %d:\n%s" % (n, old))
        s = s.replace(old, new)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      ok   %s" % NAME)
