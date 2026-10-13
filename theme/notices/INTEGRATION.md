# Native-theme integration boundary

This is trusted **site presentation code**, not a Forester extension API or
content template language. The pinned Forester 6.0~dev renderer still produces
all article, title, metadata, TOC placement IDs, native links and backmatter.
Do not replace its `style.css`, `min.js`, KaTeX files or `forest.json`.

## Explicit presentation interface

- Add `miya-native` to the body of approved native pages. Every qualified rule
  in `theme/styles/miya.css` is scoped under `body.miya-native`.
- Add `miya-home` only to the configured home route and the separately authorized
  root copy. Add `hero-page` to the authorized root `/`/`index.html` copy so its
  hero works before the client starts. The client also recognizes root entry
  paths, and `#hero` on an existing trusted home shell. A direct home route
  without that fragment remains a content page.
- Append explicit head links **after** native styles:
  `/theme/styles/fonts.css`, `/theme/styles/miya.css`, and the deferred ordinary
  script `/theme/client/hero.js`, built from `theme/client/hero.ml`.
- Preserve the source-relative `theme/styles/` and `theme/assets/` layout in
  output: font URLs resolve as `../assets/fonts/...`. The actual build target
  is `_build/default/theme/client/hero.bc.js`; only regular compiled bytes go
  into the published asset map, never a hand-written JS substitute.
- Insert `theme/layout/navigation.html` on every approved page and
  `theme/layout/home.html` only on the configured home/root, as body siblings
  **before the unchanged** `#main-wrapper`. No fragment creates an article,
  changes native IDs or wraps/reorders the native main-wrapper children.
- `navigation.html` contains exactly one `{{MENU}}` slot. The caller fills that
  slot with escaped public-root labels and exact approved-ID route links.
  There is no content-driven fragment evaluation or XML menu fetch.
- Keep `theme/assets/notices/OFL-1.1.txt` with the copied fonts, and the CC0 notice
  with the derived CSS/fragments. The byte hashes and original tracked paths
  are in `PROVENANCE.json`. That JSON is provenance, not a publishing authority.

## Client and semantic details

The new client is inert without an owned body marker and complete navigation
controls; missing optional hero/header parts do not throw. A body-level ready
marker prevents duplicate site handlers. The retired `hero-page` marker is
recognized only for the retained legacy compatibility fixture, whose selectors
and first-match/scroll behavior are still exercised with the new compiled JS.
New native controls are restricted to the owned global/hero-period buttons.

The persistent header deliberately uses `div[role=banner]`, not a `header`
element: pinned native `Collapse.ml` delegates clicks on *every* `header` and
would otherwise collapse article mainmatter when the owned Top link is clicked.
Do not add a general native-header interceptor to work around this.

Headings, metadata, slugs and TOC use Inria Sans plus Japanese Gothic fallbacks;
article prose uses the existing licensed BIZ UDMincho. No Japanese Gothic font
is installed/downloaded/merged. Browser acceptance must verify actual custom Inria and BIZ
Mincho glyph rendering, not only computed font-family declarations. The original
light canvas is intentionally retained under both light/dark OS preferences;
this port does not introduce a new dark palette. Mobile keeps native TOC usable
in normal flow after the article; desktop uses the existing two-column reading
layout. Native CSS counters/collapse/KaTeX and search remain authoritative.

## Isolated verification

This code-only distribution contains no input snapshot or local binary digest.
The synthetic push workflow consumes only its separately reviewed immutable
`config/synthetic-inputs.json` anchors, verifies the two exact snapshot Git blobs,
and invokes the reviewed converter and pinned native renderer through
`scripts/safe-web.py ci-run`. Historical local fixture builders are not included.

Compile via `python3 scripts/build-theme-client.py --site-root .`; it supplies
the fixed Dune 3.23.1 environment and owned `DUNE_ROOT`, preserving the checked-in
OCaml 5.5.1/js_of_ocaml 6.4.1 lock. A version banner or previous acceptance is
not proof that the candidate's fresh JS compiled.

For a separately approved canonical-output browser acceptance, use:

```
node test/native_theme_production_browser.mjs --production-dir dist \
  --client _build/default/theme/client/hero.bc.js --case all \
  --evidence-dir /approved/local-only/browser-evidence
```

Set `PLAYWRIGHT_MODULE` and `HYBRID_CHROMIUM` to the already installed browser
paths. The server binds only loopback, and the browser aborts/asserts every
external request. The production harness serves canonical bytes without
decorating them. `test/native_theme_browser.mjs` remains a separately labeled
test-only adapter for absent/partial/unowned controls. Those boundary fixtures
are not acceptance of the final rendered artifact. Logs/inventories stay outside
the source distribution. These browser harnesses do not dispatch CI, export
content, upload, commit, push or deploy.
