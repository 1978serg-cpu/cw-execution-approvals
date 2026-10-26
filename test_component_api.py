"""Failure injection for the real gateway HTTP boundary; no network or tokens."""
import contextlib
import io
import socket
import ssl
import unittest
import urllib.error
from unittest.mock import Mock, patch

import component_gateway as gateway
from test_component_gateway import Fixture


SECRET = "synthetic-secret-never-log"


def response(raw=b'{"ok":true}', status=200):
    value = Mock(status=status)
    value.read.return_value = raw
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    return value


def http_error(code):
    return urllib.error.HTTPError("https://invalid/" + SECRET, code, SECRET,
        {"Location": "https://invalid/" + SECRET}, io.BytesIO(SECRET.encode()))


class ComponentApiTests(unittest.TestCase):
    def invoke(self, effects, *, method="GET", path="actions/runs/123/jobs?per_page=50", body=None):
        opener = Mock()
        opener.open.side_effect = effects
        output = io.StringIO()
        with patch.object(gateway.urllib.request, "build_opener", return_value=opener), \
                patch.object(gateway.time, "sleep") as pause, contextlib.redirect_stdout(output):
            try:
                result = gateway.api(gateway.PUBLIC, method, path, SECRET, body)
                failure = None
            except ValueError as error:
                result, failure = None, str(error)
        return result, failure, opener.open.call_count, pause.call_args_list, output.getvalue()

    def test_transient_gets_recover_once_with_closed_diagnostics(self):
        errors = [http_error(c) for c in gateway.TRANSIENT_HTTP]
        errors += [TimeoutError(SECRET), ConnectionResetError(SECRET),
            urllib.error.URLError(TimeoutError(SECRET)),
            urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, SECRET))]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                result, failure, calls, pauses, output = self.invoke([error, response()])
                self.assertEqual(result, {"ok": True})
                self.assertIsNone(failure)
                self.assertEqual(calls, 2)
                self.assertEqual([p.args for p in pauses], [(1,)])
                self.assertNotIn(SECRET, output)
                self.assertNotIn("123", output)
                self.assertIn("COMPONENT_API_PUBLIC_GET_JOBS_", output)

    def test_exhausted_get_is_bounded(self):
        result, failure, calls, pauses, output = self.invoke([http_error(503), http_error(503)])
        self.assertIsNone(result)
        self.assertEqual(calls, 2)
        self.assertEqual(len(pauses), 1)
        self.assertEqual(failure, "COMPONENT_API_PUBLIC_GET_JOBS_HTTP_503_NO_RETRY")
        self.assertEqual(len(output.splitlines()), 2)
        self.assertNotIn(SECRET, output + failure)

    def test_auth_rate_limit_and_redirect_do_not_retry(self):
        errors = [http_error(c) for c in (301, 302, 307, 308, 400, 401, 403, 409, 422, 429)]
        errors += [ValueError("CODE_GATEWAY_REDIRECT_DENIED"),
            urllib.error.URLError(ssl.SSLError(SECRET)),
            urllib.error.URLError(socket.gaierror(socket.EAI_NONAME, SECRET)),
            urllib.error.URLError(SECRET), RuntimeError(SECRET)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                _, failure, calls, pauses, output = self.invoke([error, response()])
                self.assertIsNotNone(failure)
                self.assertEqual(calls, 1)
                self.assertEqual(pauses, [])
                self.assertNotIn(SECRET, failure + output)

    def test_missing_get_keeps_existing_absence_semantics(self):
        result, failure, calls, pauses, output = self.invoke([http_error(404)])
        self.assertIsNone(result)
        self.assertIsNone(failure)
        self.assertEqual(calls, 1)
        self.assertEqual(pauses, [])
        self.assertEqual(output, "")

    def test_uncertain_writes_are_never_replayed(self):
        operations = ((gateway.PUBLIC, "POST", "git/refs"),
            (gateway.PUBLIC, "POST", "actions/workflows/one-shot-gateway.yml/dispatches"),
            (gateway.SOURCE, "POST", "actions/variables"),
            (gateway.SOURCE, "POST", "actions/workflows/" + gateway.CONTROLLER + "/dispatches"),
            (gateway.SOURCE, "PATCH", "actions/variables/" + gateway.lease.LEASE),
            (gateway.SOURCE, "PATCH", "actions/variables/" + gateway.lease.CODE),
            (gateway.SOURCE, "PATCH", "actions/variables/" + gateway.lease.PAID))
        for repository, method, path in operations:
            for error in (http_error(503), TimeoutError(SECRET)):
                opener = Mock()
                opener.open.side_effect = [error, response()]
                output = io.StringIO()
                with self.subTest(method=method, path=path), \
                        patch.object(gateway.urllib.request, "build_opener", return_value=opener), \
                        patch.object(gateway.time, "sleep") as pause, contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(ValueError, "COMPONENT_API_.*_NO_RETRY") as raised:
                        gateway.api(repository, method, path, SECRET, {"secret": SECRET})
                    self.assertEqual(opener.open.call_count, 1)
                    pause.assert_not_called()
                    self.assertNotIn(SECRET, str(raised.exception) + output.getvalue())

    def test_bad_or_oversize_responses_are_not_retried(self):
        for raw, status in ((b'{', 200), (b'{"x":1,"x":2}', 200), (b'\xff', 200),
                (b'x' * (gateway.MAX_API_RESPONSE_BYTES + 1), 200), (b'{}', 202)):
            with self.subTest(status=status, size=len(raw)):
                _, failure, calls, pauses, _ = self.invoke([response(raw, status), response()])
                self.assertIn("RESPONSE_INVALID", failure)
                self.assertEqual(calls, 1)
                self.assertEqual(pauses, [])

    def test_request_identity_timeout_and_redirect_policy_are_preserved(self):
        opener = Mock()
        opener.open.side_effect = [http_error(503), response()]
        with patch.object(gateway.urllib.request, "build_opener", return_value=opener) as build, \
                patch.object(gateway.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            gateway.api(gateway.PUBLIC, "GET", "actions/runs/123", SECRET)
        self.assertEqual(opener.open.call_count, 2)
        requests = [c.args[0] for c in opener.open.call_args_list]
        self.assertIs(requests[0], requests[1])
        for call in opener.open.call_args_list:
            self.assertEqual(call.kwargs, {"timeout": 12})
            self.assertEqual(call.args[0].get_method(), "GET")
        for call in build.call_args_list:
            self.assertIsInstance(call.args[0], gateway.NoRedirect)

    def test_watchdog_read_failure_shuts_off_without_enabling_or_replaying(self):
        fixture = Fixture()
        original = fixture.api
        def call(repo, method, path, token, body=None):
            if method == "GET" and path == "actions/runs/345/jobs?per_page=50":
                raise ValueError("COMPONENT_API_PUBLIC_GET_JOBS_HTTP_503_NO_RETRY")
            return original(repo, method, path, token, body)
        with self.assertRaisesRegex(ValueError, "HTTP_503"), \
                patch.object(gateway, "source_preflight", return_value=True):
            gateway.execute(fixture.env, call=call, clock=lambda: fixture.now,
                monotonic=lambda: fixture.now, pause=fixture.pause)
        self.assertEqual(fixture.gates, dict.fromkeys(fixture.gates, "false"))
        self.assertEqual(sum(c[1] == "POST" and c[2].endswith("/dispatches") for c in fixture.calls), 2)
        self.assertFalse(any(c[1] == "PATCH" and c[3].get("value") == "true" for c in fixture.calls))


if __name__ == "__main__":
    unittest.main()
