"""Public gateway integration tests. All API calls and clocks are inert fixtures."""
import base64
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
if not (ROOT / "orchestrator_code_lease.py").is_file():
    sys.path.insert(0, str(ROOT.parent / "issue129-code-gateway"))
import code_gateway as gateway


class Fixture:
    def __init__(self):
        self.now = 1792689000
        self.calls = []
        self.source_sha, self.public_sha, self.work_id = "a" * 40, "b" * 40, "c" * 64
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
        self.budget = {"package": "issue129-20261022", "cap_cents": 1000, "max_requests": 10, "revision": 0, "entries": []}
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


class GatewayTests(unittest.TestCase):
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
