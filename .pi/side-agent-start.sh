#!/usr/bin/env bash
set -euo pipefail

PARENT_ROOT="${1:-}"
WORKTREE="${2:-$(pwd)}"
AGENT_ID="${3:-unknown}"
MAIN_BRANCH="main"

BRANCH="$(git -C "$WORKTREE" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ "$BRANCH" == "HEAD" ]]; then
  BRANCH=""
fi
if [[ -z "$BRANCH" ]]; then
  echo "[side-agent-start] Could not determine current branch in $WORKTREE."
  exit 1
fi

echo "[side-agent-start] agent=$AGENT_ID branch=$BRANCH main=$MAIN_BRANCH"

if [[ "$BRANCH" == "$MAIN_BRANCH" ]]; then
  echo "[side-agent-start] ERROR: child worktree is on $MAIN_BRANCH; expected a dedicated agent branch."
  exit 1
fi

# The worktree is already set to the parent's HEAD by the TypeScript extension.
# Just verify it's on the right branch.
echo "[side-agent-start] Worktree based on parent HEAD ($(git -C "$WORKTREE" rev-parse --short HEAD))."

# Bootstrap: regenerate mock data if generate_mock_data.py has changed
if [[ -x "$WORKTREE/generate_mock_data.py" ]]; then
  echo "[side-agent-start] Regenerating mock data..."
  cd "$WORKTREE"
  python3 generate_mock_data.py
fi