#!/usr/bin/env python3
"""Где именно два маршрута перестают совпадать.

Сравнивать итоговые 456 км против 469 км бесполезно: разница может родиться на первом же
километре или на последнем. Здесь для каждой точки первого маршрута ищется ближайшая точка
второго, и находится ПЕРВАЯ, где они разошлись больше порога — вместе с километражом от старта,
координатой и ближайшим манёвром.

Если маршруты совпадают до границы и ещё десятки километров после неё, portals и Loki
исключаются сразу, и остаётся иерархия внутри второй страны.

  usage: shape_divergence.py <a.json> <b.json> [порог_метров]
"""
import json
import math
import sys


def decode(encoded, precision=6):
    """polyline с заданной точностью -> список (lat, lon)."""
    inv = 10.0 ** -precision
    decoded, prev, i = [], [0, 0], 0
    while i < len(encoded):
        ll = [0, 0]
        for j in (0, 1):
            shift, byte = 0, 0x20
            while byte >= 0x20:
                byte = ord(encoded[i]) - 63
                i += 1
                ll[j] |= (byte & 0x1f) << shift
                shift += 5
            ll[j] = prev[j] + (~(ll[j] >> 1) if ll[j] & 1 else (ll[j] >> 1))
            prev[j] = ll[j]
        decoded.append((ll[0] * inv, ll[1] * inv))
    return decoded


def metres(a, b):
    lat = math.radians((a[0] + b[0]) / 2.0)
    dx = (b[1] - a[1]) * 111320.0 * math.cos(lat)
    dy = (b[0] - a[0]) * 110540.0
    return math.hypot(dx, dy)


def load(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    d = json.loads(raw[raw.index("{"):])
    if "error" in d:
        raise SystemExit("   %s: ОШИБКА %s" % (path, d["error"]))
    leg = d["trip"]["legs"][0]
    man = [(m.get("begin_shape_index", 0), m.get("street_names", [""])[0] if m.get("street_names")
            else m.get("instruction", "")[:40]) for m in leg["maneuvers"]]
    return decode(leg["shape"]), man, d["trip"]["summary"]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    thresh = float(sys.argv[3]) if len(sys.argv) > 3 else 50.0
    a_pts, a_man, a_sum = load(sys.argv[1])
    b_pts, b_man, b_sum = load(sys.argv[2])
    print("   A: %8.3f км, точек %5d, манёвров %3d" % (a_sum["length"], len(a_pts), len(a_man)))
    print("   B: %8.3f км, точек %5d, манёвров %3d" % (b_sum["length"], len(b_pts), len(b_man)))

    # Для каждой точки A — минимальное расстояние до любой точки B. Окно скользит вперёд, иначе
    # на длинном маршруте это квадратичная работа.
    run, j0 = 0.0, 0
    for i, pa in enumerate(a_pts):
        lo = max(0, j0 - 200)
        hi = min(len(b_pts), j0 + 2000)
        best, bj = 1e18, j0
        for j in range(lo, hi):
            d = metres(pa, b_pts[j])
            if d < best:
                best, bj = d, j
        j0 = bj
        if i:
            run += metres(a_pts[i - 1], pa)
        if best > thresh:
            name = ""
            for idx, nm in a_man:
                if idx <= i:
                    name = nm
            print()
            print("   РАСХОЖДЕНИЕ на %.3f км от старта" % (run / 1000.0))
            print("      точка A #%d  %.6f, %.6f" % (i, pa[0], pa[1]))
            print("      ближайшая точка B на %d м" % int(best))
            print("      последний манёвр A до этого места: %s" % (name or "—"))
            return
    print()
    print("   маршруты совпадают в пределах %d м на всём протяжении" % int(thresh))


main()
