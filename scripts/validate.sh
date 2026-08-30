#!/usr/bin/env bash
# KubeMedic end-to-end validation against a live cluster.
#
# Proves the whole loop with hard assertions:
#   healthy -> inject -> observe -> correlate -> propose
#           -> reject (reason required) -> revise
#           -> approve -> execute -> verify -> resolve -> reset
#
# Exit code 0 only if every check passes. The assertions live in
# scripts/validate_incident.py; this wrapper only locates the interpreter and
# the repository.
#
# Run from anywhere:  bash scripts/validate.sh
set -uo pipefail

# Rancher Desktop puts kubectl here. Harmless if the directory is absent.
export PATH="$PATH:$HOME/.rd/bin"
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"

KUBEMEDIC_BASH="$(command -v bash)"
export KUBEMEDIC_BASH

PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi

echo "repository: $REPO"
echo "python:     $($PY --version 2>&1)"

exec "$PY" scripts/validate_incident.py "$@"
