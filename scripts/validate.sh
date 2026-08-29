#!/usr/bin/env bash
# OpsPilot end-to-end validation harness (07_VALIDATION / 08_DEMO).
#
# Proves the full loop from a CLEAN baseline, TWICE, with hard assertions:
#   reset -> assert healthy -> inject incident -> detect (assert gated rollback)
#         -> refuse (assert BLOCKED + cluster UNCHANGED)
#         -> approve (assert RESOLVED + dual-signal verification PASS)
# then a final reset so the cluster is left clean.
#
# Fixtures (inject/reset) are the sanctioned incident tooling — they are NOT the
# agent. All agent decisions/assertions run through validate_incident.py against
# the live cluster. Exit code 0 iff every run passes.
#
# Run from anywhere:  bash opspilot/scripts/validate.sh
set -uo pipefail
export PATH="$PATH:$HOME/.rd/bin"
export PYTHONIOENCODING=utf-8

PY="/c/Users/shivraj/Desktop/Devops/opspilot/orchestrator/.venv/Scripts/python.exe"
ORCH="C:/Users/shivraj/Desktop/Devops/opspilot/orchestrator"
HERE="$(cd "$(dirname "$0")" && pwd)"

RUNS="${1:-2}"          # number of clean runs (default 2)
overall=0

for run in $(seq 1 "$RUNS"); do
  echo ""
  echo "==================== CLEAN RUN $run / $RUNS ===================="

  echo "[fixture] reset to healthy baseline"
  if ! bash "$HERE/reset_healthy.sh" >/dev/null 2>&1; then
    echo "  reset FAILED (rollout did not become healthy)"; overall=1; continue
  fi

  echo "[assert]  precondition: clean baseline"
  if ! "$PY" "$ORCH/check_healthy.py"; then
    echo "  precondition FAILED — not starting from a clean state"; overall=1; continue
  fi

  echo "[fixture] inject incident (bad image)"
  bash "$HERE/inject_incident.sh" >/dev/null 2>&1

  echo "[assert]  OpsPilot loop (detect -> gate -> approve -> verify)"
  "$PY" "$ORCH/validate_incident.py"
  rc=$?
  if [ "$rc" -ne 0 ]; then echo ">> RUN $run FAILED (rc=$rc)"; overall=1; else echo ">> RUN $run PASSED"; fi
done

echo ""
echo "[fixture] final reset to healthy baseline"
bash "$HERE/reset_healthy.sh" >/dev/null 2>&1 || echo "  (warning) final reset did not confirm healthy"

echo "================================================================"
if [ "$overall" -eq 0 ]; then
  echo "VALIDATION: ALL $RUNS RUN(S) PASSED"
else
  echo "VALIDATION: FAILURES DETECTED"
fi
exit "$overall"
