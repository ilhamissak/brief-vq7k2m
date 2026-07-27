#!/bin/sh
# One turn: render -> gate -> ledger+push. Aborts before pushing if the gate fails.
set -e
cd "$(dirname "$0")"
python3 render.py
python3 check.py
python3 publish.py "$1" "$2"
