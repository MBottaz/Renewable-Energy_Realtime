#!/usr/bin/env bash
set -euo pipefail

PARENT_ROOT="${PI_SIDE_PARENT_REPO:-${1:-}}"
AGENT_ID="${PI_SIDE_AGENT_ID:-${2:-unknown}}"
MAIN_BRANCH="main"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ "$BRANCH" == "HEAD" ]]; then
  BRANCH=""
fi

if [[ -z "$PARENT_ROOT" ]]; then
  echo "[side-agent-finish] Missing parent checkout path."
  echo "Usage: PI_SIDE_PARENT_REPO=/path/to/parent .pi/side-agent-finish.sh"
  exit 1
fi

if [[ -z "$BRANCH" ]]; then
  echo "[side-agent-finish] Could not determine current branch."
  exit 1
fi

LOCK_DIR="$PARENT_ROOT/.pi/side-agents"
LOCK_FILE="$LOCK_DIR/merge.lock"
mkdir -p "$LOCK_DIR"

MERGE_LOCK_TIMEOUT=120

iso_now() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

acquire_lock() {
  local payload started elapsed
  payload="{\"agentId\":\"$AGENT_ID\",\"pid\":$$,\"acquiredAt\":\"$(iso_now)\"}"
  started=$(date +%s)
  while true; do
    if ( set -o noclobber; printf '%s\n' "$payload" > "$LOCK_FILE" ) 2>/dev/null; then
      return 0
    fi
    elapsed=$(( $(date +%s) - started ))

    # Check if the lock holder is still alive (stale lock after crash/reboot)
    if [[ -f "$LOCK_FILE" ]]; then
      local holder_pid
      holder_pid="$(grep -o '"pid":[0-9]*' "$LOCK_FILE" 2>/dev/null | head -n 1 | grep -o '[0-9]*' || true)"
      if [[ -n "$holder_pid" ]] && ! kill -0 "$holder_pid" 2>/dev/null; then
        echo "[side-agent-finish] Removing stale merge lock (pid $holder_pid no longer running)."
        rm -f "$LOCK_FILE"
        continue
      fi
    fi

    if [[ "$elapsed" -ge "$MERGE_LOCK_TIMEOUT" ]]; then
      echo "[side-agent-finish] Timed out after ${MERGE_LOCK_TIMEOUT}s waiting for merge lock."
      echo "[side-agent-finish] Stale lock? Inspect: $LOCK_FILE"
      exit 3
    fi
    echo "[side-agent-finish] Waiting for merge lock... (${elapsed}s / ${MERGE_LOCK_TIMEOUT}s)"
    sleep 1
  done
}

release_lock() {
  rm -f "$LOCK_FILE" || true
}

trap 'release_lock' EXIT

while true; do
  echo "[side-agent-finish] Reconciling child branch: git rebase $MAIN_BRANCH"
  if ! git rebase "$MAIN_BRANCH"; then
    echo "[side-agent-finish] Conflict while rebasing $BRANCH onto $MAIN_BRANCH."
    echo "Resolve conflicts (git status / git rebase --continue), then rerun .pi/side-agent-finish.sh"
    exit 2
  fi

  acquire_lock

  set +e
  (
    cd "$PARENT_ROOT" || exit 1
    git checkout "$MAIN_BRANCH" >/dev/null 2>&1 || exit 1
    git merge --ff-only "$BRANCH"
  )
  merge_status=$?
  set -e

  release_lock

  if [[ "$merge_status" -eq 0 ]]; then
    echo "[side-agent-finish] Success: fast-forwarded $MAIN_BRANCH to include $BRANCH in parent checkout."
    rm -f "$(pwd)/.pi/active.lock" || true
    exit 0
  fi

  echo "[side-agent-finish] Parent fast-forward failed (likely $MAIN_BRANCH moved)."
  echo "[side-agent-finish] Retrying rebase reconcile loop..."

  sleep 1
done