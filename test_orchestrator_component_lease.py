"""Synthetic parent/lease failures exercise the real OFF implementation."""
import copy
import json
import unittest

import orchestrator_component_lease as component
from test_orchestrator_code_lease import Fixture, NOW, stamp


class ComponentFixture(Fixture):
    def __init__(self):
        super().__init__()
        self.doc.pop("work_id")
        self.doc.update(package="issue129-20261022-accelerated", cap_cents=17500, max_requests=600,
            approval_ref="c" * 40, work_order_sha256="d" * 64, spec_sha256="e" * 64,
            issued_at=NOW, expires_at=NOW + component.TTL_SECONDS)
        self.parent["created_at"] = stamp(NOW)
        self.parent["path"] = ".github/workflows/component-gateway.yml"
        self.parent["display_title"] = "CW component order " + self.doc["work_order_sha256"]
        self.source = copy.deepcopy(self.parent)
        self.source.update(id=int(self.doc["controller_run_id"]),
            repository={"full_name": component.SOURCE, "id": component.SOURCE_ID},
            head_sha=self.doc["source_sha"], head_branch=component.BRANCH,
            path=".github/workflows/orchestrator-component-controller.yml",
            display_title="CW component controller " + self.doc["work_order_sha256"])

    def api(self, repository, method, path, token, body=None):
        if method == "GET" and path == "actions/variables/" + component.LEASE:
            if (repository, method, path) in self.failures:
                raise OSError("synthetic")
            return {"name": component.LEASE, "value": self.raw if self.raw is not None else json.dumps(self.doc)}
        if repository == component.SOURCE and method == "GET" and path == "actions/runs/" + self.doc["controller_run_id"]:
            return self.source
        return super().api(repository, method, path, token, body)

    def active(self, **kw):
        return component.active_lease(self.api, "source-token", "public-token", now=NOW, **kw)

    def watch(self, **kw):
        return component.watch_component(self.api, "source-token", "public-token",
            parent_id=kw.pop("parent_id", self.doc["gateway_run_id"]),
            now=kw.pop("now", lambda: NOW), monotonic=lambda: self.mono,
            pause=self.pause, report=self.report.append, **kw)


class ComponentLeaseTests(unittest.TestCase):
    def test_real_component_schema_allows_90_minutes(self):
        f = ComponentFixture()
        self.assertEqual(f.active(), f.doc)
        self.assertEqual(component.decode(json.dumps(f.doc), now=NOW + 5399), f.doc)
        with self.assertRaises(Exception):
            component.decode(json.dumps(f.doc), now=NOW + 5400)

    def test_closed_schema_and_exact_types(self):
        f = ComponentFixture()
        faults = [("version", True), ("cap_cents", 17500.0), ("cap_cents", 17501),
            ("max_requests", True), ("issued_at", NOW + 1), ("expires_at", NOW + 5401),
            ("approval_ref", f.doc["source_sha"]), ("gateway_run_id", "01"),
            ("source_sha", "A" * 40), ("work_order_sha256", "d" * 63), ("extra", 1)]
        for name, value in faults:
            with self.subTest(name=name, value=value):
                doc = dict(f.doc, **{name: value})
                with self.assertRaises(Exception):
                    component.decode(json.dumps(doc), now=NOW)
        for name in f.doc:
            doc = dict(f.doc); del doc[name]
            with self.subTest(missing=name), self.assertRaises(Exception):
                component.decode(json.dumps(doc), now=NOW)

    def test_duplicate_key_and_oversize_are_denied(self):
        f = ComponentFixture()
        for raw in ('{"version":1,' + json.dumps(f.doc)[1:], " " * 4097):
            with self.assertRaises(Exception):
                component.decode(raw, now=NOW)

    def test_each_parent_identity_and_terminal_failure_revokes_lease(self):
        faults = {"id": 1, "head_sha": "f" * 40, "head_branch": "other", "run_attempt": 2,
            "path": ".github/workflows/code-gateway.yml", "event": "push", "status": "completed",
            "conclusion": "failure", "display_title": "unbound",
            "repository": {"id": 1, "full_name": component.PUBLIC},
            "actor": {"id": 1, "login": "1978serg-cpu"},
            "triggering_actor": {"id": 1, "login": "1978serg-cpu"}}
        for target in ("parent", "source"):
            for name, value in faults.items():
                f = ComponentFixture(); getattr(f, target)[name] = value
                with self.subTest(target=target, field=name):
                    self.assertIsNone(f.active())

    def test_lease_cannot_extend_original_parent_window(self):
        f = ComponentFixture()
        f.doc["issued_at"] += 301; f.doc["expires_at"] += 301
        self.assertIsNone(component.active_lease(f.api, "source-token", "public-token", now=NOW + 301))

    def test_exact_watch_parent_is_required_and_both_gates_are_disabled(self):
        f = ComponentFixture()
        self.assertEqual(f.watch(parent_id="999"), "COMPONENT_PARENT_OR_LEASE_INVALID_OFF")
        self.assertEqual(f.gates, {component.PAID: "false", component.CODE: "false"})

    def test_source_completion_triggers_shutdown_even_with_live_public_parent(self):
        f = ComponentFixture()
        original = f.pause
        def pause(seconds):
            original(seconds)
            f.source.update(status="completed", conclusion="success")
        f.pause = pause
        self.assertEqual(f.watch(), "COMPONENT_PARENT_OR_LEASE_INVALID_OFF")
        self.assertEqual(f.gates, {component.PAID: "false", component.CODE: "false"})

    def test_monotonic_deadline_cannot_be_extended_by_frozen_wall_clock(self):
        f = ComponentFixture()
        self.assertEqual(f.watch(), "COMPONENT_WATCHDOG_MONOTONIC_TTL_OFF")
        self.assertEqual(f.report, ["INDEPENDENT_COMPONENT_OFF_WATCHDOG_ACTIVE"])
        self.assertEqual(f.gates, {component.PAID: "false", component.CODE: "false"})

    def test_unknown_off_write_cannot_be_reported_as_verified(self):
        f = ComponentFixture(); f.parent["status"] = "completed"
        f.failures.add((component.SOURCE, "PATCH", "actions/variables/" + component.PAID))
        with self.assertRaisesRegex(Exception, "CODE_OFF_UNVERIFIED"):
            f.watch()

    def test_scheduled_guard_recognizes_component_and_preserves_legacy_fallback(self):
        f = ComponentFixture()
        self.assertEqual(component.guard_once(f.api, "source-token", "public-token", now=NOW), "COMPONENT_LEASE_WITHIN_TTL")
        f.source["status"] = "completed"
        self.assertEqual(component.guard_once(f.api, "source-token", "public-token", now=NOW), "NOT_COMPONENT_LEASE")


if __name__ == "__main__":
    unittest.main()
