#!/usr/bin/env bash
# Restore the healthy baseline (good image ticketbooking:1.0).
# Used for test hygiene between runs. The orchestrator's real remediation path
# uses `kubectl rollout undo` to achieve the same recovery.
set -euo pipefail
export PATH="$PATH:$HOME/.rd/bin"
NS=opspilot
DEP=ticket-booking

kubectl -n "$NS" set image "deployment/$DEP" app=ticketbooking:1.0
kubectl -n "$NS" annotate "deployment/$DEP" \
  kubernetes.io/change-cause="Restore ticketbooking:1.0 (healthy)" --overwrite
kubectl -n "$NS" rollout status "deployment/$DEP" --timeout=120s
echo "Restored healthy baseline (ticketbooking:1.0)."
