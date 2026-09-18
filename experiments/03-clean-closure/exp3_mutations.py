"""Experiment 3: two CLEAN topology mutations.

M2 attached to a node of a PRIMARY way, which made that node a junction and split a level-0 edge.
Its blast radius therefore mixed "a local street appeared" with "a highway was cut in two". These
two separate them:

  M3   attach a new residential way to a node of an existing RESIDENTIAL way, deep inside an
       L2 tile, where every way meeting that node is local-class. Nothing at level 0 or 1 is
       touched by the edit itself.

  M4   the same kind of edit, but within ~1 km of the L2 tile boundary, to see whether a
       horizontal dependency between neighbouring L2 tiles exists at all.

Local classes only — residential, unclassified, living_street, service. `primary`, `trunk` and
`motorway` are level 0 in Valhalla (confirmed in experiment 1: the renamed primary's name
appeared in the level-0 tile and nowhere else); `secondary` and `tertiary` are level 1.
"""
import os
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

HOME = pathlib.Path(os.environ["HOME"])
DET = HOME / "det"
SRC = DET / "src" / "moldova.osm.pbf"
WORK = DET / "mut"
WORK.mkdir(exist_ok=True)

W, S, E, N = 28.50, 47.50, 28.75, 47.75          # tile 2/000/792/834
LOCAL = {"residential", "unclassified", "living_street", "service", "track"}


def run(*a):
    subprocess.run(a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


xml = WORK / "tile.osm"
if not xml.exists():
    run("osmium", "extract", "-b", f"{W},{S},{E},{N}", str(SRC), "-o", str(WORK / "t.pbf"),
        "--overwrite")
    run("osmium", "cat", str(WORK / "t.pbf"), "-o", str(xml), "--overwrite")

root = ET.parse(xml).getroot()
nodes = {n.get("id"): (float(n.get("lat")), float(n.get("lon")))
         for n in root.iter("node") if n.get("lat")}

# Which ways use each node, and of what class — so we can require that a chosen node is met
# ONLY by local-class roads.
uses = {}
ways = {}
for w in root.iter("way"):
    tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
    hw = tags.get("highway")
    if not hw:
        continue
    refs = [nd.get("ref") for nd in w.findall("nd")]
    ways[w.get("id")] = (hw, refs)
    for r in refs:
        uses.setdefault(r, []).append((w.get("id"), hw))


def edge_distance(lat, lon):
    return min(lat - S, N - lat, lon - W, E - lon)


def pick(want_deep: bool):
    """A node met only by local roads, either deep inside the tile or close to its edge."""
    best = None
    for wid, (hw, refs) in ways.items():
        if hw not in LOCAL:
            continue
        for r in refs:
            if r not in nodes:
                continue
            if any(cls not in LOCAL for _, cls in uses.get(r, [])):
                continue                      # a higher-class road meets here -- reject
            lat, lon = nodes[r]
            d = edge_distance(lat, lon)
            if want_deep:
                score = d
                if d < 0.05:
                    continue
            else:
                score = -d
                if d > 0.012:                 # within roughly a kilometre of the boundary
                    continue
            if best is None or score > best[0]:
                best = (score, r, wid, hw, lat, lon, d)
    return best


def write_osc(name, anchor, lat, lon, node_ids, way_id):
    osc = ET.Element("osmChange", {"version": "0.6", "generator": "wedrive"})
    create = ET.SubElement(osc, "create")
    common = {"version": "1", "timestamp": "2026-09-18T00:00:00Z", "changeset": "1",
              "uid": "1", "user": "wedrive"}
    for nid, (dla, dlo) in zip(node_ids, ((0.0006, 0.0006), (0.0012, 0.0012))):
        ET.SubElement(create, "node", {"id": nid, "lat": f"{lat+dla:.7f}",
                                       "lon": f"{lon+dlo:.7f}", **common})
    w = ET.SubElement(create, "way", {"id": way_id, **common})
    for r in (anchor, *node_ids):
        ET.SubElement(w, "nd", {"ref": r})
    for k, v in (("highway", "residential"), ("name", f"WEDRIVE-{name}"),
                 ("surface", "asphalt")):
        ET.SubElement(w, "tag", {"k": k, "v": v})
    ET.ElementTree(osc).write(WORK / f"{name.lower()}.osc", encoding="utf-8",
                              xml_declaration=True)


PLAN = [("M3", True, ("9100000001", "9100000002"), "9100000001"),
        ("M4", False, ("9200000001", "9200000002"), "9200000001")]

for name, deep, nids, wid_new in PLAN:
    got = pick(deep)
    if not got:
        sys.exit(f"{name}: no suitable local-only node found")
    _, anchor, wid, hw, lat, lon, d = got
    print(f"{name}  ({'deep inside' if deep else 'near the tile boundary'})")
    print(f"    anchor node   {anchor} at {lat:.5f},{lon:.5f}")
    print(f"    on way        {wid}  highway={hw}")
    print(f"    ways meeting it: {[(w, c) for w, c in uses[anchor]]}")
    print(f"    distance to the nearest tile edge: {d:.4f} deg (~{d*111:.1f} km)")
    write_osc(name, anchor, lat, lon, nids, wid_new)

    tmp = DET / "src" / f"{name.lower()}-unsorted.osm.pbf"
    out = DET / "src" / f"moldova-{name.lower()}.osm.pbf"
    run("osmium", "apply-changes", str(SRC), str(WORK / f"{name.lower()}.osc"),
        "-o", str(tmp), "--overwrite")
    run("osmium", "sort", str(tmp), "-o", str(out), "--overwrite")
    tmp.unlink()
    print(f"    -> {out.name}  {out.stat().st_size} bytes\n")
