#!/usr/bin/env bash
# Gate 3 — inject the deterministic incident.
# Ships a bad image (ticketbooking:1.1, baked HEALTHY=false). New pods fail the
# readiness probe (/health -> 503) and stay Running-but-NotReady; the rollout
# stalls while the previous healthy pods keep serving (maxUnavailable: 0).
# Fully reversible via reset_healthy.sh or `kubectl rollout undo`.
set -euo pipefail
export PATH="$PATH:$HOME/.rd/bin"
NS=opspilot
DEP=ticket-booking

kubectl -n "$NS" set image "deployment/$DEP" app=ticketbooking:1.1
kubectl -n "$NS" annotate "deployment/$DEP" \
  kubernetes.io/change-cause="Deploy ticketbooking:1.1 (regression)" --overwrite
echo "Injected bad image ticketbooking:1.1."
echo "Watch:  kubectl -n $NS get pods -w"
