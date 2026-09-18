"""Experiment 4, part 3: route the same pairs on REF, MIXED and BROKEN_MIXED.

Every endpoint below is a coordinate that ALREADY PASSED its gate in the first Europe build, so a
failure here is about the graph and not about a point somebody typed. The Vienna centre point is
deliberately absent: the same build showed it routes as a destination and not as an origin.

`trace_attributes` is not used. Its 200 km ceiling was established experimentally
(`Path distance exceeds the max distance limit: 200000 meters`), which is what made the corridor
probes report UNCHECKED. What is compared instead is directly measurable: existence, distance,
duration, geometry continuity, worst segment jump, and the sequence of edge ids the route uses.
"""
import hashlib
import json
import math
import os
import subprocess
import sys

CASES = [
    # Romania is in the middle of every one of these
    ("MD -> RO   Chisinau to Iasi",       (47.0105, 28.8638), (47.1585, 27.6014)),
    ("HU -> RO   across the frontier",    (47.0722, 21.9217), (47.5316, 21.6273)),
    ("RO -> UA   Iasi to Chernivtsi",     (47.1585, 27.6014), (48.2921, 25.9358)),
    ("BG -> RO   Ruse to Giurgiu",        (43.8563, 25.9660), (43.8356, 25.9657)),
    ("HU -> MD   Budapest to Chisinau",   (47.4979, 19.0402), (47.0105, 28.8638)),
    ("BG -> HU   Sofia to Budapest",      (42.6977, 23.3219), (47.4979, 19.0402)),
    # CONTROLS: these do not pass through Romania and must be unaffected
    ("MD -> UA   Chisinau to Odesa  [control]", (47.0105, 28.8638), (46.4825, 30.7233)),
    ("HU -> UA   Debrecen to Uzhhorod [control]", (47.5316, 21.6273), (48.6208, 22.2879)),
]

GAP_KM = 5.0


def decode6(s):
    pts, i, lat, lon = [], 0, 0, 0
    while i < len(s):
        for ax in range(2):
            sh = res = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                res |= (b & 0x1F) << sh
                sh += 5
                if b < 0x20:
                    break
            d = ~(res >> 1) if res & 1 else (res >> 1)
            if ax == 0:
                lat += d
            else:
                lon += d
        pts.append((lat / 1e6, lon / 1e6))
    return pts


def worst_gap(pts):
    w = 0.0
    where = None
    for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
        dla, dlo = math.radians(a2 - a1), math.radians(o2 - o1)
        h = (math.sin(dla / 2) ** 2 + math.cos(math.radians(a1)) * math.cos(math.radians(a2))
             * math.sin(dlo / 2) ** 2)
        km = 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))
        if km > w:
            w, where = km, ((a1, o1), (a2, o2))
    return w, where


def run(config, frm, to):
    req = {"locations": [{"lat": frm[0], "lon": frm[1]}, {"lat": to[0], "lon": to[1]}],
           "costing": "auto"}
    try:
        out = subprocess.run(["valhalla_service", config, "route", json.dumps(req)],
                             capture_output=True, text=True, timeout=300).stdout
        doc = json.loads(out)
    except Exception as exc:                        # noqa: BLE001
        return {"ok": False, "why": f"call failed: {exc!r}"[:100]}
    if "trip" not in doc or doc["trip"].get("status") not in (0, None):
        return {"ok": False, "why": doc.get("error") or doc["trip"].get("status_message", "?")}
    trip = doc["trip"]
    shape = "".join(l.get("shape") or "" for l in trip.get("legs") or [])
    pts = decode6(shape) if shape else []
    gap, where = worst_gap(pts) if len(pts) > 1 else (None, None)
    return {"ok": True, "km": trip["summary"]["length"], "s": trip["summary"]["time"],
            "pts": len(pts), "gap": gap, "where": where,
            "shape_sha": hashlib.sha256(shape.encode()).hexdigest()[:12]}


LABELS = sys.argv[1:] or ["REF", "MIXED", "BROKEN_MIXED"]
CONFIGS = {l: f"/data/{l}/valhalla.json" for l in LABELS}

results = {}
for label in LABELS:
    results[label] = [run(CONFIGS[label], f, t) for _, f, t in CASES]

print(f"{'route':<42} " + "".join(f"{l:<26}" for l in LABELS))
print("-" * (42 + 26 * len(LABELS)))
for i, (name, _, _) in enumerate(CASES):
    row = f"{name:<42} "
    for label in LABELS:
        r = results[label][i]
        if not r["ok"]:
            row += f"{'NO ROUTE':<26}"
        else:
            g = f"{r['gap']*1000:.0f}m" if r["gap"] is not None else "-"
            row += f"{r['km']:8.1f}km {r['s']:6.0f}s {g:>7} "
    print(row)

print()
ref = results.get("REF")
if ref:
    for label in LABELS:
        if label == "REF":
            continue
        same = diff = broke = 0
        notes = []
        for i, (name, _, _) in enumerate(CASES):
            a, b = ref[i], results[label][i]
            if a["ok"] and not b["ok"]:
                broke += 1
                notes.append(f"BROKE: {name} — {b['why']}")
            elif a["ok"] and b["ok"]:
                if a["shape_sha"] == b["shape_sha"]:
                    same += 1
                else:
                    diff += 1
                    notes.append(f"DIFFERS: {name} — {a['km']:.1f} vs {b['km']:.1f} km, "
                                 f"gap {a['gap']*1000:.0f} vs {b['gap']*1000:.0f} m")
        print(f"{label} vs REF: {same} identical shape, {diff} different, {broke} broken")
        for n in notes:
            print(f"   {n}")
        # a geometry jump is a defect in its own right, whatever REF did
        for i, (name, _, _) in enumerate(CASES):
            b = results[label][i]
            if b["ok"] and b["gap"] is not None and b["gap"] > GAP_KM:
                a, c = b["where"]
                print(f"   GEOMETRY JUMP in {label}: {name} — {b['gap']:.2f} km "
                      f"({a[0]:.4f},{a[1]:.4f} -> {c[0]:.4f},{c[1]:.4f})")
        print()

json.dump({l: results[l] for l in LABELS}, open("/data/route-results.json", "w"), default=str)
