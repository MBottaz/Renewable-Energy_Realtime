---
name: finish
description: Rebase the branch with current work onto upstream and fast-forward it after explicit user sign-off (e.g. "LGTM")
---

# Parallel-agent finish workflow

When the user explicitly approves the work (e.g. says "LGTM", "ship it", "merge it"):

1. **Confirm** the finish action with the user before doing anything.

2. Run the finish script:

```bash
PI_SIDE_PARENT_REPO="$PI_SIDE_PARENT_REPO" .pi/side-agent-finish.sh
```

3. If the finish script exits with code 2 (conflict rebasing child branch onto `main`):
   - Stay in this worktree
   - Resolve conflicts (`git status`, then `git rebase --continue`)
   - Re-run the finish script after the rebase completes

4. If the parent-side fast-forward fails because `main` moved ahead:
   - The finish script retries the rebase reconcile loop automatically
   - Parent-side integration is a bit sensitive operation as it can make big mess; solve simple issues yourself, but escalate to the user with major issues (such as dirty parent worktree)

5. After success: report the landed commit(s). Suggest `/quit` if no further work is needed.