"""Offline synthetic contract tests; never use inherited credentials."""
import http.client
import importlib.util
import io
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
import time
from unittest.mock import patch
from pathlib import Path
import unittest

_network_block = patch.object(socket, "create_connection", side_effect=AssertionError("offline network forbidden"))


def setUpModule():
    _network_block.start()


def tearDownModule():
    _network_block.stop()


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/cloudflare-readiness.py"
ACCOUNT = "a" * 32
TOKEN = "SYNTHETIC_ONLY_TOKEN_CANARY_not_a_real_credential"


def load_probe(case):
    case.assertTrue(SCRIPT.is_file(), "read-only readiness entrypoint must exist")
    spec = importlib.util.spec_from_file_location("readiness_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case.assertTrue(callable(getattr(module, "probe", None)), "probe must be callable")
    return module


class CredentialsTests(unittest.TestCase):
    def test_invalid_credentials_refuse_without_transport_or_reflection(self):
        probe = load_probe(self)
        invalid = [({}, "ACCOUNT_INVALID"),
                   ({"CLOUDFLARE_ACCOUNT_ID": " " + ACCOUNT}, "ACCOUNT_INVALID"),
                   ({"CLOUDFLARE_ACCOUNT_ID": ACCOUNT + "\n"}, "ACCOUNT_INVALID"),
                   ({"CLOUDFLARE_ACCOUNT_ID": "z" * 32}, "ACCOUNT_INVALID"),
                   ({"CLOUDFLARE_ACCOUNT_ID": ACCOUNT}, "AUTH_INVALID")]
        for token in ("", "secret\r\nInjected: canary", "secret\x00canary", "a" * 4097,
                      " space ", "SYNTHETIC_秘密"):
            invalid.append(({"CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
                             "CLOUDFLARE_API_TOKEN": token}, "AUTH_INVALID"))
        calls = []
        for env, code in invalid:
            with self.subTest(code=code):
                result = probe.probe(env, transport=lambda *a, **k: calls.append(a))
                self.assertEqual(result["status"], "REFUSED")
                self.assertEqual(result["code"], code)
                self.assertIsNone(result["active_deployment"])
                self.assertNotIn(ACCOUNT, json.dumps(result))
                self.assertNotIn("canary", json.dumps(result))
        self.assertEqual(calls, [])


D1 = "11111111-1111-4111-8111-111111111111"
D0 = "22222222-2222-4222-8222-222222222222"
V1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
V0 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
V2 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
DOMAIN = "d" * 32


def environment():
    return {"CLOUDFLARE_ACCOUNT_ID": ACCOUNT, "CLOUDFLARE_API_TOKEN": TOKEN}


def envelope(result, info=None):
    body = {"success": True, "errors": [], "messages": [], "result": result}
    if info is not None:
        body["result_info"] = info
    return body


def deployment(identifier, *versions):
    return {"id": identifier, "strategy": "percentage", "created_on": "2026-01-01T00:00:00Z",
            "source": "api", "versions": [{"version_id": v, "percentage": p} for v, p in versions],
            "author_email": "SYNTHETIC_AUTHOR_CANARY@example.invalid"}


def deployments_page(items=None, page=1, pages=1, total=2):
    if items is None:
        items = [deployment(D1, (V1, 100)), deployment(D0, (V0, 100))]
    return envelope({"deployments": items}, {"page": page, "per_page": 20,
                    "count": len(items), "total_pages": pages, "total_count": total})


def versions_page(ids=(V1, V0, V2)):
    return envelope({"items": [{"id": v, "metadata": {"author_email": "PRIVATE_METADATA_CANARY"}}
                               for v in ids]})


def domains_page():
    return envelope([{"id": DOMAIN, "hostname": "miya-lis.net", "service": "miya-lis-forest",
                      "environment": "production", "zone_id": "e" * 32,
                      "zone_name": "miya-lis.net", "cert_id": V2}])


class ScriptedTransport:
    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, path, authorization, timeout):
        self.calls.append((path, authorization, timeout))
        if not self.bodies:
            raise AssertionError("offline response queue exhausted")
        value = self.bodies.pop(0)
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, tuple):
            return value
        return 200, {"Content-Type": "application/json"}, json.dumps(value).encode()


def happy_transport(first=None, versions=None, domains=None, last=None):
    return ScriptedTransport(first if first is not None else deployments_page(),
                             versions if versions is not None else versions_page(),
                             domains if domains is not None else domains_page(),
                             last if last is not None else deployments_page())


class MetadataTests(unittest.TestCase):
    def test_metadata_uses_documented_endpoints_and_real_response_ids(self):
        module = load_probe(self)
        transport = happy_transport()
        result = module.probe(environment(), transport=transport)
        self.assertEqual(result["status"], "METADATA_VERIFIED")
        self.assertEqual(result["code"], "METADATA_VERIFIED")
        self.assertEqual(result["target"], {"worker": "miya-lis-forest", "hostname": "miya-lis.net"})
        self.assertEqual(result["active_deployment"],
                         {"id": D1, "versions": [{"id": V1, "percentage": 100}]})
        self.assertEqual([d["id"] for d in result["deployments"]], [D1, D0])
        self.assertEqual(result["domain"], {"status": "MATCH", "id": DOMAIN})
        self.assertEqual(result["rollback"], {"status": "CANDIDATES_OBSERVED",
                         "current_version_ids": [V1], "prior_version_ids": [V0],
                         "execution": "NOT_TESTED"})
        self.assertEqual(result["deployment_approval"], "NOT_GRANTED")
        prefix = "/client/v4/accounts/" + ACCOUNT + "/workers/"
        self.assertEqual([r[0] for r in transport.calls],
                         [prefix + "scripts/miya-lis-forest/deployments?page=1&per_page=20",
                          prefix + "scripts/miya-lis-forest/versions?deployable=true",
                          prefix + "domains?hostname=miya-lis.net",
                          prefix + "scripts/miya-lis-forest/deployments?page=1&per_page=20"])
        self.assertTrue(all(r[1] == "Bearer " + TOKEN for r in transport.calls))
        self.assertTrue(all(0 < r[2] <= 5 for r in transport.calls))
        encoded = json.dumps(result)
        for forbidden in (ACCOUNT, TOKEN, "SYNTHETIC_AUTHOR_CANARY", "PRIVATE_METADATA_CANARY", "zone_id"):
            self.assertNotIn(forbidden, encoded)


class ResponseBoundaryTests(unittest.TestCase):
    def test_http_failures_never_count_as_metadata(self):
        module = load_probe(self)
        for status, code in [(401, "AUTH_UNAUTHORIZED"), (403, "AUTH_FORBIDDEN"),
                             (404, "HTTP_REFUSED"), (429, "HTTP_REFUSED"), (500, "HTTP_REFUSED"),
                             *[(s, "REDIRECT_REFUSED") for s in (301, 302, 303, 307, 308)]]:
            with self.subTest(status=status):
                transport = ScriptedTransport((status, {"Location": "https://" + TOKEN + ".invalid/"},
                                                ("RAW_ERROR_" + TOKEN + ACCOUNT).encode()))
                result = module.probe(environment(), transport=transport)
                self.assertEqual(result["code"], code)
                self.assertEqual(result["status"], "PARTIAL")
                self.assertEqual(len(transport.calls), 1)
                self.assertNotIn(TOKEN, json.dumps(result))
                self.assertNotIn(ACCOUNT, json.dumps(result))
                self.assertNotIn("RAW_ERROR", json.dumps(result))

    def test_success_flag_is_required_even_with_plausible_result(self):
        module = load_probe(self)
        for success in (False, None, 1, "true"):
            body = deployments_page()
            body["success"] = success
            body["errors"] = [{"message": TOKEN, TOKEN: ACCOUNT}]
            transport = ScriptedTransport(body)
            result = module.probe(environment(), transport=transport)
            self.assertEqual(result["code"], "API_UNSUCCESSFUL")
            self.assertIsNone(result["active_deployment"])
            self.assertNotIn(TOKEN, json.dumps(result))
            self.assertEqual(len(transport.calls), 1)

    def test_json_decoder_rejects_malformed_duplicate_and_nonfinite_json(self):
        module = load_probe(self)
        for body in (("{" + TOKEN).encode(), b'[]', b'{"success":true,"result":NaN}',
                     b'{"success":true,"success":false,"result":{}}', b'\xff',
                     b'\xef\xbb\xbf{"success":true,"result":{}}'):
            result = module.probe(environment(), transport=ScriptedTransport((200,
                                  {"Content-Type": "application/json"}, body)))
            self.assertEqual(result["code"], "RESPONSE_INVALID")
            self.assertIsNone(result["active_deployment"])
            self.assertNotIn(TOKEN, json.dumps(result))

    def test_response_size_and_media_type_are_bounded(self):
        module = load_probe(self)
        for headers, body, code in [({"Content-Type": "application/json"}, b" " * (256 * 1024 + 1),
                                     "RESPONSE_TOO_LARGE"),
                                    ({"Content-Type": "text/html"}, b"{}", "RESPONSE_INVALID"),
                                    ({"Content-Type": "application/json", "Content-Encoding": "gzip"},
                                     b"{}", "RESPONSE_INVALID"),
                                    ({"Content-Type": "application/json", "Content-Length": str(256 * 1024 + 1)},
                                     b"{}", "RESPONSE_TOO_LARGE"),
                                    ({"Content-Type": TOKEN}, b"{}", "RESPONSE_INVALID")]:
            result = module.probe(environment(), transport=ScriptedTransport((200, headers, body)))
            self.assertEqual(result["code"], code)
            self.assertNotIn(TOKEN, json.dumps(result))

    def test_transport_exception_never_exposes_exception_environment_or_headers(self):
        module = load_probe(self)
        transport = ScriptedTransport(RuntimeError(TOKEN + ACCOUNT + "/secret/path"))
        env = environment()
        env["UNRELATED_SECRET_CANARY"] = "DO_NOT_READ_OR_REFLECT"
        result = module.probe(env, transport=transport)
        self.assertEqual(result["code"], "TRANSPORT_REFUSED")
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertNotIn(ACCOUNT, json.dumps(result))
        self.assertNotIn("path", json.dumps(result))
        self.assertNotIn("DO_NOT_READ_OR_REFLECT", json.dumps(result))


class IdentityTests(unittest.TestCase):
    def test_invalid_or_secret_shaped_identifiers_are_never_reflected(self):
        module = load_probe(self)
        for field, value in [("deployment", TOKEN), ("deployment", " " + D1),
                             ("deployment", D1 + "/"), ("version", TOKEN), ("version", 12),
                             ("domain", TOKEN), ("domain", ACCOUNT), ("eligible", TOKEN)]:
            with self.subTest(field=field):
                first, versions, domains = deployments_page(), versions_page(), domains_page()
                if field == "deployment":
                    first["result"]["deployments"][0]["id"] = value
                elif field == "version":
                    first["result"]["deployments"][0]["versions"][0]["version_id"] = value
                elif field == "domain":
                    domains["result"][0]["id"] = value
                else:
                    versions["result"]["items"][0]["id"] = value
                result = module.probe(environment(), transport=happy_transport(first, versions, domains))
                self.assertEqual(result["code"], "IDENTIFIER_INVALID")
                self.assertNotIn(TOKEN, json.dumps(result))
                self.assertNotIn(ACCOUNT, json.dumps(result))
        env = environment()
        env["CLOUDFLARE_API_TOKEN"] = V1  # valid UUID-shaped secret must not become a result ID
        result = module.probe(env, transport=happy_transport())
        self.assertEqual(result["code"], "IDENTIFIER_INVALID")
        self.assertNotIn(V1, json.dumps(result))

    def test_multi_version_percentages_are_preserved_and_total_exactly_100(self):
        module = load_probe(self)
        first = deployments_page([deployment(D1, (V1, 12.5), (V2, 87.5)), deployment(D0, (V0, 100))])
        result = module.probe(environment(), transport=happy_transport(first=first, last=first))
        self.assertEqual(result["status"], "METADATA_VERIFIED")
        self.assertEqual(result["active_deployment"]["versions"],
                         [{"id": V1, "percentage": 12.5}, {"id": V2, "percentage": 87.5}])
        self.assertEqual(result["rollback"]["current_version_ids"], [V1, V2])
        self.assertEqual(result["rollback"]["prior_version_ids"], [V0])
        fractional = deployments_page([deployment(D1, (V1, 33.3), (V2, 66.7)), deployment(D0, (V0, 100))])
        self.assertEqual(module.probe(environment(), transport=happy_transport(first=fractional, last=fractional))["status"],
                         "METADATA_VERIFIED")
        for percentages in [(0, 100), (50, 49), (-1, 101), (True, 99), ("50", 50), (0.001, 99.999)]:
            first = deployments_page([deployment(D1, (V1, percentages[0]), (V2, percentages[1]))], total=1)
            result = module.probe(environment(), transport=happy_transport(first=first, last=first))
            self.assertEqual(result["code"], "SCHEMA_UNSUPPORTED")
            self.assertIsNone(result["active_deployment"])

    def test_unknown_legacy_or_duplicate_deployment_schema_is_partial(self):
        module = load_probe(self)
        bad = [envelope([]), envelope({"versions": [V1]}), envelope({"deployments": []}),
               deployments_page([deployment(D1, (V1, 100)), deployment(D1, (V0, 100))]),
               deployments_page([deployment(D1, (V1, 50), (V1, 50))], total=1)]
        strategy = deployments_page()
        strategy["result"]["deployments"][0]["strategy"] = "legacy"
        bad.append(strategy)
        for body in bad:
            result = module.probe(environment(), transport=happy_transport(first=body))
            self.assertEqual(result["code"], "SCHEMA_UNSUPPORTED")
            self.assertNotEqual(result["status"], "METADATA_VERIFIED")

    def test_custom_domain_requires_exact_hostname_worker_and_production_environment(self):
        module = load_probe(self)
        for field, value in [("hostname", "other.invalid"), ("hostname", "miya-lis.net."),
                             ("service", "other-worker-canary"), ("service", "MIYA-LIS-FOREST"),
                             ("environment", "staging"), ("environment", None)]:
            body = domains_page()
            body["result"][0][field] = value
            result = module.probe(environment(), transport=happy_transport(domains=body))
            self.assertEqual(result["code"], "DOMAIN_MISMATCH")
            self.assertEqual(result["domain"], {"status": "UNVERIFIED", "id": None})
            self.assertNotIn("other-worker-canary", json.dumps(result))
        for result_body, code in [([], "DOMAIN_NOT_FOUND"),
                                  (domains_page()["result"] * 2, "DOMAIN_AMBIGUOUS")]:
            result = module.probe(environment(), transport=happy_transport(domains=envelope(result_body)))
            self.assertEqual(result["code"], code)
        body = domains_page()
        body["result_info"] = {"page": 1, "total_pages": 2}
        self.assertEqual(module.probe(environment(), transport=happy_transport(domains=body))["code"],
                         "PAGINATION_UNVERIFIED")

    def test_rollback_candidates_require_deployable_and_previously_deployed_ids(self):
        module = load_probe(self)
        for ids, code in [((V0,), "ACTIVE_VERSION_UNAVAILABLE"),
                          ((V1, V2), "ROLLBACK_NOT_OBSERVED"), ((), "VERSIONS_UNAVAILABLE")]:
            result = module.probe(environment(), transport=happy_transport(versions=versions_page(ids)))
            self.assertEqual(result["code"], code)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertNotIn(V2, result["rollback"]["prior_version_ids"])
            self.assertEqual(result["rollback"]["execution"], "NOT_TESTED")

    def test_active_deployment_change_during_observation_is_not_verified(self):
        module = load_probe(self)
        changed = deployments_page([deployment(D0, (V0, 100)), deployment(D1, (V1, 100))])
        result = module.probe(environment(), transport=happy_transport(last=changed))
        self.assertEqual(result["code"], "SNAPSHOT_CHANGED")
        self.assertEqual(result["status"], "PARTIAL")


def history_two_pages():
    first = [deployment(D1, (V1, 100))]
    first.extend(deployment(f"{n:08x}-0000-4000-8000-000000000000", (V0, 100)) for n in range(2, 21))
    return deployments_page(first, page=1, pages=2, total=21), deployments_page(
        [deployment(D0, (V0, 100))], page=2, pages=2, total=21)


def closing_pagination_cases():
    cases = []
    missing = deployments_page()
    del missing["result_info"]
    cases.append(("missing", missing, "PAGINATION_UNVERIFIED"))
    for name, updates, code in [
            ("wrong-page", {"page": 2}, "PAGINATION_UNVERIFIED"),
            ("count-mismatch", {"count": 19}, "PAGINATION_UNVERIFIED"),
            ("page-limit", {"total_pages": 101}, "PAGINATION_LIMIT"),
            ("record-limit", {"total_count": 2001}, "PAGINATION_LIMIT"),
            ("reported-truncation", {"total_pages": 101, "total_count": 2001}, "PAGINATION_LIMIT"),
            ("inconsistent-total", {"total_count": 21}, "PAGINATION_UNVERIFIED"),
            ("wrong-per-page", {"per_page": 100}, "PAGINATION_UNVERIFIED"),
            ("boolean-page", {"page": True}, "PAGINATION_UNVERIFIED")]:
        last = deployments_page()
        last["result_info"].update(updates)
        cases.append((name, last, code))
    last = deployments_page([deployment(D1, (V1, 100)), deployment(D0, (V0, 100)),
                             deployment("33333333-3333-4333-8333-333333333333", (V0, 100))], total=3)
    cases.append(("changed-consistent-total", last, "PAGINATION_UNVERIFIED"))
    last = deployments_page([deployment(D0, (V0, 100)), deployment(D1, (V1, 100))])
    last["result_info"]["count"] = 19
    cases.append(("pagination-before-active-comparison", last, "PAGINATION_UNVERIFIED"))
    return cases


class BudgetTests(unittest.TestCase):
    def test_final_reread_requires_consistent_page_one_metadata(self):
        module = load_probe(self)
        for name, last, expected in closing_pagination_cases():
            with self.subTest(case=name), tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
                transport = happy_transport(last=last)
                env = environment()
                env["RUNNER_TEMP"] = base
                out, err = io.StringIO(), io.StringIO()
                with redirect_stderr(err):
                    status = module.main(argv=[], environ=env, transport=transport, stdout=out)
                result = json.loads(out.getvalue())
                self.assertEqual((status, result["status"], result["code"]), (2, "PARTIAL", expected))
                self.assertEqual(json.loads((Path(base) / "cloudflare-readiness/result.json").read_text()), result)
                self.assertEqual(len(transport.calls), 4)
                self.assertTrue(transport.calls[-1][0].endswith("deployments?page=1&per_page=20"))
                self.assertEqual(err.getvalue(), "")
                for forbidden in (TOKEN, ACCOUNT, base, "Traceback"):
                    self.assertNotIn(forbidden, out.getvalue())

    def test_documented_deployment_pagination_is_exhausted_before_verification(self):
        module = load_probe(self)
        first, second = history_two_pages()
        transport = ScriptedTransport(first, second, versions_page(), domains_page(), first)
        result = module.probe(environment(), transport=transport)
        self.assertEqual(result["status"], "METADATA_VERIFIED")
        self.assertEqual(len(result["deployments"]), 21)
        self.assertEqual(len(transport.calls), 5)
        self.assertTrue(transport.calls[1][0].endswith("deployments?page=2&per_page=20"))

    def test_missing_inconsistent_or_incomplete_pagination_never_verifies(self):
        module = load_probe(self)
        bad = deployments_page()
        del bad["result_info"]
        bodies = [bad]
        for key, value in [("count", 3), ("page", 2), ("page", True), ("per_page", 100),
                           ("total_pages", 2), ("total_count", 21)]:
            body = deployments_page()
            body["result_info"][key] = value
            bodies.append(body)
        for body in bodies:
            with self.subTest(info=body.get("result_info")):
                transport = happy_transport(first=body)
                result = module.probe(environment(), transport=transport)
                self.assertEqual(result["code"], "PAGINATION_UNVERIFIED")
                self.assertNotEqual(result["status"], "METADATA_VERIFIED")
                self.assertEqual(len(transport.calls), 1)
        first, second = history_two_pages()
        for field, value in [("page", 1), ("total_count", 22), ("count", 0)]:
            second = history_two_pages()[1]
            second["result_info"][field] = value
            result = module.probe(environment(), transport=ScriptedTransport(first, second))
            self.assertEqual(result["code"], "PAGINATION_UNVERIFIED")
        first, second = history_two_pages()
        second["result"]["deployments"][0]["id"] = D1
        self.assertEqual(module.probe(environment(), transport=ScriptedTransport(first, second))["code"],
                         "PAGINATION_UNVERIFIED")

    def test_page_record_and_request_budgets_fail_closed(self):
        module = load_probe(self)
        body = deployments_page()
        body["result_info"].update(total_pages=6, total_count=101)
        transport = ScriptedTransport(body)
        self.assertEqual(module.probe(environment(), transport=transport)["code"], "PAGINATION_LIMIT")
        self.assertEqual(len(transport.calls), 1)
        body = versions_page([f"{n:08x}-0000-4000-8000-000000000000" for n in range(101)])
        self.assertEqual(module.probe(environment(), transport=happy_transport(versions=body))["code"],
                         "RECORD_LIMIT")
        module.MAX_REQUESTS = 2
        transport = happy_transport()
        self.assertEqual(module.probe(environment(), transport=transport)["code"], "REQUEST_LIMIT")
        self.assertEqual(len(transport.calls), 2)

    def test_aggregate_response_bytes_and_total_deadline_are_bounded(self):
        module = load_probe(self)
        first, second = history_two_pages()
        bodies = [first, second, versions_page(), domains_page(), first]
        padded = []
        for body in bodies:
            clone = json.loads(json.dumps(body))
            clone["ignored_padding"] = "SYNTHETIC_PADDING" + "x" * 240000
            padded.append(clone)
        transport = ScriptedTransport(*padded)
        result = module.probe(environment(), transport=transport)
        self.assertEqual(result["code"], "TOTAL_RESPONSE_LIMIT")
        self.assertEqual(len(transport.calls), 5)
        self.assertNotIn("SYNTHETIC_PADDING", json.dumps(result))
        now = [0.0]
        transport = happy_transport()
        def late(path, authorization, timeout):
            response = transport(path, authorization, timeout)
            now[0] = 61.0
            return response
        result = module.probe(environment(), transport=late, clock=lambda: now[0])
        self.assertEqual(result["code"], "DEADLINE_EXCEEDED")
        self.assertEqual(len(transport.calls), 1)
        self.assertIsNone(result["active_deployment"])


class FakeHTTPResponse:
    def __init__(self, body=b"{}", status=200, headers=None):
        self.status = status
        self.headers = headers if headers is not None else [("Content-Type", "application/json")]
        self.body = body
        self.read_sizes = []

    def getheaders(self):
        return self.headers

    def read(self, size):
        self.read_sizes.append(size)
        return self.body[:size]


class MeteredBytes(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.consumed = 0

    def read(self, *args):
        data = super().read(*args)
        self.consumed += len(data)
        return data

    def readline(self, *args):
        data = super().readline(*args)
        self.consumed += len(data)
        return data


class MemorySocket:
    def __init__(self, stream):
        self.stream = stream

    def makefile(self, *_args, **_kwargs):
        return self.stream


class MeteredHTTPResponse(http.client.HTTPResponse):
    """Run the real HTTP parser without a socket or response-object replacement."""
    def __init__(self, body, pairs=None, wire_body=None, *, status=200):
        if pairs is None:
            pairs = [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
        head = ("HTTP/1.1 " + str(status) + " Synthetic\r\n").encode("ascii") + b"".join(
            (key + ": " + value + "\r\n").encode("ascii") for key, value in pairs) + b"\r\n"
        wire = head + (body if wire_body is None else wire_body)
        self.stream = MeteredBytes(wire)
        self.wire_bytes = len(wire)
        self.read_sizes = []
        super().__init__(MemorySocket(self.stream))
        self.begin()
        self.initial_bytes = self.stream.consumed

    def read(self, amt=None):
        self.read_sizes.append(amt)
        return super().read(amt)


class DeferredHTTPResponse(MeteredHTTPResponse):
    """Parse malformed synthetic status/headers inside getresponse, not fixture setup."""
    begin_on_get = True

    def __init__(self, wire):
        self.stream = MeteredBytes(wire)
        self.read_sizes = []
        http.client.HTTPResponse.__init__(self, MemorySocket(self.stream))


def transfer_encoding_cases(body):
    """Framings refused from initial headers alone, before any body byte is read."""
    chunk = format(len(body), "x").encode() + b"\r\n" + body + b"\r\n0\r\n"
    return [
        ("empty", [("Transfer-Encoding", "")], body),
        ("identity", [("Transfer-Encoding", "identity")], body),
        ("gzip", [("Transfer-Encoding", "gzip")], body),
        ("duplicate", [("Transfer-Encoding", "chunked"), ("transfer-encoding", "")], chunk + b"\r\n"),
        ("comma-separated", [("Transfer-Encoding", "gzip, chunked")], chunk + b"\r\n"),
        ("with-content-length", [("Content-Length", str(len(body))), ("Transfer-Encoding", "chunked")],
         chunk + b"\r\n"),
    ]


def chunked_wire(body, size=None):
    size = size or len(body)
    parts = [body[i:i + size] for i in range(0, len(body), size)]
    return b"".join(format(len(part), "x").encode() + b"\r\n" + part + b"\r\n" for part in parts) + b"0\r\n\r\n"


def chunked_refusals(body):
    """Chunked framings refused while decoding, after a bounded prefix of the body."""
    chunk = format(len(body), "x").encode() + b"\r\n" + body + b"\r\n0\r\n"
    trailers = (b"X-Synthetic-Trailer: " + b"x" * 200 + b"\r\n") * 1400
    extension = format(len(body), "x").encode() + b";synthetic=" + b"x" * 24000
    extension += b"\r\n" + body + b"\r\n0\r\n\r\n"
    return [
        ("oversized-trailers", chunk + trailers + b"\r\n"),
        ("single-trailer", chunk + b"X-Synthetic: 1\r\n\r\n"),
        ("oversized-chunk-extension", extension),
        ("short-extension", format(len(body), "x").encode() + b";a\r\n" + body + b"\r\n0\r\n\r\n"),
        ("non-hex-size", b"zz\r\n" + body + b"\r\n0\r\n\r\n"),
        ("long-size", b"0" * 9 + b"1\r\nx\r\n0\r\n\r\n"),
        ("bare-lf", format(len(body), "x").encode() + b"\n" + body + b"\n0\n\n"),
        ("missing-data-crlf", format(len(body), "x").encode() + b"\r\n" + body + b"0\r\n\r\n"),
        ("truncated-data", format(len(body) + 5, "x").encode() + b"\r\n" + body),
        ("missing-last-chunk", format(len(body), "x").encode() + b"\r\n" + body + b"\r\n"),
        ("missing-final-crlf", chunk),
    ]


class HTTPSBoundaryTests(unittest.TestCase):
    def connection_factory(self, responses, calls):
        class Connection:
            def __init__(self, host, port=None, *, timeout, context):
                self.record = {"host": host, "port": port, "timeout": timeout,
                               "context": context, "requests": [], "closed": False}
                calls.append(self.record)
            def request(self, method, path, body=None, headers=None):
                self.record["requests"].append((method, path, body, headers))
            def getresponse(self):
                response = responses.pop(0)
                if getattr(response, "begin_on_get", False):
                    response.begin()
                return response
            def close(self):
                self.record["closed"] = True
        return Connection

    def invoke_real_http(self, module, responses, *, diagnostics=False):
        calls, out, err = [], io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
            env = environment()
            env["RUNNER_TEMP"] = base
            if diagnostics:
                env["CF_READINESS_DIAGNOSTICS"] = "1"
            with patch.object(module.http.client, "HTTPSConnection", self.connection_factory(list(responses), calls)), \
                    redirect_stderr(err):
                status = module.main(argv=[], environ=env, stdout=out)
            result = json.loads(out.getvalue())
            self.assertIn(status, (0, 2), "synthetic HTTP outcome must retain a durable report")
            self.assertEqual(json.loads((Path(base) / "cloudflare-readiness/result.json").read_text()), result)
            self.assertEqual(err.getvalue(), "")
            for forbidden in (TOKEN, ACCOUNT, base, "Traceback"):
                self.assertNotIn(forbidden, out.getvalue())
        self.assertTrue(all(call["closed"] for call in calls))
        for response in responses:
            response.close()
        return status, result, calls

    def test_real_http_transfer_encoding_refuses_before_body_read(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        for name, pairs, wire_body in transfer_encoding_cases(body):
            with self.subTest(framing=name):
                response = MeteredHTTPResponse(body, [("Content-Type", "application/json"), *pairs], wire_body)
                remaining = [MeteredHTTPResponse(json.dumps(item).encode()) for item in
                             (versions_page(), domains_page(), deployments_page())]
                status, result, calls = self.invoke_real_http(module, [response, *remaining])
                self.assertEqual(status, 2)
                self.assertEqual(result["status"], "PARTIAL")
                self.assertEqual(result["code"], "RESPONSE_INVALID")
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(response.stream.consumed, response.initial_bytes)
                self.assertEqual(len(calls), 1)

    def test_real_http_bounded_chunked_json_is_decoded(self):
        module = load_probe(self)
        for name, pairs, size in (("single", [("Transfer-Encoding", "chunked")], None),
                                  ("mixed-case", [("tRaNsFeR-eNcOdInG", "ChUnKeD")], None),
                                  ("padded", [("Transfer-Encoding", " chunked ")], None),
                                  ("multiple", [("Transfer-Encoding", "chunked")], 7),
                                  ("upper-hex", [("Transfer-Encoding", "chunked")], 255)):
            with self.subTest(framing=name):
                bodies = [json.dumps(b).encode() for b in
                          (deployments_page(), versions_page(), domains_page(), deployments_page())]
                responses = [MeteredHTTPResponse(b, [("Content-Type", "application/json"), *pairs],
                                                 chunked_wire(b, size).replace(b"ff\r\n", b"FF\r\n"))
                             for b in bodies]
                status, result, calls = self.invoke_real_http(module, responses)
                self.assertEqual((status, result["status"]), (0, "METADATA_VERIFIED"))
                self.assertEqual(len(calls), 4)
                for response in responses:
                    self.assertEqual(response.read_sizes, [])
                    self.assertEqual(response.stream.consumed, response.wire_bytes)

    def test_real_http_chunked_framing_violations_refuse_within_bounded_read(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        for name, wire_body in chunked_refusals(body):
            with self.subTest(framing=name):
                response = MeteredHTTPResponse(body, [("Content-Type", "application/json"),
                                                      ("Transfer-Encoding", "chunked")], wire_body)
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["status"], result["code"]), (2, "PARTIAL", "RESPONSE_INVALID"))
                self.assertEqual(response.read_sizes, [])
                self.assertLessEqual(response.stream.consumed - response.initial_bytes, len(body) + 32)
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(result["diagnostics"]), 1)
                self.assertIn((result["diagnostics"][0]["phase"], result["diagnostics"][0]["event"]),
                              {("framing", "length_invalid"), ("body", "length_mismatch")})

    def test_real_http_chunked_limits_refuse_without_full_read(self):
        module = load_probe(self)
        big = b"x" * (module.MAX_RESPONSE_BYTES + 1)
        small = b"{}"
        for name, wire_body, code, event in (
                ("decoded-limit", chunked_wire(big, 4096), "RESPONSE_TOO_LARGE", ("body", "body_limit")),
                ("one-oversized-chunk", chunked_wire(big), "RESPONSE_TOO_LARGE", ("body", "body_limit")),
                ("chunk-count", chunked_wire(small * (module.MAX_CHUNKS + 1), 1)[:-5] + b"0\r\n\r\n",
                 "RESPONSE_INVALID", ("framing", "length_limit"))):
            with self.subTest(limit=name):
                response = MeteredHTTPResponse(small, [("Content-Type", "application/json"),
                                                       ("Transfer-Encoding", "chunked")], wire_body)
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, code))
                self.assertLess(response.stream.consumed, response.wire_bytes)
                self.assertLessEqual(response.stream.consumed - response.initial_bytes,
                                     module.MAX_RESPONSE_BYTES + 12 * module.MAX_CHUNKS)
                self.assertEqual([(d["phase"], d["event"]) for d in result["diagnostics"]], [event])

    def test_real_http_bounded_content_length_json_remains_supported(self):
        module = load_probe(self)
        responses = [MeteredHTTPResponse(json.dumps(body).encode()) for body in
                     (deployments_page(), versions_page(), domains_page(), deployments_page())]
        status, result, calls = self.invoke_real_http(module, responses)
        self.assertEqual((status, result["status"]), (0, "METADATA_VERIFIED"))
        self.assertEqual(len(calls), 4)
        for response in responses:
            self.assertEqual(response.read_sizes, [module.MAX_RESPONSE_BYTES + 1])
            self.assertEqual(response.stream.consumed, response.wire_bytes)

    def test_real_http_initial_header_limits_remain_enforced(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        for pairs in ([('X-' + str(n), 'x') for n in range(40)],
                      [('X-' + str(n), 'x' * 3000) for n in range(6)], [('X-Long', 'x' * 4097)]):
            with self.subTest(header_count=len(pairs)):
                response = MeteredHTTPResponse(body, [("Content-Type", "application/json"), *pairs])
                status, result, calls = self.invoke_real_http(module, [response])
                self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(response.stream.consumed, response.initial_bytes)
                self.assertEqual(len(calls), 1)

    def test_production_transport_uses_fixed_https_get_without_proxy_or_env_ca_override(self):
        module = load_probe(self)
        self.assertTrue(callable(getattr(module, "_https_get", None)), "fixed HTTPS transport must exist")
        bodies = [deployments_page(), versions_page(), domains_page(), deployments_page()]
        responses = [FakeHTTPResponse(json.dumps(b).encode()) for b in bodies]
        calls = []
        env = {"HTTPS_PROXY": "http://" + TOKEN + ".invalid", "ALL_PROXY": "http://127.0.0.1:9",
               "CLOUDFLARE_API_BASE_URL": "http://127.0.0.1:9", "SSL_CERT_FILE": "/" + TOKEN,
               "SSL_CERT_DIR": "/" + TOKEN}
        with patch.dict(os.environ, env, clear=True), patch.object(
                module.http.client, "HTTPSConnection", self.connection_factory(responses, calls)):
            result = module.probe(environment())
        self.assertEqual(result["status"], "METADATA_VERIFIED")
        self.assertEqual(len(calls), 4)
        for call in calls:
            self.assertEqual((call["host"], call["port"]), ("api.cloudflare.com", 443))
            self.assertTrue(call["closed"])
            self.assertTrue(call["context"].check_hostname)
            self.assertEqual(len(call["requests"]), 1)
            method, path, body, headers = call["requests"][0]
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
            self.assertEqual(headers["Accept-Encoding"], "identity")
            self.assertTrue(path.startswith("/client/v4/accounts/" + ACCOUNT + "/workers/"))

    def test_redirects_and_oversized_headers_are_closed_without_reading_or_forwarding(self):
        module = load_probe(self)
        self.assertTrue(callable(getattr(module, "_https_get", None)), "fixed HTTPS transport must exist")
        for response, code in [(FakeHTTPResponse(TOKEN.encode(), 302, [("Location", "https://evil.invalid")]),
                                "REDIRECT_REFUSED"),
                               (FakeHTTPResponse(headers=[("Content-Type", "application/json"),
                                                          ("Content-Length", str(256 * 1024 + 1))]),
                                "RESPONSE_TOO_LARGE"),
                               (FakeHTTPResponse(headers=[("Content-Type", "application/json"),
                                                          ("Content-Length", "1"), ("content-length", "2")]),
                                "RESPONSE_INVALID")]:
            calls = []
            with patch.object(module.http.client, "HTTPSConnection", self.connection_factory([response], calls)):
                result = module.probe(environment())
            self.assertEqual(result["code"], code)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0]["closed"])
            self.assertEqual(response.read_sizes, [])
            self.assertNotIn(TOKEN, json.dumps(result))

    def test_transport_body_read_and_request_path_are_allowlisted(self):
        module = load_probe(self)
        self.assertTrue(callable(getattr(module, "_https_get", None)), "fixed HTTPS transport must exist")
        calls = []
        response = FakeHTTPResponse(b"x" * (256 * 1024 + 2))
        with patch.object(module.http.client, "HTTPSConnection", self.connection_factory([response], calls)):
            result = module.probe(environment())
        self.assertEqual(result["code"], "RESPONSE_TOO_LARGE")
        self.assertEqual(response.read_sizes, [256 * 1024 + 1])
        for path in ["https://evil.invalid/", "/client/v4/accounts/" + ACCOUNT + "/workers/scripts/other/settings",
                     "/client/v4/accounts/" + ACCOUNT + "/workers/scripts/miya-lis-forest/versions/" + V1,
                     "/client/v4/accounts/" + ACCOUNT + "/workers/domains?hostname=other.invalid"]:
            calls = []
            with patch.object(module.http.client, "HTTPSConnection", self.connection_factory([], calls)):
                with self.assertRaises(module._Failure):
                    module._https_get(path, "Bearer " + TOKEN, 5)
            self.assertEqual(calls, [])

    def test_process_deadline_interrupts_a_blocking_operation_without_diagnostics(self):
        module = load_probe(self)
        self.assertTrue(callable(getattr(module, "_deadline_guard", None)), "blocking deadline guard must exist")
        start = time.monotonic()
        with self.assertRaises(module._Failure) as failure:
            with module._deadline_guard(0.02):
                time.sleep(0.5)
        self.assertEqual(failure.exception.code, "DEADLINE_EXCEEDED")
        self.assertLess(time.monotonic() - start, 0.4)


class OutputTests(unittest.TestCase):
    def temporary(self):
        return tempfile.TemporaryDirectory(prefix="readiness-test-", dir=os.environ["RUNNER_TEMP"])

    def invoke(self, module, base, transport, args=()):
        self.assertTrue(callable(getattr(module, "main", None)), "fixed-path safe CLI must exist")
        env = environment()
        env["RUNNER_TEMP"] = str(base)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stderr(err):
            status = module.main(argv=list(args), environ=env, transport=transport, stdout=out)
        self.assertEqual(err.getvalue(), "")
        text = out.getvalue()
        self.assertNotIn(TOKEN, text)
        self.assertNotIn(ACCOUNT, text)
        self.assertNotIn(str(base), text)
        self.assertNotIn("Traceback", text)
        return status, json.loads(text)

    def test_fresh_report_is_exclusive_0600_and_matches_sanitized_stdout(self):
        module = load_probe(self)
        with self.temporary() as base:
            status, result = self.invoke(module, base, happy_transport())
            target = Path(base) / "cloudflare-readiness/result.json"
            self.assertEqual(status, 0)
            self.assertEqual(result["status"], "METADATA_VERIFIED")
            self.assertEqual(json.loads(target.read_text()), result)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            self.assertEqual(target.stat().st_nlink, 1)
        with self.temporary() as base:
            transport = ScriptedTransport((403, {}, TOKEN.encode()))
            status, result = self.invoke(module, base, transport)
            self.assertEqual(status, 2)  # Partial but durably sanitized; eligible for ONLY sanitized upload.
            self.assertEqual(result["code"], "AUTH_FORBIDDEN")
            self.assertEqual(json.loads((Path(base) / "cloudflare-readiness/result.json").read_text()), result)

    def test_args_stale_paths_and_symlinks_refuse_before_network_without_overwrite(self):
        module = load_probe(self)
        for case in ("args", "stale", "output-symlink", "base-symlink", "dotdot", "writable", "missing"):
            with self.subTest(case=case), self.temporary() as root:
                base = Path(root) / "owned"
                base.mkdir(mode=0o700)
                victim = Path(root) / "victim"
                victim.write_bytes(b"DO_NOT_CHANGE")
                args = ()
                if case == "args":
                    args = ("--url=https://" + TOKEN + ".invalid", "--token=" + TOKEN,
                            "--out=" + str(victim))
                elif case == "stale":
                    target = base / "cloudflare-readiness"
                    target.mkdir()
                    (target / "result.json").write_bytes(b"EXISTING_UNTRUSTED_BYTES")
                elif case == "output-symlink":
                    (base / "cloudflare-readiness").symlink_to(victim)
                elif case == "base-symlink":
                    alias = Path(root) / "alias"
                    alias.symlink_to(base, target_is_directory=True)
                    base = alias
                elif case == "dotdot":
                    base = Path(str(base) + "/../owned")
                elif case == "writable":
                    base.chmod(0o777)
                elif case == "missing":
                    base = base / "does-not-exist"
                transport = happy_transport()
                status, result = self.invoke(module, base, transport, args)
                self.assertEqual(status, 3)
                self.assertEqual(result["code"], "INVOCATION_REFUSED" if case == "args" else "OUTPUT_REFUSED")
                self.assertEqual(transport.calls, [])
                self.assertEqual(victim.read_bytes(), b"DO_NOT_CHANGE")
                if case == "stale":
                    self.assertEqual((base / "cloudflare-readiness/result.json").read_bytes(), b"EXISTING_UNTRUSTED_BYTES")
                if case == "missing":
                    self.assertFalse(base.exists())

    def test_late_output_symlink_or_directory_replacement_is_not_an_uploadable_report(self):
        module = load_probe(self)
        for kind in ("file-symlink", "directory-replace", "hardlink"):
            with self.subTest(kind=kind), self.temporary() as base:
                victim = Path(base) / "victim"
                victim.write_bytes(b"DO_NOT_CHANGE")
                queue = happy_transport()
                def mutate(path, authorization, timeout):
                    if not queue.calls:
                        directory = Path(base) / "cloudflare-readiness"
                        target = directory / "result.json"
                        if kind == "file-symlink":
                            target.unlink()
                            target.symlink_to(victim)
                        elif kind == "directory-replace":
                            directory.rename(Path(base) / "old-owned")
                            directory.mkdir(mode=0o700)
                            (directory / "result.json").write_bytes(b"DO_NOT_REPLACE")
                        else:
                            os.link(target, Path(base) / "second-hardlink")
                    return queue(path, authorization, timeout)
                status, result = self.invoke(module, base, mutate)
                self.assertEqual(status, 3)
                self.assertEqual(result["code"], "OUTPUT_REFUSED")
                self.assertEqual(victim.read_bytes(), b"DO_NOT_CHANGE")

    def test_io_failures_do_not_emit_raw_exceptions_or_mark_artifact_ready(self):
        module = load_probe(self)
        with self.temporary() as base:
            self.assertTrue(callable(getattr(module, "main", None)), "fixed-path safe CLI must exist")
            with patch.object(module.os, "fsync", side_effect=OSError(TOKEN + "/secret/path")):
                status, result = self.invoke(module, base, happy_transport())
            self.assertEqual(status, 3)
            self.assertEqual(result["code"], "OUTPUT_REFUSED")

    def test_actual_cli_refuses_missing_auth_or_all_arguments_without_network(self):
        module = load_probe(self)
        self.assertTrue(callable(getattr(module, "main", None)), "fixed-path safe CLI must exist")
        for args, expected, code in [((), 2, "ACCOUNT_INVALID"),
                                     (("--url=" + TOKEN,), 3, "INVOCATION_REFUSED")]:
            with self.temporary() as base:
                env = {"PATH": os.defpath, "RUNNER_TEMP": base, "UNRELATED_SECRET": TOKEN}
                child = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), *args], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                self.assertEqual(child.returncode, expected)
                self.assertEqual(child.stderr, "")
                self.assertEqual(json.loads(child.stdout)["code"], code)
                self.assertNotIn(TOKEN, child.stdout)
                self.assertNotIn(base, child.stdout)

    def test_main_deadline_interrupts_hung_injected_transport(self):
        module = load_probe(self)
        module.TOTAL_SECONDS = 0.02
        def hung(*_args):
            time.sleep(0.5)
            return 200, {}, b"{}"
        with self.temporary() as base:
            start = time.monotonic()
            status, result = self.invoke(module, base, hung)
            self.assertNotEqual(status, 0)
            self.assertEqual(result["code"], "DEADLINE_EXCEEDED")
            self.assertLess(time.monotonic() - start, 0.4)


class FinalBoundaryTests(unittest.TestCase):
    def test_deadline_on_guard_exit_cannot_retain_a_success_exit_code(self):
        from contextlib import contextmanager
        module = load_probe(self)
        real_guard = module._deadline_guard
        @contextmanager
        def expired_on_exit(seconds):
            with real_guard(seconds):
                yield
            raise module._Failure("DEADLINE_EXCEEDED")
        with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
            out = io.StringIO()
            env = environment()
            env["RUNNER_TEMP"] = base
            with patch.object(module, "_deadline_guard", expired_on_exit):
                status = module.main(argv=[], environ=env, transport=happy_transport(), stdout=out)
            self.assertEqual(json.loads(out.getvalue())["code"], "DEADLINE_EXCEEDED")
            self.assertEqual(status, 3)

    def test_nonpaginated_endpoints_refuse_reported_truncation(self):
        module = load_probe(self)
        for endpoint in ("versions", "domains"):
            for info in ({"page": 1, "total_pages": 2}, {"page": True, "total_pages": 1},
                         {"page": 1, "total_pages": 1, "count": 0},
                         {"page": 1, "total_pages": 1, "total_count": 200}, {}):
                with self.subTest(endpoint=endpoint, info=info):
                    versions, domains = versions_page(), domains_page()
                    (versions if endpoint == "versions" else domains)["result_info"] = info
                    result = module.probe(environment(), transport=happy_transport(versions=versions, domains=domains))
                    self.assertEqual(result["code"], "PAGINATION_UNVERIFIED")
                    self.assertEqual(result["status"], "PARTIAL")

    def test_unknown_keys_author_data_and_late_error_bodies_never_escape(self):
        module = load_probe(self)
        first, versions, domains = deployments_page(), versions_page(), domains_page()
        for body in (first, versions, domains):
            body[TOKEN] = {"arbitrary": ACCOUNT}
        transport = happy_transport(first, versions, domains, first)
        result = module.probe(environment(), transport=transport)
        self.assertEqual(result["status"], "METADATA_VERIFIED")
        self.assertEqual(set(result), {"schema", "status", "code", "target", "active_deployment", "deployments",
                                       "domain", "rollback", "deployment_approval"})
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertNotIn(ACCOUNT, json.dumps(result))
        self.assertNotIn("author_email", json.dumps(result))
        for index in (1, 2, 3):
            bodies = [deployments_page(), versions_page(), domains_page(), deployments_page()]
            bodies[index] = (403, {TOKEN: ACCOUNT}, (TOKEN + ACCOUNT).encode())
            result = module.probe(environment(), transport=ScriptedTransport(*bodies))
            self.assertEqual(result["code"], "AUTH_FORBIDDEN")
            self.assertNotIn(TOKEN, json.dumps(result))
            self.assertNotIn(ACCOUNT, json.dumps(result))


class DiagnosticTests(unittest.TestCase):
    connection_factory = HTTPSBoundaryTests.connection_factory
    invoke_real_http = HTTPSBoundaryTests.invoke_real_http

    def invoke_collector_fault(self, module, collector, *, negative=False, before_write=None):
        """Exercise the real main/file/stdout boundary, not just a collector method."""
        calls, owned, out, err = [], [], io.StringIO(), io.StringIO()
        bodies = [deployments_page(), versions_page(), domains_page(), deployments_page()]
        responses = [MeteredHTTPResponse(json.dumps(body).encode()) for body in bodies]
        if negative:
            responses[0].close()
            responses[0] = MeteredHTTPResponse(b"{}", [("Content-Type", "application/json"),
                                                      ("Transfer-Encoding", "gzip")])
        class TrackedOutput(module._Output):
            def __init__(self, base):
                super().__init__(base)
                owned.append(self)
            def write(self, result, deadline):
                if before_write is not None:
                    before_write(result)
                return super().write(result, deadline)
        try:
            with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
                env = {**environment(), "RUNNER_TEMP": base, "CF_READINESS_DIAGNOSTICS": "1"}
                with patch.object(module, "_Diagnostics", collector), patch.object(module, "_Output", TrackedOutput), \
                        patch.object(module.http.client, "HTTPSConnection", self.connection_factory(list(responses), calls)), \
                        redirect_stderr(err):
                    status = module.main(argv=[], environ=env, stdout=out)
                result = json.loads(out.getvalue())
                self.assertEqual((status, result["code"]),
                                 (2, "RESPONSE_INVALID") if negative else (0, "METADATA_VERIFIED"))
                target = Path(base) / "cloudflare-readiness/result.json"
                self.assertEqual(target.read_bytes(), out.getvalue().encode("ascii"))
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
                self.assertEqual(err.getvalue(), "")
                for secret in (TOKEN, ACCOUNT, base, "PRIVATE_DIAGNOSTIC_CANARY", "Traceback"):
                    self.assertNotIn(secret, out.getvalue())
            self.assertTrue(all((x.file, x.directory, x.base) == (None, None, None) for x in owned))
            self.assertTrue(all(call["closed"] for call in calls))
            self.assertEqual(len(calls), 1 if negative else 4)
            if negative:
                self.assertEqual(responses[0].read_sizes, [])
                self.assertEqual(responses[0].stream.consumed, responses[0].initial_bytes)
            return result
        finally:
            for response in responses:
                response.close()

    def test_collector_records_need_closed_snapshot_at_durable_stdout_boundary(self):
        module = load_probe(self)
        for kind in ("poisoned", "nonserializable"):
            for negative in (False, True):
                with self.subTest(kind=kind, negative=negative):
                    class Collector:
                        def __init__(self):
                            self.records = [{"phase": "http", "event": "status", "status": TOKEN,
                                             "private_path": "PRIVATE_DIAGNOSTIC_CANARY"}] if kind == "poisoned" else [object()]
                        def record(self, *_args, **_kwargs):
                            pass
                    result = self.invoke_collector_fault(module, Collector, negative=negative)
                    self.assertEqual(result["diagnostics"], [])

    def test_failed_record_mutation_is_discarded_and_collector_disabled(self):
        module = load_probe(self)
        for failure_type in (RuntimeError, lambda message: module._Failure("OUTPUT_REFUSED")):
            for negative in (False, True):
                with self.subTest(failure_type=failure_type, negative=negative):
                    calls = []
                    class Collector:
                        def __init__(self):
                            self.records = []
                        def record(self, *_args, **_kwargs):
                            calls.append(1)
                            self.records.append({"phase": "http", "event": "status", "status": "200"})
                            raise failure_type("PRIVATE_DIAGNOSTIC_CANARY")
                    result = self.invoke_collector_fault(module, Collector, negative=negative)
                    self.assertEqual(result["diagnostics"], [])
                    self.assertEqual(len(calls), 1, "a failed collector must not be retried or trusted")

    def test_snapshot_rejects_untrusted_types_keys_and_values_without_hooks(self):
        module = load_probe(self)
        hooks = []
        class Trap:
            def __repr__(self):
                hooks.append("repr")
                raise AssertionError("untrusted representation must not be called")
            __str__ = __repr__
        class ForgedList(list):
            def __iter__(self):
                hooks.append("iter")
                raise AssertionError("list subclass must not be read")
        class ForgedDict(dict):
            def items(self):
                hooks.append("items")
                raise AssertionError("dict subclass must not be read")
        class ForgedStr(str):
            def __eq__(self, _other):
                hooks.append("eq")
                raise AssertionError("string subclass must not be compared")
            __hash__ = str.__hash__
        safe = {"phase": "http", "event": "status", "status": "200"}
        cases = [object(), (safe,), ForgedList([safe]), [Trap()], [ForgedDict(safe)],
                 [{"phase": "http", "event": "status", "status": Trap()}],
                 [{"phase": ForgedStr("http"), "event": "status"}],
                 [{ForgedStr("phase"): "http", "event": "status"}],
                 [{"phase": "http", "event": "status", "unknown": "PRIVATE_DIAGNOSTIC_CANARY"}],
                 [{"phase": "http", "event": "unknown"}], [{"phase": "http"}],
                 [{"phase": "http", "event": "status", "status": 200}],
                 [{"phase": "http", "event": "status", "transfer_encoding": "unknown"}],
                 [{"phase": "http", "event": "status", "status": "x" * 20545}]]
        for index, records in enumerate(cases):
            for negative in (False, True):
                with self.subTest(case=index, negative=negative):
                    class Collector:
                        def __init__(self):
                            self.records = records
                        def record(self, *_args, **_kwargs):
                            pass
                    result = self.invoke_collector_fault(module, Collector, negative=negative)
                    self.assertEqual(result["diagnostics"], [])
        self.assertEqual(hooks, [])

    def test_snapshot_detaches_list_and_each_record_before_durable_write(self):
        module = load_probe(self)
        for negative in (False, True):
            with self.subTest(negative=negative):
                held = []
                safe = {"phase": "http", "event": "status", "status": "200"}
                class Collector:
                    def __init__(self):
                        self.records = [dict(safe)] * 2
                        held.append(self)
                    def record(self, *_args, **_kwargs):
                        pass
                def mutate_aliases(result):
                    records = result["diagnostics"]
                    self.assertIsNot(records, held[0].records)
                    self.assertEqual(records, [safe, safe])
                    self.assertIsNot(records[0], held[0].records[0])
                    self.assertIsNot(records[0], records[1])
                    held[0].records[0]["status"] = TOKEN
                    held[0].records[0]["private_path"] = "PRIVATE_DIAGNOSTIC_CANARY"
                    held[0].records.append(object())
                result = self.invoke_collector_fault(module, Collector, negative=negative, before_write=mutate_aliases)
                self.assertEqual(result["diagnostics"], [safe, safe])

    def test_snapshot_caps_do_not_trust_collector_or_expanded_limits(self):
        module = load_probe(self)
        safe = {"phase": "http", "event": "status", "status": "200"}
        class Collector:
            def __init__(self):
                self.records = [safe] * 65
            def record(self, *_args, **_kwargs):
                pass
        def encode(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
        for changes, count in [({"MAX_DIAGNOSTIC_RECORDS": 1000, "MAX_DIAGNOSTIC_BYTES": 100000,
                                "MAX_DIAGNOSTIC_RECORD_BYTES": 100000}, 64),
                               ({"MAX_DIAGNOSTIC_RECORDS": 1}, 1), ({"MAX_DIAGNOSTIC_BYTES": 2}, 0),
                               ({"MAX_DIAGNOSTIC_RECORD_BYTES": 1}, 0), ({"MAX_DIAGNOSTIC_BYTES": 100}, 2)]:
            for negative in (False, True):
                with self.subTest(changes=changes, negative=negative), patch.multiple(module, **changes):
                    result = self.invoke_collector_fault(module, Collector, negative=negative)
                    self.assertEqual(len(result["diagnostics"]), count)
                    self.assertLessEqual(len(encode(result["diagnostics"])), 16384)
                    self.assertTrue(all(len(encode(record)) <= 256 for record in result["diagnostics"]))

    def test_snapshot_attachment_and_serialization_faults_drop_only_observations(self):
        module = load_probe(self)
        safe = {"phase": "http", "event": "status", "status": "200"}
        dumps = json.dumps
        for site in ("attachment", "serialization"):
            for error in (OSError("PRIVATE_DIAGNOSTIC_CANARY"), module._Failure("OUTPUT_REFUSED")):
                for negative in (False, True):
                    with self.subTest(site=site, error_type=type(error), negative=negative):
                        encoded = []
                        class Collector:
                            @property
                            def records(self):
                                if site == "attachment":
                                    raise error
                                return [safe, safe]
                            def record(self, *_args, **_kwargs):
                                pass
                        def failing_dumps(value, *args, **kwargs):
                            if type(value) is dict and value.get("phase") == "http":
                                encoded.append(1)
                                if len(encoded) == 2:
                                    raise error
                            return dumps(value, *args, **kwargs)
                        with patch.object(module.json, "dumps", failing_dumps):
                            result = self.invoke_collector_fault(module, Collector, negative=negative)
                        self.assertEqual(result["diagnostics"], [])
                        self.assertEqual(len(encoded), 2 if site == "serialization" else 0)

    def test_real_process_alarm_in_snapshot_or_final_encoding_is_not_observation_failure(self):
        module = load_probe(self)
        dumps = json.dumps
        for site in ("attachment", "snapshot-encoding", "final-encoding"):
            with self.subTest(site=site), tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
                owned, entered = [], []
                class Collector:
                    @property
                    def records(self):
                        if site == "attachment":
                            entered.append(site)
                            time.sleep(0.5)
                        return [{"phase": "http", "event": "status", "status": "200"}]
                    def record(self, *_args, **_kwargs):
                        pass
                class TrackedOutput(module._Output):
                    def __init__(self, path):
                        super().__init__(path)
                        owned.append(self)
                def slow_dumps(value, *args, **kwargs):
                    if type(value) is dict and ((site == "snapshot-encoding" and "phase" in value) or
                                               (site == "final-encoding" and "diagnostics" in value)):
                        entered.append(site)
                        time.sleep(0.5)
                    return dumps(value, *args, **kwargs)
                env = {**environment(), "RUNNER_TEMP": base, "CF_READINESS_DIAGNOSTICS": "1"}
                out, err = io.StringIO(), io.StringIO()
                started = time.monotonic()
                with patch.object(module, "TOTAL_SECONDS", 0.03), patch.object(module, "_Diagnostics", Collector), \
                        patch.object(module, "_Output", TrackedOutput), patch.object(module.json, "dumps", slow_dumps), \
                        redirect_stderr(err):
                    status = module.main(argv=[], environ=env, transport=happy_transport(), stdout=out)
                self.assertEqual((status, json.loads(out.getvalue())["code"]), (3, "DEADLINE_EXCEEDED"))
                self.assertEqual(entered, [site])
                self.assertLess(time.monotonic() - started, 0.4)
                self.assertEqual(err.getvalue(), "")
                self.assertNotIn(TOKEN, out.getvalue())
                self.assertTrue(all((x.file, x.directory, x.base) == (None, None, None) for x in owned))

    def test_real_http_auth_statuses_are_observed_without_error_body_reads(self):
        module = load_probe(self)
        for status_code, status_class, code in [(401, "401", "AUTH_UNAUTHORIZED"),
                                                (403, "403", "AUTH_FORBIDDEN"),
                                                (307, "3xx", "REDIRECT_REFUSED"),
                                                (429, "other", "HTTP_REFUSED")]:
            with self.subTest(status_class=status_class):
                response = MeteredHTTPResponse((TOKEN + ACCOUNT).encode(),
                                               [("Location", "https://" + TOKEN + ".invalid/"),
                                                ("Content-Type", TOKEN)], status=status_code)
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, code))
                self.assertEqual(result["diagnostics"], [{"phase": "http", "event": "status", "status": status_class}])
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(response.stream.consumed, response.initial_bytes)
                self.assertEqual(len(calls), 1)

    def test_optin_preserves_valid_looking_secret_identifier_refusal(self):
        module = load_probe(self)
        for secret in (D1, V1, DOMAIN):
            with self.subTest(secret_kind="synthetic-identifier"):
                env = {**environment(), "CLOUDFLARE_API_TOKEN": secret, "CF_READINESS_DIAGNOSTICS": "1"}
                result = module.probe(env, transport=happy_transport())
                self.assertEqual(result["code"], "IDENTIFIER_INVALID")
                self.assertNotIn(secret, json.dumps(result))
                self.assertTrue(all(record == {"phase": "http", "event": "status", "status": "200"}
                                    for record in result["diagnostics"]))

    def test_process_timer_is_not_swallowed_inside_observation(self):
        module = load_probe(self)
        module.TOTAL_SECONDS = 0.02
        with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
            env = {**environment(), "RUNNER_TEMP": base, "CF_READINESS_DIAGNOSTICS": "1"}
            out = io.StringIO()
            started = time.monotonic()
            with patch.object(module._Diagnostics, "record", side_effect=lambda *_a, **_k: time.sleep(0.5)):
                status = module.main(argv=[], environ=env, transport=happy_transport(), stdout=out)
            self.assertEqual((status, json.loads(out.getvalue())["code"]), (3, "DEADLINE_EXCEEDED"))
            self.assertLess(time.monotonic() - started, 0.4)
            self.assertNotIn(TOKEN, out.getvalue())

    def test_classifier_sink_uses_only_typed_closed_classes_without_source_reads(self):
        import ast
        module = load_probe(self)
        tree = ast.parse(SCRIPT.read_text())
        boundaries = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                      and node.name in ("_Diagnostics", "_observe", "_status_class")]
        self.assertEqual(len(boundaries), 3)
        for boundary in boundaries:
            for node in ast.walk(boundary):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"str", "repr", "print", "open", "eval", "exec", "getattr"})
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, {"environ", "argv", "__name__", "__class__", "getenv"})
        unknown = object()
        sink = module._Diagnostics()
        sink.record(unknown, unknown, status=unknown, transfer_encoding=unknown)
        self.assertEqual(sink.records, [{"phase": "other", "event": "other", "status": "invalid",
                                         "transfer_encoding": "other"}])
        for transfer in ("none", "chunked", "other", "duplicate", "empty"):
            sink.record("framing", "transfer_encoding", status="200", transfer_encoding=transfer)
            self.assertEqual(sink.records[-1]["transfer_encoding"], transfer)
        self.assertEqual(module.MAX_RESPONSE_BYTES, 256 * 1024)
        self.assertEqual(module.MAX_TOTAL_BYTES, 1024 * 1024)
        self.assertEqual((module.MAX_REQUESTS, module.MAX_PAGES, module.TOTAL_SECONDS), (8, 5, 60))

    def test_injected_boundary_shapes_and_total_body_budget_are_closed(self):
        module = load_probe(self)
        env = {**environment(), "CF_READINESS_DIAGNOSTICS": "1"}
        class PrivateDynamicType:
            def __repr__(self):
                raise AssertionError("diagnostics must not inspect dynamic types or representations")
            __str__ = __repr__
        for response, expected in [((200,), {"phase": "http", "event": "response_shape"}),
                                   ((200, None, b"{}"), {"phase": "headers", "event": "header_shape", "status": "200"}),
                                   ((200, {"Content-Type": "application/json"}, PrivateDynamicType()),
                                    {"phase": "body", "event": "body_type", "status": "200"})]:
            with self.subTest(event=expected["event"]):
                result = module.probe(env, transport=lambda *_args: response)
                self.assertEqual(result["code"], "RESPONSE_INVALID")
                self.assertIn(expected, result["diagnostics"])
                self.assertNotIn("PrivateDynamicType", json.dumps(result))
        first, second = history_two_pages()
        bodies = [first, second, versions_page(), domains_page(), first]
        for body in bodies:
            body[TOKEN] = "x" * 240000
        transport = ScriptedTransport(*bodies)
        result = module.probe(env, transport=transport)
        self.assertEqual(result["code"], "TOTAL_RESPONSE_LIMIT")
        self.assertIn({"phase": "body", "event": "total_body_limit", "status": "200"}, result["diagnostics"])
        self.assertEqual(len(transport.calls), 5)
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_parser_and_body_read_failures_have_only_closed_boundary_events(self):
        module = load_probe(self)
        wires = [("status", ("HTTP/1.1 " + TOKEN + "\r\n\r\n").encode()),
                 ("line", b"HTTP/1.1 200 OK\r\nX-" + TOKEN.encode() + b": " + b"x" * 65536 + b"\r\n\r\n"),
                 ("count", b"HTTP/1.1 200 OK\r\n" + b"X-Canary: x\r\n" * 101 + b"\r\n")]
        for name, wire in wires:
            with self.subTest(parser=name):
                response = DeferredHTTPResponse(wire)
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, "TRANSPORT_REFUSED"))
                self.assertEqual(result["diagnostics"], [{"phase": "headers", "event": "http_parse"}])
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(len(calls), 1)
        response = MeteredHTTPResponse(b"{}")
        with patch.object(response.stream, "read", side_effect=OSError(TOKEN + ACCOUNT + "/READ_PATH")):
            status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
        self.assertEqual((status, result["code"]), (2, "TRANSPORT_REFUSED"))
        self.assertEqual(result["diagnostics"], [{"phase": "body", "event": "read_error", "status": "200"}])
        self.assertEqual(response.read_sizes, [module.MAX_RESPONSE_BYTES + 1])
        self.assertEqual(len(calls), 1)

    def test_observer_failures_preserve_primary_verdict_and_owned_output_cleanup(self):
        module = load_probe(self)
        owned = []
        class TrackedOutput(module._Output):
            def __init__(self, base):
                super().__init__(base)
                owned.append(self)
        collector_type = module._Diagnostics
        for failure_site in ("init", "record"):
            for negative in (True, False):
                with self.subTest(site=failure_site, negative=negative):
                    failure = RuntimeError(TOKEN + ACCOUNT + "/PRIVATE_EXCEPTION_PATH")
                    fault = patch.object(module, "_Diagnostics", side_effect=failure) if failure_site == "init" else \
                        patch.object(collector_type, "record", side_effect=failure)
                    bodies = [deployments_page(), versions_page(), domains_page(), deployments_page()]
                    responses = [MeteredHTTPResponse(json.dumps(body).encode()) for body in bodies]
                    if negative:
                        responses[0].close()
                        responses[0] = MeteredHTTPResponse(b"{}", [("Content-Type", "application/json"),
                                                                  ("Transfer-Encoding", "gzip")])
                    with fault, patch.object(module, "_Output", TrackedOutput):
                        status, result, calls = self.invoke_real_http(module, responses, diagnostics=True)
                    self.assertEqual((status, result["code"]),
                                     (2, "RESPONSE_INVALID") if negative else (0, "METADATA_VERIFIED"))
                    self.assertEqual(result["diagnostics"], [])
                    self.assertEqual(len(calls), 1 if negative else 4)
                    if negative:
                        self.assertEqual(responses[0].read_sizes, [])
        for output in owned:
            self.assertEqual((output.file, output.directory, output.base), (None, None, None))
        with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
            out, err = io.StringIO(), io.StringIO()
            env = {**environment(), "RUNNER_TEMP": base, "CF_READINESS_DIAGNOSTICS": "1"}
            with patch.object(collector_type, "record", side_effect=OSError(TOKEN)), \
                    patch.object(module, "_Output", TrackedOutput), \
                    patch.object(module.os, "fsync", side_effect=OSError(TOKEN + "/PRIVATE_IO_PATH")), redirect_stderr(err):
                status = module.main(argv=[], environ=env, transport=happy_transport(), stdout=out)
            self.assertEqual((status, json.loads(out.getvalue())["code"]), (3, "OUTPUT_REFUSED"))
            self.assertEqual((owned[-1].file, owned[-1].directory, owned[-1].base), (None, None, None))
            self.assertEqual(err.getvalue(), "")
            self.assertNotIn(TOKEN, out.getvalue())
            self.assertNotIn(base, out.getvalue())

    def test_diagnostic_limits_drop_observations_without_changing_verdict_or_io(self):
        module = load_probe(self)
        collector = module._Diagnostics()
        for _ in range(100):
            collector.record(TOKEN, ACCOUNT, status=TOKEN, transfer_encoding=TOKEN)
        self.assertEqual(len(collector.records), 64, "diagnostics must stop at the closed record cap")
        self.assertEqual(collector.records, [{"phase": "other", "event": "other", "status": "invalid",
                                              "transfer_encoding": "other"}] * 64)
        def encode(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
        self.assertLessEqual(len(encode(collector.records)), 16384)
        self.assertTrue(all(len(encode(record)) <= 256 for record in collector.records))
        with patch.object(module, "MAX_DIAGNOSTIC_BYTES", 2, create=True):
            limited = module._Diagnostics()
            limited.record("http", "status", status="200")
            self.assertEqual(limited.records, [])
        body = json.dumps(deployments_page()).encode()
        for field, limit in (("MAX_DIAGNOSTIC_RECORDS", 0), ("MAX_DIAGNOSTIC_BYTES", 2),
                             ("MAX_DIAGNOSTIC_RECORD_BYTES", 1)):
            with self.subTest(budget=field), patch.object(module, field, limit, create=True):
                response = MeteredHTTPResponse(body, [("Content-Type", "application/json"),
                                                      ("Transfer-Encoding", "gzip")])
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
                self.assertEqual(result["diagnostics"], [])
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(len(calls), 1)
                clean = module.probe({**environment(), "CF_READINESS_DIAGNOSTICS": "1"}, transport=happy_transport())
                self.assertEqual((clean["status"], clean["diagnostics"]), ("METADATA_VERIFIED", []))
        fresh = module.probe({**environment(), "CF_READINESS_DIAGNOSTICS": "1"}, transport=happy_transport())
        self.assertEqual(len(fresh["diagnostics"]), 4)
        self.assertIsNot(fresh["diagnostics"], collector.records)
        with patch.object(module._Diagnostics, "record", side_effect=AssertionError("default observer must be unused")):
            self.assertEqual(module.probe(environment(), transport=happy_transport())["status"], "METADATA_VERIFIED")

    def test_real_response_format_rejections_are_phase_classified_without_payloads(self):
        module = load_probe(self)
        json_headers = [("Content-Type", "application/json")]
        duplicate = ('{"success":true,"result":{},"' + TOKEN + '":0,"' + TOKEN + '":1}').encode()
        cases = [("utf8", b"\xff", None, "json", "utf8_invalid", "RESPONSE_INVALID"),
                 ("malformed", ("{" + TOKEN).encode(), None, "json", "json_invalid", "RESPONSE_INVALID"),
                 ("duplicate", duplicate, None, "json", "json_invalid", "RESPONSE_INVALID"),
                 ("nonfinite", b'{"success":true,"result":NaN}', None, "json", "json_invalid", "RESPONSE_INVALID"),
                 ("bom", b'\xef\xbb\xbf{"success":true,"result":{}}', None, "json", "json_invalid", "RESPONSE_INVALID"),
                 ("root", b"[]", None, "json", "object_required", "RESPONSE_INVALID"),
                 ("api", json.dumps({"success": False, "errors": [{TOKEN: ACCOUNT}]}).encode(), None,
                  "schema", "api_unsuccessful", "API_UNSUCCESSFUL"),
                 ("result", json.dumps({"success": True, TOKEN: ACCOUNT}).encode(), None,
                  "schema", "result_missing", "SCHEMA_UNSUPPORTED"),
                 ("metadata", json.dumps(envelope([])).encode(), None,
                  "schema", "schema_unsupported", "SCHEMA_UNSUPPORTED"),
                 ("length", b"{}", json_headers + [("Content-Length", "3")],
                  "body", "length_mismatch", "RESPONSE_INVALID"),
                 ("body-large", b"x" * (module.MAX_RESPONSE_BYTES + 1), json_headers,
                  "body", "body_limit", "RESPONSE_TOO_LARGE"),
                 ("header-controls", b"{}", json_headers + [("X-" + TOKEN, "value\r\n " + TOKEN)],
                  "headers", "header_shape", "RESPONSE_INVALID")]
        for name, body, pairs, phase, event, code in cases:
            with self.subTest(case=name):
                response = MeteredHTTPResponse(body, pairs)
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, code))
                observation = {"phase": phase, "event": event}
                if event != "schema_unsupported":
                    observation["status"] = "200"
                if name == "api":
                    observation.update(api_envelope="success_false_errors", api_error_code="other")
                self.assertIn(observation, result["diagnostics"])
                self.assertEqual(response.read_sizes, [module.MAX_RESPONSE_BYTES + 1])
                self.assertEqual(len(calls), 1)
                for forbidden in (TOKEN, ACCOUNT, "Content-Type", "X-", '"success"', '"errors"', "NaN"):
                    self.assertNotIn(forbidden, json.dumps(result["diagnostics"]))

    def test_unsuccessful_envelope_keeps_only_closed_shape_and_numeric_code(self):
        module = load_probe(self)
        cases = [({"success": False, "errors": [{"code": 10000, "message": TOKEN}]},
                  {"api_envelope": "success_false_errors", "api_error_code": "10000"}),
                 ({"success": True, "errors": [{"code": 7003}], "result": {}},
                  {"api_envelope": "success_true_errors", "api_error_code": "7003"}),
                 ({"success": False, "errors": []}, {"api_envelope": "success_false_empty"}),
                 ({"errors": [], "result": {}}, {"api_envelope": "success_missing"}),
                 ({"success": TOKEN, "result": {}}, {"api_envelope": "success_other"}),
                 ({"success": True, "errors": {TOKEN: ACCOUNT}, "result": {}}, {"api_envelope": "errors_invalid"}),
                 ({"success": True, "errors": 0, "result": {}}, {"api_envelope": "errors_invalid"}),
                 ({"success": False, "errors": None}, {"api_envelope": "success_false_null"}),
                 ({"success": False, "errors": [{"code": True}]},
                  {"api_envelope": "success_false_errors", "api_error_code": "other"}),
                 ({"success": False, "errors": [{"code": 123456789}]},
                  {"api_envelope": "success_false_errors", "api_error_code": "other"}),
                 ({"success": False, "errors": [{"code": "10000"}]},
                  {"api_envelope": "success_false_errors", "api_error_code": "other"}),
                 ({"success": False, "errors": [TOKEN]},
                  {"api_envelope": "success_false_errors", "api_error_code": "other"})]
        for body, classes in cases:
            with self.subTest(body=sorted(classes.items())):
                response = MeteredHTTPResponse(json.dumps(body).encode())
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, "API_UNSUCCESSFUL"))
                self.assertEqual(result["diagnostics"][-1],
                                 {"phase": "schema", "event": "api_unsuccessful", "status": "200", **classes})
                for forbidden in (TOKEN, ACCOUNT, '"message"'):
                    self.assertNotIn(forbidden, json.dumps(result["diagnostics"]))
        for forged in ({"phase": "schema", "event": "api_unsuccessful", "api_error_code": TOKEN[:8]},
                       {"phase": "schema", "event": "api_unsuccessful", "api_error_code": "0123"},
                       {"phase": "schema", "event": "api_unsuccessful", "api_envelope": TOKEN[:8]}):
            class Collector:
                def __init__(self):
                    self.records = [forged]
            self.assertEqual(module._diagnostic_snapshot([Collector()]), [])

    def test_successful_envelope_accepts_null_errors(self):
        module = load_probe(self)
        bodies = [deployments_page(), versions_page(), domains_page(), deployments_page()]
        for body in bodies:
            body["errors"] = None
        responses = [MeteredHTTPResponse(json.dumps(body).encode()) for body in bodies]
        status, result, calls = self.invoke_real_http(module, responses, diagnostics=True)
        self.assertEqual((status, result["status"]), (0, "METADATA_VERIFIED"))
        self.assertEqual(len(calls), 4)

    def test_initial_http_rejections_identify_closed_header_or_framing_category(self):
        module = load_probe(self)
        body = ("{" + TOKEN + ACCOUNT).encode()
        content_type = [("Content-Type", "application/json")]
        cases = [("missing-type", [], "headers", "content_type_missing", "RESPONSE_INVALID"),
                 ("other-type", [("Content-Type", TOKEN)], "headers", "content_type_other", "RESPONSE_INVALID"),
                 ("encoding", content_type + [("Content-Encoding", TOKEN)], "headers",
                  "content_encoding_unsupported", "RESPONSE_INVALID"),
                 ("duplicate", content_type + [("X-" + TOKEN, ACCOUNT), ("x-" + TOKEN, ACCOUNT)],
                  "headers", "header_shape", "RESPONSE_INVALID"),
                 ("count", content_type + [("X-" + str(n), "x") for n in range(40)],
                  "headers", "header_count", "RESPONSE_INVALID"),
                 ("aggregate", content_type + [("X-" + str(n), "x" * 3000) for n in range(6)],
                  "headers", "header_budget", "RESPONSE_INVALID"),
                 ("single", content_type + [("X-Long", "x" * 4097)],
                  "headers", "header_budget", "RESPONSE_INVALID"),
                 ("length-invalid", content_type + [("Content-Length", TOKEN)],
                  "framing", "length_invalid", "RESPONSE_INVALID"),
                 ("length-large", content_type + [("Content-Length", str(module.MAX_RESPONSE_BYTES + 1))],
                  "framing", "length_limit", "RESPONSE_TOO_LARGE")]
        for name, pairs, phase, event, code in cases:
            with self.subTest(case=name):
                response = MeteredHTTPResponse(body, pairs)
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, code))
                self.assertEqual(result["diagnostics"], [{"phase": phase, "event": event, "status": "200"}])
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(response.stream.consumed, response.initial_bytes)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("X-", json.dumps(result["diagnostics"]))

    def test_transfer_classification_precedes_real_http_body_reads(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        classes = {"empty": "empty",
                   "identity": "other", "gzip": "other", "duplicate": "duplicate",
                   "comma-separated": "other", "with-content-length": "chunked", "canary": "other"}
        cases = transfer_encoding_cases(body) + [("canary", [("Transfer-Encoding", TOKEN)], body)]
        for name, pairs, wire_body in cases:
            with self.subTest(framing=name):
                response = MeteredHTTPResponse(body, [("Content-Type", "application/json"), *pairs], wire_body)
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["status"], result["code"]), (2, "PARTIAL", "RESPONSE_INVALID"))
                self.assertEqual(result["diagnostics"], [{
                    "phase": "headers" if name == "duplicate" else "framing",
                    "event": "header_shape" if name == "duplicate" else "transfer_encoding",
                    "status": "200", "transfer_encoding": classes[name]}])
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(response.stream.consumed, response.initial_bytes)
                self.assertEqual(len(calls), 1)
        responses = [MeteredHTTPResponse(json.dumps(value).encode()) for value in
                     (deployments_page(), versions_page(), domains_page(), deployments_page())]
        status, result, calls = self.invoke_real_http(module, responses, diagnostics=True)
        self.assertEqual((status, result["status"]), (0, "METADATA_VERIFIED"))
        self.assertEqual(result["diagnostics"], [{"phase": "http", "event": "status", "status": "200"}] * 4)
        self.assertEqual(len(calls), 4)
        for response in responses:
            self.assertEqual(response.read_sizes, [module.MAX_RESPONSE_BYTES + 1])
            self.assertEqual(response.stream.consumed, response.wire_bytes)

    def test_optin_is_exact_and_observes_only_closed_http_status_classes(self):
        module = load_probe(self)
        baseline = module.probe(environment(), transport=happy_transport())
        self.assertEqual(len(baseline), 9)
        for flag in (None, "", "0", "true", 1, True):
            env = {**environment(), "CF_READINESS_DIAGNOSTICS": flag}
            self.assertEqual(module.probe(env, transport=happy_transport()), baseline)
        env = {**environment(), "CF_READINESS_DIAGNOSTICS": "1"}
        for status, expected, code in [(401, "401", "AUTH_UNAUTHORIZED"),
                                       (403, "403", "AUTH_FORBIDDEN"),
                                       (302, "3xx", "REDIRECT_REFUSED"),
                                       (500, "other", "HTTP_REFUSED"),
                                       (TOKEN, "invalid", "RESPONSE_INVALID"),
                                       (True, "invalid", "RESPONSE_INVALID")]:
            with self.subTest(status_class=expected):
                transport = ScriptedTransport((status, {TOKEN: ACCOUNT}, TOKEN.encode()))
                result = module.probe(env, transport=transport)
                self.assertEqual((result["status"], result["code"]), ("PARTIAL", code))
                self.assertIn("diagnostics", result, "explicit opt-in must classify the HTTP boundary")
                self.assertEqual(result["diagnostics"], [{"phase": "http", "event": "status", "status": expected}])
                self.assertEqual(len(transport.calls), 1)
                for forbidden in (TOKEN, ACCOUNT, "Traceback"):
                    self.assertNotIn(forbidden, json.dumps(result))
        result = module.probe(env, transport=happy_transport())
        self.assertEqual(result.pop("diagnostics", None),
                         [{"phase": "http", "event": "status", "status": "200"}] * 4)
        self.assertEqual(result, baseline)
        self.assertEqual(module.probe({"CF_READINESS_DIAGNOSTICS": "1"})["diagnostics"], [])


class RepeatedCookieTests(unittest.TestCase):
    """One narrow repeatable-field exception, exercised with real wire parsing."""
    connection_factory = HTTPSBoundaryTests.connection_factory
    invoke_real_http = HTTPSBoundaryTests.invoke_real_http

    def responses(self, extra):
        responses = []
        for item in (deployments_page(), versions_page(), domains_page(), deployments_page()):
            body = json.dumps(item).encode()
            pairs = [("Content-Type", "application/json"), ("Content-Length", str(len(body))), *extra]
            responses.append(MeteredHTTPResponse(body, pairs))
        return responses

    def test_repeated_set_cookie_preserves_metadata_and_closed_diagnostics(self):
        module = load_probe(self)
        expected = module.probe(environment(), transport=happy_transport())
        cookies = [("Set-Cookie", "first=COOKIE_PRIVATE_CANARY; Path=/; HttpOnly"),
                   ("sEt-CoOkIe", "second=other; Expires=Wed, 21 Oct 2037 07:28:00 GMT")]
        for diagnostics in (False, True):
            with self.subTest(diagnostics=diagnostics):
                responses = self.responses(cookies)
                self.assertEqual(responses[0].getheaders()[-2:], cookies)
                self.assertTrue(all(type(k) is str and type(v) is str for k, v in responses[0].getheaders()))
                status, result, calls = self.invoke_real_http(module, responses, diagnostics=diagnostics)
                self.assertEqual((status, result["code"]), (0, "METADATA_VERIFIED"))
                if diagnostics:
                    self.assertEqual(result.pop("diagnostics"), [{"phase": "http", "event": "status", "status": "200"}] * 4)
                self.assertEqual(result, expected)
                self.assertEqual(len(calls), 4)
                self.assertNotIn("COOKIE_PRIVATE_CANARY", json.dumps(result))
                for response in responses:
                    self.assertEqual(response.read_sizes, [module.MAX_RESPONSE_BYTES + 1])
                    self.assertEqual(response.stream.consumed, response.wire_bytes)

    def test_unique_cookie_and_ordinary_headers_keep_default_optin_parity(self):
        module = load_probe(self)
        expected = module.probe(environment(), transport=happy_transport())
        for extra in ([], [("Set-Cookie", "single=COOKIE_PRIVATE_CANARY")], [("X-Synthetic", "opaque")]):
            for diagnostics in (False, True):
                with self.subTest(extra=extra, diagnostics=diagnostics):
                    status, result, calls = self.invoke_real_http(module, self.responses(extra), diagnostics=diagnostics)
                    if diagnostics:
                        self.assertEqual(result.pop("diagnostics"),
                                         [{"phase": "http", "event": "status", "status": "200"}] * 4)
                    self.assertEqual((status, result), (0, expected))
                    self.assertEqual(len(calls), 4)

    def test_invalid_later_cookie_occurrences_are_not_hidden(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        bad_values = ["left" + chr(n) + "right" for n in (*range(32), 127) if n not in (10, 13)]
        bad_values += ["left\r\n COOKIE_PRIVATE_CANARY"]
        for value in bad_values:
            for index in (1, 2):
                with self.subTest(value_codepoints=[ord(c) for c in value], index=index):
                    cookies = [("Set-Cookie", "valid=first")] * index + [("set-cookie", value)]
                    response = MeteredHTTPResponse(body, [("Content-Type", "application/json"), *cookies])
                    status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                    self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
                    self.assertEqual(result["diagnostics"], [{"phase": "headers", "event": "header_shape", "status": "200"}])
                    self.assertEqual(response.read_sizes, [])
                    self.assertEqual(response.stream.consumed, response.initial_bytes)
                    self.assertEqual(len(calls), 1)

    def test_invalid_retained_first_cookie_still_reaches_second_validator(self):
        module = load_probe(self)
        response = self.responses([("Set-Cookie", "left\tright"), ("set-cookie", "valid=second")])[0]
        # The retained first value must not be replaced by a later, valid value.
        # Before compatibility support the blanket duplicate check refuses earlier.
        status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
        self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
        self.assertEqual(result["diagnostics"], [{"phase": "http", "event": "status", "status": "200"},
                                                {"phase": "headers", "event": "header_shape", "status": "200"}])
        self.assertEqual(response.read_sizes, [module.MAX_RESPONSE_BYTES + 1])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("left", json.dumps(result))

    def test_each_cookie_occurrence_counts_toward_header_count(self):
        module = load_probe(self)
        # Two decision headers plus 38 cookies is the exact 40-field ceiling.
        status, result, calls = self.invoke_real_http(module, self.responses([("Set-Cookie", "a=b")] * 38))
        self.assertEqual((status, result["code"], len(calls)), (0, "METADATA_VERIFIED", 4))
        responses = self.responses([("Set-Cookie", "a=b")] * 39)
        for response in responses:
            self.assertEqual(len(response.getheaders()), 41)
        status, result, calls = self.invoke_real_http(module, responses, diagnostics=True)
        self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
        self.assertEqual(result["diagnostics"], [{"phase": "headers", "event": "header_count", "status": "200"}])
        self.assertEqual(responses[0].read_sizes, [])
        self.assertEqual(len(calls), 1)

    def test_each_cookie_occurrence_counts_toward_aggregate_header_budget(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        base = [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
        remaining = 16384 - sum(len(k) + len(v) for k, v in base) - 4 * len("Set-Cookie") - 3 * 4096
        self.assertTrue(2 < remaining <= 4096)
        pairs = base + [("Set-Cookie", "a=" + "x" * 4094)] * 3
        exact = MeteredHTTPResponse(body, pairs + [("set-cookie", "b=" + "y" * (remaining - 2))])
        self.assertEqual(sum(len(k) + len(v) for k, v in exact.getheaders()), 16384)
        remaining_responses = [MeteredHTTPResponse(json.dumps(item).encode()) for item in
                               (versions_page(), domains_page(), deployments_page())]
        status, result, calls = self.invoke_real_http(module, [exact, *remaining_responses])
        self.assertEqual((status, result["code"], len(calls)), (0, "METADATA_VERIFIED", 4))
        response = MeteredHTTPResponse(body, pairs + [("set-cookie", "b=" + "y" * (remaining - 1))])
        self.assertEqual(sum(len(k) + len(v) for k, v in response.getheaders()), 16385)
        status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
        self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
        self.assertEqual(result["diagnostics"], [{"phase": "headers", "event": "header_budget", "status": "200"}])
        self.assertEqual(response.read_sizes, [])
        self.assertEqual(len(calls), 1)

    def test_later_cookie_value_cap_and_nonstring_refusals_remain(self):
        module = load_probe(self)
        status, result, calls = self.invoke_real_http(module, self.responses([
            ("Set-Cookie", "valid=first"), ("set-cookie", "a=" + "x" * 4094)]))
        self.assertEqual((status, result["code"], len(calls)), (0, "METADATA_VERIFIED", 4))
        for value in ("a=" + "x" * 4095, None, 7):
            with self.subTest(value_type=type(value).__name__):
                response = FakeHTTPResponse(json.dumps(deployments_page()).encode(), headers=[
                    ("Content-Type", "application/json"), ("Set-Cookie", "valid=first"), ("set-cookie", value)])
                response.close = lambda: None
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(len(calls), 1)

    def test_decision_header_duplicates_still_refuse_before_body(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        for key, first, second in [("Content-Type", "application/json", "application/json"),
                                   ("Content-Type", "application/json", "text/html"),
                                   ("Content-Length", str(len(body)), str(len(body))),
                                   ("Content-Length", str(len(body)), "1"),
                                   ("Content-Encoding", "identity", "identity"),
                                   ("Content-Encoding", "identity", "gzip")]:
            with self.subTest(key=key, same=first == second):
                pairs = [("Set-Cookie", "first=1"), ("set-cookie", "second=2")]
                if key != "Content-Type":
                    pairs += [("Content-Type", "application/json")]
                response = MeteredHTTPResponse(body, pairs + [(key, first), (key.lower(), second)])
                status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
                self.assertEqual(result["diagnostics"], [{"phase": "headers", "event": "header_shape", "status": "200"}])
                self.assertEqual(response.read_sizes, [])
                self.assertEqual(response.stream.consumed, response.initial_bytes)
                self.assertEqual(len(calls), 1)

    def test_any_transfer_encoding_with_repeated_cookies_is_prebody_refused(self):
        module = load_probe(self)
        body = json.dumps(deployments_page()).encode()
        for name, framing, wire_body in transfer_encoding_cases(body):
            for cookies_first in (False, True):
                with self.subTest(framing=name, cookies_first=cookies_first):
                    cookies = [("Set-Cookie", "first=1"), ("set-cookie", "second=2")]
                    extra = cookies + framing if cookies_first else framing + cookies
                    response = MeteredHTTPResponse(body, [("Content-Type", "application/json"), *extra], wire_body)
                    status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
                    self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
                    self.assertEqual(response.read_sizes, [])
                    self.assertEqual(response.stream.consumed, response.initial_bytes)
                    self.assertEqual(len(calls), 1)

    def test_unknown_repeated_fields_remain_conservatively_refused(self):
        module = load_probe(self)
        response = self.responses([("X-Synthetic", "first"), ("x-synthetic", "second")])[0]
        status, result, calls = self.invoke_real_http(module, [response], diagnostics=True)
        self.assertEqual((status, result["code"]), (2, "RESPONSE_INVALID"))
        self.assertEqual(result["diagnostics"], [{"phase": "headers", "event": "header_shape", "status": "200"}])
        self.assertEqual(response.read_sizes, [])
        self.assertEqual(len(calls), 1)


class WorkflowTests(unittest.TestCase):
    def workflow(self):
        path = ROOT / ".github/workflows/cloudflare-readiness.yml"
        self.assertTrue(path.is_file(), "branch-only read-only workflow must exist")
        return json.loads(path.read_text(encoding="utf-8"))  # JSON is a strict YAML subset.

    def test_only_exact_authorized_push_and_source_sha_can_enter_job(self):
        wf = self.workflow()
        self.assertEqual(set(wf), {"name", "on", "permissions", "concurrency", "jobs"})
        self.assertEqual(wf["on"], {"push": {"branches": ["ci/cloudflare-readiness-20261015-142216"]}})
        self.assertEqual(wf["permissions"], {"contents": "read"})
        self.assertEqual(wf["concurrency"], {"group": "cloudflare-readiness-20261015-142216-${{ github.ref }}",
                                             "cancel-in-progress": False})
        self.assertEqual(list(wf["jobs"]), ["readiness"])
        job = wf["jobs"]["readiness"]
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertEqual(job["timeout-minutes"], 5)
        self.assertEqual(job["if"], "${{ github.repository == 'ryoryoryo3838/miya-lis.net' && "
                         "github.event_name == 'push' && github.ref == 'refs/heads/ci/cloudflare-readiness-20261015-142216' && "
                         "github.sha == github.event.after && !github.event.deleted }}")
        self.assertEqual(job["env"], {"PYTHONDONTWRITEBYTECODE": "1"})
        steps = job["steps"]
        self.assertEqual(len(steps), 5)
        self.assertEqual(steps[0]["uses"], "actions/checkout@11d5960a326750d5838078e36cf38b85af677262")
        self.assertEqual(steps[0]["with"], {"repository": "ryoryoryo3838/miya-lis.net", "ref": "${{ github.sha }}",
                                           "persist-credentials": False, "fetch-depth": 1,
                                           "submodules": False, "lfs": False})
        self.assertEqual(steps[1]["run"], "python3 -I -B -m unittest discover -s test -p 'test_cloudflare_readiness.py' -v")
        self.assertFalse(any("env" in s for s in steps if s is not steps[2]))
        self.assertEqual(steps[2]["env"], {"CLOUDFLARE_ACCOUNT_ID": "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}",
                                         "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
                                         "CF_READINESS_DIAGNOSTICS": "1"})
        self.assertEqual(steps[2]["id"], "probe")
        self.assertEqual(steps[2]["continue-on-error"], True)
        self.assertEqual(steps[2]["timeout-minutes"], 2)
        self.assertEqual(steps[4]["if"], "${{ !cancelled() && steps.probe.outcome != 'success' }}")
        self.assertEqual(steps[4]["run"], "exit 1")
        text = json.dumps(wf)
        for forbidden in ("PUBLIC_CONTENT_TOKEN", "CONTENT_TOKEN", "workflow_dispatch", "repository_dispatch",
                          "pull_request", "wrangler", "cache@", "setup-node", "setup-python", "download-artifact",
                          "wiki.miya-lis.net", "converter", "compiler", "main", "miya'"):
            self.assertNotIn(forbidden, text)

    def test_only_a_verified_fresh_sanitized_file_is_uploaded_with_existing_pin(self):
        step = self.workflow()["jobs"]["readiness"]["steps"][3]
        self.assertEqual(step["uses"], "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02")
        self.assertEqual(step["if"], "${{ !cancelled() && steps.probe.outputs.artifact_ready == 'true' }}")
        self.assertEqual(step["with"], {"name": "cloudflare-readiness-${{ github.run_id }}-${{ github.run_attempt }}",
                                       "path": "${{ runner.temp }}/cloudflare-readiness/result.json",
                                       "if-no-files-found": "error", "include-hidden-files": False,
                                       "retention-days": 1, "compression-level": 6, "overwrite": False})

    def test_real_shell_marks_only_0_or_2_uploadable_and_preserves_failure_exit(self):
        script = self.workflow()["jobs"]["readiness"]["steps"][2]["run"]
        command = "timeout --signal=TERM --kill-after=5s 75s python3 -I -B scripts/cloudflare-readiness.py"
        self.assertEqual(script.count(command), 1)
        self.assertNotIn("set -x", script)
        for status in (0, 2, 3, 1, 124, 137):
            with self.subTest(status=status), tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
                output = Path(base) / "step-output"
                substituted = script.replace(command, f"'{sys.executable}' -I -B -c 'raise SystemExit({status})'")
                child = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", substituted],
                                       env={"PATH": os.defpath, "GITHUB_OUTPUT": str(output)},
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                self.assertEqual(child.returncode, status)
                self.assertEqual(child.stderr, "")
                self.assertEqual(child.stdout, "")
                self.assertEqual(output.read_text() if output.exists() else "",
                                 "artifact_ready=true\n" if status in (0, 2) else "")

    def test_real_shell_refuses_readable_nonwritable_output_without_path_reflection(self):
        script = self.workflow()["jobs"]["readiness"]["steps"][2]["run"]
        command = "timeout --signal=TERM --kill-after=5s 75s python3 -I -B scripts/cloudflare-readiness.py"
        self.assertEqual(script.count(command), 1)
        for status in (0, 2):
            with self.subTest(probe_exit=status), tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
                output = Path(base) / "PRIVATE_OUTPUT_PATH_CANARY"
                output.write_text("")
                output.chmod(0o400)
                self.assertTrue(output.is_file())
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o400)
                self.assertEqual(output.read_text(), "")
                self.assertFalse(os.access(output, os.W_OK))
                substituted = script.replace(command, f"'{sys.executable}' -I -B -c 'raise SystemExit({status})'")
                child = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", substituted],
                                       env={"PATH": os.defpath, "GITHUB_OUTPUT": str(output)},
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                self.assertEqual(child.returncode, 3)
                self.assertEqual(output.read_text(), "")
                self.assertEqual(child.stdout, "")
                self.assertEqual(child.stderr, "")

    def test_real_outer_timeout_does_not_mark_durable_report_uploadable(self):
        script = self.workflow()["jobs"]["readiness"]["steps"][2]["run"]
        command = "timeout --signal=TERM --kill-after=5s 75s python3 -I -B scripts/cloudflare-readiness.py"
        self.assertEqual(script.count(command), 1)
        with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as base:
            driver = Path(base) / "synthetic-delayed-exit.py"
            driver.write_text(
                "import importlib.util,io,json,os,time\n"
                + "spec=importlib.util.spec_from_file_location('probe'," + repr(str(SCRIPT)) + ")\n"
                + "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
                + "bodies=" + repr([deployments_page(), versions_page(), domains_page(), deployments_page()]) + "\n"
                + "def transport(*args):\n    return 200,{'Content-Type':'application/json'},json.dumps(bodies.pop(0)).encode()\n"
                + "env=" + repr(environment()) + "\n"
                + "env['RUNNER_TEMP']=os.environ['RUNNER_TEMP']\n"
                + "status=module.main(argv=[],environ=env,transport=transport,stdout=io.StringIO())\n"
                + "assert status==0\ntime.sleep(2)\nraise SystemExit(status)\n")
            output = Path(base) / "step-output"
            substituted = script.replace(command, 'timeout --signal=TERM --kill-after=0.1s 0.4s '
                                         + f"'{sys.executable}' -I -B \"$SYNTHETIC_DRIVER\"")
            child = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", substituted],
                                   env={"PATH": os.defpath, "RUNNER_TEMP": base, "GITHUB_OUTPUT": str(output),
                                        "SYNTHETIC_DRIVER": str(driver)},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4)
            self.assertEqual(child.returncode, 124)
            self.assertEqual(json.loads((Path(base) / "cloudflare-readiness/result.json").read_text())["status"],
                             "METADATA_VERIFIED")
            self.assertFalse(output.exists())
            self.assertEqual(child.stdout, "")
            self.assertEqual(child.stderr, "")

    def test_distribution_contains_only_explicit_code_and_minimal_documentation(self):
        paths = []
        for directory, names, files in os.walk(ROOT, followlinks=False):
            names[:] = [name for name in names if not (Path(directory) == ROOT and name == ".git")]
            for name in names + files:
                self.assertFalse((Path(directory) / name).is_symlink())
            paths.extend(str((Path(directory) / f).relative_to(ROOT)) for f in files)
        self.assertEqual(sorted(paths), sorted([".github/workflows/cloudflare-readiness.yml", "README.md",
                                               "scripts/cloudflare-readiness.py", "test/test_cloudflare_readiness.py"]))
        readme = (ROOT / "README.md").read_text()
        for required in ("METADATA_VERIFIED", "NOT_GRANTED", "34f440fe0c275c177add4ca678d4900450725641",
                         "555a616cfa4bb826fbfd2b60e0ee2b15d30c866e", "DOMAIN_NOT_FOUND",
                         "PAGINATION_UNVERIFIED", "NOT_TESTED", "CF_READINESS_DIAGNOSTICS=1",
                         "16384", "256 bytes", "diagnostics", "http_parse", "schema_unsupported"):
            self.assertIn(required, readme)


if __name__ == "__main__":
    unittest.main()
