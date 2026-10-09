# Safe public snapshot build — isolated, build-only

**Status: local gates and pinned native rendering exercised; CI deliberately BLOCKED.**
The JSON-only `tree_of_md` adapter has no reviewed committed full revision/build driver in this change. `.github/safe-web-pins.json` therefore contains `null` converter fields. Both CI preflight and CI build stop with `SW_PIN` before accessing the content repository. This is not a working/green GitHub Actions claim.

## Boundary

- Consume an already reviewed **public-only** snapshot; do not authorize publication here.
- No vault discovery, vault checkout, legacy compile, `publish.from`, attachment copier, raw-content fallback, or publication shorthand changes. `%%p%%` remains **private**.
- Preserve every approved ID and case, and existing routes. IDs are never minted or normalized.
- Do not invoke the old site's `site/build.sh`, existing theme/lock, old deployment workflow, or Wrangler. This path uses the native theme bundled with the independently pinned Forester 6 package.
- The new workflow is manual **build only**. There is no live deploy step or Cloudflare product change. A future reviewed deployment remains Workers + Wrangler 4.

## Snapshot format and approval anchor

A snapshot directory (and the snapshot commit's entire root Git tree) contains **exactly**:

```text
manifest.json
public-forest.json
```

The manifest has no optional keys or arbitrary command/path fields:

```json
{
  "schema": "forester-public-snapshot-v1",
  "files": {
    "public-forest.json": "<64 lowercase hex characters: SHA-256 of exact forest bytes>"
  }
}
```

`SNAPSHOT_SHA256` / `--manifest-sha256` is the SHA-256 of the **exact manifest bytes**, not the forest digest. This external approval anchor authenticates the manifest; the manifest in turn authenticates every allowlisted input. Whitespace changes require a new approval digest. The README-only initial content-repository commit is intentionally not a valid snapshot.

`public-forest.json` uses the `forester-public-v2` wire contract: strict keys/discriminants, named root trees, anonymous/named nested sections, structured transclusions with boolean header/TOC flags, sanitized attribution and metadata, empty assets. Unknown/source keys, duplicate JSON keys, case-fold ID collisions, non-ASCII/path IDs, invalid dates, missing targets and containment/transclusion cycles fail closed. Named descendants are defined inline, not duplicated as root `.tree` files.

The site consumer is a second validation boundary, **not** a replacement for the producer's public projection or the converter's independent Markdown/IR validation. It checks unvetted HTML/raw Forester/assets/file references and declarations **outside recognized literal code/math**, without rewriting the input. Closed backtick/tilde fences, top-level indented code at a block boundary, exact-length inline backtick spans, and closed `$`/`$$` math spans are masked only for this defensive wire check. The internal non-whitespace mask preserves offsets, LF/CRLF, blank lines and token separation; the exact original snapshot bytes reach `tree_of_md`. Inline spans stop at paragraph/block boundaries, and separate Markdown chunks are never joined.

Unclosed/mismatched fences are refused; unmatched inline delimiters cannot shield forbidden syntax. Lone CR and forbidden syntax outside literal spans remain fail-closed. Container-relative list/quote indentation is deliberately not guessed: indented code following a list/quote in the same chunk can still be over-rejected. This is not a full Markdown parser, a third publication/privacy parser, or complete Markdown compatibility. The real converter still parses the original chunks and refuses unsupported or unsafe constructs before tree emission. No actual notes were used in these checks.

Limits: manifest 64 KiB; forest 16 MiB; individual strings 1 MiB of strict UTF-8 encoded bytes (not Unicode codepoints); arrays/trees 20,000; containment depth 64; artifact 128 MiB and 30,000 files. Symlinks in input/output ancestors, symlink/hardlink/special input files, traversal, overlapping namespaces and extra files are refused. Staging and final HTML destinations must not already exist. A replacement/revocation build therefore cannot merge with stale outputs; use a new output directory each time. Existing output directories are preserved on refusal, not recursively deleted.

Oversized strings and non-scalar strings (including escaped lone UTF-16 surrogates in JSON) fail with generic `SW_SCHEMA` before staging is created. Accepted JSON bytes are copied unchanged: this gate does not normalize Unicode, remove a string BOM, repair invalid UTF-8, or rewrite line endings. Existing control-character and lone-CR refusals still apply.

## Local entry points

Run focused tests:

```sh
python3 -m unittest discover -s test -p test_safe_web.py -v
```

Tests use synthetic null-pin fixtures rather than assuming checked-in converter pins remain null. A separate syntax-only ready-pin fixture exercises successful `validate_pins` and `ci-config`; its placeholder revision and build argv are test-only, never real converter provenance or a CI-green claim. Null pins still reject before any content/output arguments are accessed. The test runner reports the current suite count.

Stage a reviewed synthetic snapshot:

```sh
python3 scripts/safe-web.py stage \
  --snapshot-dir /approved/snapshot \
  --out-dir /fresh/scratch/stage \
  --content-rev FULL_40_CHARACTER_COMMIT \
  --manifest-sha256 MANIFEST_SHA256
```

Local staging validates revision **syntax**, not Git provenance for an arbitrary directory. CI additionally reads back both checked-out HEADs and reads only the two allowlisted regular Git blobs at the specified exact content revision. The caller-provided manifest digest authenticates local bytes.

Build once the actual reviewed adapter exists:

```sh
python3 scripts/safe-web.py build \
  --snapshot-dir /approved/snapshot \
  --out-dir /fresh/scratch/public-html \
  --content-rev FULL_40_CHARACTER_CONTENT_COMMIT \
  --manifest-sha256 MANIFEST_SHA256 \
  --converter /reviewed/bin/tree_of_md \
  --converter-rev FULL_40_CHARACTER_CONVERTER_COMMIT \
  --converter-sha256 REVIEWED_BINARY_SHA256 \
  --forester /pinned/forester/bin/forester \
  --home EXISTING_PUBLIC_HOME_ID
```

The only converter interface invoked is:

```sh
tree_of_md --public-forest INPUT --out-dir OUTPUT
```

A caller-supplied converter revision/hash is an explicit local attestation; it is not a proof that an arbitrary binary came from a Git revision. CI builds the exact reviewed checkout afresh using the reviewed source-only build driver and hashes that output. No build commands are accepted from the content manifest.

The native renderer verifies its resolved binary against `nix eval` of the fixed full-revision flake's output and checks `6.0~dev`. It copies only web assets from that pinned package's default theme to writable scratch directories, not Nix directory modes. It never uses `--dev`. It checks all generated routes and the final inventory before moving the HTML directory to the requested fresh destination. Tool failures expose generic codes, not their stdout/stderr or file paths.

Local synthetic verification also exercised the **real producer → snapshot staging → JSON-only converter → pinned Forester** path: the shared producer-v2 fixture yielded eight approved named routes and 88 audited web files. A separate synthetic extension with inline and display `$`/`$$` `x < y` passed the same path and preserved TeX in the native HTML's `data-tex`. KaTeX's final browser rendering was not exercised here. The producer still refuses some TeX command examples as `unsupported-raw`; consumer masking does not bypass that upstream boundary. The converter worktree was uncommitted, so its baseline revision and binary hash were local attestations only, not a reviewed committed pin or a CI-green claim.

## CI pins and secret scope

GitHub Actions references were resolved read-only from GitHub's tag API:

- `actions/checkout` v4: `11d5960a326750d5838078e36cf38b85af677262`
- `actions/upload-artifact` v4: `ea165f8d65b6e75b540449e92b4886f43607fa02`
- `cachix/install-nix-action` v31 (peeled annotated tag): `13d8dd58da0234aa297dedd986986ccb8e7f3e24`

Forester revision: `f8fb5f5d88923db36643cf9c20c662adff969c98`.
Flake: `git+https://tangled.org/jonmsterling.com/ocaml-forester?ref=forester-6.0-dev&rev=f8fb5f5d88923db36643cf9c20c662adff969c98#legacyPackages.x86_64-linux.forester`.

Before unblocking, independently review and populate all three converter fields: full Git revision, reproducible locked build argv, and real relative executable path ending in `tree_of_md` or `tree_of_md.exe`. The existing converter Devbox config alone is not a verified CI build driver/toolchain. The source-only argv is never evaluated by a shell; only explicit `dune`, `nix`, `devbox`, or `opam` entry points are allowed. Verify that driver on the real runner before making any CI-green claim.

`PUBLIC_CONTENT_TOKEN` must be a separate read-only, least-privilege credential restricted to `ryoryoryo3838/miya-lis-public` only. It is supplied only to the content checkout action; credentials are not persisted. No secret was created, read, printed, changed or tested here. The old private vault GitHub backup stays unchanged. There is no cache step and no artifact upload of snapshot JSON, Markdown, trees, XML, Git checkouts, logs or tool binaries.

The uploaded web directory must contain **both root `index.html` redirect and public native `forest.json` search metadata**, every exact approved named HTML route, and every byte-hash-verified pinned theme CSS/JS/font/icon asset. Omission of any required file blocks the artifact with `SW_OUTPUT`. Local refusal checks deleted each expected file separately from scratch copies of the actual eight-route/88-file native artifact: all incomplete copies were refused, the complete artifact passed, and the original artifact's byte hashes stayed unchanged. That public search JSON is necessary for the native theme; it is not the source snapshot. Extra routes/files or source-path/source-metadata/token/canary leak signatures block the whole artifact. Leak signatures are defense in depth, not a universal secret classifier or proof of publication authorization.

## Remaining approval gates

- Apply these new source files to the actual site only after its write-root restriction is explicitly resolved. This agent did not bypass it.
- Commit/review the real `tree_of_md` adapter and locked build driver; fill pins with observed values, not placeholders.
- Complete XML/native graph/transclusion/metadata and browser route/load/security checks on the shared synthetic pipeline; local JSON staging and audited HTML E2E are now exercised. Final browser KaTeX rendering remains a separate check.
- Independent read-only source/hash review, actual content review, then separate deployment approval and local Wrangler 4 dry-run. No dispatch, push, commit, deployment, visibility or secret changes were performed by this agent.
