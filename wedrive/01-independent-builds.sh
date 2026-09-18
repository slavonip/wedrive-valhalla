#!/usr/bin/env bash
# Experiment 7, steps 1-2: build MD and RO INDEPENDENTLY and measure what collides.
#
# Not a merged master and not a cut: two separate Mjolnir runs, each knowing nothing of the other,
# which is what the multi-region architecture assumes. Their tile paths are expected to collide —
# the grid is global, so the same 0.25 degree cell has the same filename in both — and their
# contents to disagree, because the ids inside are each build's own.
#
# Stock 3.6.3 throughout. Nothing is patched here; this establishes the ground the reader would
# have to stand on.
set -eu
IMAGE=wedrive-delta:3.6.3
R="$HOME/exp7"
mkdir -p "$R/src"

# Reuse what already exists rather than re-downloading.
[ -f "$R/src/moldova.osm.pbf" ] || cp "$HOME/det/src/moldova.osm.pbf" "$R/src/moldova.osm.pbf"
[ -f "$R/src/romania.osm.pbf" ] || cp "$HOME/exp4/src/romania-260901.osm.pbf" "$R/src/romania.osm.pbf"
for f in moldova romania; do
  printf '%-14s %8s  %s\n' "$f" "$(du -h "$R/src/$f.osm.pbf" | cut -f1)" \
    "$(sha256sum "$R/src/$f.osm.pbf" | cut -c1-16)"
done

build_alone() {
  local name="$1"
  [ -d "$R/$name/tiles" ] && [ "$(find "$R/$name/tiles" -name '*.gph' | wc -l)" -gt 0 ] && {
    echo "  $name already built"; return; }
  rm -rf "$R/$name"; mkdir -p "$R/$name/tiles"
  docker run --rm --user root -v "$R":/data -e name="$name" "$IMAGE" bash -c '
    set -e
    out=/data/$name
    valhalla_build_config --mjolnir-tile-dir $out/tiles \
      --mjolnir-admin $out/admins.sqlite --mjolnir-concurrency 22 > $out/valhalla.json
    python3 - "$out/valhalla.json" <<PY
import json, sys
c = json.load(open(sys.argv[1]))
c["mjolnir"].pop("tile_extract", None); c["mjolnir"].pop("timezone", None)
json.dump(c, open(sys.argv[1], "w"), indent=2)
PY
    valhalla_build_admins -c $out/valhalla.json /data/src/$name.osm.pbf > $out/a.log 2>&1
    valhalla_build_tiles  -c $out/valhalla.json /data/src/$name.osm.pbf > $out/t.log 2>&1
  ' >/dev/null 2>&1
  echo "  $name: $(find "$R/$name/tiles" -name '*.gph' | wc -l) tiles, $(du -sh "$R/$name/tiles" | cut -f1)"
}

echo
echo "=== two independent builds, neither knowing of the other ==="
build_alone moldova
build_alone romania

echo
echo "=== what collides ==="
python3 - <<'PY'
import hashlib, os, pathlib
R = pathlib.Path(os.environ["HOME"]) / "exp7"
def tiles(n):
    b = R / n / "tiles"
    return {str(p.relative_to(b)).replace("\\", "/"): p for p in b.rglob("*.gph")}
md, ro = tiles("moldova"), tiles("romania")
shared = sorted(set(md) & set(ro))
same = [n for n in shared if hashlib.sha256(md[n].read_bytes()).digest()
                          == hashlib.sha256(ro[n].read_bytes()).digest()]
print(f"  moldova {len(md)} tiles   romania {len(ro)} tiles")
print(f"  SAME FILENAME in both: {len(shared)}")
print(f"     byte-identical:     {len(same)}")
for lvl in (0, 1, 2):
    s = [n for n in shared if n.startswith(f"{lvl}/")]
    if s:
        print(f"     level {lvl}: {len(s)}  e.g. {s[:2]}")
print()
print("  so a single tile_dir cannot hold both: one build's file would overwrite the other's,")
print("  and the ids inside are each build's own. THAT is what a region namespace has to fix.")
PY
