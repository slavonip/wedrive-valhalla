#!/usr/bin/env bash
# BASELINE EXPERIMENT 1: is stock Mjolnir 3.6.3 deterministic for identical input?
#
# Nothing is patched here and nothing is diagnosed here. One question only:
#
#     same PBF, same config, same image, same concurrency  ->  same .gph ?
#
# The input file is downloaded ONCE and both builds read that same file, because
# "moldova-latest.osm.pbf" is a moving target and downloading twice would test Geofabrik
# rather than Valhalla.
set -euo pipefail

IMAGE="ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43"
ROOT="$HOME/det"
PBF_URL="https://download.geofabrik.de/europe/moldova-latest.osm.pbf"

mkdir -p "$ROOT/src"
PBF="$ROOT/src/moldova.osm.pbf"

if [ ! -f "$PBF" ]; then
  echo "==> downloading the input ONCE"
  curl -fsSL -o "$PBF" "$PBF_URL"
fi

echo "=============================== INPUT ==============================="
echo "url:    $PBF_URL"
echo "bytes:  $(stat -c%s "$PBF")"
echo "sha256: $(sha256sum "$PBF" | cut -d' ' -f1)"
echo "image:  $IMAGE"
echo "cores:  $(nproc)"
echo

# ── ONE BUILD ───────────────────────────────────────────────────────────────────────────────
# `--user root` and a clean output tree per run. CONCURRENCY is passed in so the same function
# can later answer the single-threaded question, but A and B use the SAME value, as asked.
build() {
  local label="$1"
  local concurrency="$2"
  local out="$ROOT/$label"

  rm -rf "$out"
  mkdir -p "$out/tiles"

  docker run --rm --user root \
    -v "$ROOT":/data \
    -e label="$label" -e concurrency="$concurrency" \
    "$IMAGE" bash -c '
      set -e
      out=/data/$label
      valhalla_build_config \
        --mjolnir-tile-dir $out/tiles \
        --mjolnir-admin $out/admins.sqlite \
        --mjolnir-concurrency $concurrency > $out/valhalla.json
      python3 - "$out/valhalla.json" <<PY
import json, sys
p = sys.argv[1]
c = json.load(open(p))
# popped, never blanked: an empty string makes Valhalla look for a file called ""
c["mjolnir"].pop("tile_extract", None)
c["mjolnir"].pop("timezone", None)
json.dump(c, open(p, "w"), indent=2)
PY
      valhalla_build_admins -c $out/valhalla.json /data/src/moldova.osm.pbf > $out/admins.log 2>&1
      valhalla_build_tiles  -c $out/valhalla.json /data/src/moldova.osm.pbf > $out/tiles.log 2>&1
    ' 2>&1 | tail -3

  echo "    $label: $(find "$out/tiles" -name '*.gph' | wc -l) tiles, $(du -sh "$out/tiles" | cut -f1)"
}

echo "=============================== BUILD A ==============================="
time build A "$(nproc)"
echo
echo "=============================== BUILD B ==============================="
time build B "$(nproc)"
echo

echo "=============================== COMPARE ==============================="
cd "$ROOT"
python3 - <<'PY'
import hashlib, os, pathlib

root = pathlib.Path(os.environ["HOME"]) / "det"

def tiles(label):
    base = root / label / "tiles"
    return {str(p.relative_to(base)): p for p in sorted(base.rglob("*.gph"))}

A, B = tiles("A"), tiles("B")

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

only_a = sorted(set(A) - set(B))
only_b = sorted(set(B) - set(A))
shared = sorted(set(A) & set(B))

identical, different, sized = [], [], []
for name in shared:
    if A[name].stat().st_size != B[name].stat().st_size:
        sized.append(name)
    if sha(A[name]) == sha(B[name]):
        identical.append(name)
    else:
        different.append(name)

print(f"tiles in A            {len(A)}")
print(f"tiles in B            {len(B)}")
print(f"only in A             {len(only_a)}  {only_a[:3]}")
print(f"only in B             {len(only_b)}  {only_b[:3]}")
print(f"shared paths          {len(shared)}")
print(f"  byte-identical      {len(identical)}")
print(f"  byte-different      {len(different)}")
print(f"  differing in SIZE   {len(sized)}  {sized[:5]}")
print()
if different:
    print("first 10 differing tiles, with the first differing byte offset:")
    for name in different[:10]:
        a, b = A[name].read_bytes(), B[name].read_bytes()
        off = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        print(f"   {name:24} {len(a):>9} vs {len(b):>9} bytes   first diff at byte {off}")
else:
    print("every shared tile is byte-identical")

# the admin database is an INPUT to tile building, so its own determinism matters
for extra in ("admins.sqlite",):
    pa, pb = root / "A" / extra, root / "B" / extra
    if pa.exists() and pb.exists():
        print(f"\n{extra}: {'identical' if sha(pa)==sha(pb) else 'DIFFERENT'} "
              f"({pa.stat().st_size} vs {pb.stat().st_size} bytes)")
PY
