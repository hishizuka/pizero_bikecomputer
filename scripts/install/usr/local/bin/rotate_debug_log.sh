#!/bin/bash
set -euo pipefail
LOG=
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")

if [[ ! -f "$LOG" ]]; then
  : > "$LOG"
  exit 0
fi

ARCHIVE="${LOG}-${STAMP}"
mv "$LOG" "$ARCHIVE"

if [[ ! -s "$ARCHIVE" ]]; then
  rm -f "$ARCHIVE"
fi

: > "$LOG"