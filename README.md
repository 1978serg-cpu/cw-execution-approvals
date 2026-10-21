# cw-execution-approvals

Minimal, public, owner-controlled **approval gate**, currently in **Phase 0: NO SPEND / NO MODEL**.

This repository does **not** contain trading software, private project source code, credentials or a workflow capable of launching paid agents. No billing authorization is granted.

## Phase 0 — mandatory reviewer smoke test

The sole workflow, `.github/workflows/owner-review-probe.yml`, can run only from a manual owner trigger on `main`. It requires the `paid-one-shot` GitHub Environment and has `permissions: {}`. Its one job prints a constant confirmation and does not use secrets, fetch private data, or dispatch other workflows.

**Before running:** the owner must configure Settings → Environments → `paid-one-shot` with Required reviewers = owner, allow self-review for this single-owner account, and limit deployment branches to the exact `main` branch. Protect `main` from unreviewed writes, force pushes and deletion to the extent supported by GitHub. These settings have not been verified yet.

**Validation:** when the owner manually runs the workflow, it must remain **waiting for approval**, and the owner should verify that state before clicking Review deployments → Approve and deploy. Merely seeing a green workflow does **not** establish protection. If it runs without approval, STOP.

No secrets or source-repo write tokens should be installed until both the reviewer barrier and independent shutdown design are separately approved and verified. Before any future secret is stored, revoke all unnecessary third-party application write permissions to this repository.

Each future paid experiment needs a new explicit owner approval and a budget; the public repository's creation itself is not approval.

Public workflow code and logs are visible to everyone. Do not commit or print private tasks, API tokens, project spending records or trading data.
