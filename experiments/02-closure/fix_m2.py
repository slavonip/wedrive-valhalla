"""M2 again, with ids that do not break PBF sort order.

`osmium apply-changes` happily wrote the negative ids a .osc normally uses for not-yet-uploaded
objects, and valhalla_build_tiles refused the result with "Detected unsorted input data": a PBF
must be ordered by type then ascending id, and -1001 does not sort after 9 999 999 999.

So: high positive ids past anything real, plus an explicit `osmium sort` pass, which makes the
ordering a property of the file rather than a hope about the merge.
"""
import os
import pathlib
import subprocess
import xml.etree.ElementTree as ET

HOME = pathlib.Path(os.environ["HOME"])
DET = HOME / "det"
SRC = DET / "src" / "moldova.osm.pbf"
WORK = DET / "mut"

ANCHOR = "565330077"
ALAT, ALON = 47.57479, 28.56396
N1, N2, W1 = "9000000001", "9000000002", "9000000001"


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


osc = ET.Element("osmChange", {"version": "0.6", "generator": "wedrive"})
create = ET.SubElement(osc, "create")
common = {"version": "1", "timestamp": "2026-09-18T00:00:00Z", "changeset": "1",
          "uid": "1", "user": "wedrive"}
for nid, (dla, dlo) in ((N1, (0.0007, 0.0007)), (N2, (0.0014, 0.0014))):
    ET.SubElement(create, "node",
                  {"id": nid, "lat": f"{ALAT + dla:.7f}", "lon": f"{ALON + dlo:.7f}", **common})
w = ET.SubElement(create, "way", {"id": W1, **common})
for r in (ANCHOR, N1, N2):
    ET.SubElement(w, "nd", {"ref": r})
for k, v in (("highway", "residential"), ("name", "WEDRIVE-M2"), ("surface", "asphalt")):
    ET.SubElement(w, "tag", {"k": k, "v": v})
ET.ElementTree(osc).write(WORK / "m2.osc", encoding="utf-8", xml_declaration=True)

tmp = DET / "src" / "m2-unsorted.osm.pbf"
out = DET / "src" / "moldova-m2.osm.pbf"
run("osmium", "apply-changes", str(SRC), str(WORK / "m2.osc"), "-o", str(tmp), "--overwrite")
run("osmium", "sort", str(tmp), "-o", str(out), "--overwrite")
tmp.unlink()

print(f"M2 rebuilt: {out.name}  {out.stat().st_size} bytes "
      f"(original {SRC.stat().st_size})")
print(f"   new way {W1}: {ANCHOR} -> {N1} -> {N2}, attached at {ALAT},{ALON}")

# Prove the change is exactly what we think it is, by diffing the object counts.
for label, p in (("original", SRC), ("m2", out)):
    r = subprocess.run(["osmium", "fileinfo", "-e", "-g",
                        "data.count.nodes,data.count.ways", str(p)],
                       capture_output=True, text=True)
    print(f"   {label:<9} nodes/ways: {' '.join(r.stdout.split())}")
