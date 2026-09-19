#!/usr/bin/env bash
set -u
SP="/mnt/c/Users/vpere/AppData/Local/Temp/claude/C--Users-vpere-AndroidStudioProjects-wedrive/9d672018-fcd7-4735-9e25-f33a3c723c7f/scratchpad"
mkdir -p "$HOME/wd-tools"
sed 's/\r$//' "$SP/fork/wedrive/tools/compare_long_route.sh" > "$HOME/wd-tools/compare_long_route.sh"
sed 's/\r$//' "$SP/fork/wedrive/tools/shape_divergence.py" > "$HOME/wd-tools/shape_divergence.py"
chmod +x "$HOME/wd-tools/compare_long_route.sh"
bash "$HOME/wd-tools/compare_long_route.sh"
