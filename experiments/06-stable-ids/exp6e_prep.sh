#!/usr/bin/env bash
# Run INSIDE the Valhalla container, where we are root and need no sudo.
set -u
echo "=== what is already here ==="
for t in zstd xdelta3 bsdiff bspatch python3; do
  printf '%-10s %s\n' "$t" "$(command -v "$t" || echo MISSING)"
done
echo
echo "=== installing what is missing ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq zstd xdelta3 bsdiff >/dev/null 2>&1
for t in zstd xdelta3 bsdiff bspatch; do
  printf '%-10s %s\n' "$t" "$(command -v "$t" || echo STILL-MISSING)"
done
zstd --version 2>&1 | head -1
xdelta3 -V 2>&1 | head -1
