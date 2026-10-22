"""Run the actual inline OFF program with an inert transport, not a model."""
import contextlib
import hashlib
import io
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import orchestrator_code_lease as lease
from test_orchestrator_code_lease import Fixture, NOW

ROOT = Path(__file__).parent
WORKFLOW = ROOT / ".github/workflows/one-shot-gateway.yml"


def inline():
    source = WORKFLOW.read_text().split("          python3 - <<'PYCODE'\n", 1)[1].split("          PYCODE", 1)[0]
    return "\n".join(line[10:] if line.startswith("          ") else line for line in source.splitlines())


class GatewayTests(unittest.TestCase):
    def run_program(self, f, *, mode, parent="456"):
        namespace = {"__name__": "gateway_under_test"}
        exec(compile(inline(), str(WORKFLOW), "exec"), namespace)
        namespace["api"] = f.api
        namespace["time"] = types.SimpleNamespace(time=lambda: f.time, monotonic=lambda: f.mono, sleep=f.pause)
        env = {"GITHUB_REPOSITORY": lease.PUBLIC, "GITHUB_REF": "refs/heads/main", "GITHUB_ACTOR": lease.OWNER,
            "GITHUB_EVENT_NAME": "workflow_dispatch", "CW_GATEWAY_SHUTOFF_TOKEN": "source-token",
            "GH_PUBLIC_TOKEN": "public-token", "CW_MODE": mode, "CW_PARENT_RUN_ID": parent}
        with patch.dict("os.environ", env, clear=True), contextlib.redirect_stdout(io.StringIO()) as output:
            result = namespace["run"]()
        return result, output.getvalue()

    def test_real_selftest_program_can_only_write_false_to_both_gates(self):
        f = Fixture()
        status, output = self.run_program(f, mode="off_selftest")
        self.assertEqual(status, 0)
        self.assertIn("CODE_OFF_SELFTEST_VERIFIED", output)
        self.assertIn("OFF_SELFTEST_SUCCESS_NO_MODEL_NO_SPEND", output)
        self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})

    def test_real_scheduled_program_preserves_a_verified_code_window(self):
        f = Fixture()
        status, output = self.run_program(f, mode="scheduled_off")
        self.assertEqual(status, 0); self.assertIn("CODE_LEASE_WITHIN_TTL", output)
        self.assertTrue(all(call[1] == "GET" for call in f.calls))

    def test_real_scheduled_program_shuts_orphaned_code_window(self):
        f = Fixture(); f.doc["expires_at"] = NOW
        status, output = self.run_program(f, mode="scheduled_off")
        self.assertEqual(status, 0); self.assertIn("CODE_ORPHAN_DISABLED", output)
        self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})

    def test_real_continuous_code_watch_requires_the_exact_parent(self):
        f = Fixture()
        status, output = self.run_program(f, mode="code_watch", parent="457")
        self.assertEqual(status, 0); self.assertIn("CODE_LEASE_TERMINAL_EXPIRED_OR_UNVERIFIABLE_OFF", output)
        self.assertEqual(f.gates, {lease.PAID: "false", lease.CODE: "false"})

    def test_real_code_watch_stops_after_parent_finishes(self):
        f = Fixture(); f.after_pause = lambda: f.parent.update(status="completed")
        status, output = self.run_program(f, mode="code_watch")
        self.assertEqual(status, 0); self.assertIn("INDEPENDENT_CODE_OFF_WATCHDOG_ACTIVE", output)
        self.assertIn("CODE_LEASE_TERMINAL_EXPIRED_OR_UNVERIFIABLE_OFF", output)

    def test_existing_documentation_healthy_off_still_works(self):
        f = Fixture(); f.gates = {lease.PAID: "false", lease.CODE: "false"}
        status, output = self.run_program(f, mode="scheduled_off")
        self.assertEqual(status, 0); self.assertIn("SCHEDULED_GATE_HEALTHY_OFF", output)
        self.assertTrue(all(call[1] == "GET" for call in f.calls))

    def test_historical_paid_pilot_and_consumed_marker_program_are_byte_identical(self):
        pilot = WORKFLOW.read_text().split("\n  pilot:\n", 1)[1]
        self.assertEqual(hashlib.sha256(pilot.encode()).hexdigest(),
            "962b8ac330280296d7997cee18895a2b9381f9f3de0a7717cad1572eabf89e62")


if __name__ == "__main__":
    unittest.main()
