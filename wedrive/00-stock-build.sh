#!/usr/bin/env bash
# Experiment 7, step 0: build STOCK Valhalla 3.6.3 from source, unmodified.
#
# Nothing is patched until this works. A first patch on top of a build that was never verified
# makes "my change broke it" and "it never built" indistinguishable — and this project has spent
# enough time on that class of confusion already.
#
# The recipe is upstream's own docker/Dockerfile: ubuntu 24.04, scripts/install-linux-deps.sh,
# cmake Release, make -j. Built locally: 22 cores here against a GitHub runner's 4, and a C++
# edit-compile loop on a remote runner would be unusable.
set -eu
W="$HOME/vhbuild"
mkdir -p "$W"

# The source, WITH submodules — third_party/ is copied by the upstream Dockerfile, so a plain
# clone is not enough and the build would fail late with missing headers.
if [ ! -d "$W/src/.git" ]; then
  echo "==> cloning 3.6.3 with submodules"
  git clone --depth 1 --branch 3.6.3 --recurse-submodules --shallow-submodules \
    https://github.com/valhalla/valhalla.git "$W/src" 2>&1 | tail -3
fi
echo "source: $(du -sh "$W/src" | cut -f1), submodules: $(ls "$W/src/third_party" | wc -l)"

cat > "$W/Dockerfile" <<'EOF'
FROM ubuntu:24.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH
ENV LD_LIBRARY_PATH=/usr/local/lib:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu
RUN apt-get update && apt-get install -y sudo ccache
WORKDIR /src/valhalla
COPY scripts/install-linux-deps.sh scripts/install-linux-deps.sh
RUN bash ./scripts/install-linux-deps.sh
COPY . .
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=gcc \
      -DENABLE_TESTS=Off -DENABLE_SINGLE_FILES_WERROR=Off \
      -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
 && make -C build all -j$(nproc) \
 && make -C build install
EOF

echo "==> building (first time: expect tens of minutes)"
time docker build -f "$W/Dockerfile" -t wedrive-valhalla:stock "$W/src" 2>&1 | tail -25

echo
echo "==> does the freshly built binary agree with the image we have been using?"
docker run --rm wedrive-valhalla:stock bash -c \
  'valhalla_build_tiles --version; valhalla_service --version 2>&1 | head -1; ls /usr/local/lib/libvalhalla* 2>/dev/null | head -3'
