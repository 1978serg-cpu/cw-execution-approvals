"""Independent OFF support for the existing native four-component controller.

This module never enables a gate, changes a budget, dispatches work or calls a
model. Both immutable owner runs must remain active throughout the finite lease.
"""
import json
import re

from orchestrator_code_lease import (
    SOURCE, PUBLIC, SOURCE_ID, PUBLIC_ID, OWNER_ID, OWNER, PAID, CODE,
    ACTIVE, require, unique, created_at, force_off, read_gate,
)

LEASE = "CW_CODEX_COMPONENT_LEASE"
TTL_SECONDS = 5400
BRANCH = "feature/emergency-close-persistence"
FIELDS = {"version", "package", "source_sha", "approval_ref", "work_order_sha256",
          "spec_sha256", "controller_run_id", "gateway_run_id", "gateway_sha",
          "issued_at", "expires_at", "cap_cents", "max_requests"}


def decode(raw, *, now):
    require(type(raw) is str and len(raw.encode("utf-8")) <= 4096 and type(now) is int)
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except Exception:
        raise ValueError("COMPONENT_LEASE_DENIED") from None
    require(type(value) is dict and set(value) == FIELDS
            and type(value["version"]) is int and value["version"] == 1
            and value["package"] == "issue129-20261022-accelerated"
            and type(value["cap_cents"]) is int and value["cap_cents"] == 27500
            and type(value["max_requests"]) is int and value["max_requests"] == 1000)
    for name, size in (("source_sha", 40), ("approval_ref", 40), ("gateway_sha", 40),
                       ("work_order_sha256", 64), ("spec_sha256", 64)):
        require(type(value[name]) is str and re.fullmatch("[a-f0-9]{" + str(size) + "}", value[name]))
    require(value["approval_ref"] != value["source_sha"])
    for name in ("controller_run_id", "gateway_run_id"):
        require(type(value[name]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value[name]))
    require(type(value["issued_at"]) is int and type(value["expires_at"]) is int
            and 0 < value["issued_at"] <= now < value["expires_at"]
            and 0 < value["expires_at"] - value["issued_at"] <= TTL_SECONDS)
    return value


def parent(run, *, repository, repository_id, run_id, head, branch, workflow, title, now, completed=False):
    require(type(run) is dict and type(run.get("id")) is int and str(run["id"]) == run_id
            and type(run.get("repository")) is dict
            and run["repository"].get("full_name") == repository
            and type(run["repository"].get("id")) is int and run["repository"]["id"] == repository_id
            and run.get("head_sha") == head and run.get("head_branch") == branch
            and run.get("path") == workflow and run.get("event") == "workflow_dispatch"
            and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
            and ((run.get("status") == "completed" and run.get("conclusion") == "success") if completed
                 else (run.get("status") in ACTIVE and run.get("conclusion") is None))
            and run.get("display_title") == title)
    for name in ("actor", "triggering_actor"):
        identity = run.get(name)
        require(type(identity) is dict and identity.get("login") == OWNER
                and type(identity.get("id")) is int and identity["id"] == OWNER_ID)
    start = created_at(run)
    require(0 <= now - start < TTL_SECONDS)
    return start


def public_parent(lease, run, *, now):
    lease = decode(json.dumps(lease), now=now)
    start = parent(run, repository=PUBLIC, repository_id=PUBLIC_ID,
        run_id=lease["gateway_run_id"], head=lease["gateway_sha"], branch="main",
        workflow=".github/workflows/component-gateway.yml",
        title="CW component order " + lease["work_order_sha256"], now=now)
    require(start <= lease["issued_at"] <= start + 300 and lease["expires_at"] <= start + TTL_SECONDS)


def source_parent(lease, run, *, now, completed=False):
    lease = decode(json.dumps(lease), now=now)
    start = parent(run, repository=SOURCE, repository_id=SOURCE_ID,
        run_id=lease["controller_run_id"], head=lease["source_sha"], branch=BRANCH,
        workflow=".github/workflows/orchestrator-component-controller.yml",
        title="CW component controller " + lease["work_order_sha256"], now=now, completed=completed)
    require(abs(start - lease["issued_at"]) <= 300)


def active_lease(api, token, public_token, *, now, parent_id=None):
    try:
        raw = api(SOURCE, "GET", "actions/variables/" + LEASE, token)
        require(type(raw) is dict and raw.get("name") == LEASE)
        lease = decode(raw.get("value"), now=now)
        require(parent_id is None or lease["gateway_run_id"] == parent_id)
        public_parent(lease, api(PUBLIC, "GET", "actions/runs/" + lease["gateway_run_id"], public_token), now=now)
        source_parent(lease, api(SOURCE, "GET", "actions/runs/" + lease["controller_run_id"], token), now=now)
        return lease
    except Exception:
        return None


def guard_once(api, token, public_token, *, now):
    # An absent/expired component lease falls through to the existing code and
    # documentation policies. A valid legacy lease must remain usable too.
    if read_gate(api, token, CODE) == "true" and active_lease(api, token, public_token, now=now):
        read_gate(api, token, PAID)
        return "COMPONENT_LEASE_WITHIN_TTL"
    return "NOT_COMPONENT_LEASE"


def watch_component(api, token, public_token, *, parent_id, now, monotonic, pause, report):
    require(type(parent_id) is str and re.fullmatch(r"[1-9][0-9]{0,19}", parent_id))
    deadline = monotonic() + TTL_SECONDS
    ready = False
    while monotonic() < deadline:
        if active_lease(api, token, public_token, now=now(), parent_id=parent_id) is None:
            force_off(api, token)
            return "COMPONENT_PARENT_OR_LEASE_INVALID_OFF"
        try:
            for name in (PAID, CODE):
                read_gate(api, token, name)
        except Exception:
            force_off(api, token)
            return "COMPONENT_GATE_UNVERIFIABLE_OFF"
        if not ready:
            report("INDEPENDENT_COMPONENT_OFF_WATCHDOG_ACTIVE")
            ready = True
        pause(15)
    force_off(api, token)
    return "COMPONENT_WATCHDOG_MONOTONIC_TTL_OFF"


def prepare_watch_component(api, token, public_token, *, parent_id, now, monotonic, pause):
    """A finite OFF-only job proves the same guard can authenticate both runs.

    Its completed Actions job is observable even when GitHub omits all steps.
    The independent continuous watchdog starts only after this job succeeds.
    """
    require(type(parent_id) is str and re.fullmatch(r"[1-9][0-9]{0,19}", parent_id))
    def verify():
        require(active_lease(api, token, public_token, now=now(), parent_id=parent_id) is not None)
        require(all(read_gate(api, token, gate) == "false" for gate in (PAID, CODE)))
    try:
        verify()
        force_off(api, token)
        deadline = monotonic() + 25
        while True:
            verify()
            if monotonic() >= deadline:
                return "COMPONENT_WATCHDOG_READINESS_VERIFIED_OFF"
            pause(min(5, deadline - monotonic()))
    except Exception:
        force_off(api, token)
        raise ValueError("COMPONENT_WATCHDOG_READINESS_DENIED_OFF") from None
