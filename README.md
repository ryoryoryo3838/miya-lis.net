# Cloudflare readiness — offline header-compatibility candidate

**Independent source review and separately authorized push are still required.** Only code/synthetic fixtures belong here; no site build, deployment, vault, real content, assets, compiler, credential cache or credential retrieval.

## Identity ≠ live evidence

The infrastructure audit observed default `miya` revision `34f440fe0c275c177add4ca678d4900450725641` and separately reviewed local site revision `555a616cfa4bb826fbfd2b60e0ee2b15d30c866e`. Both configurations name Worker **`miya-lis-forest`**, hostname **`miya-lis.net`**. These are repository facts, not an authenticated account/domain/deployment association. The old config is assets-only; the probe does not read code/settings/version resources/secret bindings to prove that model. Unsupported legacy responses stay partial.

Never check out the default branch: its tree/history contains tracked local state and legacy/private content. This four-file candidate derives from the frozen non-Git `cloudflare-diagnostic-fix-cycle1` source inventory, corresponding to the diagnostic publication at `a98fb78f4d1fb624f0b5b46390dee447e0f15ef5` (original parentless code revision `b5dfda97e1b4d1c5a3e8f3486699385d5044a584`). The parent owns independent review, cold Git-copy rehearsal, exact-tree verification and any separately authorized publication. This header candidate has not been committed, published, hosted or probed against live Cloudflare; the diagnostic publication and old evidence are unchanged.

## Exact read contract

Only HTTPS `GET` to `api.cloudflare.com:443`, under `/client/v4/accounts/{validated_account_id}`:

- `/workers/scripts/miya-lis-forest/deployments?page=N&per_page=20`: latest active first; preserve returned deployment/version IDs and traffic percentages.
- `/workers/scripts/miya-lis-forest/versions?deployable=true`: documented deployable set, which ignores pagination.
- `/workers/domains?hostname=miya-lis.net`: exactly one record must match this hostname, Worker and `production` environment.
- Re-read deployment page 1; validate page identity, count, totals and existing pagination budgets, including consistency with the observed history, **before** comparing active state. Missing optional metadata still refuses conservatively; this does not refetch history, expand the request budget or claim an atomic resource snapshot.

Rollback candidates are observed historical-deployment version IDs ∩ deployable IDs, excluding active versions. Current IDs must also be deployable. Never-deployed uploads are not candidates. `CANDIDATES_OBSERVED` proves metadata eligibility only: rollback execution stays `NOT_TESTED`; resource/binding compatibility, content safety and actual rollback remain unverified. `METADATA_VERIFIED` is **not production readiness**; `deployment_approval` always stays `NOT_GRANTED`.

Unknown schema, insufficient authorization, invalid IDs/traffic totals, missing rollback evidence and ambiguous/incomplete pagination fail closed with constant codes. `DOMAIN_NOT_FOUND` may mean route-only hosting: there is no automatic zone/route/service/environment fallback. `PAGINATION_UNVERIFIED` includes absent deployment pagination metadata or ambiguous totals; optional metadata for nonpaginated reads must also be consistent. Too much history is partial, not silently truncated.

## Safety and bounds

- Python stdlib, Linux/POSIX. Account ID is exactly 32 hex characters without trimming/normalization; nonempty ASCII bearer token, ≤4096 characters, no controls. No credential values/hashes, emails, paths, raw responses/errors, arbitrary keys, argv or environment are emitted.
- ≤8 requests; ≤5 pages/100 deployments; ≤10 versions/deployment; ≤100 deployable versions; one exact domain. Percentages 0.01–100 must sum exactly using Decimal; unsupported precision (over 16 digits/exponent outside -12…3 or inexact JSON representation) refuses rather than rounds.
- ≤256 KiB/response, ≤1 MiB aggregate body bytes; bounded initial headers; strict UTF-8 JSON, duplicate/nonfinite rejection, no compression. Any `Transfer-Encoding` header (including empty, duplicate or mixed-case fields) is unsupported and refused as `RESPONSE_INVALID` **before body reads**, so chunk extensions/trailers cannot bypass those counters. Ordinary bounded JSON with `Content-Length` remains supported. This is a conservative framing compatibility limit, not evidence of invalid credentials. No redirects/error-body reads, retries, proxy/CA environment override, caller URLs or endpoint/file/token CLI options.
- Socket/process timer ≤5 seconds/request; 60-second overall process/monotonic deadline. Workflow outer timeout 75 seconds plus bounded kill grace, job limit 5 minutes.
- CLI accepts **no arguments**. Before credentials/network, exclusively reserve `$RUNNER_TEMP/cloudflare-readiness/result.json`: existing UID-owned, non-group/other-writable, symlink/dot-traversal-free temp base; fresh 0700 directory and 0600 regular file. Never delete/overwrite stale paths. Held descriptors, pre/post namespace/ownership/link/mode checks, fsync and byte readback guard the write. This is not an atomic-defense claim against a hostile concurrent same-UID process.
- Stdout is one closed-shape sanitized JSON record. Exit **0** = metadata verified + durable report; **2** = refusal/partial + durable report; both require exact file/stdout byte consistency. Exit **3**/timeout is not uploadable: as in the baseline, a late guard-exit deadline or close failure can leave already-written file bytes different from the refusal stdout. The workflow uploads the **one exact sanitized file** only after 0/2 **and a successful artifact-marker append**; a failed `$GITHUB_OUTPUT` append exits 3 without a marker or raw path/error diagnostics. A successful append preserves probe exit 2; 1/3/124/137 never append a marker. The final gate fails the job for every nonzero probe-step verdict.

## Opt-in closed observation (not a compatibility fix)

Only the exact string `CF_READINESS_DIAGNOSTICS=1` enables observation. Without it, the probe retains the original nine report keys, stdout serialization, exit codes and fail-closed decisions. Only the workflow's probe step sets this flag; the offline-test step still has no credentials or diagnostic opt-in. No request, timeout, header/body/page/record cap, endpoint, schema, pagination, active-state/domain/rollback check or output/upload gate is relaxed or retried.

When `probe` runs with that flag, the same report gains an optional `diagnostics` list (empty if no observation was available). Its closed record shape is:

```json
{"phase":"framing","event":"transfer_encoding","status":"200","transfer_encoding":"chunked"}
```

- Required `phase`: `http`, `headers`, `framing`, `body`, `json`, `schema`, `other`.
- Required `event`, grouped by boundary:
  - HTTP: `status`, `response_shape`.
  - Headers: `http_parse`, `header_count`, `header_shape`, `header_budget`, `content_type_missing`, `content_type_other`, `content_encoding_unsupported`.
  - Framing: `transfer_encoding`, `length_invalid`, `length_limit`.
  - Body: `read_error`, `body_type`, `body_limit`, `total_body_limit`, `length_mismatch`.
  - JSON: `utf8_invalid`, `json_invalid`, `object_required` (syntax, duplicate members, nonfinite values and BOM stay rejected, without keys/prefixes/errors).
  - Schema: `api_unsuccessful`, `result_missing`, `schema_unsupported`; fallback: `other`.
- Optional `status`: only `200`, `401`, `403`, `3xx`, `other`, `invalid`; omitted when no code was observed. Non-integer status values map to `invalid`, never a dynamic type name. A status class is not proof of usable credentials, complete metadata or production readiness.
- Optional `transfer_encoding`: only `none`, `chunked`, `other`, `duplicate`, `empty`. Emitted only at the existing transfer-encoding refusal; other rejections do not imply absence. A duplicate transfer field is observed at the existing header-duplicate rejection. Any transfer field still refuses **before reading the body**. No raw header names/values are recorded. Content-type/encoding distinctions are the fixed rejection events above, not separate raw fields.

Unknown classifications map to closed `other`/`invalid` constants. No response payload, prefix, arbitrary JSON key, exception text/repr, environment/argv/path/account/token/hash/secret length or dynamic type is recorded. Only the original sanitized report core can contain the already-validated metadata identifiers. These are per-invocation observations, not a global log or an alternative HTTP parser.

Before final report attachment, an independent trusted snapshot accepts only exact built-in lists/dicts/strings, the fixed keys and enums above, and creates a new list and new record dicts. Collector-owned mutable containers are never attached directly. Invalid records are dropped, with independent ceilings of **64 records**, **16384 serialized ASCII bytes** including brackets/commas, and **256 bytes per record** (compact JSON); lower configured limits still apply. The list remains inside the unchanged 256 KiB whole-report limit. If a record call fails, the collector is disabled and all its state (including partial mutation) is discarded. Ordinary snapshot/diagnostic-serialization failure drops only the optional observations, leaving an empty list and preserving the primary verdict and the 0/2 durable/stdout contract. Genuine process deadlines still propagate and actual output I/O failures still refuse with exit 3; cleanup and default-off behavior are unchanged. These guarantees cover the scoped collector-replacement/append-then-raise fault fixtures, not unrestricted arbitrary code execution, and do not demonstrate a remote-response exploit against the ordinary collector. Missing observations prove nothing. Invocation/output failures can omit the optional field and remain non-uploadable under the original rules.

The prior hosted run `38698902153` remains failed with sanitized `PARTIAL/RESPONSE_INVALID`; its actual HTTP/format subcause and real credential validity are **unknown**. Synthetic classification tests do not establish transfer framing, header, authorization or other causes for that run, and are not a readiness success. Independent review and parent-owned authorization/accounting are still required before any additional hosted execution; this implementation performs none.

## Workflow / offline tests

Push-only branch `ci/cloudflare-readiness-20261015-142216`, exact repository/event/ref/SHA/deletion guards. Checkout `github.sha` only, pinned action, depth 1, no persisted credentials/submodules/LFS; `contents: read`, explicit non-cancelling concurrency. Only the probe step receives the two existing Cloudflare GitHub Secrets. The upload-artifact pin was read from the reviewed site's `synthetic-dry-run.yml:155`. No content token, build/cache/deploy job or package installation.

With an owned `RUNNER_TEMP`, run:

```sh
python3 -I -B -m unittest discover -s test -p 'test_cloudflare_readiness.py' -v
```

Tests use synthetic credentials/injected transports and block outbound socket creation. Child CLI environments contain no credentials. Keep logs outside source. The workflow is JSON syntax (a YAML subset), allowing stdlib-only guard tests. Distribution inventory permits only this README, probe, test and workflow; Git metadata is excluded.

## Bounded offline header compatibility

The latest sanitized hosted receipt, run `38714994080`, remains failed: `PARTIAL/RESPONSE_INVALID`, with exactly one observation `{"event":"header_shape","phase":"headers","status":"200"}` and no `http/status` observation. In the frozen source, the early `_https_get` pair check can produce that sequence for a repeated non-transfer field or a non-string pair. The later `_response` value/control check first emits `http/status`, so it does not explain that exact sequence under the ordinary collector. The stdlib parser normally returns string pairs and preserves repeated fields. No raw hosted headers were captured: the actual field name, value, framing, credential validity and incident cause remain unknown. An earlier repeated field may mask later framing headers; the receipt does not prove that transfer encoding was absent.

In-memory `HTTPResponse`/socket fixtures reproduce a specific compatibility defect: ordinary repeated **`Set-Cookie`** fields, valid as separate fields (RFC 9110 §5.3), were refused solely because they repeat. The sole exception now permits only that unused, opaque field to repeat, case-insensitively. It never comma-combines cookies, installs a cookie jar, forwards a cookie, interprets its value or adds header telemetry. The first value is retained only for the unchanged second-stage validator; every later occurrence is type/value/control checked before being discarded. A malformed first value still fails the second validator rather than being replaced by a valid later value. HTAB/control refusal is deliberately unchanged.

All occurrences, including discarded repeats, count toward the existing **40 initial fields**, **16384 aggregate name/value bytes** and **4096 bytes per value** ceilings. The stdlib's Latin-1 header decoding gives one character per header byte. `Content-Type`, `Content-Length`, `Content-Encoding` and every other field remain singleton-only; unknown repeated metadata is still conservatively refused. Any `Transfer-Encoding`, including duplicates/empty/mixed-case fields, remains unsupported and refused before body reads. No framing/trailer, deadline, pagination, collector, auth/endpoint, output-marker or workflow rule changes. The workflow file remains byte-identical to the frozen baseline.

This is a **synthetically established parser-compatibility correction only**, not an established repair of the hosted incident, not hosted readiness success and not authorization for another hosted attempt. Independent read-only source review is pending. Local baseline/regression logs, exact RED/GREEN source manifests, static scans and diff are stored separately in `cloudflare-header-compat-cycle1-evidence`; no extra files belong in this four-file distribution.

## Official sources (retrieved before the original implementation; not fetched in this offline cycle)

- [Deployments: schema, pagination, latest active first](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/)
- [Versions: result.items and deployable filter](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/list/)
- [Domains: hostname/service/environment association; no documented page query](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/)
- [Rollback limits and binding constraints](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)
- [Deployment management / last-100-uploaded-version limit](https://developers.cloudflare.com/workers/versions-and-deployments/deployment-management/)
