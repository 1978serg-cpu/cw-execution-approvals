"""One owner-approved code package. No model, private source writes or queue editor.

The native source controller selects/verifies the immutable Work and preserves
the original scheduler, credential validator and native Result channel.
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

from orchestrator_code_lease import (
    SOURCE, PUBLIC, SOURCE_ID, PUBLIC_ID, OWNER_ID, PAID, CODE, LEASE,
    TTL_SECONDS, require, unique, checked_run, created_at, public_parent, source_parent,
    force_off, read_gate,
)

BRANCH = "feature/emergency-close-persistence"
CONTROLLER = "orchestrator-code-controller.yml"
WATCHDOG = "one-shot-gateway.yml"
MARKER = "cw-issue129-code-package-consumed"
LIVE = ("requested", "queued", "in_progress", "waiting", "pending")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("CODE_GATEWAY_REDIRECT_DENIED")


def api(repository, method, path, token, body=None):
    require(repository in (SOURCE, PUBLIC) and method in ("GET", "POST", "PATCH")
            and type(path) is str and not any(x in path for x in ("..", "#", "\\"))
            and type(token) is str and 15 <= len(token) <= 16384)
    if method != "GET":
        allowed = (
            repository == SOURCE and method == "PATCH" and path in tuple("actions/variables/" + x for x in (PAID, CODE, LEASE))
            or repository == SOURCE and method == "POST" and path in ("actions/variables", "actions/workflows/" + CONTROLLER + "/dispatches")
            or repository == PUBLIC and method == "POST" and path in ("git/refs", "actions/workflows/" + WATCHDOG + "/dispatches")
        )
        require(allowed)
    request = urllib.request.Request("https://api.github.com/repos/" + repository + ("/" + path if path else ""),
        data=None if body is None else json.dumps(body, separators=(",", ":")).encode(), method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "Content-Type": "application/json", "Cache-Control": "no-cache",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "cw-issue129-code-gateway"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            require(response.status in (200, 201, 204))
            raw = response.read(262145)
            require(len(raw) <= 262144)
            return json.loads(raw, object_pairs_hook=unique) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        if method == "GET" and exc.code == 404:
            return None
        raise ValueError("CODE_GATEWAY_OUTCOME_UNKNOWN_NO_RETRY") from None
    except Exception:
        raise ValueError("CODE_GATEWAY_OUTCOME_UNKNOWN_NO_RETRY") from None


def context(environment):
    expected = {"GITHUB_REPOSITORY": PUBLIC, "GITHUB_REPOSITORY_ID": str(PUBLIC_ID),
        "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_ACTOR": "1978serg-cpu", "GITHUB_ACTOR_ID": str(OWNER_ID), "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": PUBLIC + "/.github/workflows/code-gateway.yml@refs/heads/main"}
    require(all(environment.get(name) == value for name, value in expected.items()))
    values = {name: environment.get(name, "") for name in ("GITHUB_SHA", "CW_SOURCE_SHA", "CW_WORK_ID", "GITHUB_RUN_ID")}
    for name in ("GITHUB_SHA", "CW_SOURCE_SHA"):
        require(re.fullmatch("[a-f0-9]{40}", values[name]))
    require(re.fullmatch("[a-f0-9]{64}", values["CW_WORK_ID"])
            and re.fullmatch("[1-9][0-9]{0,19}", values["GITHUB_RUN_ID"]))
    return values


def rows(document, name):
    require(type(document) is dict and type(document.get(name)) is list and len(document[name]) <= 50)
    return document[name]


def source_preflight(call, token, source_sha):
    repository = call(SOURCE, "GET", "", token)
    require(repository.get("full_name") == SOURCE and repository.get("id") == SOURCE_ID
            and repository.get("default_branch") == BRANCH)
    tip = call(SOURCE, "GET", "git/ref/heads/" + BRANCH, token)
    require(tip.get("object", {}).get("sha") == source_sha)
    require(all(read_gate(call, token, name) == "false" for name in (PAID, CODE)))
    file = call(SOURCE, "GET", "contents/package-budget.json?ref=cw-issue129-budget", token)
    require(file.get("type") == "file" and file.get("encoding") == "base64" and file.get("size", 999999) <= 65536)
    budget = json.loads(base64.b64decode(file["content"], validate=False), object_pairs_hook=unique)
    require(budget.get("package") == "issue129-20261022" and budget.get("cap_cents") == 1000
            and budget.get("max_requests") == 10 and budget.get("revision") == 0 and budget.get("entries") == [])
    for workflow in (CONTROLLER, "gh-aw-code-worker.lock.yml", "gh-aw-worker-probe.lock.yml", "gh-aw-dispatcher-probe.lock.yml"):
        history = rows(call(SOURCE, "GET", "actions/workflows/" + workflow + "/runs?per_page=50", token), "workflow_runs")
        require(not any(run.get("status") in LIVE for run in history))


def approval(call, token, own, now):
    run = call(PUBLIC, "GET", "actions/runs/" + own["GITHUB_RUN_ID"], token)
    checked_run(run, repository=PUBLIC, repository_id=PUBLIC_ID, run_id=own["GITHUB_RUN_ID"],
        head=own["GITHUB_SHA"], branch="main", workflow=".github/workflows/code-gateway.yml", now=now)
    require(run.get("display_title") == "CW issue129 code " + own["CW_WORK_ID"])
    branch = call(PUBLIC, "GET", "branches/main", token)
    require(branch.get("protected") is True and branch.get("commit", {}).get("sha") == own["GITHUB_SHA"])
    reviews = call(PUBLIC, "GET", "actions/runs/" + own["GITHUB_RUN_ID"] + "/approvals", token)
    require(type(reviews) is list and len(reviews) == 1)
    review = reviews[0]
    require(review.get("state") == "approved" and review.get("user", {}).get("id") == OWNER_ID
            and type(review.get("environments")) is list and len(review["environments"]) == 1
            and review["environments"][0].get("name") == "paid-one-shot"
            and review["environments"][0].get("can_admins_bypass") is False)
    history = rows(call(PUBLIC, "GET", "actions/workflows/" + WATCHDOG + "/runs?per_page=50", token), "workflow_runs")
    require(any(r.get("head_sha") == own["GITHUB_SHA"] and r.get("event") == "workflow_dispatch"
        and r.get("display_title") == "CW issue88 off_selftest 0" and r.get("status") == "completed"
        and r.get("conclusion") == "success" and r.get("run_attempt") == 1
        and r.get("actor", {}).get("id") == OWNER_ID and 0 <= now - created_at(r) < 3600 for r in history))
    return run


def discover(call, token, repository, workflow, title, sha, branch, started, *, clock, monotonic, pause, owner_required=True):
    deadline = monotonic() + 75
    while monotonic() < deadline:
        history = rows(call(repository, "GET", "actions/workflows/" + workflow + "/runs?per_page=50", token), "workflow_runs")
        matches = [r for r in history if r.get("display_title") == title and r.get("head_sha") == sha
            and r.get("head_branch") == branch and r.get("event") == "workflow_dispatch"
            and r.get("path") == ".github/workflows/" + workflow and created_at(r) >= started - 2]
        require(len(matches) <= 1)
        if matches:
            run = matches[0]
            require(run.get("run_attempt") == 1 and run.get("status") in LIVE)
            for name in ("actor", "triggering_actor"):
                identity = run.get(name, {})
                require(identity.get("id") == OWNER_ID if owner_required else
                        identity.get("login") == "github-actions[bot]" and identity.get("type") == "Bot")
            if run["status"] == "in_progress":
                return run
        pause(2)
    raise ValueError("CODE_GATEWAY_RUN_NOT_CONFIRMED_NO_REDISPATCH")


def arm_watchdog(call, token, own, *, clock, monotonic, pause):
    started = int(clock())
    call(PUBLIC, "POST", "actions/workflows/" + WATCHDOG + "/dispatches", token,
        {"ref": "main", "inputs": {"mode": "code_watch", "parent_run_id": own["GITHUB_RUN_ID"]}})
    run = discover(call, token, PUBLIC, WATCHDOG, "CW issue88 code_watch " + own["GITHUB_RUN_ID"],
        own["GITHUB_SHA"], "main", started, clock=clock, monotonic=monotonic, pause=pause, owner_required=False)
    deadline = monotonic() + 65
    active_since = None
    while monotonic() < deadline:
        current = call(PUBLIC, "GET", "actions/runs/" + str(run["id"]), token)
        require(current.get("status") == "in_progress" and current.get("run_attempt") == 1
                and current.get("head_sha") == own["GITHUB_SHA"])
        jobs = rows(call(PUBLIC, "GET", "actions/runs/" + str(run["id"]) + "/jobs?per_page=50", token), "jobs")
        active_jobs = [j for j in jobs if j.get("name") == "Independent OFF-only watchdog"]
        require(len(active_jobs) == 1 and active_jobs[0].get("status") == "in_progress")
        steps = active_jobs[0].get("steps", [])
        active = any(s.get("name") == "Verify gate OFF or guard active pilot (no models)"
            and s.get("status") == "in_progress" for s in steps)
        if active:
            if active_since is None:
                active_since = monotonic()
            if monotonic() - active_since >= 25:
                return
        else:
            active_since = None
        pause(5)
    raise ValueError("INDEPENDENT_CODE_OFF_NOT_ARMED")


def execute(environment, *, call=api, clock=time.time, monotonic=time.monotonic, pause=time.sleep):
    own = context(environment)
    source_token, public_token = environment["CW_GATEWAY_OPERATOR_TOKEN"], environment["GH_PUBLIC_TOKEN"]
    own_run = approval(call, public_token, own, int(clock()))
    source_preflight(call, source_token, own["CW_SOURCE_SHA"])
    require(call(PUBLIC, "GET", "git/ref/heads/" + MARKER, public_token) is None)
    # From here any uncertain outcome consumes the attempt. Never repeat a POST.
    try:
        call(PUBLIC, "POST", "git/refs", public_token, {"ref": "refs/heads/" + MARKER, "sha": own["GITHUB_SHA"]})
        marker = call(PUBLIC, "GET", "git/ref/heads/" + MARKER, public_token)
        require(marker.get("ref") == "refs/heads/" + MARKER and marker.get("object", {}).get("sha") == own["GITHUB_SHA"])
        started = int(clock())
        call(SOURCE, "POST", "actions/workflows/" + CONTROLLER + "/dispatches", source_token,
            {"ref": BRANCH, "inputs": {"mode": "launch", "work_id": own["CW_WORK_ID"],
                "gateway_run_id": own["GITHUB_RUN_ID"], "gateway_sha": own["GITHUB_SHA"]}})
        source = discover(call, source_token, SOURCE, CONTROLLER, "CW issue129 launch " + own["CW_WORK_ID"],
            own["CW_SOURCE_SHA"], BRANCH, started, clock=clock, monotonic=monotonic, pause=pause)
        issued = int(clock())
        lease = {"version": 1, "package": "issue129-20261022", "source_sha": own["CW_SOURCE_SHA"],
            "work_id": own["CW_WORK_ID"], "controller_run_id": str(source["id"]),
            "gateway_run_id": own["GITHUB_RUN_ID"], "gateway_sha": own["GITHUB_SHA"], "issued_at": issued,
            "expires_at": created_at(own_run) + TTL_SECONDS, "cap_cents": 1000, "max_requests": 10}
        public_parent(lease, own_run, now=issued)
        source_parent(lease, source, now=issued, source_sha=own["CW_SOURCE_SHA"], work_id=own["CW_WORK_ID"])
        old = call(SOURCE, "GET", "actions/variables/" + LEASE, source_token)
        value = {"name": LEASE, "value": json.dumps(lease, separators=(",", ":"))}
        call(SOURCE, "POST" if old is None else "PATCH", "actions/variables" if old is None else "actions/variables/" + LEASE,
            source_token, value)
        stored = call(SOURCE, "GET", "actions/variables/" + LEASE, source_token)
        require(stored.get("name") == LEASE and stored.get("value") == value["value"])
        arm_watchdog(call, public_token, own, clock=clock, monotonic=monotonic, pause=pause)
        for repository, token, run_id in ((PUBLIC, public_token, own["GITHUB_RUN_ID"]), (SOURCE, source_token, str(source["id"]))):
            current = call(repository, "GET", "actions/runs/" + run_id, token)
            if repository == PUBLIC:
                public_parent(lease, current, now=int(clock()))
            else:
                source_parent(lease, current, now=int(clock()), source_sha=own["CW_SOURCE_SHA"], work_id=own["CW_WORK_ID"])
        require(all(read_gate(call, source_token, name) == "false" for name in (PAID, CODE)))
        # CODE first: the existing scheduled guard recognizes the valid code lease
        # before PAID is enabled. Neither flag alone can authorize the worker.
        for name in (CODE, PAID):
            call(SOURCE, "PATCH", "actions/variables/" + name, source_token, {"name": name, "value": "true"})
            require(read_gate(call, source_token, name) == "true")
        deadline = monotonic() + max(0, lease["expires_at"] - int(clock()))
        while monotonic() < deadline:
            current = call(SOURCE, "GET", "actions/runs/" + str(source["id"]), source_token)
            if current.get("status") == "completed":
                require(current.get("conclusion") == "success")
                return "CODE_CONTROLLER_COMPLETED_NATIVE_RESULT_REQUIRES_READBACK"
            source_parent(lease, current, now=int(clock()), source_sha=own["CW_SOURCE_SHA"], work_id=own["CW_WORK_ID"])
            require(all(read_gate(call, source_token, name) == "true" for name in (PAID, CODE)))
            pause(10)
        raise ValueError("CODE_CONTROLLER_TIMEOUT_RESULT_UNVERIFIED")
    finally:
        force_off(call, source_token)


if __name__ == "__main__":
    try:
        print(execute(os.environ))
        print("BOTH_EXECUTION_GATES_OFF_VERIFIED")
    except Exception:
        raise SystemExit("CODE_GATEWAY_DENIED_OR_UNKNOWN_NO_RETRY") from None
