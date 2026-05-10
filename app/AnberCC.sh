#!/bin/bash
# AnberCC launcher dla App Center / dmenu
progdir="$(cd "$(dirname "$0")" || exit; pwd)"/anbercc
export PYSDL2_DLL_PATH="/usr/lib"
export HOME=/root
export PATH="/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
LOG=/mnt/data/anbercc.log
echo "$(date +%H:%M:%S): start" >> "$LOG"
python3 "${progdir}/main.py" >> "$LOG" 2>&1
echo "$(date +%H:%M:%S): exit $?" >> "$LOG"
