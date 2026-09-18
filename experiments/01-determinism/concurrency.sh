#!/usr/bin/env bash
# BASELINE 1b: does the result survive a third run, and does THREAD COUNT change it?
#
# The second question is not academic curiosity. eu-core builds on a 4-core GitHub runner and
# Europe is building on a 16-core Hetzner machine right now. If concurrency changes the bytes,
# then the same PBF on two machines yields two different graphs -- which would break delta
# downloads before they were even attempted, and would mean a build is not reproducible off the
# machine that made it.
set -euo pipefail

IMAGE="ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43"
ROOT="$HOME/det"

build() {
  local label="$1" concurrency="$2"
  local out="$ROOT/$label"
  rm -rf "$out"; mkdir -p "$out/tiles"
  docker run --rm --user root -v "$ROOT":/data \
    -e label="$label" -e concurrency="$concurrency" "$IMAGE" bash -c '
      set -e
      out=/data/$label
      valhalla_build_config --mjolnir-tile-dir $out/tiles \
        --mjolnir-admin $out/admins.sqlite \
        --mjolnir-concurrency $concurrency > $out/valhalla.json
      python3 - "$out/valhalla.json" <<PY
import json, sys
c = json.load(open(sys.argv[1]))
c["mjolnir"].pop("tile_extract", None)
c["mjolnir"].pop("timezone", None)
json.dump(c, open(sys.argv[1], "w"), indent=2)
PY
      valhalla_build_admins -c $out/valhalla.json /data/src/moldova.osm.pbf > $out/admins.log 2>&1
      valhalla_build_tiles  -c $out/valhalla.json /data/src/moldova.osm.pbf > $out/tiles.log 2>&1
    ' >/dev/null 2>&1
  echo "    $label built with concurrency=$concurrency"
}

echo "==> C: a third run at the same concurrency as A and B"
build C "$(nproc)"
echo "==> D: ONE thread"
build D 1
echo "==> E: four threads, the shape of a GitHub runner"
build E 4
echo

python3 - <<'PY'
import hashlib, os, pathlib

root = pathlib.Path(os.environ["HOME"]) / "det"

def digest_set(label):
    base = root / label / "tiles"
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob("*.gph"))}

sets = {l: digest_set(l) for l in "ABCDE"}
ref = sets["A"]

print("                     tiles   identical to A   different   missing/extra")
for label, s in sets.items():
    shared = set(ref) & set(s)
    same = sum(1 for n in shared if ref[n] == s[n])
    diff = len(shared) - same
    extra = len(set(s) ^ set(ref))
    note = ""
    if label in "BC":
        note = "  <- same concurrency as A"
    if label == "D":
        note = "  <- 1 thread"
    if label == "E":
        note = "  <- 4 threads"
    print(f"   {label}   {len(s):>18}   {same:>10}   {diff:>9}   {extra:>12}{note}")

print()
for label in "DE":
    shared = set(ref) & set(sets[label])
    diff = sorted(n for n in shared if ref[n] != sets[label][n])
    if diff:
        print(f"A vs {label}: {len(diff)} tiles differ, e.g. {diff[:4]}")
        name = diff[0]
        a = (root / "A" / "tiles" / name).read_bytes()
        b = (root / label / "tiles" / name).read_bytes()
        off = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), -1)
        print(f"   {name}: {len(a)} vs {len(b)} bytes, first differing byte at {off}")
    else:
        print(f"A vs {label}: every tile identical -- thread count does not change the output")

# and the counters, which are the semantic summary the builder prints about itself
print()
import re
def counters(label):
    txt = (root / label / "tiles.log").read_text(errors="replace")
    return [re.sub(r'^\S+ \S+ ', '', l).strip()
            for l in txt.splitlines()
            if "Finished with" in l or "Directed Edge Count" in l or "Building " in l]
base = counters("A")
for label in "BCDE":
    print(f"counters A vs {label}: {'IDENTICAL' if counters(label) == base else 'DIFFER'}")
PY
