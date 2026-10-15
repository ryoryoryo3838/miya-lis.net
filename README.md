# Cloudflare readiness — source candidate

**Independent source review and separately authorized push are still required.** Only code/synthetic fixtures belong here; no site build, deployment, vault, real content, assets, compiler, credential cache or credential retrieval.

## Identity ≠ live evidence

The infrastructure audit observed default `miya` revision `34f440fe0c275c177add4ca678d4900450725641` and separately reviewed local site revision `555a616cfa4bb826fbfd2b60e0ee2b15d30c866e`. Both configurations name Worker **`miya-lis-forest`**, hostname **`miya-lis.net`**. These are repository facts, not an authenticated account/domain/deployment association. The old config is assets-only; the probe does not read code/settings/version resources/secret bindings to prove that model. Unsupported legacy responses stay partial.

Never check out the default branch: its tree/history contains tracked local state and legacy/private content. The parent must prepare a reviewed parentless commit from the four-file allowlist, without object alternates, and independently authorize the first push. No Git, hosted execution or live Cloudflare probe has been performed for this candidate.

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
- Stdout is one closed-shape sanitized JSON record. Exit **0** = metadata verified + durable report; **2** = refusal/partial + durable report; **3**/timeout = not uploadable, even if a partial file remains. The workflow uploads the **one exact sanitized file** only after 0/2 **and a successful artifact-marker append**; a failed `$GITHUB_OUTPUT` append exits 3 without a marker or raw path/error diagnostics. A successful append preserves probe exit 2; 1/3/124/137 never append a marker. The final gate fails the job for every nonzero probe-step verdict.

## Workflow / offline tests

Push-only branch `ci/cloudflare-readiness-20261015-142216`, exact repository/event/ref/SHA/deletion guards. Checkout `github.sha` only, pinned action, depth 1, no persisted credentials/submodules/LFS; `contents: read`, explicit non-cancelling concurrency. Only the probe step receives the two existing Cloudflare GitHub Secrets. The upload-artifact pin was read from the reviewed site's `synthetic-dry-run.yml:155`. No content token, build/cache/deploy job or package installation.

With an owned `RUNNER_TEMP`, run:

```sh
python3 -I -B -m unittest discover -s test -p 'test_cloudflare_readiness.py' -v
```

Tests use synthetic credentials/injected transports and block outbound socket creation. Child CLI environments contain no credentials. Keep logs outside source. The workflow is JSON syntax (a YAML subset), allowing stdlib-only guard tests. Distribution inventory permits only this README, probe, test and workflow; Git metadata is excluded.

## Official sources (retrieved before implementation)

- [Deployments: schema, pagination, latest active first](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/)
- [Versions: result.items and deployable filter](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/list/)
- [Domains: hostname/service/environment association; no documented page query](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/)
- [Rollback limits and binding constraints](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)
- [Deployment management / last-100-uploaded-version limit](https://developers.cloudflare.com/workers/versions-and-deployments/deployment-management/)
