"""Public gateway integration tests. All API calls and clocks are inert fixtures."""
import base64
import copy
import datetime as dt
import json
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
if not (ROOT / "orchestrator_code_lease.py").is_file():
    sys.path.insert(0, str(ROOT.parent / "issue129-code-gateway"))
import code_gateway as gateway


RETAINED_BUDGET = json.loads('''{
  "cap_cents": 1000,
  "entries": [
    {
      "ceiling_cents": 100,
      "phase": "worker",
      "request_id": "d34d48c860440cf6ba11248960b31a21bf9c5daeee6b4c94244dd10e15744637",
      "request_sha256": "1a90fdf4c5ba94cea9d92add2309a073dfc991fec8b28b3bdb813da3975bff03",
      "response_sha256": "8aca5ab74eea28621462d2b224d81abfd1d81b210330741bc14a6708f5927260",
      "sequence": 1,
      "state": "FINALIZED",
      "work_id": "078fc14324d2bbd501e38c8b6641e0f1f4ae0bac6ada8db0d63f9a996e391691"
    },
    {
      "ceiling_cents": 100,
      "phase": "worker",
      "request_id": "2a213b4f7f29957d8169f12ee927239146f6150da809cde22bf717c5c9317f54",
      "request_sha256": "eb5029e83ddfa9949ff67f8b690a1f03e26dac48b2e63bd692abe04197cf8bf8",
      "response_sha256": "453ee7a3dece2e590541495058c571d78563e2b19bf4f6632d4df934cd0b1f70",
      "sequence": 2,
      "state": "FINALIZED",
      "work_id": "078fc14324d2bbd501e38c8b6641e0f1f4ae0bac6ada8db0d63f9a996e391691"
    },
    {
      "ceiling_cents": 100,
      "phase": "worker",
      "request_id": "7ac02793898f419c26de885161c99db60d2563dea2e4659de878482aa3dc6709",
      "request_sha256": "47ac05acf6001d654110ec50dad4c6dac1439ca051183cc8ca02216bec4ae737",
      "sequence": 3,
      "state": "CONSUMED",
      "work_id": "078fc14324d2bbd501e38c8b6641e0f1f4ae0bac6ada8db0d63f9a996e391691"
    },
    {
      "ceiling_cents": 100,
      "phase": "worker",
      "request_id": "200b125da62dac1a14c566bbf8e8a73e71d5abb846e22b4a540874bb4eef80b6",
      "request_sha256": "969d3fe32391d6f2aa6ee8f2838cee933b0ab100cfdba09bd576f34c2835f778",
      "response_sha256": "9665e70d1ecf02b4d6c681b935127f0bfc5bf5e35892d78a25bbd1d58d8dbaec",
      "sequence": 1,
      "state": "FINALIZED",
      "work_id": "df442f6a440d52a3533ccbda0c20671ab54259f54ff481b5cfba2970594b88c5"
    },
    {
      "ceiling_cents": 100,
      "phase": "worker",
      "request_id": "f7ad247a7f4b693542457894551c29e018d2859c05fa5cd5656f88a5540aebe8",
      "request_sha256": "fddf57e26c790021515efe5dd859af2148a9e0552c435ec68fb39ddb9ab43ca2",
      "response_sha256": "7e9fc63eb306a1c45ef6a8dea80865f2a584de5c95b0b46f97b732040d6fffee",
      "sequence": 2,
      "state": "FINALIZED",
      "work_id": "df442f6a440d52a3533ccbda0c20671ab54259f54ff481b5cfba2970594b88c5"
    },
    {
      "ceiling_cents": 100,
      "phase": "worker",
      "request_id": "294e9df9d4cc850d143d280fe7de8ae681c9b0066d18b2f2ae264b15c25dc8f3",
      "request_sha256": "abdb381e4dc513da0bdd4f710f5437b3aa3b54fbe143df83c2a3f629fa0bea32",
      "response_sha256": "8e2cc25a006dd7f113c495bf82d78b76f726f0af6f78f9b7d8f5584d95f999cb",
      "sequence": 3,
      "state": "FINALIZED",
      "work_id": "df442f6a440d52a3533ccbda0c20671ab54259f54ff481b5cfba2970594b88c5"
    },
    {
      "ceiling_cents": 100,
      "phase": "worker",
      "request_id": "d293430e20e834f5537f81eebc581b4037cc0acffa8b7fe45c57ac5a499b6dd1",
      "request_sha256": "c79887a29aca22e102fae718f4353f4a27daa5dbad4ccb6932d6bdea0883542c",
      "response_sha256": "503854b36e96a7845b90619303c28cee4025a4bb88944fbb0fefbd2f46aee4eb",
      "sequence": 4,
      "state": "FINALIZED",
      "work_id": "df442f6a440d52a3533ccbda0c20671ab54259f54ff481b5cfba2970594b88c5"
    }
  ],
  "max_requests": 10,
  "package": "issue129-20261022",
  "revision": 20,
  "transition_id": "66fe7979c30145a82956c7f8e70a72d4",
  "version": 2
}''')


class Fixture:
    def __init__(self):
        self.now = 1792689000
        self.calls = []
        self.source_sha, self.public_sha, self.work_id = "a" * 40, "b" * 40, gateway.RECOVERY_WORK_ID
        self.environment = {"GITHUB_REPOSITORY": gateway.PUBLIC, "GITHUB_REPOSITORY_ID": str(gateway.PUBLIC_ID),
            "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": "1978serg-cpu",
            "GITHUB_ACTOR_ID": str(gateway.OWNER_ID), "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_REF": gateway.PUBLIC + "/.github/workflows/code-gateway.yml@refs/heads/main",
            "GITHUB_SHA": self.public_sha, "CW_SOURCE_SHA": self.source_sha, "CW_WORK_ID": self.work_id,
            "GITHUB_RUN_ID": "123", "CW_GATEWAY_OPERATOR_TOKEN": "synthetic-source-token", "GH_PUBLIC_TOKEN": "synthetic-public-token"}
        self.gates = {gateway.PAID: "false", gateway.CODE: "false"}
        self.lease, self.marker = None, None
        self.dispatched, self.watching = False, False
        self.fail, self.duplicate = None, False
        self.watch_ready = True
        self.source_outcome = "success"
        self.budget = copy.deepcopy(RETAINED_BUDGET)
        self.public_run = self.run(123, gateway.PUBLIC, gateway.PUBLIC_ID, self.public_sha, "main", "code-gateway.yml")
        self.public_run["display_title"] = "CW issue129 code " + self.work_id
        self.source_run = self.run(234, gateway.SOURCE, gateway.SOURCE_ID, self.source_sha, gateway.BRANCH, gateway.CONTROLLER)
        self.source_run["display_title"] = "CW issue129 launch " + self.work_id
        self.watch = self.run(345, gateway.PUBLIC, gateway.PUBLIC_ID, self.public_sha, "main", gateway.WATCHDOG)
        self.watch.update(display_title="CW issue88 code_watch 123", actor={"login": "github-actions[bot]", "type": "Bot", "id": 1},
            triggering_actor={"login": "github-actions[bot]", "type": "Bot", "id": 1})
        self.selftest = {**self.watch, "display_title": "CW issue88 off_selftest 0", "status": "completed", "conclusion": "success",
            "actor": {"login": "1978serg-cpu", "id": gateway.OWNER_ID}}
        self.reviews = [{"state": "approved", "user": {"id": gateway.OWNER_ID},
            "environments": [{"name": "paid-one-shot", "can_admins_bypass": False}]}]
        self.original_marker = {"ref": "refs/heads/" + gateway.ORIGINAL_MARKER,
            "object": {"sha": gateway.ORIGINAL_PUBLIC_SHA}}
        self.recovery1_marker = {"ref": "refs/heads/" + gateway.RECOVERY1_MARKER,
            "object": {"sha": gateway.RECOVERY1_PUBLIC_SHA}}
        self.recovery2_marker = {"ref": "refs/heads/" + gateway.RECOVERY2_MARKER,
            "object": {"sha": gateway.RECOVERY2_PUBLIC_SHA}}
        self.previous = {}
        for repository, repository_id, run_id, sha, branch, workflow, actor, title in (
            (gateway.PUBLIC, gateway.PUBLIC_ID, "39840999602", gateway.ORIGINAL_PUBLIC_SHA, "main", "code-gateway.yml",
             gateway.OWNER_ID, "CW issue129 code " + gateway.ORIGINAL_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39841115852", gateway.ORIGINAL_SOURCE_SHA, gateway.BRANCH, gateway.CONTROLLER,
             gateway.OWNER_ID, "CW issue129 launch " + gateway.ORIGINAL_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39841262708", gateway.ORIGINAL_SOURCE_SHA,
             "gh-aw/work-queue/" + gateway.ORIGINAL_SOURCE_SHA, "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_ef8262a3e68600f48828dad443358ce5a9ac11d458fd935b078a1b2a965ac864_1"),
            (gateway.PUBLIC, gateway.PUBLIC_ID, "39852724729", gateway.RECOVERY1_PUBLIC_SHA, "main", "code-gateway.yml",
             gateway.OWNER_ID, "CW issue129 code " + gateway.RECOVERY1_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39852966443", gateway.RECOVERY1_SOURCE_SHA, gateway.BRANCH, gateway.CONTROLLER,
             gateway.OWNER_ID, "CW issue129 launch " + gateway.RECOVERY1_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39853131813", gateway.RECOVERY1_SOURCE_SHA,
             "gh-aw/work-queue/" + gateway.RECOVERY1_SOURCE_SHA, "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_e62d9eeaf7d5fbbedaeb9d5dce8f22542b7a1f805558414125ab90d37e244e59_1"),
            (gateway.PUBLIC, gateway.PUBLIC_ID, "39870019362", gateway.RECOVERY2_PUBLIC_SHA, "main", "code-gateway.yml",
             gateway.OWNER_ID, "CW issue129 code " + gateway.RECOVERY2_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39870151844", gateway.RECOVERY2_SOURCE_SHA, gateway.BRANCH, gateway.CONTROLLER,
             gateway.OWNER_ID, "CW issue129 launch " + gateway.RECOVERY2_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39870273851", gateway.RECOVERY2_SOURCE_SHA,
             "gh-aw/work-queue/" + gateway.RECOVERY2_SOURCE_SHA, "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_1ccd2e9191760f194efbb0dcd269965ba78292b77d234371dd958ab39d823ae0_1")):
            row = self.run(int(run_id), repository, repository_id, sha, branch, workflow)
            row.update(status="completed", conclusion="failure", display_title=title,
                actor={"id": actor}, triggering_actor={"id": actor})
            self.previous[run_id] = row

    def run(self, run_id, repository, repository_id, sha, branch, workflow):
        return {"id": run_id, "repository": {"full_name": repository, "id": repository_id},
            "head_sha": sha, "head_branch": branch, "path": ".github/workflows/" + workflow,
            "event": "workflow_dispatch", "run_attempt": 1, "status": "in_progress", "conclusion": None,
            "created_at": dt.datetime.fromtimestamp(self.now - 1, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actor": {"login": "1978serg-cpu", "id": gateway.OWNER_ID},
            "triggering_actor": {"login": "1978serg-cpu", "id": gateway.OWNER_ID}}

    def pause(self, seconds):
        self.now += seconds

    def call(self, repository, method, path, token, body=None):
        self.calls.append((repository, method, path, copy.deepcopy(body)))
        if self.fail and self.fail(repository, method, path, body):
            raise ValueError("synthetic lost reply")
        if method == "GET":
            if path == "git/ref/heads/" + gateway.ORIGINAL_MARKER:
                return copy.deepcopy(self.original_marker)
            if path == "git/ref/heads/" + gateway.RECOVERY1_MARKER:
                return copy.deepcopy(self.recovery1_marker)
            if path == "git/ref/heads/" + gateway.RECOVERY2_MARKER:
                return copy.deepcopy(self.recovery2_marker)
            if path.startswith("actions/runs/") and path.endswith("/attempts/1"):
                return copy.deepcopy(self.previous[path.split("/")[2]])
            if repository == gateway.SOURCE and path == "":
                return {"full_name": gateway.SOURCE, "id": gateway.SOURCE_ID, "default_branch": gateway.BRANCH}
            if path == "git/ref/heads/" + gateway.BRANCH:
                return {"object": {"sha": self.source_sha}}
            if path == "contents/package-budget.json?ref=cw-issue129-budget":
                return {"type": "file", "encoding": "base64", "size": 200,
                    "content": base64.b64encode(json.dumps(self.budget).encode()).decode()}
            if path == "actions/runs/123":
                return copy.deepcopy(self.public_run)
            if path == "actions/runs/234":
                result = copy.deepcopy(self.source_run)
                if all(value == "true" for value in self.gates.values()) and self.source_outcome is not None:
                    result.update(status="completed", conclusion=self.source_outcome)
                return result
            if path == "actions/runs/345":
                return copy.deepcopy(self.watch)
            if path == "branches/main":
                return {"protected": True, "commit": {"sha": self.public_sha}}
            if path == "actions/runs/123/approvals":
                return self.reviews
            if path == "git/ref/heads/" + gateway.MARKER:
                return self.marker
            if path.startswith("actions/variables/"):
                name = path.split("/")[-1]
                return ({"name": name, "value": self.lease} if self.lease is not None else None) if name == gateway.LEASE else {"name": name, "value": self.gates[name]}
            if path.endswith("/runs?per_page=50"):
                if repository == gateway.PUBLIC:
                    return {"workflow_runs": [self.selftest] + ([self.watch] if self.watching else [])}
                result = [self.source_run] if self.dispatched and gateway.CONTROLLER in path else []
                if self.duplicate and result:
                    result += [{**self.source_run, "id": 235}]
                return {"workflow_runs": result}
            if path == "actions/runs/345/jobs?per_page=50":
                return {"jobs": [{"name": "Independent OFF-only watchdog", "status": "in_progress", "steps": [{
                    "name": "Verify gate OFF or guard active pilot (no models)", "status": "in_progress" if self.watch_ready else "queued"}]},
                    {"name": "One specifically owner-approved Issue88 pilot", "status": "completed", "conclusion": "skipped"}]}
        if repository == gateway.PUBLIC and method == "POST" and path == "git/refs":
            self.marker = {"ref": body["ref"], "object": {"sha": body["sha"]}}
            return self.marker
        if repository == gateway.SOURCE and method == "POST" and path.endswith("/dispatches"):
            self.dispatched = True
            return None
        if repository == gateway.PUBLIC and method == "POST" and path.endswith("/dispatches"):
            self.watching = True
            return None
        if repository == gateway.SOURCE and method in ("PATCH", "POST"):
            if body["name"] == gateway.LEASE:
                self.lease = body["value"]
            else:
                self.gates[body["name"]] = body["value"]
            return None
        raise AssertionError((repository, method, path))

    def execute(self):
        return gateway.execute(self.environment, call=self.call, clock=lambda: self.now,
            monotonic=lambda: self.now, pause=self.pause)


class AcceleratedFixture(Fixture):
    def __init__(self):
        super().__init__()
        self.work_id = gateway.ACCELERATED_WORK
        self.environment["CW_WORK_ID"] = self.work_id
        self.public_run["display_title"] = "CW issue129 code " + self.work_id
        self.source_run["display_title"] = "CW issue129 accelerated_launch " + self.work_id
        self.accelerated_budget = {"version": 2, "package": gateway.ACCELERATED_PACKAGE,
            "cap_cents": 5000, "max_requests": 100, "revision": 0, "entries": [], "transition_id": "a" * 32}
        self.original_head = gateway.RETAINED_FINAL_HEAD
        self.recovery3_marker = {"ref": "refs/heads/" + gateway.MARKER, "object": {"sha": gateway.RECOVERY3_PUBLIC}}
        for repository, repository_id, run_id, sha, branch, workflow, actor, title in (
            (gateway.PUBLIC, gateway.PUBLIC_ID, "39877788233", gateway.RECOVERY3_PUBLIC, "main", "code-gateway.yml", gateway.OWNER_ID,
             "CW issue129 code " + gateway.RECOVERY_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39877875874", gateway.RECOVERY3_SOURCE, gateway.BRANCH, gateway.CONTROLLER, gateway.OWNER_ID,
             "CW issue129 launch " + gateway.RECOVERY_WORK_ID),
            (gateway.SOURCE, gateway.SOURCE_ID, "39877972752", gateway.RECOVERY3_SOURCE, "gh-aw/work-queue/" + gateway.RECOVERY3_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_3f8f143cf17f300c2f5859459fdfc046958c8037f701e33ca50fb8957aaa0602_1"),
        ):
            run = self.run(int(run_id), repository, repository_id, sha, branch, workflow)
            run.update(status="completed", conclusion="failure", display_title=title,
                actor={"id": actor}, triggering_actor={"id": actor})
            self.previous[run_id] = run

    def call(self, repository, method, path, token, body=None):
        value = NotImplemented
        if method == "GET":
            if repository == gateway.SOURCE and path == "git/ref/heads/cw-issue129-budget":
                value = {"ref": "refs/heads/cw-issue129-budget", "object": {"sha": self.original_head}}
            if repository == gateway.SOURCE and path == "contents/package-budget.json?ref=cw-issue129-accelerated-budget":
                raw = json.dumps(self.accelerated_budget).encode()
                value = {"type": "file", "encoding": "base64", "size": len(raw), "content": base64.b64encode(raw).decode()}
            if repository == gateway.PUBLIC and path == "git/ref/heads/" + gateway.MARKER:
                value = self.recovery3_marker
            if repository == gateway.PUBLIC and path == "git/ref/heads/" + gateway.ACCELERATED_MARKER:
                value = self.marker
        if value is not NotImplemented:
            self.calls.append((repository, method, path, copy.deepcopy(body)))
            return copy.deepcopy(value)
        return super().call(repository, method, path, token, body)


class AcceleratedSuccessorFixture(AcceleratedFixture):
    def __init__(self):
        super().__init__()
        self.work_id = gateway.ACCELERATED2_WORK; self.environment["CW_WORK_ID"] = self.work_id
        self.public_run["display_title"] = "CW issue129 code " + self.work_id
        self.source_run["display_title"] = "CW issue129 accelerated_launch " + self.work_id
        self.first_consumed = {"ref": "refs/heads/" + gateway.ACCELERATED_MARKER,
            "object": {"sha": gateway.ACCELERATED1_PUBLIC}}
        for repository, repository_id, run_id, sha, branch, workflow, actor, title, conclusion in (
            (gateway.PUBLIC, gateway.PUBLIC_ID, "39883821037", gateway.ACCELERATED1_PUBLIC, "main", "code-gateway.yml", gateway.OWNER_ID,
             "CW issue129 code " + gateway.ACCELERATED_WORK, "cancelled"),
            (gateway.SOURCE, gateway.SOURCE_ID, "39883932232", gateway.ACCELERATED1_SOURCE, gateway.BRANCH, gateway.CONTROLLER, gateway.OWNER_ID,
             "CW issue129 accelerated_launch " + gateway.ACCELERATED_WORK, "failure"),
            (gateway.SOURCE, gateway.SOURCE_ID, "39884029905", gateway.ACCELERATED1_SOURCE, "gh-aw/work-queue/" + gateway.ACCELERATED1_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_28d184129b57493ba0a57d3e81ca083da9b843ca455d90954c0578f935c9184e_1", "cancelled"),
        ):
            run = self.run(int(run_id), repository, repository_id, sha, branch, workflow)
            run.update(status="completed", conclusion=conclusion, display_title=title,
                actor={"id": actor}, triggering_actor={"id": actor}); self.previous[run_id] = run

    def call(self, repository, method, path, token, body=None):
        if repository == gateway.PUBLIC and method == "GET" and path in (
                "git/ref/heads/" + gateway.ACCELERATED_MARKER, "git/ref/heads/" + gateway.ACCELERATED2_MARKER):
            self.calls.append((repository, method, path, copy.deepcopy(body)))
            return copy.deepcopy(self.first_consumed if path.endswith(gateway.ACCELERATED_MARKER) else self.marker)
        return super().call(repository, method, path, token, body)


class AcceleratedSuccessorTests(unittest.TestCase):
    def test_distinct_successor_preserves_the_first_consumption_marker_and_same_unused_package(self):
        f = AcceleratedSuccessorFixture(); marker = copy.deepcopy(f.first_consumed); budget = copy.deepcopy(f.accelerated_budget)
        self.assertEqual(f.execute(), "CODE_CONTROLLER_COMPLETED_NATIVE_RESULT_REQUIRES_READBACK")
        self.assertEqual(f.marker["ref"], "refs/heads/" + gateway.ACCELERATED2_MARKER)
        self.assertEqual(f.first_consumed, marker); self.assertEqual(f.accelerated_budget, budget)
        self.assertEqual(json.loads(f.lease)["max_requests"], 100)
        self.assertEqual(list(f.gates.values()), ["false", "false"])

    def test_successor_requires_exact_cancelled_run_and_unmodified_attempt_marker(self):
        for mutate in (lambda f: setattr(f, "first_consumed", None),
                       lambda f: f.previous["39884029905"].update(conclusion="failure"),
                       lambda f: f.previous["39884029905"].update(head_sha="c" * 40),
                       lambda f: f.accelerated_budget.update(entries=[{}])):
            f = AcceleratedSuccessorFixture(); mutate(f)
            with self.assertRaises(Exception): f.execute()
            self.assertTrue(all(c[1] == "GET" for c in f.calls))


class AcceleratedGatewayTests(unittest.TestCase):
    def test_new_package_keeps_all_old_markers_and_issues_only_the_new_bounded_lease(self):
        f = AcceleratedFixture(); before = copy.deepcopy(f.recovery3_marker)
        self.assertEqual(f.execute(), "CODE_CONTROLLER_COMPLETED_NATIVE_RESULT_REQUIRES_READBACK")
        self.assertEqual(f.recovery3_marker, before)
        self.assertEqual(f.original_head, gateway.RETAINED_FINAL_HEAD)
        lease = json.loads(f.lease)
        self.assertEqual((lease["package"], lease["cap_cents"], lease["max_requests"]),
            (gateway.ACCELERATED_PACKAGE, 5000, 100))
        dispatches = [c for c in f.calls if c[0] == gateway.SOURCE and c[1] == "POST" and c[2].endswith("/dispatches")]
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(dispatches[0][3]["inputs"]["mode"], "accelerated_launch")
        self.assertEqual(f.marker["ref"], "refs/heads/" + gateway.ACCELERATED_MARKER)
        self.assertEqual(list(f.gates.values()), ["false", "false"])
        with self.assertRaises(Exception): f.execute()
        self.assertEqual(len([c for c in f.calls if c[0] == gateway.SOURCE and c[1] == "POST" and c[2].endswith("/dispatches")]), 1)

    def test_new_readiness_check_is_read_only(self):
        f = AcceleratedFixture(); f.environment["CW_PREFLIGHT_ONLY"] = "true"
        self.assertEqual(f.execute(), "CODE_GATEWAY_PREFLIGHT_VERIFIED_NO_DISPATCH_NO_SPEND")
        self.assertTrue(all(c[1] == "GET" for c in f.calls))

    def test_used_or_changed_new_budget_and_missing_terminal_evidence_never_dispatch(self):
        changes = (lambda f: f.accelerated_budget.update(cap_cents=5001),
            lambda f: f.accelerated_budget.update(max_requests=101),
            lambda f: f.accelerated_budget.update(entries=[{}]),
            lambda f: f.accelerated_budget.update(revision=1),
            lambda f: setattr(f, "original_head", "c" * 40),
            lambda f: setattr(f, "recovery3_marker", None),
            lambda f: f.previous["39877972752"].update(status="in_progress", conclusion=None))
        for mutate in changes:
            with self.subTest(change=changes.index(mutate)):
                f = AcceleratedFixture(); mutate(f)
                with self.assertRaises(Exception): f.execute()
                self.assertTrue(all(c[1] == "GET" for c in f.calls))

    def test_unknown_dispatch_and_independent_watchdog_failure_leave_both_gates_off(self):
        for change in (lambda f: setattr(f, "watch_ready", False), lambda f: setattr(f, "source_outcome", "failure")):
            f = AcceleratedFixture(); change(f)
            with self.assertRaises(Exception): f.execute()
            self.assertEqual(list(f.gates.values()), ["false", "false"])
            self.assertIsNotNone(f.marker)


class GatewayTests(unittest.TestCase):
    def test_retained_unknown_request_cannot_be_refunded_relabelled_or_finalized(self):
        changes = (
            lambda f: f.budget["entries"].pop(),
            lambda f: f.budget["entries"][2].update(state="FINALIZED"),
            lambda f: f.budget["entries"][2].update(work_id=f.work_id),
            lambda f: f.budget.update(revision=9),
            lambda f: f.budget.update(cap_cents=1001),
            lambda f: f.budget.update(max_requests=11),
            lambda f: f.budget["entries"][0].update(response_sha256="f" * 64),
        )
        for mutate in changes:
            with self.subTest(change=changes.index(mutate)):
                f = Fixture(); mutate(f)
                with self.assertRaises(Exception):
                    f.execute()
                self.assertTrue(all(c[1] == "GET" for c in f.calls))
                self.assertEqual(list(f.gates.values()), ["false", "false"])

    def test_one_successor_preserves_original_marker_and_has_a_separate_consumption_record(self):
        f = Fixture()
        original = copy.deepcopy(f.original_marker)
        recovery1 = copy.deepcopy(f.recovery1_marker)
        recovery2 = copy.deepcopy(f.recovery2_marker)
        budget = copy.deepcopy(f.budget)
        f.execute()
        self.assertEqual(f.original_marker, original)
        self.assertEqual(f.recovery1_marker, recovery1)
        self.assertEqual(f.recovery2_marker, recovery2)
        self.assertEqual(f.budget, budget)
        self.assertEqual(f.budget["entries"][2]["state"], "CONSUMED")
        creates = [c for c in f.calls if c[1] == "POST" and c[2] == "git/refs"]
        self.assertEqual([c[3]["ref"] for c in creates], ["refs/heads/" + gateway.MARKER])
        self.assertNotEqual(gateway.MARKER, gateway.ORIGINAL_MARKER)

    def test_predecessor_drift_or_unknown_outcome_never_consumes_or_dispatches(self):
        changes = (
            lambda f: setattr(f, "original_marker", None),
            lambda f: setattr(f, "recovery1_marker", None),
            lambda f: setattr(f, "recovery2_marker", None),
            lambda f: f.recovery2_marker["object"].update(sha="d" * 40),
            lambda f: f.environment.update(CW_WORK_ID=gateway.RECOVERY2_WORK_ID),
            lambda f: f.environment.update(CW_SOURCE_SHA=gateway.RECOVERY2_SOURCE_SHA),
            lambda f: f.recovery1_marker["object"].update(sha="d" * 40),
            lambda f: f.environment.update(CW_WORK_ID=gateway.RECOVERY1_WORK_ID),
            lambda f: f.environment.update(CW_SOURCE_SHA=gateway.RECOVERY1_SOURCE_SHA),
            lambda f: f.original_marker["object"].update(sha="d" * 40),
            lambda f: f.environment.update(CW_WORK_ID=gateway.ORIGINAL_WORK_ID),
            lambda f: f.environment.update(CW_WORK_ID="d" * 64),
            lambda f: f.environment.update(CW_SOURCE_SHA=gateway.ORIGINAL_SOURCE_SHA),
        )
        for mutate in changes:
            with self.subTest(change=changes.index(mutate)):
                f = Fixture(); mutate(f)
                with self.assertRaises(Exception):
                    f.execute()
                self.assertTrue(all(c[1] == "GET" for c in f.calls))
        for run_id in ("39840999602", "39841115852", "39841262708", "39852724729", "39852966443", "39853131813", "39870019362", "39870151844", "39870273851"):
            for change in ({"status": "in_progress", "conclusion": None}, {"conclusion": "success"},
                           {"run_attempt": 2}, {"head_sha": "d" * 40}, {"event": "push"},
                           {"actor": {"id": 123}}, {"repository": {"full_name": "foreign", "id": 0}}):
                with self.subTest(run=run_id, change=change):
                    f = Fixture(); f.previous[run_id].update(change)
                    with self.assertRaises(Exception):
                        f.execute()
                    self.assertTrue(all(c[1] == "GET" for c in f.calls))

    def test_read_only_preflight_never_creates_marker_lease_dispatch_or_enables(self):
        f = Fixture()
        f.environment["CW_PREFLIGHT_ONLY"] = "true"
        self.assertEqual(f.execute(), "CODE_GATEWAY_PREFLIGHT_VERIFIED_NO_DISPATCH_NO_SPEND")
        self.assertTrue(all(c[1] == "GET" for c in f.calls))
        self.assertIsNone(f.marker)
        self.assertIsNone(f.lease)
        self.assertFalse(f.dispatched)
        self.assertFalse(f.watching)
        self.assertEqual(list(f.gates.values()), ["false", "false"])
        f = Fixture()
        f.environment["CW_PREFLIGHT_ONLY"] = "yes"
        with self.assertRaises(Exception):
            f.execute()
        self.assertEqual(f.calls, [])

    def test_http_error_diagnostic_contains_only_status_never_url_body_or_credential(self):
        opener = mock.Mock()
        opener.open.side_effect = gateway.urllib.error.HTTPError(
            "https://example.invalid/synthetic-private-url", 403,
            "synthetic-private-response", {}, None)
        output = io.StringIO()
        with mock.patch.object(gateway.urllib.request, "build_opener", return_value=opener), \
                mock.patch("sys.stdout", output):
            with self.assertRaisesRegex(ValueError, "CODE_GATEWAY_OUTCOME_UNKNOWN_NO_RETRY"):
                gateway.api(gateway.SOURCE, "GET", "git/ref/heads/" + gateway.BRANCH,
                            "synthetic-private-token")
        self.assertEqual(output.getvalue(), "CODE_GATEWAY_HTTP_ERROR_403\n")

    def test_realistic_fifty_run_api_response_and_finite_byte_ceiling(self):
        listing = {"workflow_runs": [{"id": i, "repository_metadata": "x" * 14000}
                                    for i in range(50)]}
        raw = json.dumps(listing).encode()
        self.assertGreater(len(raw), 262144)
        for body, accepted in ((raw, True),
                               (b" " * (gateway.MAX_API_RESPONSE_BYTES + 1), False),
                               (b'{"workflow_runs":[],"workflow_runs":[]}', False)):
            with self.subTest(accepted=accepted, size=len(body)):
                reply = mock.MagicMock()
                reply.status = 200
                reply.__enter__.return_value = reply
                reply.read.side_effect = lambda limit: body[:limit]
                opener = mock.Mock()
                opener.open.return_value = reply
                with mock.patch.object(gateway.urllib.request, "build_opener", return_value=opener):
                    args = (gateway.PUBLIC, "GET", "actions/runs?per_page=50", "synthetic-public-token")
                    if accepted:
                        self.assertEqual(gateway.api(*args), listing)
                    else:
                        with self.assertRaisesRegex(ValueError, "CODE_GATEWAY_OUTCOME_UNKNOWN_NO_RETRY"):
                            gateway.api(*args)
                reply.read.assert_called_once_with(gateway.MAX_API_RESPONSE_BYTES + 1)

    def test_one_native_dispatch_independent_watchdog_lease_and_both_off(self):
        f = Fixture()
        self.assertEqual(f.execute(), "CODE_CONTROLLER_COMPLETED_NATIVE_RESULT_REQUIRES_READBACK")
        self.assertEqual(list(f.gates.values()), ["false", "false"])
        dispatches = [c for c in f.calls if c[1] == "POST" and c[2].endswith("/dispatches")]
        self.assertEqual(len(dispatches), 2)
        self.assertEqual(sum(c[0] == gateway.SOURCE for c in dispatches), 1)
        value = json.loads(f.lease)
        self.assertEqual(value["controller_run_id"], "234")
        self.assertEqual(value["gateway_run_id"], "123")
        self.assertEqual(value["cap_cents"], 1000)
        self.assertLessEqual(value["expires_at"] - value["issued_at"], 1200)
        self.assertTrue(f.watching)
        self.assertLess(f.calls.index(dispatches[1]), next(i for i, c in enumerate(f.calls) if c[3] == {"name": gateway.CODE, "value": "true"}))

    def test_consumed_attempt_and_used_budget_do_not_dispatch(self):
        for mutate in (lambda f: setattr(f, "marker", {"existing": True}), lambda f: f.budget.update(revision=1, entries=[{}])):
            f = Fixture()
            mutate(f)
            with self.assertRaises(Exception):
                f.execute()
            self.assertFalse(f.dispatched)
            self.assertFalse(any(c[1] != "GET" for c in f.calls))

    def test_owner_context_and_real_environment_review_required(self):
        for mutate in (lambda f: f.environment.update(GITHUB_ACTOR_ID="123"),
            lambda f: f.environment.update(GITHUB_RUN_ATTEMPT="2"), lambda f: f.reviews.clear(),
            lambda f: f.reviews[0].update(state="rejected"),
            lambda f: f.reviews[0]["environments"][0].update(can_admins_bypass=True)):
            f = Fixture()
            mutate(f)
            with self.assertRaises(Exception):
                f.execute()
            self.assertFalse(any(c[1] != "GET" for c in f.calls))

    def test_source_or_recent_off_evidence_drift_blocks_before_consumption(self):
        for mutate in (lambda f: f.environment.update(CW_SOURCE_SHA="d" * 40),
            lambda f: f.selftest.update(head_sha="d" * 40), lambda f: f.selftest.update(conclusion="failure"),
            lambda f: f.gates.update({gateway.PAID: "true"})):
            f = Fixture()
            mutate(f)
            with self.assertRaises(Exception):
                f.execute()
            self.assertIsNone(f.marker)
            self.assertFalse(f.dispatched)

    def test_uncertain_source_dispatch_is_sent_once_and_forces_both_off(self):
        f = Fixture()
        f.fail = lambda repo, method, path, body: repo == gateway.SOURCE and method == "POST" and path.endswith("/dispatches")
        with self.assertRaises(Exception):
            f.execute()
        self.assertEqual(sum(c[0] == gateway.SOURCE and c[1] == "POST" and c[2].endswith("/dispatches") for c in f.calls), 1)
        self.assertEqual(sum(c[1] == "PATCH" and c[3]["value"] == "false" for c in f.calls), 2)

    def test_duplicate_source_runs_and_unready_watchdog_never_enable(self):
        for mutate in (lambda f: setattr(f, "duplicate", True), lambda f: setattr(f, "watch_ready", False)):
            f = Fixture()
            mutate(f)
            with self.assertRaises(Exception):
                f.execute()
            self.assertFalse(any(c[1] == "PATCH" and c[3].get("value") == "true" for c in f.calls))
            self.assertEqual(list(f.gates.values()), ["false", "false"])

    def test_lost_gate_enable_reply_is_not_retried_and_finally_off_runs(self):
        f = Fixture()
        f.fail = lambda repo, method, path, body: method == "PATCH" and body == {"name": gateway.PAID, "value": "true"}
        with self.assertRaises(Exception):
            f.execute()
        self.assertEqual(sum(c[3] == {"name": gateway.PAID, "value": "true"} for c in f.calls), 1)
        self.assertEqual(list(f.gates.values()), ["false", "false"])

    def test_stale_public_parent_cannot_be_renewed(self):
        f = Fixture()
        f.pause(121)
        with self.assertRaises(Exception):
            f.execute()
        self.assertIsNotNone(f.marker)
        self.assertFalse(f.watching)
        self.assertEqual(list(f.gates.values()), ["false", "false"])

    def test_failed_off_readback_is_reported_as_unknown(self):
        f = Fixture()
        f.fail = lambda repo, method, path, body: method == "PATCH" and body == {"name": gateway.PAID, "value": "false"}
        with self.assertRaises(Exception):
            f.execute()
        self.assertTrue(any(c[3] == {"name": gateway.CODE, "value": "false"} for c in f.calls))

    def test_failed_or_timed_out_source_parent_is_not_a_result_and_forces_off(self):
        for outcome in ("failure", None):
            f = Fixture()
            f.source_outcome = outcome
            with self.assertRaises(Exception):
                f.execute()
            self.assertEqual(list(f.gates.values()), ["false", "false"])
            self.assertEqual(sum(c[0] == gateway.SOURCE and c[1] == "POST" and c[2].endswith("/dispatches") for c in f.calls), 1)


if __name__ == "__main__":
    unittest.main()

