# cw-execution-approvals

## Native component controller gateway

`component-gateway.yml` connects the private native four-worker controller to
the protected `paid-one-shot` approval environment. Its default is read-only
preflight. It accepts only immutable source/order/spec revisions and digests;
private task text and request records are never printed or committed here.

The existing aggregate package and immutable historical cost/unknown records
are retained. Insufficient concurrent reserves or request slots stop before
any write, marker, queue preparation or dispatch. The current frozen package
cannot fund a four-worker wave; this code does not increase its ceiling or
refund historical records. Changing that package requires a separately
authorized, consistent update to the private controller and its budget policy.

A launch consumes one order marker, waits for OFF-only native graph preparation,
arms the independent watchdog and only then enables the existing execution
flags. Both immutable owner runs must remain active within the original
45-minute window. Completion, expiry, unreadable evidence and unknown outcomes
cause both flags to be written false and read back. The watchdog cannot enable
execution. The scheduled fallback supports both legacy code leases and the
component lease. No uncertain dispatch is repeated.

Offline transport simulations verify these boundaries. They do not establish
a successful live four-worker graph or a native Result. Run a fresh OFF selftest
at the exact public revision before any protected launch.

## Historical Phase 0 setup notes

Minimal, public, owner-controlled **approval gate**, currently in **Phase 0: NO SPEND / NO MODEL**.

This repository does **not** contain trading software, private project source code, credentials or a workflow capable of launching paid agents. No billing authorization is granted.

## Phase 0 — mandatory reviewer smoke test

The sole workflow, `.github/workflows/owner-review-probe.yml`, can run only from a manual owner trigger on `main`. It requires the `paid-one-shot` GitHub Environment and has `permissions: {}`. Its one job prints a constant confirmation and does not use secrets, fetch private data, or dispatch other workflows.

**Before running:** the owner must configure Settings → Environments → `paid-one-shot` with Required reviewers = owner, allow self-review for this single-owner account, and limit deployment branches to the exact `main` branch. Protect `main` from unreviewed writes, force pushes and deletion to the extent supported by GitHub. These settings have not been verified yet.

**Validation:** when the owner manually runs the workflow, it must remain **waiting for approval**, and the owner should verify that state before clicking Review deployments → Approve and deploy. Merely seeing a green workflow does **not** establish protection. If it runs without approval, STOP.

No secrets or source-repo write tokens should be installed until both the reviewer barrier and independent shutdown design are separately approved and verified. Before any future secret is stored, revoke all unnecessary third-party application write permissions to this repository.

Each future paid experiment needs a new explicit owner approval and a budget; the public repository's creation itself is not approval.

Public workflow code and logs are visible to everyone. Do not commit or print private tasks, API tokens, project spending records or trading data.
