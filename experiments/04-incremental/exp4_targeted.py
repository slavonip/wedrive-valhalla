"""Experiment 4, part 4: probes built FROM the stale references, not chosen by hand.

The eight general routes may never traverse a particular stale reference, and a green result
there would say nothing. These probes are derived from the references themselves: for each T0
tile that provably holds a GraphId pointing into a renumbered tile, route from that tile towards
the tile it points at, so the reference is on the path by construction.

A probe only counts if REF answers it. A pair REF cannot route says nothing about BROKEN_MIXED.
"""
import hashlib
import json
import math
import subprocess
import sys

GAP_KM = 5.0
LABELS = ["REF", "MINIMAL_MIXED", "BROKEN_MIXED", "MIXED"]


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
    w, where = 0.0, None
    for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
        dla, dlo = math.radians(a2 - a1), math.radians(o2 - o1)
        h = (math.sin(dla / 2) ** 2 + math.cos(math.radians(a1)) * math.cos(math.radians(a2))
             * math.sin(dlo / 2) ** 2)
        km = 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))
        if km > w:
            w, where = km, ((a1, o1), (a2, o2))
    return w, where


def route(label, frm, to):
    req = {"locations": [{"lat": frm[0], "lon": frm[1]}, {"lat": to[0], "lon": to[1]}],
           "costing": "auto"}
    try:
        out = subprocess.run(["valhalla_service", f"/data/{label}/valhalla.json", "route",
                              json.dumps(req)], capture_output=True, text=True,
                             timeout=300).stdout
        doc = json.loads(out)
    except Exception as exc:                        # noqa: BLE001
        return {"ok": False, "why": repr(exc)[:70]}
    if "trip" not in doc:
        return {"ok": False, "why": str(doc.get("error", "no trip"))[:70]}
    trip = doc["trip"]
    shape = "".join(l.get("shape") or "" for l in trip.get("legs") or [])
    pts = decode6(shape) if shape else []
    gap, where = worst_gap(pts) if len(pts) > 1 else (None, None)
    return {"ok": True, "km": trip["summary"]["length"], "s": trip["summary"]["time"],
            "gap": gap, "where": where, "sha": hashlib.sha256(shape.encode()).hexdigest()[:10]}


probes = json.load(open("/data/closure.json"))["probes"]
if not probes:
    print("no stale references were found, so there is nothing to probe")
    sys.exit(0)

print(f"{len(probes)} targeted probes, each aimed along a proven stale reference\n")
print(f"{'probe':<44} " + "".join(f"{l:<22}" for l in LABELS))
print("-" * (44 + 22 * len(LABELS)))

verdicts = []
for p in probes:
    res = {l: route(l, p["from"], p["to"]) for l in LABELS}
    if not res["REF"]["ok"]:
        print(f"{p['label'][:43]:<44} REF cannot route this pair — probe discarded")
        continue
    row = f"{p['label'][:43]:<44} "
    for l in LABELS:
        r = res[l]
        row += (f"{'NO ROUTE':<22}" if not r["ok"]
                else f"{r['km']:7.1f}km {r['sha']:<11} ")
    print(row)
    ref = res["REF"]
    for l in ("BROKEN_MIXED", "MINIMAL_MIXED", "MIXED"):
        r = res[l]
        if not r["ok"]:
            verdicts.append((l, p["label"], "NO ROUTE where REF routes"))
        elif r["sha"] != ref["sha"]:
            verdicts.append((l, p["label"],
                             f"different path: {r['km']:.1f} vs {ref['km']:.1f} km"))
        elif r["gap"] and r["gap"] > GAP_KM:
            verdicts.append((l, p["label"], f"geometry jump {r['gap']:.2f} km"))

print()
for label in ("BROKEN_MIXED", "MINIMAL_MIXED", "MIXED"):
    bad = [v for v in verdicts if v[0] == label]
    print(f"{label:<14} differs from REF on {len(bad)} of {len(probes)} targeted probes")
    for _, name, why in bad[:6]:
        print(f"      {name[:60]}  —  {why}")
