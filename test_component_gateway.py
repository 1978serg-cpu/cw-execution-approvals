"""Finite gateway integration with inert GitHub, clocks and synthetic budgets."""
import base64
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import component_gateway as gateway
import orchestrator_component_lease as lease
from test_orchestrator_code_lease import NOW, stamp


def synthetic_budget():
    return {"version": 2, "package": "issue129-20261022-accelerated", "cap_cents": 15000,
        "max_requests": 500, "entries": [
            {"state": "CONSUMED", "ceiling_cents": 200 if i < 29 else 164,
             "request_id": f"{i:064x}"} for i in range(30)]}


class Fixture:
    def __init__(self):
        self.now = NOW
        self.calls, self.values, self.markers = [], {}, {}
        self.gates = {lease.PAID: "false", lease.CODE: "false"}
        self.failure, self.prepared, self.finish_at = None, True, None
        self.budget = synthetic_budget()
        self.env = {"GITHUB_REPOSITORY": lease.PUBLIC, "GITHUB_REPOSITORY_ID": str(lease.PUBLIC_ID),
            "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_ACTOR": lease.OWNER, "GITHUB_ACTOR_ID": str(lease.OWNER_ID), "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_REF": lease.PUBLIC + "/.github/workflows/component-gateway.yml@refs/heads/main",
            "GITHUB_SHA": "b" * 40, "CW_SOURCE_SHA": "a" * 40, "CW_APPROVAL_REF": "c" * 40,
            "CW_WORK_ORDER_SHA256": "d" * 64, "CW_SPEC_SHA256": "e" * 64,
            "GITHUB_RUN_ID": "123", "CW_PREFLIGHT_ONLY": "false",
            "CW_GATEWAY_OPERATOR_TOKEN": "source-test-token", "GH_PUBLIC_TOKEN": "public-test-token"}
        owner = {"id": lease.OWNER_ID, "login": lease.OWNER}
        def run(identifier, repo, repo_id, head, branch, workflow, title):
            return {"id": identifier, "repository": {"id": repo_id, "full_name": repo}, "head_sha": head,
                "head_branch": branch, "path": ".github/workflows/" + workflow, "display_title": title,
                "run_attempt": 1, "event": "workflow_dispatch", "actor": owner, "triggering_actor": owner,
                "status": "in_progress", "conclusion": None, "created_at": stamp(NOW)}
        self.public = run(123, lease.PUBLIC, lease.PUBLIC_ID, "b" * 40, "main", "component-gateway.yml", "CW component order " + "d" * 64)
        self.source = run(234, lease.SOURCE, lease.SOURCE_ID, "a" * 40, lease.BRANCH, gateway.CONTROLLER, "CW component controller " + "d" * 64)
        self.watch = run(345, lease.PUBLIC, lease.PUBLIC_ID, "b" * 40, "main", gateway.WATCHDOG, "CW issue88 component_watch 123")
        bot = {"id": 1, "login": "github-actions[bot]", "type": "Bot"}
        self.watch.update(actor=bot, triggering_actor=bot)
        self.selftest = dict(self.public, id=100, display_title="CW issue88 off_selftest 0", status="completed", conclusion="success")

    def pause(self, seconds):
        self.now += seconds

    def file(self, document):
        raw = gateway.canonical(document)
        return {"type": "file", "encoding": "base64", "size": len(raw),
            "content": base64.b64encode(raw).decode(),
            "sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}

    def api(self, repo, method, path, token, body=None):
        self.calls.append((repo, method, path, copy.deepcopy(body)))
        if self.failure == (repo, method, path):
            raise ValueError("SYNTHETIC_UNKNOWN_NO_RETRY")
        if method == "GET":
            if repo == lease.PUBLIC:
                if path == "actions/runs/123": return copy.deepcopy(self.public)
                if path == "branches/main": return {"protected": True, "commit": {"sha": "b" * 40}}
                if path == "actions/runs/123/approvals": return [{"state": "approved", "user": {"id": lease.OWNER_ID},
                    "environments": [{"name": "paid-one-shot", "can_admins_bypass": False}]}]
                if path == "actions/workflows/one-shot-gateway.yml/runs?per_page=50":
                    return {"workflow_runs": [self.selftest, self.watch]}
                if path == "actions/runs/345": return copy.deepcopy(self.watch)
                if path == "actions/runs/345/jobs?per_page=50": return {"jobs": [{"name": "Independent OFF-only watchdog", "status": "in_progress",
                    "steps": [{"name": "Verify gate OFF or guard active pilot (no models)", "status": "in_progress"}]}]}
                if path.startswith("git/ref/heads/cw-component-"): return self.markers.get(path)
            if repo == lease.SOURCE:
                if path == "": return {"id": lease.SOURCE_ID, "full_name": lease.SOURCE, "default_branch": lease.BRANCH}
                if path == "git/ref/heads/" + lease.BRANCH: return {"object": {"sha": "a" * 40}}
                if path == "git/ref/heads/" + gateway.BUDGET: return {"object": {"sha": "f" * 40}}
                if path.startswith("contents/package-budget.json?ref="):
                    return self.file({**synthetic_budget(), "cap_cents": 7000, "max_requests": 100} if path.endswith(gateway.CHECKPOINT) else self.budget)
                if path.startswith("actions/variables/"):
                    name = path.split("/")[-1]
                    if name in self.gates: return {"name": name, "value": self.gates[name]}
                    value = self.values.get(name)
                    return None if value is None else {**value, "created_at": stamp(NOW)}
                if path == "actions/workflows/" + gateway.CONTROLLER + "/runs?per_page=50": return {"workflow_runs": [self.source]}
                if path == "actions/runs/234":
                    if self.finish_at is not None and self.now >= self.finish_at:
                        return dict(self.source, status="completed", conclusion="success")
                    return copy.deepcopy(self.source)
                if path == "actions/runs/234/jobs?per_page=50": return {"jobs": [{"steps": [{"name": "Prepare native graph while OFF",
                    "status": "completed", "conclusion": "success" if self.prepared else "failure"}]}]}
        if repo == lease.PUBLIC and method == "POST":
            if path == "git/refs":
                self.markers["git/ref/heads/" + body["ref"].removeprefix("refs/heads/")] = {"ref": body["ref"], "object": {"sha": body["sha"]}}
                return None
            if path == "actions/workflows/one-shot-gateway.yml/dispatches": return None
        if repo == lease.SOURCE:
            if method == "POST" and path == "actions/workflows/" + gateway.CONTROLLER + "/dispatches": return None
            if (method == "POST" and path == "actions/variables") or (method == "PATCH" and path == "actions/variables/" + lease.LEASE):
                self.values[body["name"]] = dict(body); return None
            if method == "PATCH" and path.startswith("actions/variables/"):
                self.gates[body["name"]] = body["value"]
                if body == {"name": lease.PAID, "value": "true"}: self.finish_at = self.now + 30
                return None
        raise AssertionError((repo, method, path))

    def execute(self):
        return gateway.execute(self.env, call=self.api, clock=lambda: self.now,
            monotonic=lambda: self.now, pause=self.pause)


class ComponentGatewayTests(unittest.TestCase):
    def test_reservation_queue_keeps_150_dollars_500_calls_and_all_retained_unknowns(self):
        retained = {**synthetic_budget(), "cap_cents":7000, "max_requests":100}
        for cash, slots, ready in ((600,192,True),(599,192,False),(1965,229,True),(600,191,False)):
            current = synthetic_budget()
            current["entries"].append({"state":"CONSUMED", "ceiling_cents":15000-5964-cash})
            current["entries"].extend({"state":"FINALIZED", "ceiling_cents":1, "settled_cents":0}
                for _ in range(500-slots-len(current["entries"])))
            before = copy.deepcopy(current)
            with self.subTest(cash=cash, slots=slots):
                self.assertEqual(gateway.budget_capacity(current,retained),ready)
                self.assertEqual(current,before)
                self.assertEqual((current["cap_cents"],current["max_requests"]),(15000,500))

    def test_actual_retained_budget_blocks_before_any_write_even_in_launch_mode(self):
        f = Fixture()
        f.budget["entries"].append({"state":"CONSUMED","ceiling_cents":9000})
        original = copy.deepcopy(f.budget)
        self.assertEqual(f.execute(), "COMPONENT_GATEWAY_BUDGET_BLOCKED_NO_DISPATCH_NO_SPEND")
        self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))
        self.assertEqual(f.budget, original)

    def test_historical_prefix_and_uncertain_costs_cannot_be_discounted(self):
        original = {**synthetic_budget(), "cap_cents":7000, "max_requests":100}
        for change in ("prefix", "unknown_settlement", "over_cap", "wrong_package"):
            d = {**copy.deepcopy(original), "cap_cents":15000, "max_requests":500}
            if change == "prefix": d["entries"][0]["ceiling_cents"] = 1
            if change == "unknown_settlement": d["entries"].append({"state": "CONSUMED", "ceiling_cents": 600, "settled_cents": 0})
            if change == "over_cap": d["entries"].append({"state": "RESERVED", "ceiling_cents": 15000})
            if change == "wrong_package": d["package"] = "replacement"
            with self.subTest(change=change), self.assertRaises(Exception):
                gateway.budget_capacity(d, original)

    def test_exact_context_rejects_other_actor_attempt_and_injection_before_api(self):
        for name, value in (("GITHUB_ACTOR_ID", "1"), ("GITHUB_RUN_ATTEMPT", "2"),
                            ("CW_SOURCE_SHA", "../other"), ("CW_PREFLIGHT_ONLY", "yes")):
            f = Fixture(); f.env[name] = value
            with self.subTest(field=name), self.assertRaises(Exception): f.execute()
            self.assertEqual(f.calls, [])

    def test_read_only_mode_never_writes_when_readiness_is_injected(self):
        # Current immutable budget cannot fund a wave. Inject readiness only to
        # test the later launch boundary without altering real policy or costs.
        f = Fixture(); f.env["CW_PREFLIGHT_ONLY"] = "true"
        with patch.object(gateway, "source_preflight", return_value=True):
            self.assertEqual(f.execute(), "COMPONENT_GATEWAY_PREFLIGHT_VERIFIED_NO_DISPATCH_NO_SPEND")
        self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))

    def test_finite_controller_protocol_and_both_off_with_injected_readiness(self):
        f = Fixture()
        with patch.object(gateway, "source_preflight", return_value=True):
            self.assertEqual(f.execute(), "COMPONENT_CONTROLLER_SUCCEEDED_NATIVE_RESULTS_REQUIRE_READBACK")
        self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})
        dispatches = [c for c in f.calls if c[1] == "POST" and c[2].endswith("/dispatches")]
        self.assertEqual(len(dispatches), 2)
        self.assertEqual(dispatches[0][3]["inputs"]["source_sha"], f.env["CW_SOURCE_SHA"])
        self.assertEqual(dispatches[1][3]["inputs"]["mode"], "component_watch")

    def test_failed_prepare_cannot_enable_either_gate(self):
        f = Fixture(); f.prepared = False
        with patch.object(gateway, "source_preflight", return_value=True), self.assertRaises(Exception): f.execute()
        self.assertFalse(any(c[1] == "PATCH" and c[3].get("value") == "true" for c in f.calls))
        self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})

    def test_unknown_dispatch_is_never_repeated_and_finishes_off(self):
        f = Fixture(); f.failure = (lease.SOURCE, "POST", "actions/workflows/" + gateway.CONTROLLER + "/dispatches")
        with patch.object(gateway, "source_preflight", return_value=True), self.assertRaises(Exception): f.execute()
        self.assertEqual(sum(c[:3] == f.failure for c in f.calls), 1)
        self.assertEqual(len(f.markers), 1)
        self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})

    def test_consumed_order_marker_prevents_another_dispatch(self):
        f = Fixture()
        f.markers["git/ref/heads/cw-component-" + f.env["CW_WORK_ORDER_SHA256"]] = {"object": {"sha": "b" * 40}}
        with patch.object(gateway, "source_preflight", return_value=True), self.assertRaises(Exception): f.execute()
        self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))

    def test_delayed_owner_review_stops_before_marker_or_controller_dispatch(self):
        for delay in (301, 1046):
            f = Fixture(); f.now += delay
            with self.subTest(delay=delay), patch.object(gateway, "source_preflight") as preflight:
                self.assertEqual(f.execute(), "COMPONENT_APPROVAL_WINDOW_EXPIRED_NO_DISPATCH_NO_SPEND")
                preflight.assert_not_called()
            self.assertEqual(f.markers, {})
            self.assertEqual(f.values, {})
            self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))
            self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})

    def test_prelaunch_window_retains_existing_inclusive_boundary(self):
        f = Fixture(); f.now += 300; f.env["CW_PREFLIGHT_ONLY"] = "true"
        with patch.object(gateway, "source_preflight", return_value=True):
            self.assertEqual(f.execute(), "COMPONENT_GATEWAY_PREFLIGHT_VERIFIED_NO_DISPATCH_NO_SPEND")
        self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))

    def recovery(self, record=None):
        record = gateway.PRELAUNCH_RECOVERIES[0] if record is None else record
        f = Fixture()
        f.env.update(record["approval"])
        original = "git/ref/heads/cw-component-" + f.env["CW_WORK_ORDER_SHA256"]
        f.markers[original] = {"object": {"sha": record["gateway_sha"]}}
        proofs = {}
        for repo, old, identifier, sha, title in (
            (lease.PUBLIC, f.public, record["gateway_run_id"], record["gateway_sha"], "CW component order "),
            (lease.SOURCE, f.source, record["controller_run_id"], f.env["CW_SOURCE_SHA"], "CW component controller "),
        ):
            proofs[(repo, "actions/runs/" + str(identifier))] = dict(old, id=identifier, head_sha=sha,
                display_title=title + f.env["CW_WORK_ORDER_SHA256"], status="completed", conclusion="failure")
        proofs[(lease.SOURCE, "git/ref/heads/work-queue")] = {"object": {"sha": record["queue_sha"]}}
        proofs[(lease.SOURCE, "git/ref/heads/" + gateway.BUDGET)] = {"object": {"sha": record["budget_sha"]}}
        def call(repo, method, path, token, body=None):
            if (repo, path) in proofs:
                self.assertEqual(method, "GET")
                return copy.deepcopy(proofs[(repo, path)])
            return f.api(repo, method, path, token, body)
        return f, proofs, call, original

    def test_exact_delayed_review_failure_has_one_read_only_recovery(self):
        f, _, call, original = self.recovery(gateway.PRELAUNCH_RECOVERIES[1])
        before = copy.deepcopy(f.markers)
        name = gateway.launch_marker(call, "source-test-token", "public-test-token", f.env)
        self.assertEqual(name, original.removeprefix("git/ref/heads/") + "-prelaunch-recovery1")
        self.assertEqual(f.markers, before)
        self.assertEqual(f.values, {})
        self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))
        f.markers["git/ref/heads/" + name] = {"object": {"sha": f.env["GITHUB_SHA"]}}
        with self.assertRaises(Exception):
            gateway.launch_marker(call, "source-test-token", "public-test-token", f.env)
        self.assertEqual(f.markers[original], before[original])

    def test_delayed_review_recovery_rejects_changed_evidence(self):
        record = gateway.PRELAUNCH_RECOVERIES[1]
        for damage in ("queue", "budget", "active", "successful", "attempt", "actor", "source", "order", "spec", "marker", "gate", "unknown"):
            f, proofs, call, original = self.recovery(record)
            private = proofs[(lease.SOURCE, "actions/runs/" + str(record["controller_run_id"]))]
            if damage in ("queue", "budget"):
                branch = "work-queue" if damage == "queue" else gateway.BUDGET
                proofs[(lease.SOURCE, "git/ref/heads/" + branch)]["object"]["sha"] = "0" * 40
            if damage == "active": private["status"] = "in_progress"
            if damage == "successful": private["conclusion"] = "success"
            if damage == "attempt": private["run_attempt"] = 2
            if damage == "actor": private["actor"] = {"id": 1}
            if damage == "source": private["head_sha"] = "0" * 40
            if damage == "order": f.env["CW_APPROVAL_REF"] = "0" * 40
            if damage == "spec": f.env["CW_SPEC_SHA256"] = "0" * 64
            if damage == "marker": f.markers[original]["object"]["sha"] = "0" * 40
            if damage == "gate": f.gates[lease.PAID] = "true"
            if damage == "unknown": proofs[(lease.SOURCE, "actions/runs/" + str(record["controller_run_id"]))] = None
            with self.subTest(damage=damage), self.assertRaises(Exception):
                gateway.launch_marker(call, "source-test-token", "public-test-token", f.env)
            self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))

    def test_audited_prelaunch_recovery_retains_history_and_is_single_use(self):
        f, _, call, original = self.recovery()
        before = copy.deepcopy(f.markers)
        name = gateway.launch_marker(call, "source-test-token", "public-test-token", f.env)
        self.assertEqual(name, original.removeprefix("git/ref/heads/") + "-prelaunch-recovery1")
        self.assertEqual(f.markers, before)
        self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))
        f.markers["git/ref/heads/" + name] = {"object": {"sha": f.env["GITHUB_SHA"]}}
        with self.assertRaises(Exception):
            gateway.launch_marker(call, "source-test-token", "public-test-token", f.env)
        self.assertEqual(f.markers[original], before[original])

    def test_recovery_rejects_any_changed_history_identity_order_or_gate(self):
        for damage in ("queue", "budget", "active", "successful", "attempt", "actor", "source", "order", "marker", "gate", "unknown"):
            f, proofs, call, original = self.recovery()
            private = proofs[(lease.SOURCE, "actions/runs/40019128698")]
            if damage in ("queue", "budget"):
                branch = "work-queue" if damage == "queue" else gateway.BUDGET
                proofs[(lease.SOURCE, "git/ref/heads/" + branch)]["object"]["sha"] = "0" * 40
            if damage == "active": private["status"] = "in_progress"
            if damage == "successful": private["conclusion"] = "success"
            if damage == "attempt": private["run_attempt"] = 2
            if damage == "actor": private["actor"] = {"id": 1}
            if damage == "source": private["head_sha"] = "0" * 40
            if damage == "order": f.env["CW_APPROVAL_REF"] = "0" * 40
            if damage == "marker": f.markers[original]["object"]["sha"] = "0" * 40
            if damage == "gate": f.gates[lease.PAID] = "true"
            if damage == "unknown": proofs[(lease.SOURCE, "actions/runs/40019128698")] = None
            with self.subTest(damage=damage), self.assertRaises(Exception):
                gateway.launch_marker(call, "source-test-token", "public-test-token", f.env)
            self.assertTrue(all(method == "GET" for _, method, _, _ in f.calls))


if __name__ == "__main__":
    unittest.main()
