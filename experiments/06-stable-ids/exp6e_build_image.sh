#!/usr/bin/env bash
# A one-off image: stock Valhalla 3.6.3 plus the three delta tools. Built locally, never pushed.
set -eu
D="$HOME/exp6img"; mkdir -p "$D"
cat > "$D/Dockerfile" <<'EOF'
FROM ghcr.io/valhalla/valhalla@sha256:2b19ea46551a9687b245022551183829d817fdee9b58c5e7b2adb6e422749c43
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq zstd xdelta3 bsdiff && rm -rf /var/lib/apt/lists/*
EOF
docker build -q -t wedrive-delta:3.6.3 "$D" >/dev/null
docker run --rm wedrive-delta:3.6.3 bash -c 'zstd --version | head -1; xdelta3 -V 2>&1 | head -1; echo "bsdiff: $(command -v bsdiff)"'
