# Home Hero Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the HERO only when the site home entry is opened, while `/index/` remains the normal individual index page.

**Architecture:** Keep Forester's `root="true"` XML output and distinguish the browser entry with an explicit `?hero=1` marker. The generated js_of_ocaml runtime keeps navigation active on every page but enables HERO-only behavior only when the marker is present. The root redirect is rewritten during static deployment; the `/index/` redirect remains unmarked.

**Tech Stack:** Forester, XSLT 1.0, OCaml/js_of_ocaml, Dune, static Cloudflare Pages.

## Global Constraints

- No runtime dependencies or server-side routing.
- `/index/` must retain the index content and navigation without HERO.
- `theme/hero.js` is generated from `lib_theme/hero.ml`; do not hand-edit it.
- Verify both home and individual index routes after generation.

---

### Task 1: Add Route Regression Check

**Files:**
- Create: `test/hero-route.sh`

- [ ] Assert `output/index.html` redirects to `/index/index.xml?hero=1`.
- [ ] Assert `output/index/index.html` redirects to `/index/index.xml` without the marker.
- [ ] Assert `output/index/index.xml` retains `root="true"`.

Run: `sh test/hero-route.sh`
Expected before implementation: FAIL because the generated root redirect has no `?hero=1` marker.

### Task 2: Add Runtime Home-Mode Selection

**Files:**
- Modify: `lib_theme/hero.ml`
- Generate: `theme/hero.js`

- [ ] Read the exact browser search marker `?hero=1`.
- [ ] Keep HERO scroll/header setup only in home mode.
- [ ] In normal `/index/` mode, hide `#hero`, remove `hero-page` from `body`, and leave shared navigation active.
- [ ] Regenerate with `opam exec -- dune build lib_theme/` and copy `_build/default/lib_theme/hero.bc.js` to `theme/hero.js`.

### Task 3: Mark Only the Home Redirect

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] After `opam exec -- forester .`, rewrite `output/index.html` to redirect to `/index/index.xml?hero=1`.
- [ ] Leave generated `output/index/index.html` unmarked for direct `/index/` navigation.
- [ ] Run `sh test/hero-route.sh` before deployment.

### Task 4: Verify Routes

- [ ] Run `dune exec forester -- build forest.toml`.
- [ ] Run `node --check output/hero.js`.
- [ ] Confirm source diagnostics for `lib_theme/hero.ml` are clean.
- [ ] Confirm home mode preserves HERO and `/index/` mode hides it using fresh browser/static evidence.
