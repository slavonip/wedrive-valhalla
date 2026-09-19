#!/usr/bin/env bash
set -u
V=/src/valhalla/src/thor/bidirectional_astar.cc
docker exec vhdev bash -c "
  echo '===== где устанавливается соединение и порог'
  grep -n 'SetForwardConnection\|SetReverseConnection\|cost_threshold_\|best_connection_\|threshold' $V | head -30
"
