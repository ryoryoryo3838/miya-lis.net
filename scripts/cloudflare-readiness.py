"""Read-only, source-free metadata probe for one existing Cloudflare Worker."""
import http.client
import json
import os
import stat
import sys
import re
import time
import signal
import ssl
from contextlib import contextmanager
from decimal import Decimal

WORKER = "miya-lis-forest"
HOSTNAME = "miya-lis.net"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 1024 * 1024
MAX_CHUNKS = 4096
MAX_PAGES = 5
MAX_REQUESTS = 8
TOTAL_SECONDS = 60
MAX_DIAGNOSTIC_RECORDS = 64
MAX_DIAGNOSTIC_BYTES = 16384
MAX_DIAGNOSTIC_RECORD_BYTES = 256
PAGINATION_FIELDS = frozenset({"result_info", "page", "total_pages", "count", "total_count", "per_page"})
PAGINATION_RELATIONS = frozenset({"missing", "type", "lower", "higher"})
API_ENVELOPES = frozenset({"success_false_errors", "success_false_empty", "success_true_errors",
                           "success_missing", "success_other", "success_false_null", "errors_invalid"})
CODES = frozenset({"ACCOUNT_INVALID", "AUTH_INVALID", "AUTH_UNAUTHORIZED", "AUTH_FORBIDDEN",
                   "REDIRECT_REFUSED", "HTTP_REFUSED", "TRANSPORT_REFUSED", "RESPONSE_INVALID",
                   "RESPONSE_TOO_LARGE", "API_UNSUCCESSFUL", "SCHEMA_UNSUPPORTED", "METADATA_VERIFIED",
                   "INTERNAL_REFUSED", "IDENTIFIER_INVALID", "DOMAIN_MISMATCH", "DOMAIN_NOT_FOUND",
                   "DOMAIN_AMBIGUOUS", "PAGINATION_UNVERIFIED", "ACTIVE_VERSION_UNAVAILABLE",
                   "ROLLBACK_NOT_OBSERVED", "VERSIONS_UNAVAILABLE", "SNAPSHOT_CHANGED",
                   "PAGINATION_LIMIT", "RECORD_LIMIT", "REQUEST_LIMIT", "TOTAL_RESPONSE_LIMIT",
                   "DEADLINE_EXCEEDED", "OUTPUT_REFUSED", "INVOCATION_REFUSED", "INTERRUPTED"})


class _Failure(Exception):
    def __init__(self, code, **classes):
        super().__init__()
        self.code = code if code in CODES else "INTERNAL_REFUSED"
        self.classes = classes  # Closed diagnostic classes only, observed by probe().


def _status_class(status):
    if type(status) is not int:
        return "invalid"
    if status in (200, 401, 403):
        return {200: "200", 401: "401", 403: "403"}[status]
    return "3xx" if 300 <= status < 400 else "other"


class _Diagnostics:
    """Per-probe, closed classifications; never retain an API value."""
    def __init__(self):
        self.records = []
        self.bytes = 2  # The serialized list's brackets; commas counted per append.

    def record(self, phase, event, *, status=None, transfer_encoding=None, api_envelope=None,
               api_error_code=None, pagination_field=None, pagination_relation=None):
        if len(self.records) >= MAX_DIAGNOSTIC_RECORDS:
            return
        record = {"phase": phase if type(phase) is str and phase in {
                      "http", "headers", "framing", "body", "json", "schema"} else "other",
                  "event": event if type(event) is str and event in {
                      "status", "header_shape", "transfer_encoding", "header_count", "header_budget",
                      "content_type_missing", "content_type_other", "content_encoding_unsupported",
                      "length_invalid", "length_limit", "length_mismatch", "body_limit",
                      "utf8_invalid", "json_invalid", "object_required", "api_unsuccessful",
                      "result_missing", "schema_unsupported", "http_parse", "read_error",
                      "body_type", "total_body_limit", "response_shape",
                      "pagination_unverified"} else "other"}
        if status is not None:
            record["status"] = status if type(status) is str and status in {
                "200", "401", "403", "3xx", "other", "invalid"} else "invalid"
        if transfer_encoding is not None:
            record["transfer_encoding"] = transfer_encoding if type(transfer_encoding) is str and transfer_encoding in {
                "none", "chunked", "other", "duplicate", "empty"} else "other"
        if api_envelope is not None:
            record["api_envelope"] = api_envelope if type(api_envelope) is str and api_envelope in API_ENVELOPES \
                else "other"
        if pagination_field is not None:
            record["pagination_field"] = pagination_field if type(pagination_field) is str \
                and pagination_field in PAGINATION_FIELDS else "other"
        if pagination_relation is not None:
            record["pagination_relation"] = pagination_relation if type(pagination_relation) is str \
                and pagination_relation in PAGINATION_RELATIONS else "other"
        if api_error_code is not None:
            record["api_error_code"] = api_error_code if type(api_error_code) is str and re.fullmatch(
                r"[1-9][0-9]{3,4}", api_error_code) else "other"
        size = len(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii"))
        total = self.bytes + size + bool(self.records)
        if size > MAX_DIAGNOSTIC_RECORD_BYTES or total > MAX_DIAGNOSTIC_BYTES:
            return
        self.records.append(record)
        self.bytes = total


def _diagnostic_snapshot(diagnostics):
    """Only detached, independently validated observations may enter a report."""
    try:
        if diagnostics is None or diagnostics[0] is None:
            return []
        records = diagnostics[0].records
        if type(records) is not list:
            return []
        allowed = {
            "phase": {"http", "headers", "framing", "body", "json", "schema", "other"},
            "event": {"status", "header_shape", "transfer_encoding", "header_count", "header_budget",
                      "content_type_missing", "content_type_other", "content_encoding_unsupported",
                      "length_invalid", "length_limit", "length_mismatch", "body_limit",
                      "utf8_invalid", "json_invalid", "object_required", "api_unsuccessful",
                      "result_missing", "schema_unsupported", "http_parse", "read_error",
                      "body_type", "total_body_limit", "response_shape", "pagination_unverified",
                      "other"},
            "status": {"200", "401", "403", "3xx", "other", "invalid"},
            "transfer_encoding": {"none", "chunked", "other", "duplicate", "empty"},
            "api_envelope": API_ENVELOPES | {"other"},
            "pagination_field": PAGINATION_FIELDS | {"other"},
            "pagination_relation": PAGINATION_RELATIONS | {"other"}}
        snapshot, total = [], 2
        for record in records[:min(64, MAX_DIAGNOSTIC_RECORDS)]:
            if type(record) is not dict or not 2 <= len(record) <= 5:
                continue
            clean = {}
            for key, value in record.items():
                if (type(key) is not str or type(value) is not str or len(value) > 32
                        or key not in allowed and key != "api_error_code"
                        or key in allowed and value not in allowed[key]
                        or key == "api_error_code" and value != "other"
                        and not re.fullmatch(r"[1-9][0-9]{3,4}", value)):
                    break
                clean[key] = value
            else:
                if not {"phase", "event"} <= clean.keys():
                    continue
                size = len(json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii"))
                budget = total + size + bool(snapshot)
                if size > min(256, MAX_DIAGNOSTIC_RECORD_BYTES) or budget > min(16384, MAX_DIAGNOSTIC_BYTES):
                    continue
                snapshot.append(clean)
                total = budget
        return snapshot
    except _Failure as failure:
        if failure.code == "DEADLINE_EXCEEDED":
            raise
    except Exception:
        pass  # Discard optional observations, never serialize their raw contents.
    return []


def _observe(diagnostics, phase, event, **classes):
    if diagnostics is not None and diagnostics[0] is not None:
        try:
            diagnostics[0].record(phase, event, **classes)
        except _Failure as failure:
            if failure.code == "DEADLINE_EXCEEDED":
                raise  # Instrumentation must not swallow the process timer.
            diagnostics[0] = None
        except Exception:
            diagnostics[0] = None  # Drop all state, including a failed record's partial mutation.


def _alarm(_signum, _frame):
    raise _Failure("DEADLINE_EXCEEDED")


@contextmanager
def _deadline_guard(seconds):
    """POSIX process timer, including blocking DNS/TLS/response reads; no retries."""
    started = time.monotonic()
    previous = signal.getsignal(signal.SIGALRM)
    old_delay, old_interval = signal.getitimer(signal.ITIMER_REAL)
    if seconds <= 0 or old_interval:
        raise _Failure("DEADLINE_EXCEEDED")
    delay = min(seconds, old_delay) if old_delay else seconds
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, delay)
    try:
        yield
        if time.monotonic() - started >= delay:
            raise _Failure("DEADLINE_EXCEEDED")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        remaining = old_delay - (time.monotonic() - started)
        if old_delay and remaining > 0:
            signal.setitimer(signal.ITIMER_REAL, remaining)


def _https_get(path, authorization, timeout, *, diagnostics=None):
    """Only three fixed API reads. http.client neither uses proxies nor follows redirects."""
    pattern = (r"/client/v4/accounts/[a-fA-F0-9]{32}/workers/(?:scripts/miya-lis-forest/"
               r"(?:deployments\?page=[1-5]&per_page=20|versions\?deployable=true)"
               r"|domains\?hostname=miya-lis\.net)")
    if not isinstance(path, str) or not re.fullmatch(pattern, path):
        raise _Failure("HTTP_REFUSED")
    if (not isinstance(authorization, str) or not authorization.startswith("Bearer ")
            or not 1 <= len(authorization[7:]) <= 4096
            or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", authorization[7:])):
        raise _Failure("AUTH_INVALID")
    if type(timeout) not in (int, float) or not 0 < timeout <= 5:
        raise _Failure("DEADLINE_EXCEEDED")
    with _deadline_guard(timeout):
        # Use the compiled system trust locations, NOT SSL_CERT_FILE/SSL_CERT_DIR overrides.
        paths = ssl.get_default_verify_paths()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=paths.openssl_cafile, capath=paths.openssl_capath)
        connection = http.client.HTTPSConnection("api.cloudflare.com", port=443, timeout=timeout, context=context)
        try:
            connection.request("GET", path, headers={"Authorization": authorization,
                               "Accept": "application/json", "Accept-Encoding": "identity",
                               "User-Agent": "miya-lis-readiness/1"})
            try:
                response = connection.getresponse()
            except http.client.HTTPException:
                _observe(diagnostics, "headers", "http_parse")
                raise
            if response.status != 200:
                return response.status, {}, b""  # Never read error bodies or redirect locations.
            pairs = response.getheaders()
            if len(pairs) > 40:
                _observe(diagnostics, "headers", "header_count", status="200")
                raise _Failure("RESPONSE_INVALID")
            headers, header_size = {}, 0
            for key, value in pairs:
                if (not isinstance(key, str) or not isinstance(value, str)
                        or (key.lower() in headers and key.lower() != "set-cookie")):
                    if isinstance(key, str) and key.lower() == "transfer-encoding" and key.lower() in headers:
                        _observe(diagnostics, "headers", "header_shape", status="200", transfer_encoding="duplicate")
                    else:
                        _observe(diagnostics, "headers", "header_shape", status="200")
                    raise _Failure("RESPONSE_INVALID")
                header_size += len(key) + len(value)
                if header_size > 16384 or len(value) > 4096:
                    _observe(diagnostics, "headers", "header_budget", status="200")
                    raise _Failure("RESPONSE_INVALID")
                if key.lower() in headers:
                    # Only opaque Set-Cookie repeats reach here; count and validate each before discarding.
                    if any(ord(c) < 32 or ord(c) == 127 for c in value):
                        _observe(diagnostics, "headers", "header_shape", status="200")
                        raise _Failure("RESPONSE_INVALID")
                    continue  # Keep the first value for the unchanged second-stage validator, never combine.
                headers[key.lower()] = value
            # Only a lone "chunked" coding without Content-Length is decoded, by _chunked_body below.
            chunked = False
            if "transfer-encoding" in headers:
                value = headers["transfer-encoding"].strip().lower()
                if value != "chunked" or "content-length" in headers:
                    framing = "chunked" if value == "chunked" else "empty" if not value else "other"
                    _observe(diagnostics, "framing", "transfer_encoding", status="200", transfer_encoding=framing)
                    raise _Failure("RESPONSE_INVALID")
                chunked = True
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                _observe(diagnostics, "headers", "content_type_other" if "content-type" in headers
                         else "content_type_missing", status="200")
                raise _Failure("RESPONSE_INVALID")
            if headers.get("content-encoding", "identity").lower() != "identity":
                _observe(diagnostics, "headers", "content_encoding_unsupported", status="200")
                raise _Failure("RESPONSE_INVALID")
            length = headers.get("content-length")
            if length is not None:
                if not re.fullmatch(r"[0-9]{1,10}", length):
                    _observe(diagnostics, "framing", "length_invalid", status="200")
                    raise _Failure("RESPONSE_INVALID")
                if int(length) > MAX_RESPONSE_BYTES:
                    _observe(diagnostics, "framing", "length_limit", status="200")
                    raise _Failure("RESPONSE_TOO_LARGE")
            try:
                body = (_chunked_body(response.fp, diagnostics) if chunked
                        else response.read(MAX_RESPONSE_BYTES + 1))
            except _Failure:
                raise
            except Exception:
                _observe(diagnostics, "body", "read_error", status="200")
                raise
            return response.status, headers, body
        finally:
            connection.close()


def _chunked_body(stream, diagnostics):
    """Decode chunked framing from the raw stream; extensions and trailers are refused, not skipped."""
    body = b""
    for _ in range(MAX_CHUNKS):
        line = stream.readline(11)
        if not re.fullmatch(rb"[0-9A-Fa-f]{1,8}\r\n", line):
            _observe(diagnostics, "framing", "length_invalid", status="200")
            raise _Failure("RESPONSE_INVALID")
        size = int(line[:-2], 16)
        if size == 0:
            if stream.readline(3) != b"\r\n":
                _observe(diagnostics, "framing", "length_invalid", status="200")
                raise _Failure("RESPONSE_INVALID")
            return body
        if len(body) + size > MAX_RESPONSE_BYTES:
            _observe(diagnostics, "body", "body_limit", status="200")
            raise _Failure("RESPONSE_TOO_LARGE")
        data = stream.read(size + 2)
        if len(data) != size + 2 or data[-2:] != b"\r\n":
            _observe(diagnostics, "body", "length_mismatch", status="200")
            raise _Failure("RESPONSE_INVALID")
        body += data[:-2]
    _observe(diagnostics, "framing", "length_limit", status="200")
    raise _Failure("RESPONSE_INVALID")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _Failure("RESPONSE_INVALID")
        result[key] = value
    return result


def _nonfinite(_value):
    raise _Failure("RESPONSE_INVALID")


def _envelope_classes(data):
    """Closed shape of an unsuccessful envelope; only a public numeric error code is kept."""
    success, errors = data.get("success", None), data.get("errors", [])
    if "success" not in data:
        envelope = "success_missing"
    elif type(success) is not bool:
        envelope = "success_other"
    elif errors is None and not success:
        envelope = "success_false_null"
    elif type(errors) is not list:
        envelope = "errors_invalid"
    elif success:
        envelope = "success_true_errors"
    else:
        envelope = "success_false_errors" if errors else "success_false_empty"
    classes = {"api_envelope": envelope}
    if type(errors) is list and errors:
        code = errors[0].get("code") if type(errors[0]) is dict else None
        classes["api_error_code"] = str(code) if type(code) is int and 1000 <= code <= 99999 else "other"
    return classes


def _response(status, headers, body, *, diagnostics=None):
    _observe(diagnostics, "http", "status", status=_status_class(status))
    if type(status) is not int:
        raise _Failure("RESPONSE_INVALID")
    if 300 <= status < 400:
        raise _Failure("REDIRECT_REFUSED")
    if status == 401:
        raise _Failure("AUTH_UNAUTHORIZED")
    if status == 403:
        raise _Failure("AUTH_FORBIDDEN")
    if status != 200:
        raise _Failure("HTTP_REFUSED")
    phase, event, classes = "headers", "header_shape", {}
    try:
        lowered = {}
        for key, value in headers.items():
            if (not isinstance(key, str) or not isinstance(value, str)
                    or len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value)
                    or key.lower() in lowered):
                raise _Failure("RESPONSE_INVALID")
            lowered[key.lower()] = value
        event = "content_type_other" if "content-type" in lowered else "content_type_missing"
        if lowered.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise _Failure("RESPONSE_INVALID")
        event = "content_encoding_unsupported"
        if lowered.get("content-encoding", "identity").lower() != "identity":
            raise _Failure("RESPONSE_INVALID")
        phase, event = "framing", "length_invalid"
        length = lowered.get("content-length")
        if length is not None:
            if not re.fullmatch(r"[0-9]{1,10}", length):
                raise _Failure("RESPONSE_INVALID")
            event = "length_limit"
            if int(length) > MAX_RESPONSE_BYTES:
                raise _Failure("RESPONSE_TOO_LARGE")
        phase, event = "body", "body_type"
        if not isinstance(body, bytes):
            raise _Failure("RESPONSE_INVALID")
        event = "body_limit"
        if len(body) > MAX_RESPONSE_BYTES:
            raise _Failure("RESPONSE_TOO_LARGE")
        event = "length_mismatch"
        if length is not None and int(length) != len(body):
            raise _Failure("RESPONSE_INVALID")
        phase, event = "json", "utf8_invalid"
        text = body.decode("utf-8")
        event = "json_invalid"
        data = json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_nonfinite, parse_float=Decimal)
        event = "object_required"
        if not isinstance(data, dict):
            raise _Failure("RESPONSE_INVALID")
        phase, event = "schema", "api_unsuccessful"
        # The versions API reports success with "errors": null rather than an empty list.
        errors = data.get("errors", [])
        if data.get("success") is not True or not (errors is None or type(errors) is list and not errors):
            classes = _envelope_classes(data)
            raise _Failure("API_UNSUCCESSFUL")
        event = "result_missing"
        if "result" not in data:
            raise _Failure("SCHEMA_UNSUPPORTED")
        return data
    except _Failure:
        _observe(diagnostics, phase, event, status="200", **classes)
        raise
    except Exception:
        _observe(diagnostics, phase, event, status="200")
        raise _Failure("RESPONSE_INVALID") from None


def _report():
    return {"schema": "cloudflare-readiness-v1", "status": "REFUSED", "code": "AUTH_INVALID",
            "target": {"worker": WORKER, "hostname": HOSTNAME},
            "active_deployment": None, "deployments": [],
            "domain": {"status": "UNVERIFIED", "id": None},
            "rollback": {"status": "UNVERIFIED", "current_version_ids": [],
                         "prior_version_ids": [], "execution": "NOT_TESTED"},
            "deployment_approval": "NOT_GRANTED"}


def _identifier(value, sensitive, *, domain=False):
    pattern = r"[a-fA-F0-9]{32}" if domain else r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}"
    if (not isinstance(value, str) or not re.fullmatch(pattern, value)
            or any(secret.lower() in value.lower() for secret in sensitive)):
        raise _Failure("IDENTIFIER_INVALID")
    return value


def _deployments(data, sensitive):
    result = data["result"]
    if not isinstance(result, dict) or not isinstance(result.get("deployments"), list):
        raise _Failure("SCHEMA_UNSUPPORTED")
    items = result["deployments"]
    if not 1 <= len(items) <= 20:
        raise _Failure("SCHEMA_UNSUPPORTED")
    selected, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or item.get("strategy") != "percentage":
            raise _Failure("SCHEMA_UNSUPPORTED")
        identifier = _identifier(item.get("id"), sensitive)
        if identifier.lower() in seen:
            raise _Failure("SCHEMA_UNSUPPORTED")
        seen.add(identifier.lower())
        versions = item.get("versions")
        if not isinstance(versions, list) or not 1 <= len(versions) <= 10:
            raise _Failure("SCHEMA_UNSUPPORTED")
        clean, version_ids, percentages = [], set(), []
        for version in versions:
            if not isinstance(version, dict):
                raise _Failure("SCHEMA_UNSUPPORTED")
            vid = _identifier(version.get("version_id"), sensitive)
            percentage = version.get("percentage")
            if type(percentage) not in (int, Decimal):
                raise _Failure("SCHEMA_UNSUPPORTED")
            percentage = Decimal(percentage)
            if (not percentage.is_finite() or not Decimal("0.01") <= percentage <= 100
                    or len(percentage.as_tuple().digits) > 16
                    or not -12 <= percentage.as_tuple().exponent <= 3
                    or Decimal(str(float(percentage))) != percentage
                    or vid.lower() in version_ids):
                raise _Failure("SCHEMA_UNSUPPORTED")
            version_ids.add(vid.lower())
            percentages.append(percentage)
            clean.append({"id": vid, "percentage": int(percentage) if percentage == int(percentage)
                          else float(percentage)})
        if sum(percentages) != 100:
            raise _Failure("SCHEMA_UNSUPPORTED")
        selected.append({"id": identifier, "versions": clean})
    return selected


def _pagination_refusal(field, value, expected):
    relation = ("missing" if value is _ABSENT else "type" if type(value) is not int
                else "lower" if value < expected else "higher")
    return _Failure("PAGINATION_UNVERIFIED", pagination_field=field, pagination_relation=relation)


_ABSENT = object()


def _nonpaginated(data, size):
    if "result_info" not in data:
        return
    info = data["result_info"]
    if not isinstance(info, dict):
        raise _Failure("PAGINATION_UNVERIFIED", pagination_field="result_info", pagination_relation="type")
    for field in ("page", "total_pages"):
        if type(info.get(field, _ABSENT)) is not int or info[field] != 1:
            raise _pagination_refusal(field, info.get(field, _ABSENT), 1)
    for field in ("count", "total_count"):
        if field in info and (type(info[field]) is not int or info[field] != size):
            raise _pagination_refusal(field, info[field], size)
    if "per_page" in info and (type(info["per_page"]) is not int or info["per_page"] < size):
        raise _pagination_refusal("per_page", info["per_page"], size)


def _eligible(data, sensitive):
    result = data["result"]
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        raise _Failure("SCHEMA_UNSUPPORTED")
    items = result["items"]
    _nonpaginated(data, len(items))
    if not items:
        raise _Failure("VERSIONS_UNAVAILABLE")
    if len(items) > 100:
        raise _Failure("RECORD_LIMIT")
    ids = [_identifier(item.get("id"), sensitive) for item in items if isinstance(item, dict)]
    if len(ids) != len(items) or len({v.lower() for v in ids}) != len(ids):
        raise _Failure("SCHEMA_UNSUPPORTED")
    return set(ids)


def _domain(data, sensitive):
    domains = data["result"]
    if not isinstance(domains, list):
        raise _Failure("SCHEMA_UNSUPPORTED")
    _nonpaginated(data, len(domains))
    if not domains:
        raise _Failure("DOMAIN_NOT_FOUND")
    if len(domains) != 1:
        raise _Failure("DOMAIN_AMBIGUOUS")
    item = domains[0]
    if not isinstance(item, dict):
        raise _Failure("SCHEMA_UNSUPPORTED")
    if (item.get("hostname") != HOSTNAME or item.get("service") != WORKER
            or item.get("environment") != "production"):
        raise _Failure("DOMAIN_MISMATCH")
    return {"status": "MATCH", "id": _identifier(item.get("id"), sensitive, domain=True)}


def _pagination(data, page, size):
    info = data.get("result_info")
    fields = ("page", "per_page", "count", "total_pages", "total_count")
    if not isinstance(info, dict) or any(type(info.get(k)) is not int for k in fields):
        raise _Failure("PAGINATION_UNVERIFIED")
    if info["total_pages"] > MAX_PAGES or info["total_count"] > MAX_PAGES * 20:
        raise _Failure("PAGINATION_LIMIT")
    total = info["total_count"]
    if (info["page"] != page or info["per_page"] != 20 or info["count"] != size
            or not 1 <= info["total_pages"] <= MAX_PAGES or total < 1
            or info["total_pages"] != (total + 19) // 20
            or not 1 <= page <= info["total_pages"]
            or size != min(20, total - (page - 1) * 20)):
        raise _Failure("PAGINATION_UNVERIFIED")
    return info["total_pages"], total


class _Reader:
    def __init__(self, account, token, transport, clock, diagnostics=None):
        self.prefix = "/client/v4/accounts/" + account + "/workers/"
        self.authorization = "Bearer " + token
        self.transport = transport
        self.clock = clock
        self.deadline = clock() + TOTAL_SECONDS
        self.requests = 0
        self.bytes = 0
        self.diagnostics = diagnostics

    def remaining(self):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise _Failure("DEADLINE_EXCEEDED")
        return remaining

    def get(self, suffix):
        timeout = min(5, self.remaining())
        if self.requests >= MAX_REQUESTS:
            raise _Failure("REQUEST_LIMIT")
        self.requests += 1
        try:
            response = self.transport(self.prefix + suffix, self.authorization, timeout)
        except _Failure:
            raise
        except Exception:
            raise _Failure("TRANSPORT_REFUSED") from None
        self.remaining()
        if not isinstance(response, tuple) or len(response) != 3:
            _observe(self.diagnostics, "http", "response_shape")
            raise _Failure("RESPONSE_INVALID")
        body = response[2]
        if isinstance(body, bytes):
            if len(body) > MAX_RESPONSE_BYTES:
                _observe(self.diagnostics, "body", "body_limit", status=_status_class(response[0]))
                raise _Failure("RESPONSE_TOO_LARGE")
            self.bytes += len(body)
            if self.bytes > MAX_TOTAL_BYTES:
                _observe(self.diagnostics, "body", "total_body_limit", status=_status_class(response[0]))
                raise _Failure("TOTAL_RESPONSE_LIMIT")
        return _response(*response, diagnostics=self.diagnostics)


def _history(reader, sensitive):
    query = "scripts/" + WORKER + "/deployments?page={}&per_page=20"
    data = reader.get(query.format(1))
    selected = _deployments(data, sensitive)
    pages, total = _pagination(data, 1, len(selected))
    seen = {d["id"].lower() for d in selected}
    for page in range(2, pages + 1):
        data = reader.get(query.format(page))
        batch = _deployments(data, sensitive)
        if _pagination(data, page, len(batch)) != (pages, total):
            raise _Failure("PAGINATION_UNVERIFIED")
        for deployment in batch:
            if deployment["id"].lower() in seen:
                raise _Failure("PAGINATION_UNVERIFIED")
            seen.add(deployment["id"].lower())
        selected.extend(batch)
    if len(selected) != total:
        raise _Failure("PAGINATION_UNVERIFIED")
    return selected


def probe(environ, *, transport=None, clock=None):
    """Return only closed-shape metadata; the transport seam is for offline tests."""
    result = _report()
    diagnostics = None
    if type(environ.get("CF_READINESS_DIAGNOSTICS")) is str and environ.get("CF_READINESS_DIAGNOSTICS") == "1":
        result["diagnostics"] = []
        try:
            diagnostics = [_Diagnostics()]  # Trusted slot: a failed collector cannot re-enable itself.
        except _Failure as failure:
            if failure.code == "DEADLINE_EXCEEDED":
                raise
        except Exception:
            diagnostics = None
    account = environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = environ.get("CLOUDFLARE_API_TOKEN", "")
    if not isinstance(account, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", account):
        result["code"] = "ACCOUNT_INVALID"
        return result
    if (not isinstance(token, str) or not 1 <= len(token) <= 4096
            or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token)):
        return result
    result["status"] = "PARTIAL"
    if transport is None:
        if diagnostics is None:
            transport = _https_get
        else:
            def transport(path, authorization, timeout):
                return _https_get(path, authorization, timeout, diagnostics=diagnostics)
    try:
        sensitive = (account, token)
        reader = _Reader(account, token, transport, clock or time.monotonic, diagnostics)
        get = reader.get
        deployment_query = "scripts/" + WORKER + "/deployments?page=1&per_page=20"
        selected = _history(reader, sensitive)
        result["active_deployment"] = selected[0]
        result["deployments"] = selected
        eligible = _eligible(get("scripts/" + WORKER + "/versions?deployable=true"), sensitive)
        current = [v["id"] for v in selected[0]["versions"]]
        if not set(current) <= eligible:
            raise _Failure("ACTIVE_VERSION_UNAVAILABLE")
        prior = sorted({v["id"] for d in selected[1:] for v in d["versions"]
                        if v["id"] in eligible and v["id"] not in current})
        result["rollback"] = {"status": "CANDIDATES_OBSERVED" if prior else "NONE_OBSERVED",
                              "current_version_ids": current, "prior_version_ids": prior,
                              "execution": "NOT_TESTED"}
        if not prior:
            raise _Failure("ROLLBACK_NOT_OBSERVED")
        result["domain"] = _domain(get("domains?hostname=" + HOSTNAME), sensitive)
        final_data = get(deployment_query)
        final_page = _deployments(final_data, sensitive)
        if _pagination(final_data, 1, len(final_page)) != ((len(selected) + 19) // 20, len(selected)):
            raise _Failure("PAGINATION_UNVERIFIED")
        if final_page[0] != selected[0]:
            raise _Failure("SNAPSHOT_CHANGED")
        result["status"] = "METADATA_VERIFIED"
        result["code"] = "METADATA_VERIFIED"
    except _Failure as failure:
        result["code"] = failure.code
        if failure.code == "PAGINATION_UNVERIFIED" and failure.classes:
            _observe(diagnostics, "schema", "pagination_unverified", **failure.classes)
        if failure.code == "SCHEMA_UNSUPPORTED":
            _observe(diagnostics, "schema", "schema_unsupported")
    except Exception:
        result["code"] = "SCHEMA_UNSUPPORTED"
        _observe(diagnostics, "schema", "schema_unsupported")
    if "diagnostics" in result:
        result["diagnostics"] = _diagnostic_snapshot(diagnostics)
    return result


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _open_directory(path):
    if (not isinstance(path, str) or not 1 < len(path) <= 4096 or not path.startswith("/")
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or any(part in ("", ".", "..") for part in path.split("/")[1:])):
        raise _Failure("OUTPUT_REFUSED")
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in path.split("/")[1:]:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _identity(info):
    return info.st_dev, info.st_ino


class _Output:
    """Exclusive fixed basename, held descriptors, and pre/post namespace checks."""
    def __init__(self, base):
        self.path = base
        self.base = self.directory = self.file = None
        try:
            self.base = _open_directory(base)
            info = os.fstat(self.base)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise _Failure("OUTPUT_REFUSED")
            os.mkdir("cloudflare-readiness", mode=0o700, dir_fd=self.base)
            self.directory = os.open("cloudflare-readiness", _DIRECTORY_FLAGS, dir_fd=self.base)
            os.fchmod(self.directory, 0o700)
            self.file = os.open("result.json", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                0o600, dir_fd=self.directory)
            os.fchmod(self.file, 0o600)
            self.check()
        except BaseException:
            self.close()
            raise _Failure("OUTPUT_REFUSED") from None

    def check(self):
        current = _open_directory(self.path)
        try:
            base_info = os.fstat(current)
            if (_identity(base_info) != _identity(os.fstat(self.base))
                    or base_info.st_uid != os.geteuid() or base_info.st_mode & 0o022):
                raise _Failure("OUTPUT_REFUSED")
        finally:
            os.close(current)
        for name, parent, held, is_directory, mode in (
                ("cloudflare-readiness", self.base, self.directory, True, 0o700),
                ("result.json", self.directory, self.file, False, 0o600)):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            live = os.fstat(held)
            correct_type = stat.S_ISDIR(info.st_mode) if is_directory else stat.S_ISREG(info.st_mode)
            if (not correct_type or _identity(info) != _identity(live)
                    or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != mode
                    or (not is_directory and (info.st_nlink != 1 or live.st_nlink != 1))):
                raise _Failure("OUTPUT_REFUSED")

    def write(self, result, deadline):
        try:
            data = (json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
            if len(data) > MAX_RESPONSE_BYTES:
                raise _Failure("OUTPUT_REFUSED")
            self.check()
            if time.monotonic() >= deadline:
                raise _Failure("DEADLINE_EXCEEDED")
            if os.write(self.file, data) != len(data):
                raise _Failure("OUTPUT_REFUSED")
            os.fsync(self.file)
            os.fsync(self.directory)
            os.fsync(self.base)
            self.check()
            os.lseek(self.file, 0, os.SEEK_SET)
            if os.read(self.file, len(data) + 1) != data:
                raise _Failure("OUTPUT_REFUSED")
        except _Failure:
            raise
        except Exception:
            raise _Failure("OUTPUT_REFUSED") from None

    def close(self):
        failed = False
        for name in ("file", "directory", "base"):
            fd = getattr(self, name)
            if fd is not None:
                setattr(self, name, None)
                try:
                    os.close(fd)
                except OSError:
                    failed = True
        if failed:
            raise _Failure("OUTPUT_REFUSED")


def main(*, argv=None, environ=None, transport=None, stdout=None):
    """No CLI options. Credentials exist only in env; output is a fixed fresh report."""
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    result, output, status = _report(), None, 3
    try:
        if argv:
            raise _Failure("INVOCATION_REFUSED")
        deadline = time.monotonic() + TOTAL_SECONDS
        with _deadline_guard(TOTAL_SECONDS):
            output = _Output(environ.get("RUNNER_TEMP", ""))  # Before credentials or network.
            result = probe(environ, transport=transport)
            output.write(result, deadline)
            status = 0 if result["status"] == "METADATA_VERIFIED" else 2
    except _Failure as failure:
        status = 3
        result = _report()
        result["code"] = failure.code
    except KeyboardInterrupt:
        status = 3
        result = _report()
        result["code"] = "INTERRUPTED"
    except Exception:
        status = 3
        result = _report()
        result["code"] = "INTERNAL_REFUSED"
    finally:
        if output is not None:
            try:
                output.close()
            except Exception:
                result = _report()
                result["code"] = "OUTPUT_REFUSED"
                status = 3
    try:
        text = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        if stdout is None:
            os.write(1, text.encode("ascii"))
        else:
            stdout.write(text)
    except Exception:
        return 3
    return status


if __name__ == "__main__":
    raise SystemExit(main())
