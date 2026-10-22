"""Independent OFF/lease behavior using inert API and clock fixtures only."""
import copy
import datetime as dt
import json
import unittest

import orchestrator_code_lease as lease

NOW = 1792684800


def stamp(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Fixture:
    def __init__(self):
        self.time, self.mono = NOW, 1
        self.doc = {"version": 1, "package": "issue129-20261022", "source_sha": "a" * 40,
            "gateway_sha": "b" * 40, "work_id": "c" * 64, "controller_run_id": "123",
            "gateway_run_id": "456", "issued_at": NOW - 10, "expires_at": NOW + 600,
            "cap_cents": 1000, "max_requests": 10}
        who = {"id": lease.OWNER_ID, "login": lease.OWNER}
        self.parent = {"id": 456, "repository": {"full_name": lease.PUBLIC, "id": lease.PUBLIC_ID},
            "head_sha": self.doc["gateway_sha"], "head_branch": "main",
            "path": ".github/workflows/code-gateway.yml", "event": "workflow_dispatch", "run_attempt": 1,
            "status": "in_progress", "conclusion": None, "created_at": stamp(NOW - 20),
            "actor": dict(who), "triggering_actor": dict(who),
            "display_title": "CW issue129 code " + self.doc["work_id"]}
        self.source = {**copy.deepcopy(self.parent), "id": 123,
            "repository": {"full_name": lease.SOURCE, "id": lease.SOURCE_ID},
            "head_sha": self.doc["source_sha"], "head_branch": "feature/emergency-close-persistence",
            "path": ".github/workflows/orchestrator-code-controller.yml"}
        self.gates = {lease.PAID: "true", lease.CODE: "true"}
        self.calls, self.failures, self.ignored, self.report = [], set(), set(), []
        self.raw, self.after_pause = None, None

    def api(self, repository, method, path, token, body=None):
        self.calls.append((repository, method, path, token, copy.deepcopy(body)))
        if (repository, method, path) in self.failures:
            raise RuntimeError("synthetic secret must never be returned")
        if repository == lease.PUBLIC:
            assert method == "GET" and path == "actions/runs/456" and token == "public-token"
            return copy.deepcopy(self.parent)
        assert repository == lease.SOURCE and token == "source-token"
        name = path.removeprefix("actions/variables/")
        assert name in (lease.PAID, lease.CODE, lease.LEASE)
        if method == "PATCH":
            assert name != lease.LEASE and body == {"name": name, "value": "false"}
            if name not in self.ignored:
                self.gates[name] = "false"
            return None
        assert method == "GET" and body is None
        return {"name": name, "value": self.raw if self.raw is not None else json.dumps(self.doc)} if name == lease.LEASE else {
            "name": name, "value": self.gates[name]}

    def guard(self, **kwargs):
        return lease.guard_once(self.api, "source-token", "public-token", now=self.time, **kwargs)

    def pause(self, seconds):
        self.time += seconds; self.mono += seconds
        if self.after_pause:
            self.after_pause()

    def watch(self, parent="456"):
        return lease.watch_code(self.api, "source-token", "public-token", parent_id=parent,
            now=lambda: self.time, monotonic=lambda: self.mono, pause=self.pause, report=self.report.append)


class CodeLeaseTests(unittest.TestCase):
    def assert_off(self, f):
        self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})
        mutations = [c for c in f.calls if c[1] != "GET"]
        self.assertEqual(len(mutations), 2)
        self.assertTrue(all(c[1] == "PATCH" and c[4]["value"] == "false" for c in mutations))

    def test_valid_code_window_never_mutates_or_dispatches(self):
        f = Fixture()
        self.assertEqual(f.guard(), "CODE_LEASE_WITHIN_TTL")
        self.assertTrue(all(c[1] == "GET" for c in f.calls))

    def test_existing_documentation_path_is_left_to_original_guard(self):
        f = Fixture(); f.gates[lease.CODE] = "false"
        self.assertEqual(f.guard(), "NOT_CODE_LEASE")
        self.assertEqual(len(f.calls), 1)

    def test_selftest_writes_and_reads_both_flags_even_already_off(self):
        f = Fixture(); f.gates = {lease.PAID: "false", lease.CODE: "false"}
        self.assertEqual(f.guard(self_test=True), "CODE_OFF_SELFTEST_VERIFIED")
        self.assert_off(f)
        self.assertEqual([c[2].split("/")[-1] for c in f.calls], [lease.PAID, lease.CODE] * 2)

    def test_either_gate_can_stay_off_during_a_valid_window(self):
        f = Fixture(); f.gates[lease.PAID] = "false"
        self.assertEqual(f.guard(), "CODE_LEASE_WITHIN_TTL")
        self.assertEqual(f.gates[lease.PAID], "false")

    def test_expiry_boundary_forces_both_off(self):
        f = Fixture(); f.time = f.doc["expires_at"]
        self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_missing_or_unreadable_lease_forces_both_off(self):
        f = Fixture(); f.failures.add((lease.SOURCE, "GET", "actions/variables/" + lease.LEASE))
        self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_malformed_or_duplicate_lease_never_authorizes(self):
        for raw in ("{", "[]", "null", "x" * 4097,
                    json.dumps(Fixture().doc)[:-1] + ',"version":1}',
                    json.dumps({**Fixture().doc, "version": True})):
            with self.subTest(raw=raw[:20]):
                f = Fixture(); f.raw = raw
                self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_closed_schema_budget_and_identity_fields(self):
        changes = {"extra": 1, "package": "old", "source_sha": "branch", "gateway_sha": "z" * 40,
            "work_id": "c" * 40, "controller_run_id": "00123", "gateway_run_id": 456,
            "cap_cents": 1001, "max_requests": 11, "issued_at": True, "expires_at": NOW - 1}
        for key, value in changes.items():
            with self.subTest(key=key):
                f = Fixture(); f.doc[key] = value
                self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_future_issue_time_and_overlong_window_are_denied(self):
        for changes in ({"issued_at": NOW + 1}, {"expires_at": NOW + lease.TTL_SECONDS}):
            f = Fixture(); f.doc.update(changes)
            self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_same_parent_cannot_renew_beyond_its_original_ttl(self):
        f = Fixture(); f.doc["issued_at"] = NOW; f.doc["expires_at"] = NOW + lease.TTL_SECONDS
        self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_terminal_parent_even_success_forces_off(self):
        f = Fixture(); f.parent.update(status="completed", conclusion="success")
        self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_unverifiable_public_parent_forces_off(self):
        f = Fixture(); f.failures.add((lease.PUBLIC, "GET", "actions/runs/456"))
        self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_wrong_parent_route_branch_sha_actor_attempt_and_title(self):
        changes = {"id": 457, "head_branch": "other", "head_sha": "d" * 40,
            "path": ".github/workflows/one-shot-gateway.yml", "event": "push", "run_attempt": 2,
            "actor": {"id": lease.OWNER_ID, "login": "other"},
            "triggering_actor": {"id": 9, "login": lease.OWNER},
            "repository": {"id": lease.PUBLIC_ID, "full_name": lease.SOURCE},
            "display_title": "CW issue88 paid_pilot 0", "created_at": "unknown"}
        for key, value in changes.items():
            with self.subTest(key=key):
                f = Fixture(); f.parent[key] = value
                self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_future_or_stale_parent_is_denied(self):
        for value in (NOW + 1, NOW - lease.TTL_SECONDS):
            f = Fixture(); f.parent["created_at"] = stamp(value)
            self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_creation_timestamp_cannot_have_local_timezone(self):
        f = Fixture(); f.parent["created_at"] = "2026-10-22T16:00:00-04:00"
        self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_patch_failure_still_attempts_other_gate_and_both_readbacks(self):
        f = Fixture(); f.failures.add((lease.SOURCE, "PATCH", "actions/variables/" + lease.PAID))
        with self.assertRaisesRegex(lease.LeaseDenied, "CODE_OFF_UNVERIFIED"):
            f.guard(self_test=True)
        self.assertEqual(f.gates[lease.CODE], "false")
        self.assertEqual([c[1] for c in f.calls], ["PATCH", "PATCH", "GET", "GET"])

    def test_positive_patch_reply_is_not_shutdown_proof(self):
        f = Fixture(); f.ignored.add(lease.CODE)
        with self.assertRaisesRegex(lease.LeaseDenied, "CODE_OFF_UNVERIFIED"):
            f.guard(self_test=True)
        self.assertEqual(f.gates[lease.PAID], "false")

    def test_readback_failure_never_claims_verified_off(self):
        f = Fixture(); f.failures.add((lease.SOURCE, "GET", "actions/variables/" + lease.CODE))
        with self.assertRaisesRegex(lease.LeaseDenied, "CODE_OFF_UNVERIFIED"):
            f.guard(self_test=True)
        self.assertEqual(len([c for c in f.calls if c[1] == "PATCH"]), 2)

    def test_unknown_code_gate_causes_shutdown_attempt(self):
        f = Fixture(); f.gates[lease.CODE] = "invalid"
        self.assertEqual(f.guard(), "CODE_ORPHAN_DISABLED"); self.assert_off(f)

    def test_continuous_watch_stops_at_terminal_parent(self):
        f = Fixture(); f.after_pause = lambda: f.parent.update(status="completed")
        self.assertEqual(f.watch(), "CODE_LEASE_TERMINAL_EXPIRED_OR_UNVERIFIABLE_OFF")
        self.assertEqual(f.report, ["INDEPENDENT_CODE_OFF_WATCHDOG_ACTIVE"]); self.assert_off(f)

    def test_watch_cannot_adopt_a_different_public_parent(self):
        f = Fixture()
        self.assertEqual(f.watch(parent="457"), "CODE_LEASE_TERMINAL_EXPIRED_OR_UNVERIFIABLE_OFF")
        self.assert_off(f)

    def test_watch_never_reports_active_before_verifying_parent_and_gates(self):
        f = Fixture(); f.parent["status"] = "completed"
        self.assertEqual(f.watch(), "CODE_LEASE_TERMINAL_EXPIRED_OR_UNVERIFIABLE_OFF")
        self.assertEqual(f.report, [])
        self.assert_off(f)

    def test_wall_clock_rollback_stops_new_permissions(self):
        f = Fixture(); f.after_pause = lambda: setattr(f, "time", NOW - 100)
        self.assertEqual(f.watch(), "CODE_LEASE_TERMINAL_EXPIRED_OR_UNVERIFIABLE_OFF"); self.assert_off(f)

    def test_monotonic_ttl_cannot_be_extended_by_frozen_wall_clock(self):
        f = Fixture(); f.after_pause = lambda: setattr(f, "time", NOW)
        self.assertEqual(f.watch(), "CODE_WATCHDOG_MONOTONIC_TTL_OFF"); self.assert_off(f)

    def test_source_parent_requires_matching_work_and_immutable_source(self):
        f = Fixture()
        lease.source_parent(f.doc, f.source, now=NOW, source_sha=f.doc["source_sha"], work_id=f.doc["work_id"])
        for key in ("source_sha", "work_id"):
            args = {"source_sha": f.doc["source_sha"], "work_id": f.doc["work_id"], key: "d" * (40 if key == "source_sha" else 64)}
            with self.assertRaises(lease.LeaseDenied):
                lease.source_parent(f.doc, f.source, now=NOW, **args)

    def test_source_parent_must_be_real_active_owner_controller(self):
        for key, value in (("path", ".github/workflows/gh-aw-code-worker.lock.yml"), ("status", "completed"),
                           ("run_attempt", 2), ("head_sha", "d" * 40), ("created_at", stamp(NOW - 200))):
            f = Fixture(); f.source[key] = value
            with self.subTest(key=key), self.assertRaises(lease.LeaseDenied):
                lease.source_parent(f.doc, f.source, now=NOW, source_sha=f.doc["source_sha"], work_id=f.doc["work_id"])


if __name__ == "__main__":
    unittest.main()
