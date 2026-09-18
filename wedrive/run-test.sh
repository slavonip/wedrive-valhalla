#!/usr/bin/env bash
# Install the patched library, compile the test against it, run it on the two real builds.
set -u

echo "=== install the freshly patched library ==="
docker exec vhdev bash -c 'make -C /src/valhalla/build install 2>&1 | tail -3'

echo
echo "=== compile the test ==="
docker exec vhdev bash -c '
  set -e
  cd /tmp
  if pkg-config --exists libvalhalla; then
    echo "  using pkg-config"
    g++ -std=c++17 -O1 wedrive_regions_test.cc -o regions_test \
      $(pkg-config --cflags --libs libvalhalla) 2>&1 | head -25
  else
    echo "  pkg-config has no libvalhalla; linking by hand"
    g++ -std=c++17 -O1 wedrive_regions_test.cc -o regions_test \
      -I/src/valhalla -I/src/valhalla/valhalla -I/src/valhalla/build \
      -I/src/valhalla/third_party/date/include \
      -I/src/valhalla/third_party/rapidjson/include \
      -L/src/valhalla/build/src -lvalhalla \
      -lprotobuf-lite -lz -lboost_program_options \
      -lsqlite3 -lspatialite -lgeos_c -lluajit-5.1 -lcurl -lpthread 2>&1 | head -25
  fi
  ls -la /tmp/regions_test 2>/dev/null || echo "  BUILD FAILED"'

echo
echo "=== run it against the two independent builds ==="
docker exec vhdev bash -c '/tmp/regions_test /regions/moldova/tiles /regions/romania/tiles'
