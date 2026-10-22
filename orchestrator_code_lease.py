"""Finite code-launch lease and independent OFF policy; never enables a gate.

Shared verbatim with the public approval repository. No provider, queue writes,
secret discovery or grant issuer. API and clocks are injected by trusted hosts.
"""
import datetime as dt
import json
import re

SOURCE = "1978serg-cpu/crypto-watchdog"
PUBLIC = "1978serg-cpu/cw-execution-approvals"
SOURCE_ID, PUBLIC_ID, OWNER_ID = 1423483358, 1428447847, 344015223
OWNER = "1978serg-cpu"
PAID, CODE, LEASE = "CW_CODEX_PAID_ENABLED", "CW_CODEX_CODE_ENABLED", "CW_CODEX_CODE_LEASE"
TTL_SECONDS = 20 * 60
ACTIVE = ("queued", "in_progress", "waiting", "pending")
FIELDS = {"version", "package", "source_sha", "work_id", "controller_run_id", "gateway_run_id",
          "gateway_sha", "issued_at", "expires_at", "cap_cents", "max_requests"}


class LeaseDenied(Exception):
    """Fixed error code only; API bodies and credentials must not be logged."""


def require(value):
    if not value:
        raise LeaseDenied("CODE_LEASE_DENIED")


def unique(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result)
        result[name] = value
    return result


def decode(value, *, now):
    require(type(value) is str and len(value.encode("utf-8")) <= 4096 and type(now) is int)
    try:
        lease = json.loads(value, object_pairs_hook=unique)
    except Exception:
        raise LeaseDenied("CODE_LEASE_DENIED") from None
    require(type(lease) is dict and set(lease) == FIELDS)
    require(type(lease["version"]) is int and lease["version"] == 1
            and lease["package"] == "issue129-20261022")
    for name, length in (("source_sha", 40), ("gateway_sha", 40), ("work_id", 64)):
        require(type(lease[name]) is str and re.fullmatch("[a-f0-9]{" + str(length) + "}", lease[name]))
    for name in ("controller_run_id", "gateway_run_id"):
        require(type(lease[name]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", lease[name]))
    require(type(lease["issued_at"]) is int and type(lease["expires_at"]) is int
            and 0 < lease["issued_at"] <= now < lease["expires_at"]
            and 0 < lease["expires_at"] - lease["issued_at"] <= TTL_SECONDS)
    require(type(lease["cap_cents"]) is int and lease["cap_cents"] == 1000
            and type(lease["max_requests"]) is int and lease["max_requests"] == 10)
    return lease


def created_at(run):
    value = run.get("created_at")
    require(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value))
    try:
        return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        raise LeaseDenied("CODE_LEASE_DENIED") from None


def checked_run(run, *, repository, repository_id, run_id, head, branch, workflow, now):
    require(type(run) is dict and type(run.get("id")) is int and str(run["id"]) == run_id)
    require(type(run.get("repository")) is dict and run["repository"].get("full_name") == repository
            and type(run["repository"].get("id")) is int and run["repository"]["id"] == repository_id)
    require(run.get("head_sha") == head and run.get("head_branch") == branch
            and run.get("path") == workflow and run.get("event") == "workflow_dispatch"
            and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
            and run.get("status") in ACTIVE and run.get("conclusion") is None)
    for name in ("actor", "triggering_actor"):
        identity = run.get(name)
        require(type(identity) is dict and identity.get("login") == OWNER
                and type(identity.get("id")) is int and identity["id"] == OWNER_ID)
    start = created_at(run)
    require(0 <= now - start < TTL_SECONDS)
    return start


def public_parent(lease, run, *, now):
    lease = decode(json.dumps(lease), now=now)
    start = checked_run(run, repository=PUBLIC, repository_id=PUBLIC_ID,
        run_id=lease["gateway_run_id"], head=lease["gateway_sha"], branch="main",
        workflow=".github/workflows/code-gateway.yml", now=now)
    require(run.get("display_title") == "CW issue129 code " + lease["work_id"])
    # A renewed variable cannot extend the same public run's original window.
    require(start <= lease["issued_at"] <= start + 120 and lease["expires_at"] <= start + TTL_SECONDS)


def source_parent(lease, run, *, now, source_sha, work_id):
    """For a future trusted native launch host; data alone is not Claim proof."""
    lease = decode(json.dumps(lease), now=now)
    require(lease["source_sha"] == source_sha and lease["work_id"] == work_id)
    start = checked_run(run, repository=SOURCE, repository_id=SOURCE_ID,
        run_id=lease["controller_run_id"], head=source_sha, branch="feature/emergency-close-persistence",
        workflow=".github/workflows/orchestrator-code-controller.yml", now=now)
    require(abs(start - lease["issued_at"]) <= 120)


def read_gate(api, token, name):
    require(name in (PAID, CODE))
    value = api(SOURCE, "GET", "actions/variables/" + name, token)
    require(type(value) is dict and value.get("name") == name and value.get("value") in ("true", "false"))
    return value["value"]


def read_lease(api, token, *, now):
    value = api(SOURCE, "GET", "actions/variables/" + LEASE, token)
    require(type(value) is dict and value.get("name") == LEASE)
    return decode(value.get("value"), now=now)


def active_code_lease(api, token, public_token, *, now, parent_id=None):
    try:
        lease = read_lease(api, token, now=now)
        if parent_id is not None:
            require(lease["gateway_run_id"] == parent_id)
        run = api(PUBLIC, "GET", "actions/runs/" + lease["gateway_run_id"], public_token)
        public_parent(lease, run, now=now)
        return True
    except Exception:
        return False


def force_off(api, token):
    # Try BOTH writes even if the first reply is lost. A successful HTTP send
    # alone proves nothing: independently read back both values. Never retry.
    failures = []
    for name in (PAID, CODE):
        try:
            api(SOURCE, "PATCH", "actions/variables/" + name, token, {"name": name, "value": "false"})
        except Exception:
            failures.append(name)
    for name in (PAID, CODE):
        try:
            require(read_gate(api, token, name) == "false")
        except Exception:
            failures.append(name)
    if failures:
        raise LeaseDenied("CODE_OFF_UNVERIFIED")


def guard_once(api, token, public_token, *, now, self_test=False):
    if self_test:
        force_off(api, token)
        return "CODE_OFF_SELFTEST_VERIFIED"
    try:
        code = read_gate(api, token, CODE)
        if code == "false":
            return "NOT_CODE_LEASE"  # Original documentation guard still runs.
        read_gate(api, token, PAID)  # A partial OFF is safe; never re-enable it.
        if active_code_lease(api, token, public_token, now=now):
            return "CODE_LEASE_WITHIN_TTL"
    except Exception:
        pass
    force_off(api, token)
    return "CODE_ORPHAN_DISABLED"


def watch_code(api, token, public_token, *, parent_id, now, monotonic, pause, report):
    require(type(parent_id) is str and re.fullmatch(r"[1-9][0-9]{0,19}", parent_id))
    deadline = monotonic() + TTL_SECONDS
    ready = False
    while monotonic() < deadline:
        if not active_code_lease(api, token, public_token, now=now(), parent_id=parent_id):
            force_off(api, token)
            return "CODE_LEASE_TERMINAL_EXPIRED_OR_UNVERIFIABLE_OFF"
        try:
            for name in (PAID, CODE):
                read_gate(api, token, name)
        except Exception:
            force_off(api, token)
            return "CODE_GATE_UNVERIFIABLE_OFF"
        if not ready:
            report("INDEPENDENT_CODE_OFF_WATCHDOG_ACTIVE")
            ready = True
        pause(15)
    force_off(api, token)
    return "CODE_WATCHDOG_MONOTONIC_TTL_OFF"
