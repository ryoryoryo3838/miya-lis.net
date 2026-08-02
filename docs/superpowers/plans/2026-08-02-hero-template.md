# Hero Template for Forester — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full-viewport hero landing screen (MIYA-LIS / .NET) to the forester index page, with scroll-based period pinning, nav panel toggle, and persistent header — all driven by OCaml-compiled JS.

**Architecture:** Split the forester XSLT root template to render a hero layout on the top page (`@root='true'`) while preserving the existing layout for all other pages. OCaml (`js_of_ocaml`) compiles to `hero.js` handling dynamic behaviors. Navigation links are defined in `navigation.tree` and rendered by XSLT via `document()`.

**Tech Stack:** XSLT 1.0, CSS3, OCaml 5 + js_of_ocaml, Dune

**Spec:** `docs/superpowers/specs/2026-08-02-hero-template-design.md`

## Global Constraints

- Do NOT modify forester core. All changes stay in the user's forest repo.
- Non-top pages must render identically to before.
- `trees/navigation.tree` must remain a valid forester tree.
- Build output: `dune build lib_theme/` → `hero.js` in `assets/`.
- Use the existing Inria Sans font from `theme/fonts/`.
- No new CSS framework dependencies.
- Use `@root='true'` to detect the top page (existing pattern in tree.xsl line 31).

---

### Task 1: CSS — Hero, Nav Panel, Persistent Header

**Files:**
- Modify: `theme/style.css` (append at end of file)

**Interfaces:**
- Produces: CSS classes `.hero`, `.hero-title`, `.hero-line`, `.hero-line--net`, `.hero-period`, `.hero-period-placeholder`, `.hero-period.is-fixed`, `.persistent-header`, `.persistent-header.is-visible`, `.nav-panel`, `.nav-panel.is-open`, `.nav-overlay`, `.nav-overlay.is-visible`, `body.hero-page`

- [ ] **Step 1: Append hero CSS to style.css**

Open `theme/style.css` and append the following at the end (after line 624):

```css
/* ── Hero Section ── */
body.hero-page {
  margin: 0;
}

.hero {
  height: 100vh;
  width: 100vw;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}

.hero-title {
  margin: 0;
  width: 100%;
  font-family: "Inria Sans", sans-serif;
  font-size: clamp(6rem, 19.5vw, 28rem);
  font-weight: 900;
  line-height: 0.85;
  text-align: left;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.02em;
  padding-left: 0.5rem;
}

.hero-line {
  display: inline-block;
  white-space: nowrap;
}

.hero-line--net {
  position: relative;
}

/* ── Period (navigation trigger) ── */
.hero-period {
  color: inherit;
  text-decoration: none;
  cursor: pointer;
  user-select: none;
}

.hero-period:hover,
.hero-period:focus-visible {
  color: #555;
}

.hero-period.is-fixed {
  position: fixed;
  top: -0.4em;
  left: 0.5rem;
  z-index: 11;
  pointer-events: auto;
}

.hero-period-placeholder {
  display: none;
  visibility: hidden;
}

.hero-period.is-fixed + .hero-period-placeholder {
  display: inline;
}

/* ── Persistent Header ── */
.persistent-header {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  padding: 0.5rem 1rem;
  background: #fff;
  z-index: 10;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
  box-sizing: border-box;
  font-family: "Inria Sans", sans-serif;
  font-size: 0.9rem;
}

.persistent-header.is-visible {
  opacity: 1;
  pointer-events: auto;
}

/* ── Nav Panel ── */
.nav-panel {
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 30;
  background: #1a1a1a;
  color: #eee;
  border-radius: 0.5rem;
  padding: 1.5rem;
  min-width: 200px;
  transform: scale(0);
  transform-origin: top left;
  transition: transform 0.25s ease, opacity 0.2s ease;
  opacity: 0;
  font-family: "Inria Sans", sans-serif;
}

.nav-panel.is-open {
  transform: scale(1);
  opacity: 1;
}

.nav-panel a {
  color: #ccc;
  text-decoration: none;
  display: block;
  padding: 0.25rem 0;
}

.nav-panel a:hover {
  color: #fff;
}

.nav-overlay {
  position: fixed;
  inset: 0;
  z-index: 25;
  background: #000;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.nav-overlay.is-visible {
  opacity: 0.3;
  pointer-events: auto;
}
```

- [ ] **Step 2: Commit**

```bash
git add theme/style.css
git commit -m "feat: add hero, nav panel, and persistent header CSS"
```

---

### Task 2: XSLT — Hero Page Branch

**Files:**
- Modify: `theme/tree.xsl:9-57` (root template match="/")

**Interfaces:**
- Consumes: `@root='true'` attribute on `/f:tree` (existing forester XML)
- Produces: `<section id="hero">`, `<header class="persistent-header">`, `<nav id="nav-panel">`, `<div class="nav-overlay">`, body class via `<body class="hero-page">`
- Consumes for nav: `document(concat(/f:tree/@base-url, 'navigation/index.xml'))` → navigation tree XML

- [ ] **Step 1: Replace the body tag in the root template to conditionally add hero-page class**

In `theme/tree.xsl`, find line 29 (`<body>`) and replace it with:

```xml
<body>
  <xsl:if test="/f:tree[@root='true']">
    <xsl:attribute name="class">hero-page</xsl:attribute>
  </xsl:if>
```

- [ ] **Step 2: Add hero section, persistent header, nav overlay, and nav panel before the ninja-keys element**

In `theme/tree.xsl`, after line 29 (`<body>`) and before line 30 (`<ninja-keys>`), insert the following block (wrapped in an `xsl:if` for the root tree):

```xml
<xsl:if test="/f:tree[@root='true']">
  <!-- Hero -->
  <section id="hero" class="hero">
    <div class="hero-title">
      <span class="hero-line">MIYA-LIS</span>
      <span class="hero-line hero-line--net">
        <a class="hero-period" id="hero-period" href="#">.</a>
        <span class="hero-period-placeholder">.</span>NET
      </span>
    </div>
  </section>

  <!-- Persistent Header -->
  <header id="persistent-header" class="persistent-header">
    <a href="/" style="text-decoration:none;color:#555;">.</a>&#160;MIYA-LIS.NET
  </header>

  <!-- Nav Overlay -->
  <div id="nav-overlay" class="nav-overlay"></div>

  <!-- Nav Panel: populated from navigation.tree -->
  <nav id="nav-panel" class="nav-panel">
    <xsl:variable name="nav-doc" select="document(concat(/f:tree/@base-url, 'navigation/index.xml'))" />
    <xsl:if test="$nav-doc">
      <xsl:for-each select="$nav-doc//f:tree/f:mainmatter/f:p">
        <xsl:apply-templates select="f:link|f:ref" mode="nav-link" />
      </xsl:for-each>
    </xsl:if>
  </nav>
</xsl:if>
```

- [ ] **Step 3: Add a nav-link mode template at the end of tree.xsl**

Before the closing `</xsl:stylesheet>` (line 395), add:

```xml
<xsl:template match="f:link|f:ref" mode="nav-link">
  <a>
    <xsl:attribute name="href">
      <xsl:choose>
        <xsl:when test="@href">
          <xsl:value-of select="@href" />
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="concat(/f:tree/@base-url, @uri, '/')" />
        </xsl:otherwise>
      </xsl:choose>
    </xsl:attribute>
    <xsl:apply-templates />
  </a>
</xsl:template>
```

- [ ] **Step 4: Add hero.js script tag in head**

In `theme/tree.xsl`, after line 23 (the `<!-- hot reload -->` comment) and before the `<script>` on line 24, add:

```xml
<xsl:if test="/f:tree[@root='true']">
  <script src="{/f:tree/@base-url}hero.js"></script>
</xsl:if>
```

- [ ] **Step 5: Verify the XSL is well-formed**

```bash
xmllint --noout theme/tree.xsl
```

Expected: no output (no errors).

- [ ] **Step 6: Commit**

```bash
git add theme/tree.xsl
git commit -m "feat: add hero page branch to XSLT root template"
```

---

### Task 3: Navigation Tree

**Files:**
- Create: `trees/navigation.tree`

**Interfaces:**
- Produces: Valid `.tree` file that forester compiles to XML. XSLT reads the generated `output/navigation/index.xml` via `document()`.

- [ ] **Step 1: Create navigation.tree**

```forester
\taxon{navigation}

\p{\link{aboutme}{About}}
\p{\link{grad-research}{卒業研究}}
\p{\link{dev/0001}{開発ノート}}
```

- [ ] **Step 2: Commit**

```bash
git add trees/navigation.tree
git commit -m "feat: add navigation tree for hero nav panel"
```

---

### Task 4: OCaml/JS — Dune Project Setup

**Files:**
- Create: `lib_theme/dune`
- Create: `lib_theme/dune-project`

**Interfaces:**
- Produces: Dune build target that compiles OCaml sources to JS via js_of_ocaml.
- Output: `_build/default/lib_theme/hero.bc.js`

- [ ] **Step 1: Create dune-project**

```lisp
(lang dune 3.16)
(using js_of_ocaml 0.1)
```

- [ ] **Step 2: Create dune file**

```lisp
(executable
 (name hero)
 (modes js)
 (libraries js_of_ocaml))
```

- [ ] **Step 3: Verify dune configuration**

```bash
dune build lib_theme/
```

Expected: error about missing `hero.ml` (not a build failure — expected since we haven't written it yet). The dune config itself should parse without errors.

- [ ] **Step 4: Commit**

```bash
git add lib_theme/dune-project lib_theme/dune
git commit -m "feat: add dune project for hero.js"
```

---

### Task 5: OCaml/JS — Hero Implementation

**Files:**
- Create: `lib_theme/hero.ml`

**Interfaces:**
- Produces: `hero.bc.js` — a self-contained JS bundle that:
  - On `window.onload`: sets up period click handler (toggle nav panel + overlay), scroll listener (pin period), and IntersectionObserver (header visibility)
  - Externally depends on DOM IDs: `hero`, `hero-period`, `hero-period-placeholder`, `persistent-header`, `nav-panel`, `nav-overlay`

- [ ] **Step 1: Write hero.ml**

```ocaml
open Js_of_ocaml

(* Helper: get element by id or fail *)
let get_element id =
  Js.Opt.get
    (Dom_html.document##getElementById (Js.string id))
    (fun () -> failwith ("element not found: " ^ id))

(* Helper: check if element has a CSS class *)
let has_class el cls =
  Js.to_bool (el##.classList##contains (Js.string cls))

(* Helper: add CSS class *)
let add_class el cls =
  el##.classList##add (Js.string cls)

(* Helper: remove CSS class *)
let remove_class el cls =
  el##.classList##remove (Js.string cls)

(* Helper: toggle CSS class *)
let toggle_class el cls =
  if has_class el cls then remove_class el cls else add_class el cls

(* ── Nav panel toggle ── *)
let setup_nav () =
  let period = get_element "hero-period" in
  let panel = get_element "nav-panel" in
  let overlay = get_element "nav-overlay" in

  let open_panel () =
    add_class panel "is-open";
    add_class overlay "is-visible";
    add_class period "is-open"
  in
  let close_panel () =
    remove_class panel "is-open";
    remove_class overlay "is-visible";
    remove_class period "is-open"
  in

  (* Click period → toggle *)
  period##.onclick := Dom_html.handler (fun ev ->
    Dom.preventDefault ev;
    toggle_class panel "is-open";
    toggle_class overlay "is-visible";
    toggle_class period "is-open";
    Js._false
  );

  (* Click overlay → close *)
  overlay##.onclick := Dom_html.handler (fun _ev ->
    close_panel ();
    Js._false
  );

  (* Escape key → close *)
  Dom_html.document##.onkeydown := Dom_html.handler (fun ev ->
    if ev##.keyCode = 27 then begin
      close_panel ();
      Js._false
    end else
      Js._true
  )

(* ── Period scroll pinning ── *)
let setup_period_pin () =
  let period = get_element "hero-period" in
  let placeholder = get_element "hero-period-placeholder" in
  let hero = get_element "hero" in

  let on_scroll () =
    let hero_rect = hero##getBoundingClientRect in
    (* Pin the period when hero bottom is above viewport top *)
    if hero_rect##.bottom < 0. then begin
      add_class period "is-fixed"
    end else begin
      remove_class period "is-fixed"
    end
  in

  (* Throttled scroll handler *)
  let ticking = ref false in
  Dom_html.window##.onscroll := Dom_html.handler (fun _ev ->
    if not !ticking then begin
      ticking := true;
      Dom_html.window##requestAnimationFrame (Js.wrap_callback (fun _ ->
        on_scroll ();
        ticking := false
      ))
    end;
    Js._true
  )

(* ── Intersection Observer: persistent header ── *)
let setup_header_observer () =
  let hero = get_element "hero" in
  let header = get_element "persistent-header" in

  (* Create IntersectionObserver via js_of_ocaml *)
  let callback entries _observer =
    let entry = Js.array_get entries 0 in
    if Js.to_bool (entry##.isIntersecting) then
      remove_class header "is-visible"
    else
      add_class header "is-visible"
  in

  let options =
    Js.Unsafe.obj [|
      ("threshold", Js.Unsafe.inject (Js.number_of_float 0.0))
    |]
  in

  let observer =
    jsnew (Js.Unsafe.global##._IntersectionObserver)
      (Js.wrap_callback callback, options)
  in

  observer##observe hero

(* ── Main ── *)
let () =
  Dom_html.window##.onload := Dom_html.handler (fun _ ->
    setup_nav ();
    setup_period_pin ();
    setup_header_observer ();
    Js._false
  )
```

- [ ] **Step 2: Build hero.js**

```bash
dune build lib_theme/
```

Expected: `_build/default/lib_theme/hero.bc.js` is generated without errors.

- [ ] **Step 3: Copy to assets**

```bash
cp _build/default/lib_theme/hero.bc.js assets/hero.js
```

- [ ] **Step 4: Commit**

```bash
git add lib_theme/hero.ml assets/hero.js
git commit -m "feat: implement hero.js (period pin, nav panel, header observer) in OCaml/js_of_ocaml"
```

---

### Task 6: Verification — Full Build

**Files:**
- No changes to files. This task verifies the full pipeline.

- [ ] **Step 1: Run forester build**

```bash
forester build forest.toml
```

Expected: Build completes without errors. Check that `output/index/index.xml` exists and contains the hero section.

- [ ] **Step 2: Verify hero HTML in output**

```bash
grep -c 'id="hero"' output/index/index.xml
```

Expected: `1` (hero section exists in the index XML)

- [ ] **Step 3: Verify hero.js is in output**

```bash
test -f output/hero.js && echo "hero.js deployed"
```

Expected: `hero.js deployed`

- [ ] **Step 4: Verify CSS is in output**

```bash
grep -c 'hero-page' output/style.css
```

Expected: `1` (hero CSS is present)

- [ ] **Step 5: Commit any build artifacts**

```bash
git status
```

If `assets/hero.js` was regenerated, commit it.

---

### Task 7: CI/CD — GitHub Actions Deploy

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: Forest repo with `.tree` sources, `theme/` (XSLT + CSS), `lib_theme/` (OCaml), `assets/` (static)
- Produces: Cloudflare Pages deployment from `output/`

- [ ] **Step 1: Create deploy workflow**

```yaml
name: Deploy to Cloudflare Pages

on:
  push:
    branches: [main, miya, hero-theme]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true

      - name: Setup OCaml
        uses: ocaml/setup-ocaml@v3
        with:
          ocaml-compiler: "5.2"

      - name: Install dependencies
        run: |
          opam install forester js_of_ocaml

      - name: Build hero.js
        run: |
          opam exec -- dune build lib_theme/
          cp _build/default/lib_theme/hero.bc.js assets/hero.js

      - name: Build forester site
        run: |
          opam exec -- forester build forest.toml

      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy output/ --project-name=miya-lis-forest
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Actions deploy to Cloudflare Pages"
```

---

## Implementation Order

Tasks must run sequentially: 1 (CSS) → 2 (XSLT) → 3 (navigation.tree) → 4 (dune) → 5 (hero.ml) → 6 (verify) → 7 (CI/CD).

Tasks 1-3 can be done in any order relative to each other, and Task 4 can be done in parallel with 1-3. Task 5 depends on 4. Task 6 depends on all previous tasks. Task 7 is independent of 6.
