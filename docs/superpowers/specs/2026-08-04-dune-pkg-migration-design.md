# Dune Package Management Migration

Date: 2026-08-04
Status: Approved (design review)

## Overview

Migrate this forest repository from the opam `default` switch to Dune's integrated package management (`(pkg enabled)`), so that the project is self-contained in `dune-project` / `dune-workspace` and the site can be built without a project-specific opam switch.

Follows: https://dune.readthedocs.io/en/stable/tutorials/dune-package-management/setup.html

## Current State

- This repo is a **forest (site)** repository, not the forester source:
  - `trees/` — content trees; `theme/` — XSLT/CSS submodule (forester-base-theme fork)
  - `lib_theme/` — nested dune project (`lib_theme/dune-project`, lang 3.16) building `hero.js` via js_of_ocaml
  - `forester` 5.0 binary installed in opam `default` switch; site is generated with `forester build`
  - CI (`deploy.yml`): `ocaml/setup-ocaml` → `opam install forester js_of_ocaml` → `dune build lib_theme/` → copy `hero.bc.js` → `forester build` → Cloudflare deploy
- dune 3.22.2 installed. forester requires `ocaml >= 5.3.0` and `dune >= 3.13`.
- forester source repo: `https://git.sr.ht/~jonsterling/ocaml-forester`, tag `5.0` exists.

## Design Decisions

1. **Pin forester via git submodule at tag `5.0`** (local-path pin `(pin (url "forester") ...)`).
   - Reproducible (exact same source as the currently installed 5.0 → identical site output).
   - Mirrors the existing `theme/` submodule workflow; CI already checks out submodules.
   - Alternative rejected: direct `git+` URL pin tracks HEAD (dev) and is not reproducible.
2. **Absorb `lib_theme/` into the root project** — delete `lib_theme/dune-project`.
   - Nested dune projects are outside the root workspace, so `(pkg enabled)` would not cover `lib_theme`'s js_of_ocaml dependencies.
   - `dune build lib_theme/` from the root and the artifact path `_build/default/lib_theme/hero.bc.js` are unchanged → CI copy lines untouched.
3. **Local package name**: `miya-forest` (renameable; matches the Cloudflare project `miya-lis-forest`).
4. **Lock file committed**: `dune.lock/` is checked in (like `package-lock.json`) for reproducibility.
5. **opam stays only as the dune bootstrap** (dune binary itself is not yet distributable via dune pkg). The OCaml compiler and all project dependencies become dune-managed.

## Changes

### 1. `dune-project` (root) — rewrite

```lisp
(lang dune 3.22)
(name miya-forest)

(pin
 (url "forester")
 (package (name forester) (version "5.0")))

(package
 (name miya-forest)
 (allow_empty)
 (depends
  (ocaml (>= 5.3))
  js_of_ocaml
  js_of_ocaml-ppx
  forester))
```

(dune 3.22: the version field must live inside the (package ...) form, not at pin top level.)

### 2. `dune-workspace` (new file)

```lisp
(lang dune 3.21)
(pkg enabled)
```

### 3. forester submodule

```
git submodule add https://git.sr.ht/~jonsterling/ocaml-forester forester
# checkout tag 5.0 inside the submodule
```

### 4. lib_theme absorption

- Delete `lib_theme/dune-project`.
- Delete stale `lib_theme/_build/`.

### 5. Lock + first build

- `dune pkg lock` → generates `dune.lock/` (committed).
- `dune show depexts` → install required system packages (expected: `libgmp-dev` and/or `pkg-config`; system already has pkg-config 1.8.1, gmp.h currently absent).
- First `dune build` compiles OCaml 5.3.x + forester's full dependency tree (~100 packages; 10–30 min, cached afterwards).
- Locate the generated forester binary (expected: `_build/install/default/bin/forester`) and confirm it runs `forester build`.

### 6. Site build entry point

Replace direct `forester` invocation (which resolves from the opam switch) with the dune-built binary:
`_build/install/default/bin/forester build` (exact path to be confirmed empirically after first build).

### 7. CI (`deploy.yml`)

- Remove `ocaml/setup-ocaml` + `opam install forester js_of_ocaml` steps.
- Install dune + build via package management (official howto: `ocaml-dune/setup-dune@v2`; exact options — dune version pin, whether the action's built-in build is used — verified against the action README at implementation time).
- Install system depexts via `apt-get` before building.
- Keep: hero.js copy steps, `forester build` site build, home-entry hero redirect, `test/hero-route.sh`, Cloudflare Pages deploy.

### 8. devbox.json

Unchanged initially — opam remains as the dune bootstrap; the `eval $(opam env)` init hook stays. Add `gmp`/`pkg-config` packages only if `dune show depexts` requires them outside devbox's current profile.

### 9. .gitignore

- Add `_build/` (currently untracked but not ignored).
- Keep `dune.lock/` committed (do not ignore).
- `forester/` submodule is tracked as a gitlink (no ignore entry).

## Verification

1. `dune build lib_theme/` produces `_build/default/lib_theme/hero.bc.js` using dune-pkg-provided js_of_ocaml.
2. `dune pkg lock` succeeds; `dune.lock/` exists and is committed.
3. Generated forester binary runs `forester build` and produces `output/`; spot-check index pages and hero route (`test/hero-route.sh` passes).
4. Site output matches the pre-migration build (same forester 5.0 source → no content drift).
5. CI (deploy.yml) deploys successfully from a clean checkout.

## Non-Goals

- Modifying forester source, the theme submodule, or site content/design.
- Removing the opam `default` switch itself (user may do this afterwards).
- Making dune itself distributable without opam (out of scope for dune pkg today).

## Rollback

- Revert the migration commit(s); restore opam-based workflow from git history (deploy.yml is already in git).
- Submodule removal: `git rm forester` if the pin is abandoned.
