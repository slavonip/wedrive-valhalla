"""Build two minimally-changed copies of the Moldova PBF, and say exactly what changed.

Target tile 792834 — L2, bbox 28.50,47.50 .. 28.75,47.75, all eight neighbours built, 1.2 MB.
Chosen over Chisinau's tile (12 MB) because a smaller tile makes the blast radius readable.

Two mutations, run as separate builds, because they ask different questions:

  M1  change ONE TAG on one existing way      no topology change, no new objects
  M2  add ONE NEW WAY plus two new nodes      an insertion, which is what shifts indices

If M1 changes only its own tile and M2 changes many, the difference IS the answer about
instability under changed input.
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

W, S, E, N = 28.50, 47.50, 28.75, 47.75
MARGIN = 0.03          # keep well clear of the tile edges, so we are not testing the boundary


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


tile_pbf = WORK / "tile.osm.pbf"
tile_xml = WORK / "tile.osm"
if not tile_xml.exists():
    run("osmium", "extract", "-b", f"{W},{S},{E},{N}", str(SRC), "-o", str(tile_pbf),
        "--overwrite")
    run("osmium", "cat", str(tile_pbf), "-o", str(tile_xml), "--overwrite")

tree = ET.parse(tile_xml)
root = tree.getroot()
nodes = {n.get("id"): (float(n.get("lat")), float(n.get("lon")))
         for n in root.iter("node") if n.get("lat")}

candidates = []
for way in root.iter("way"):
    tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
    if "highway" not in tags or "name" not in tags:
        continue
    refs = [nd.get("ref") for nd in way.findall("nd")]
    pts = [nodes[r] for r in refs if r in nodes]
    if len(pts) != len(refs) or len(pts) < 4:
        continue                       # incomplete in this extract, or too short to be typical
    if not all(S + MARGIN < la < N - MARGIN and W + MARGIN < lo < E - MARGIN for la, lo in pts):
        continue                       # must be wholly clear of the tile edges
    candidates.append((len(refs), way, tags, pts))

if not candidates:
    sys.exit("no suitable way found well inside the tile")

candidates.sort(key=lambda c: abs(c[0] - 8))       # a middling number of nodes, nothing exotic
_, way, tags, pts = candidates[0]
wid, ver = way.get("id"), int(way.get("version", "1"))
mid = pts[len(pts) // 2]

print("TARGET WAY")
print(f"   osm way id   {wid}  version {ver}")
print(f"   highway      {tags.get('highway')}")
print(f"   name         {tags.get('name')}")
print(f"   nodes        {len(pts)}")
print(f"   midpoint     {mid[0]:.5f}, {mid[1]:.5f}")
print(f"   tile         2/000/792/834.gph   bbox {W},{S} .. {E},{N}")


def way_xml(action_version, extra_tags=None, tag_overrides=None):
    o = ET.Element("way", {"id": wid, "version": str(action_version),
                           "timestamp": "2026-09-18T00:00:00Z", "changeset": "1", "uid": "1",
                           "user": "wedrive"})
    for nd in way.findall("nd"):
        ET.SubElement(o, "nd", {"ref": nd.get("ref")})
    merged = dict(tags)
    merged.update(tag_overrides or {})
    merged.update(extra_tags or {})
    for k, v in merged.items():
        ET.SubElement(o, "tag", {"k": k, "v": v})
    return o


# ── M1: one tag, on one existing way ────────────────────────────────────────────────────────
osc = ET.Element("osmChange", {"version": "0.6", "generator": "wedrive"})
mod = ET.SubElement(osc, "modify")
mod.append(way_xml(ver + 1, tag_overrides={"name": tags["name"] + " WEDRIVE-M1"}))
ET.ElementTree(osc).write(WORK / "m1.osc", encoding="utf-8", xml_declaration=True)
print(f"\nM1  rename way {wid}: '{tags['name']}' -> '{tags['name']} WEDRIVE-M1'")

# ── M2: a NEW way and two NEW nodes, attached to an existing node of the same way ───────────
# Attached rather than floating: an unconnected edge may be filtered out of the graph entirely,
# and then the experiment would measure the filter rather than the insertion.
anchor = way.findall("nd")[len(pts) // 2].get("ref")
alat, alon = nodes[anchor]
osc2 = ET.Element("osmChange", {"version": "0.6", "generator": "wedrive"})
create = ET.SubElement(osc2, "create")
NEW_N1, NEW_N2, NEW_W = "-1001", "-1002", "-2001"
for nid, (dla, dlo) in ((NEW_N1, (0.0007, 0.0007)), (NEW_N2, (0.0014, 0.0014))):
    ET.SubElement(create, "node", {"id": nid, "version": "1", "lat": f"{alat + dla:.7f}",
                                   "lon": f"{alon + dlo:.7f}", "timestamp": "2026-09-18T00:00:00Z",
                                   "changeset": "1", "uid": "1", "user": "wedrive"})
nw = ET.SubElement(create, "way", {"id": NEW_W, "version": "1",
                                   "timestamp": "2026-09-18T00:00:00Z", "changeset": "1",
                                   "uid": "1", "user": "wedrive"})
for r in (anchor, NEW_N1, NEW_N2):
    ET.SubElement(nw, "nd", {"ref": r})
for k, v in (("highway", "residential"), ("name", "WEDRIVE-M2"), ("surface", "asphalt")):
    ET.SubElement(nw, "tag", {"k": k, "v": v})
ET.ElementTree(osc2).write(WORK / "m2.osc", encoding="utf-8", xml_declaration=True)
print(f"M2  new residential way + 2 new nodes, attached to existing node {anchor} "
      f"at {alat:.5f},{alon:.5f}")

# ── apply ───────────────────────────────────────────────────────────────────────────────────
for label in ("m1", "m2"):
    out = DET / "src" / f"moldova-{label}.osm.pbf"
    run("osmium", "apply-changes", str(SRC), str(WORK / f"{label}.osc"), "-o", str(out),
        "--overwrite")
    print(f"\n{label}: {out.name}  {out.stat().st_size} bytes")

print("\nsize of the untouched original:", SRC.stat().st_size, "bytes")
