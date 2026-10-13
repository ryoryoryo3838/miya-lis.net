# Safe public snapshot build — native Forester 6

**code-only candidate for an approved synthetic build-only dry run. No production deployment.**

The canonical converter is `tree_of_md`. `config/pins.json` selects the reviewed source revision `a98f2800a88748381fcf9821d64e713925a0a027`, its real locked source-only build driver `nix develop --no-write-lock-file --command python3 scripts/build-public-cli.py`, and regular executable `_build/public-cli/tree_of_md`. Fixed Forester source and dependencies remain pinned. Only separately approved synthetic inputs may use this candidate.

## Responsibilities and boundary

- The Markdown vault remains the private source of truth. Locally reviewed public projection and the private `miya-lis-public` input repository are separate from site implementation.
- This consumer validates an already authorized **public-only snapshot**; links, titles and reachability do not grant publication permission. `%%p%%` remains private.
- No vault discovery/checkout, whole-file `publish.from`, raw-content fallback, attachment copier or publication shorthand change.
- `theme/` contains active trusted site code; `config/`, `scripts/`, `test/` and `docs/` have separate responsibilities. `_build/` and `dist/` are Git-ignored outputs.
- This distribution omits old Git history, `legacy/`, `site/`, cached credentials, generated output and real Markdown notes. Licensed owned font/assets and their source-code provenance are retained; that metadata is not an archive of private notes.
- Native Forester assets and semantics remain authoritative. The site-specific shell is an explicitly trusted presentation layer, **not** an invented Forester template API or a renderer fork.
- The only workflow is a build-only push trigger for `ci/synthetic-dry-run-*`. No manual dispatch, production branch trigger or deployment is provided. Production publication needs a separate approval.

## Public snapshot format

A snapshot directory and the specified snapshot commit's root Git tree contain exactly:

```text
manifest.json
public-forest.json
```

The manifest has no optional keys or command/path fields:

```json
{
  "schema": "forester-public-snapshot-v1",
  "files": {
    "public-forest.json": "<SHA-256: 64 lowercase hexadecimal characters>"
  }
}
```

The external `SNAPSHOT_SHA256` / `--manifest-sha256` approval anchor hashes the **exact manifest bytes**, not the forest itself. The manifest then binds the exact allowlisted forest bytes; whitespace changes require a new approval digest. A README-only content commit is not a snapshot.

The `forester-public-v2` contract contains named public roots, nested named/anonymous sections, typed transclusions with header/TOC flags, sanitized attribution and metadata, and empty content assets. Unknown/duplicate/source keys, unsafe or case-colliding IDs, invalid dates, missing targets and containment/transclusion cycles fail closed. The converter emits one `.tree` per root; nested named definitions also acquire independent native routes without duplicate root definitions.

The site's defensive Markdown guard recognizes literal code/math without rewriting the bytes passed to the independent converter. Its internal mask preserves offsets, LF/CRLF, blank lines and token separation. Unclosed literals, lone CR, raw Forester/HTML, unsupported assets and declarations remain fail-closed. Container-relative code is not guessed, and separate chunks are not concatenated. This is neither a publication authority nor a complete Markdown parser.

Limits: manifest 64 KiB; forest 16 MiB; individual strings 1 MiB of strict UTF-8 bytes; arrays/trees 20,000; containment depth 64; final artifact 128 MiB / 30,000 files. Escaped lone surrogates, traversal, namespace overlap, unsafe ancestor links, symlink/hardlink/special inputs and unknown files are refused. Accepted bytes are not normalized or repaired. Both staging and HTML destinations must be fresh; existing output is never merged or recursively replaced on refusal.

## Local build

Compile only trusted client sources with the fixed toolchain and unchanged lock:

```sh
python3 scripts/build-theme-client.py --site-root .
```

The builder copies only explicit root configs/locks and `theme/client/` into an owned workspace. It constructs its compiler environment without inherited content tokens or user OCaml/Nix settings, sets `DUNE_ROOT`, bounds subprocesses, kills the compiler process group on timeout, and atomically publishes a fresh regular JS file only after source-hash recheck. It does not solve a new lock or copy archive/content inputs.

Build an independently approved snapshot:

```sh
python3 scripts/safe-web.py build \
  --snapshot-dir /approved/snapshot \
  --out-dir /fresh/output/public-html \
  --content-rev FULL_40_CHARACTER_CONTENT_COMMIT \
  --manifest-sha256 MANIFEST_SHA256 \
  --converter /reviewed/bin/tree_of_md \
  --converter-rev FULL_40_CHARACTER_CONVERTER_COMMIT \
  --converter-sha256 REVIEWED_BINARY_SHA256 \
  --forester /pinned/forester/bin/forester \
  --home EXISTING_APPROVED_PUBLIC_HOME_ID \
  --theme-config config/theme.json --site-root .
```

Omit both theme flags to retain the pinned standard native presentation. Local revision arguments verify syntax and explicit binary/digest attestations; they are not Git provenance for arbitrary directories. CI additionally checks exact checkout revisions and the two allowlisted content Git blobs and builds the reviewed converter source afresh. No command comes from the snapshot.

Fixed Forester source: `f8fb5f5d88923db36643cf9c20c662adff969c98`, banner **`6.0~dev`**, not a claim of stable 6.0 identity. The renderer checks the binary against the fixed Nix package, keeps native `style.css`, `min.js`, KaTeX and font/icon bytes unchanged, and never uses `--dev` or legacy XML/XSL navigation.

## Trusted presentation and audit

- `config/theme.json` explicitly lists the active assets and source-only notices. No glob grants approval. Unknown theme files/directories, links, mismatched mappings, late source changes and native asset collisions are refused.
- The current static inventory declares 254 byte-preserved font files and two public license notices. Together with two CSS files and the freshly compiled JS, there are 259 owned public assets.
- `theme/notices/INTEGRATION.md` and strict-JSON `PROVENANCE.json` are source-only documentation: bounded, hashed and rechecked, never copied into the public artifact.
- Static navigation/home fragment roots are **direct body children**, before unchanged native `#main-wrapper`. A new wrapper would break the client's deliberately scoped `body > #nav-toggle-global` selector. Native header/article/TOC/backmatter bytes remain unchanged.
- Native head links remain; additional links load `/theme/styles/fonts.css`, `/theme/styles/miya.css` and `/theme/client/hero.js` explicitly.
- Only the reviewed navigation fragment's single `{{MENU}}` marker is substituted, using escaped validated **public root** IDs/titles in source order. Content is never used as a template, and nested/anonymous/private targets do not automatically gain menu entries.
- The root page must be an exact byte-copy of the decorated approved home route, with its expected digest. The client progressively enables the landing hero for `/` and `/index.html`; a direct home-route link starts in content mode unless `#hero` is requested.
- Native assets, owned assets, generated pages and native public `forest.json` have separate exact hash inventories. Root HTML, search metadata and every approved route/asset are required. Extra or stale output fails closed.
- Leak signatures remain defense in depth, not a universal secret classifier. The compiled client's existing runtime `offset`/`aliases` exception is confined to its hashed asset. For the two fixed owned CSS files only, exact complete `outline-offset` / `--hero-mark-offset` declaration token spans are distinguished from serialized source fields; quoted/bare payload fields, other property names, paths, secrets and canaries still fail. Native HTML/search receive no CSS exception.

## Verification scope

Run the portable synthetic unit and distribution suites:

```sh
python3 -B -m unittest discover -s test -p 'test*.py' -v
python3 -B test/forester_version_test.py
```

Real compiler tests require explicit `TC_REAL_BUILD=1`; native integration tests require explicitly supplied `SW_NATIVE_FORESTER` and, where applicable, `SW_PUBLIC_CONVERTER`. No test discovers a local worktree binary automatically. Passing unit fixtures is not a fresh compiler/native/browser acceptance claim.

`test/native_theme_production_browser.mjs` serves the **canonical rendered directory byte-for-byte**, without a fixture HTML/asset adapter. It checks real hero/menu/header, desktop/mobile placement, actual self-hosted glyphs, native TOC/collapse/backmatter/KaTeX/search and duplicate initialization. Its unowned-CSS contrast explicitly removes the owned class in the browser, not in served artifact bytes. `test/native_theme_browser.mjs` remains a separately labeled test-only adapter for missing/partial/unowned shell boundary cases; that result is not a production-renderer acceptance claim.

Machine-specific inventories, execution logs and local acceptance reports are not distributed. Prior local browser results must not be used as acceptance of newly compiled client bytes. Hosted runner acceptance and production authorization are separate outcomes.

## CI and remaining gates

`.github/workflows/synthetic-dry-run.yml` starts only on a push to `ci/synthetic-dry-run-*` in the approved site repository. `scripts/synthetic-ci-config.py` also checks the event/repository/branch, exact reviewed converter driver and strict `config/synthetic-inputs.json` before installation or content access. Inputs are fixed site-code fields (`dataset: synthetic-only`, full lowercase content commit, exact manifest digest, approved home ID), not workflow-dispatch arguments. Any null/missing/malformed anchor returns `SW_SYNTHETIC_INPUT` without creating runner outputs; wrong scope returns `SW_SYNTHETIC_SCOPE`. The independent null fixture remains active after reviewed values are filled.

All checkout/upload/Nix actions are immutable revisions. Permissions are read-only, all three checkouts disable credential persistence/submodules/LFS and use depth 1, no Actions cache is used, and source-only client compilation precedes content checkout. `test_owned_css_leak.py` is explicitly run in CI. The only uploaded artifact is audited synthetic HTML/assets with one-day retention; snapshots, Markdown, trees, XML, checkouts, logs and tool binaries are excluded.

`PUBLIC_CONTENT_TOKEN` is the sole explicit secret, used only by the `approved-content` checkout of `ryoryoryo3838/miya-lis-public`. It needs least-privilege read access to that repository, not the private Markdown backup. It is never a job-wide environment variable or passed to compilers. Both site and snapshot repositories remain private.

The parent operator owns commit/push and the real GitHub Actions run. Local preparation performs none of those operations. A successful hosted synthetic build would still not authorize real-note upload, a default-branch change, visibility changes, history rewriting or Cloudflare deployment. Retained `wrangler.jsonc` is inert configuration; this workflow never invokes it.
