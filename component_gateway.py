"""Protected finite gateway for the existing native four-worker controller.

No provider client, private source execution, budget writer or queue editor.
The private controller verifies the actual order, Claims, Results and Releases.
"""
import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

import orchestrator_component_lease as lease
from orchestrator_code_lease import require, unique, force_off, read_gate, created_at
from code_gateway import NoRedirect, MAX_API_RESPONSE_BYTES, rows, discover

SOURCE, PUBLIC = lease.SOURCE, lease.PUBLIC
CONTROLLER = "orchestrator-component-controller.yml"
WATCHDOG = "one-shot-gateway.yml"
CHECKPOINT = "6059deec7553c7f2a665f1e24c2b4fcde92e4c89"
BUDGET = "cw-issue129-accelerated-budget"
SHA = re.compile("[a-f0-9]{40}")
HASH = re.compile("[a-f0-9]{64}")
# One audited pre-provider failure. The original marker is retained forever.
# A changed queue/budget or any other order is ineligible for this recovery.
PRELAUNCH_RECOVERY = {
    "CW_SOURCE_SHA": "b6ef9aba11026e6cb189fba9afcf339b089b7d96",
    "CW_APPROVAL_REF": "df2ca83e58dde8104e9f08f542909417f33c323c",
    "CW_WORK_ORDER_SHA256": "249829acaa55d7e43277921bedc523a6883047a51f57676fc33c5121de9b8bbd",
    "CW_SPEC_SHA256": "b0402134c9e14326760630b45f930768bbf83cd31efa4bb777601681da08baea",
}
PRELAUNCH_GATEWAY_SHA = "cadc6489b9190cdd7977a93f72cd6a088ca06055"
PRELAUNCH_QUEUE_SHA = "452654213ec99acd94132c56b02f591cd6e88e78"
PRELAUNCH_BUDGET_SHA = "e0a007bb0e41aabba259d4609d1e05d8ff21cc38"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def api(repository, method, path, token, body=None):
    require(repository in (SOURCE, PUBLIC) and method in ("GET", "POST", "PATCH")
            and type(path) is str and not any(c in path for c in ("..", "#", "\\"))
            and type(token) is str and 15 <= len(token) <= 16384)
    if method != "GET":
        require((repository == SOURCE and method == "PATCH" and path in (
                    "actions/variables/" + lease.PAID, "actions/variables/" + lease.CODE,
                    "actions/variables/" + lease.LEASE))
            or (repository == SOURCE and method == "POST" and path in (
                    "actions/variables", "actions/workflows/" + CONTROLLER + "/dispatches"))
            or (repository == PUBLIC and method == "POST" and path in (
                    "git/refs", "actions/workflows/" + WATCHDOG + "/dispatches")))
    request = urllib.request.Request("https://api.github.com/repos/" + repository + ("/" + path if path else ""),
        data=None if body is None else canonical(body), method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "Content-Type": "application/json", "Cache-Control": "no-cache",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "cw-component-gateway"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            require(response.status in (200, 201, 204))
            raw = response.read(MAX_API_RESPONSE_BYTES + 1)
            require(len(raw) <= MAX_API_RESPONSE_BYTES)
            return json.loads(raw, object_pairs_hook=unique) if raw.strip() else None
    except urllib.error.HTTPError as error:
        if method == "GET" and error.code == 404:
            return None
        raise ValueError("COMPONENT_API_OUTCOME_UNKNOWN_NO_RETRY") from None
    except Exception:
        raise ValueError("COMPONENT_API_OUTCOME_UNKNOWN_NO_RETRY") from None


def context(env):
    expected = {"GITHUB_REPOSITORY": PUBLIC, "GITHUB_REPOSITORY_ID": str(lease.PUBLIC_ID),
        "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_ACTOR": lease.OWNER, "GITHUB_ACTOR_ID": str(lease.OWNER_ID), "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": PUBLIC + "/.github/workflows/component-gateway.yml@refs/heads/main"}
    require(all(env.get(k) == v for k, v in expected.items()))
    for name in ("GITHUB_SHA", "CW_SOURCE_SHA", "CW_APPROVAL_REF"):
        require(type(env.get(name)) is str and SHA.fullmatch(env[name]))
    require(env["CW_SOURCE_SHA"] != env["CW_APPROVAL_REF"])
    for name in ("CW_WORK_ORDER_SHA256", "CW_SPEC_SHA256"):
        require(type(env.get(name)) is str and HASH.fullmatch(env[name]))
    require(re.fullmatch(r"[1-9][0-9]{0,19}", env.get("GITHUB_RUN_ID", ""))
            and env.get("CW_PREFLIGHT_ONLY") in ("true", "false"))
    return dict(env)


def public_approval(call, token, own, now):
    run = call(PUBLIC, "GET", "actions/runs/" + own["GITHUB_RUN_ID"], token)
    lease.parent(run, repository=PUBLIC, repository_id=lease.PUBLIC_ID,
        run_id=own["GITHUB_RUN_ID"], head=own["GITHUB_SHA"], branch="main",
        workflow=".github/workflows/component-gateway.yml",
        title="CW component order " + own["CW_WORK_ORDER_SHA256"], now=now)
    branch = call(PUBLIC, "GET", "branches/main", token)
    require(branch.get("protected") is True and branch.get("commit", {}).get("sha") == own["GITHUB_SHA"])
    approvals = call(PUBLIC, "GET", "actions/runs/" + own["GITHUB_RUN_ID"] + "/approvals", token)
    require(type(approvals) is list and len(approvals) == 1)
    review = approvals[0]
    require(review.get("state") == "approved" and review.get("user", {}).get("id") == lease.OWNER_ID
        and type(review.get("environments")) is list and len(review["environments"]) == 1
        and review["environments"][0].get("name") == "paid-one-shot"
        and review["environments"][0].get("can_admins_bypass") is False)
    history = rows(call(PUBLIC, "GET", "actions/workflows/" + WATCHDOG + "/runs?per_page=50", token), "workflow_runs")
    require(any(r.get("head_sha") == own["GITHUB_SHA"] and r.get("event") == "workflow_dispatch"
        and r.get("display_title") == "CW issue88 off_selftest 0" and r.get("status") == "completed"
        and r.get("conclusion") == "success" and r.get("run_attempt") == 1
        and r.get("actor", {}).get("id") == lease.OWNER_ID and 0 <= now - created_at(r) < 3600 for r in history))
    return run


def read_file(call, token, path, ref):
    value = call(SOURCE, "GET", "contents/" + path + "?ref=" + ref, token)
    require(type(value) is dict and value.get("type") == "file" and value.get("encoding") == "base64"
        and type(value.get("content")) is str and type(value.get("size")) is int
        and 0 < value["size"] <= 262144 and SHA.fullmatch(value.get("sha", "")))
    encoded = "".join(value["content"].splitlines())
    raw = base64.b64decode(encoded, validate=True)
    require(len(raw) == value["size"] and base64.b64encode(raw).decode() == encoded
        and hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == value["sha"])
    return raw


def budget_capacity(current, retained):
    for budget, cap, count in ((current, 15000, 500), (retained, 7000, 100)):
        require(type(budget) is dict and budget.get("version") == 2
            and budget.get("package") == "issue129-20261022-accelerated"
            and type(budget.get("cap_cents")) is int and budget["cap_cents"] == cap
            and type(budget.get("max_requests")) is int and budget["max_requests"] == count
            and type(budget.get("entries")) is list and 30 <= len(budget["entries"]) <= count)
    require(len(retained["entries"]) == 30 and canonical(current["entries"][:30]) == canonical(retained["entries"]))
    def cost(entry):
        require(type(entry) is dict and entry.get("state") in ("RESERVED", "CONSUMED", "FINALIZED")
            and type(entry.get("ceiling_cents")) is int and entry["ceiling_cents"] > 0)
        if entry["state"] == "FINALIZED":
            require(type(entry.get("settled_cents")) is int and 0 <= entry["settled_cents"] <= entry["ceiling_cents"])
            return entry["settled_cents"]
        require("settled_cents" not in entry)
        return entry["ceiling_cents"]
    require(sum(cost(e) for e in retained["entries"]) == 5964)
    remaining = 15000 - sum(cost(e) for e in current["entries"])
    require(remaining >= 0)
    # The protected broker queues before a send when another approved Work is
    # holding a reserve. The private controller independently checks the four
    # implementation allowances (48 each) and fresh integration headroom.
    return remaining >= 600 and 500 - len(current["entries"]) >= 192


def source_preflight(call, token, own):
    repo = call(SOURCE, "GET", "", token)
    require(repo.get("id") == lease.SOURCE_ID and repo.get("full_name") == SOURCE
            and repo.get("default_branch") == lease.BRANCH)
    head = call(SOURCE, "GET", "git/ref/heads/" + lease.BRANCH, token)
    require(head.get("object", {}).get("sha") == own["CW_SOURCE_SHA"])
    require(all(read_gate(call, token, name) == "false" for name in (lease.PAID, lease.CODE)))
    tip = call(SOURCE, "GET", "git/ref/heads/" + BUDGET, token).get("object", {}).get("sha")
    require(type(tip) is str and SHA.fullmatch(tip))
    current = json.loads(read_file(call, token, "package-budget.json", tip), object_pairs_hook=unique)
    retained = json.loads(read_file(call, token, "package-budget.json", CHECKPOINT), object_pairs_hook=unique)
    require(call(SOURCE, "GET", "git/ref/heads/" + BUDGET, token).get("object", {}).get("sha") == tip)
    if not budget_capacity(current, retained):
        return False
    for workflow in (CONTROLLER, "orchestrator-code-controller.yml", "gh-aw-component-worker.lock.yml",
                     "gh-aw-code-worker.lock.yml", "gh-aw-worker-probe.lock.yml", "gh-aw-dispatcher-probe.lock.yml"):
        history = rows(call(SOURCE, "GET", "actions/workflows/" + workflow + "/runs?per_page=50", token), "workflow_runs")
        require(not any(r.get("status") in (*lease.ACTIVE, "requested") for r in history))
    approval = call(SOURCE, "GET", "git/commits/" + own["CW_APPROVAL_REF"], token)
    require(approval.get("sha") == own["CW_APPROVAL_REF"] and type(approval.get("parents")) is list
            and len(approval["parents"]) == 1 and approval["parents"][0].get("sha") == own["CW_SOURCE_SHA"])
    for path, name in (("orchestrator-work-order.json", "CW_WORK_ORDER_SHA256"),
                       ("orchestrator-specification.json", "CW_SPEC_SHA256")):
        raw = read_file(call, token, path, own["CW_APPROVAL_REF"])
        require(hashlib.sha256(raw).hexdigest() == own[name])
    return True


def arm_watchdog(call, token, own, *, clock, monotonic, pause):
    started = int(clock())
    call(PUBLIC, "POST", "actions/workflows/" + WATCHDOG + "/dispatches", token,
        {"ref": "main", "inputs": {"mode": "component_watch", "parent_run_id": own["GITHUB_RUN_ID"]}})
    run = discover(call, token, PUBLIC, WATCHDOG, "CW issue88 component_watch " + own["GITHUB_RUN_ID"],
        own["GITHUB_SHA"], "main", started, clock=clock, monotonic=monotonic, pause=pause, owner_required=False, timeout_seconds=300)
    deadline, active_since = monotonic() + 65, None
    while monotonic() < deadline:
        current = call(PUBLIC, "GET", "actions/runs/" + str(run["id"]), token)
        require(current.get("status") == "in_progress" and current.get("run_attempt") == 1
            and current.get("head_sha") == own["GITHUB_SHA"])
        jobs = rows(call(PUBLIC, "GET", "actions/runs/" + str(run["id"]) + "/jobs?per_page=50", token), "jobs")
        jobs = [j for j in jobs if j.get("name") == "Independent OFF-only watchdog"]
        require(len(jobs) == 1 and jobs[0].get("status") == "in_progress")
        active = any(s.get("name") == "Verify gate OFF or guard active pilot (no models)"
            and s.get("status") == "in_progress" for s in jobs[0].get("steps", []))
        if active:
            if active_since is None: active_since = monotonic()
            if monotonic() - active_since >= 25: return str(run["id"])
        else: active_since = None
        pause(5)
    raise ValueError("COMPONENT_WATCHDOG_NOT_ARMED")


def launch_marker(call, source_token, public_token, own):
    name = "cw-component-" + own["CW_WORK_ORDER_SHA256"]
    original = call(PUBLIC, "GET", "git/ref/heads/" + name, public_token)
    if original is None:
        return name
    require(all(own.get(k) == v for k, v in PRELAUNCH_RECOVERY.items())
        and original.get("object", {}).get("sha") == PRELAUNCH_GATEWAY_SHA)
    for repository, token, run_id, repo_id, head, branch, workflow, title in (
        (PUBLIC, public_token, 40018993718, lease.PUBLIC_ID, PRELAUNCH_GATEWAY_SHA, "main",
         "component-gateway.yml", "CW component order "),
        (SOURCE, source_token, 40019128698, lease.SOURCE_ID, own["CW_SOURCE_SHA"], lease.BRANCH,
         CONTROLLER, "CW component controller "),
    ):
        run = call(repository, "GET", "actions/runs/" + str(run_id), token)
        require(type(run) is dict and run.get("id") == run_id and run.get("status") == "completed"
            and run.get("conclusion") == "failure" and run.get("run_attempt") == 1
            and run.get("repository", {}).get("id") == repo_id
            and run.get("repository", {}).get("full_name") == repository
            and run.get("head_sha") == head and run.get("head_branch") == branch
            and run.get("path") == ".github/workflows/" + workflow
            and run.get("display_title") == title + own["CW_WORK_ORDER_SHA256"]
            and run.get("event") == "workflow_dispatch"
            and all(run.get(field, {}).get("id") == lease.OWNER_ID for field in ("actor", "triggering_actor")))
    for branch, expected in (("work-queue", PRELAUNCH_QUEUE_SHA), (BUDGET, PRELAUNCH_BUDGET_SHA)):
        ref = call(SOURCE, "GET", "git/ref/heads/" + branch, source_token)
        require(type(ref) is dict and ref.get("object", {}).get("sha") == expected)
    # Exact unchanged histories are mandatory, not merely a remaining balance.
    # Private prepare independently requires all five Works available/attempts=0.
    require(all(read_gate(call, source_token, gate) == "false" for gate in (lease.PAID, lease.CODE)))
    name += "-prelaunch-recovery1"
    require(call(PUBLIC, "GET", "git/ref/heads/" + name, public_token) is None)
    return name


def execute(env, *, call=api, clock=time.time, monotonic=time.monotonic, pause=time.sleep):
    own = context(env)
    source_token, public_token = own["CW_GATEWAY_OPERATOR_TOKEN"], own["GH_PUBLIC_TOKEN"]
    public_run = public_approval(call, public_token, own, int(clock()))
    if not source_preflight(call, source_token, own):
        return "COMPONENT_GATEWAY_BUDGET_BLOCKED_NO_DISPATCH_NO_SPEND"
    marker_name = launch_marker(call, source_token, public_token, own)
    if own["CW_PREFLIGHT_ONLY"] == "true":
        return "COMPONENT_GATEWAY_PREFLIGHT_VERIFIED_NO_DISPATCH_NO_SPEND"
    try:
        call(PUBLIC, "POST", "git/refs", public_token, {"ref": "refs/heads/" + marker_name, "sha": own["GITHUB_SHA"]})
        marker = call(PUBLIC, "GET", "git/ref/heads/" + marker_name, public_token)
        require(marker.get("object", {}).get("sha") == own["GITHUB_SHA"])
        started = int(clock())
        inputs = {"mode": "run", "source_sha": own["CW_SOURCE_SHA"], "approval_ref": own["CW_APPROVAL_REF"],
            "work_order_sha256": own["CW_WORK_ORDER_SHA256"], "spec_sha256": own["CW_SPEC_SHA256"],
            "gateway_run_id": own["GITHUB_RUN_ID"], "gateway_sha": own["GITHUB_SHA"]}
        call(SOURCE, "POST", "actions/workflows/" + CONTROLLER + "/dispatches", source_token,
            {"ref": lease.BRANCH, "inputs": inputs})
        source = discover(call, source_token, SOURCE, CONTROLLER, "CW component controller " + own["CW_WORK_ORDER_SHA256"],
            own["CW_SOURCE_SHA"], lease.BRANCH, started, clock=clock, monotonic=monotonic, pause=pause, timeout_seconds=300)
        issued = int(clock())
        grant = {"version": 1, "package": "issue129-20261022-accelerated", "source_sha": own["CW_SOURCE_SHA"],
            "approval_ref": own["CW_APPROVAL_REF"], "work_order_sha256": own["CW_WORK_ORDER_SHA256"],
            "spec_sha256": own["CW_SPEC_SHA256"], "controller_run_id": str(source["id"]),
            "gateway_run_id": own["GITHUB_RUN_ID"], "gateway_sha": own["GITHUB_SHA"], "issued_at": issued,
            "expires_at": created_at(public_run) + lease.TTL_SECONDS, "cap_cents": 15000, "max_requests": 500}
        lease.public_parent(grant, public_run, now=issued); lease.source_parent(grant, source, now=issued)
        old = call(SOURCE, "GET", "actions/variables/" + lease.LEASE, source_token)
        value = {"name": lease.LEASE, "value": canonical(grant).decode()}
        call(SOURCE, "POST" if old is None else "PATCH", "actions/variables" if old is None else "actions/variables/" + lease.LEASE,
            source_token, value)
        stored = call(SOURCE, "GET", "actions/variables/" + lease.LEASE, source_token)
        require(type(stored) is dict and stored.get("name") == lease.LEASE and stored.get("value") == value["value"])
        watch_id = arm_watchdog(call, public_token, own, clock=clock, monotonic=monotonic, pause=pause)
        # The source must finish OFF-only graph admission before either gate can
        # be enabled. Merely starting its controller job is insufficient.
        deadline = monotonic() + 180
        prepared = False
        while monotonic() < deadline:
            jobs = rows(call(SOURCE, "GET", "actions/runs/" + str(source["id"]) + "/jobs?per_page=50", source_token), "jobs")
            steps = [s for j in jobs for s in j.get("steps", []) if s.get("name") == "Prepare native graph while OFF"]
            require(len(steps) <= 1)
            if steps and steps[0].get("status") == "completed":
                require(steps[0].get("conclusion") == "success"); prepared = True; break
            pause(2)
        require(prepared and lease.active_lease(call, source_token, public_token, now=int(clock()), parent_id=own["GITHUB_RUN_ID"]) == grant)
        require(all(read_gate(call, source_token, name) == "false" for name in (lease.PAID, lease.CODE)))
        for name in (lease.CODE, lease.PAID):
            call(SOURCE, "PATCH", "actions/variables/" + name, source_token, {"name": name, "value": "true"})
            require(read_gate(call, source_token, name) == "true")
        deadline = monotonic() + max(0, grant["expires_at"] - int(clock()))
        while monotonic() < deadline:
            current = call(SOURCE, "GET", "actions/runs/" + str(source["id"]), source_token)
            if current.get("status") == "completed":
                require(current.get("conclusion") == "success")
                return "COMPONENT_CONTROLLER_SUCCEEDED_NATIVE_RESULTS_REQUIRE_READBACK"
            require(lease.active_lease(call, source_token, public_token, now=int(clock()), parent_id=own["GITHUB_RUN_ID"]) == grant)
            watch = call(PUBLIC, "GET", "actions/runs/" + watch_id, public_token)
            require(watch.get("status") == "in_progress" and watch.get("head_sha") == own["GITHUB_SHA"])
            require(all(read_gate(call, source_token, name) == "true" for name in (lease.PAID, lease.CODE)))
            pause(10)
        raise ValueError("COMPONENT_CONTROLLER_TIMEOUT_NO_RETRY")
    finally:
        force_off(call, source_token)


if __name__ == "__main__":
    try:
        print(execute(os.environ))
    except Exception:
        raise SystemExit("COMPONENT_GATEWAY_DENIED_OR_UNKNOWN_NO_RETRY") from None
