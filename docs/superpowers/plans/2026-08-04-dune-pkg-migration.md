# Dune Package Management Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate this forest repository from the opam `default` switch to Dune's integrated package management (`(pkg enabled)`), so the site builds with a dune-resolved compiler + dependencies and a pinned forester 5.0, with no project opam switch.

**Architecture:** Declare the local package (`miya-forest`) with `forester`, `js_of_ocaml`, `js_of_ocaml-ppx` in `dune-project`; pin forester to a local git submodule checked out at tag `5.0`; enable `(pkg enabled)` in a new `dune-workspace`; generate and commit `dune.lock/`; absorb the nested `lib_theme/` project into the root project; run the site with the dune-built forester binary; replace the opam-based CI with `ocaml-dune/setup-dune@v2`.

**Tech Stack:** dune 3.22.2 (installed via opam `default` switch — remains only as the dune bootstrap), dune package management (experimental), forester 5.0 (pinned submodule), js_of_ocaml, GitHub Actions (`ocaml-dune/setup-dune@v2`).

**Spec:** `docs/superpowers/specs/2026-08-04-dune-pkg-migration-design.md`

## Global Constraints

- Working tree must be clean before any `dune build` (AGENTS.md). Commit each task's output before moving on.
- Do NOT run `dune clean`. A `dune build --watch` process runs in the background; explicit `dune build` calls may wait on its lock — that is normal, be patient.
- dune 3.22.2 is the build tool; never run builds from inside the opam switch beyond dune itself.
- `dune-project` project lang: `(lang dune 3.22)`; `dune-workspace` lang: `(lang dune 3.21)` with `(pkg enabled)` (verified parseable on dune 3.22.2).
- Local package name: `miya-forest`. Dependencies (exact): `(ocaml (>= 5.3))`, `js_of_ocaml`, `js_of_ocaml-ppx`, `forester`.
- forester pin: local path `forester` (submodule), `(version "5.0")`.
- `dune.lock/` is committed (never gitignored).
- Commit style (repo convention): semantic prefixes (`feat:`, `ci:`, `chore:`, `docs:`), English messages, one concern per commit.
- The opam `default` switch is NOT removed (out of scope; user may remove it afterwards).
- `lib_theme/dune-project` is deleted; `lib_theme/dune` and `lib_theme/hero.ml` are NOT otherwise modified.

---

### Task 1: Add forester source submodule pinned at tag 5.0

**Files:**
- Create: `forester/` (git submodule)
- Modify: `.gitmodules`

**Interfaces:**
- Produces: `forester/` directory containing forester 5.0 source — consumed by the `(pin (url "forester") ...)` stanza in Task 2.

- [ ] **Step 1: Add the submodule**

```bash
GIT_MASTER=1 git submodule add https://git.sr.ht/~jonsterling/ocaml-forester forester
```

Expected: `.gitmodules` gains a `[submodule "forester"]` entry with `path = forester`, `url = https://git.sr.ht/~jonsterling/ocaml-forester`.

- [ ] **Step 2: Pin at tag 5.0 (detached HEAD)**

```bash
GIT_MASTER=1 git -C forester fetch --tags origin
GIT_MASTER=1 git -C forester checkout 5.0
```

Expected: `git -C forester describe --tags` prints `5.0`.

- [ ] **Step 3: Commit**

```bash
GIT_MASTER=1 git add .gitmodules forester
GIT_MASTER=1 git commit -m "chore: add forester source submodule pinned at 5.0"
```

Expected: commit contains `.gitmodules` + a `160000` (gitlink) entry for `forester`.

---

### Task 2: Rewrite dune-project, add dune-workspace, absorb lib_theme, ignore _build

**Files:**
- Modify: `dune-project` (full rewrite)
- Create: `dune-workspace`
- Delete: `lib_theme/dune-project`
- Delete: `lib_theme/_build/` (stale nested-project artifacts)
- Modify: `.gitignore` (append `_build/`)

**Interfaces:**
- Consumes: `forester/` submodule from Task 1.
- Produces: the pkg-enabled workspace that Task 3 locks; `lib_theme/` now builds as part of the root project (artifact path `_build/default/lib_theme/hero.bc.js` unchanged).

- [ ] **Step 1: Rewrite `dune-project`**

Replace the entire file with:

```lisp
(lang dune 3.22)
(name miya-forest)

(pin
 (url "forester")
 (package (name forester))
 (version "5.0"))

(package
 (name miya-forest)
 (depends
  (ocaml (>= 5.3))
  js_of_ocaml
  js_of_ocaml-ppx
  forester))
```

- [ ] **Step 2: Create `dune-workspace`**

```lisp
(lang dune 3.21)
(pkg enabled)
```

- [ ] **Step 3: Absorb lib_theme and delete stale build dir**

```bash
GIT_MASTER=1 git rm lib_theme/dune-project
rm -rf lib_theme/_build
```

Expected: `lib_theme/` now contains only `dune`, `hero.ml`.

- [ ] **Step 4: Ignore build directories**

Append to `.gitignore` (current content: `output/`, `/devbox.lock`, `/theme`):

```
_build/
```

- [ ] **Step 5: Verify the workspace parses and pkg is enabled**

```bash
dune pkg enabled && echo "PKG_ENABLED_OK"
```

Expected: prints `PKG_ENABLED_OK` (exit 0). This does not solve or download anything.

- [ ] **Step 6: Commit**

```bash
GIT_MASTER=1 git add dune-project dune-workspace .gitignore
GIT_MASTER=1 git commit -m "feat: enable dune package management, absorb lib_theme into root project"
```

Expected: commit contains `dune-project` (rewrite), `dune-workspace` (new), `.gitignore`; `lib_theme/dune-project` deletion is recorded (same commit — the absorption is what makes pkg cover `lib_theme`).

---

### Task 3: Generate and commit the lock file

**Files:**
- Create: `dune.lock/` (generated)

**Interfaces:**
- Consumes: Task 2's `dune-project`/`dune-workspace`.
- Produces: `dune.lock/lock.dune` + `dune.lock/packages/*` — pins the solver's package solution; consumed by every later build and by `dune show depexts` in Task 4.

- [ ] **Step 1: Solve and lock (network; may take several minutes)**

```bash
dune pkg lock
```

Expected: exits 0; `dune.lock/` exists with `lock.dune` and `packages/` subdirectories (including `forester/` from the pin and `ocaml/`).

- [ ] **Step 2: List required system packages**

```bash
dune show depexts
```

Expected: prints the system packages needed (e.g. `libgmp-dev`, `pkg-config`). Record the exact list — Task 4 installs them.

- [ ] **Step 3: Commit**

```bash
GIT_MASTER=1 git add dune.lock
GIT_MASTER=1 git commit -m "chore: add dune.lock for package management"
```

Expected: commit adds `dune.lock/` (directory + all package entries).

---

### Task 4: Install system dependencies (depexts)

**Files:** none (system state).

- [ ] **Step 1: Install the depexts reported in Task 3 Step 2**

```bash
sudo apt-get update
sudo apt-get install -y <each package listed by `dune show depexts`, space-separated>
```

- [ ] **Step 2: Verify**

```bash
dune show depexts
```

Expected: empty output (all system deps satisfied). No commit.

---

### Task 5: First full build; locate the forester binary

**Files:** none (build artifacts only; `dune.lock` untouched).

- [ ] **Step 1: Build everything (first build compiles OCaml 5.3.x + the full dependency tree; 10–30 min)**

```bash
dune build
```

If the build is interrupted, resume with `dune build @pkg-install` first (caches dependency installation), then `dune build` again.

- [ ] **Step 2: Verify hero.js artifact**

```bash
ls -la _build/default/lib_theme/hero.bc.js
```

Expected: file exists (js_of_ocaml now provided by dune pkg).

- [ ] **Step 3: Locate and test the forester binary**

```bash
find _build -name forester -type f
_build/install/default/bin/forester --version
```

Expected: `_build/install/default/bin/forester` (if the path differs, record the actual path — Task 6 and Task 7 use it). `--version` reports 5.0.

- [ ] **Step 4: Confirm the lock file is unchanged**

```bash
git status --short
```

Expected: no modifications to `dune.lock/` (a dirty lock file means the solver re-ran; commit it separately in that case with `chore: refresh dune.lock`).

---

### Task 6: Build the site with the dune-built forester

**Files:** none (generates `output/`, which is gitignored).

- [ ] **Step 1: Generate the site**

```bash
_build/install/default/bin/forester .
```

Expected: exits 0; `output/` regenerated.

- [ ] **Step 2: Apply the hero home redirect and run the route test (same as CI)**

```bash
printf '%s\n' \
  '<!DOCTYPE html>' \
  '<html>' \
  '  <head>' \
  '    <meta http-equiv="refresh" content="0;url=/index/index.xml?hero=1" />' \
  '  </head>' \
  '</html>' > output/index.html
sh test/hero-route.sh
```

Expected: script exits 0 (all four greps succeed: redirect in `output/index.html`, `url=/index/index.xml` in `output/index/index.html`, no `?hero=1` in `output/index/index.html`, `root="true"` in `output/index/index.xml`).

- [ ] **Step 3: Spot-check parity with the pre-migration output**

```bash
grep -c 'MIYA-LIS' output/index/index.xml; ls output/index/index.xml
```

Expected: home index contains the MIYA-LIS content and looks identical to the previous forester 5.0 build (same pinned source ⇒ no content drift). No commit.

---

### Task 7: Migrate CI to dune package management

**Files:**
- Modify: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: `_build/install/default/bin/forester` path confirmed in Task 5; `dune.lock/` from Task 3.
- Produces: opam-free CI pipeline.

- [ ] **Step 1: Replace the setup/build steps**

Rewrite `.github/workflows/deploy.yml` to:

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

      - name: Build with dune package management
        uses: ocaml-dune/setup-dune@v2
        with:
          version: latest
          steps: install-dune install-gpatch install-depexts build-deps build

      - name: Build hero.js
        run: |
          cp _build/default/lib_theme/hero.bc.js theme/hero.js
          cp _build/default/lib_theme/hero.bc.js assets/hero.js

      - name: Build forester site
        run: |
          _build/install/default/bin/forester .

      - name: Mark home entry for HERO
        run: |
          printf '%s\n' \
            '<!DOCTYPE html>' \
            '<html>' \
            '  <head>' \
            '    <meta http-equiv="refresh" content="0;url=/index/index.xml?hero=1" />' \
            '  </head>' \
            '</html>' > output/index.html
          sh test/hero-route.sh

      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy output/ --project-name=miya-lis-forest
```

Notes: `setup-dune`'s `install-depexts` handles the apt packages (Task 4 list) automatically; `build-deps` + `build` compile the pinned forester and `lib_theme`. If Task 5 found the forester binary at a different path, adjust the "Build forester site" step accordingly.

- [ ] **Step 2: Validate the YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml')); print('YAML_OK')"
```

Expected: prints `YAML_OK`.

- [ ] **Step 3: Commit**

```bash
GIT_MASTER=1 git add .github/workflows/deploy.yml
GIT_MASTER=1 git commit -m "ci: build with dune package management (setup-dune), drop opam switch"
```

---

### Task 8: Final verification

**Files:** none.

- [ ] **Step 1: Confirm clean state**

```bash
git status --short
```

Expected: empty (no untracked/modified files; `_build/` and `output/` are gitignored).

- [ ] **Step 2: Review the migration history**

```bash
git log --oneline -8
```

Expected: the seven migration commits (Task 1–7) on top of the merged hero work, each atomic:
`chore: add forester source submodule pinned at 5.0` → `feat: enable dune package management, absorb lib_theme into root project` → `chore: add dune.lock for package management` → (no commit for Task 4) → (no commit for Task 5/6) → `ci: build with dune package management (setup-dune), drop opam switch`.

- [ ] **Step 3: Confirm the local workflow end-to-end once more**

```bash
dune build && _build/install/default/bin/forester . && sh test/hero-route.sh
```

Expected: all exit 0 (after the redirect step from Task 6 has been re-applied to `output/index.html`).

---

## Self-Review

**Spec coverage:**
- §1 dune-project rewrite → Task 2 ✓
- §2 dune-workspace `(pkg enabled)` → Task 2 ✓
- §3 forester submodule @ 5.0 → Task 1 ✓
- §4 lib_theme absorption → Task 2 ✓
- §5 lock + first build + depexts + binary location → Tasks 3–5 ✓
- §6 site build entry point → Task 6 ✓
- §7 CI → Task 7 ✓
- §8 devbox unchanged (depexts handled locally via apt; devbox untouched) → Task 4 ✓
- §9 .gitignore `_build/`, dune.lock committed → Tasks 2–3 ✓
- Non-goals respected (no forester source edits, no theme edits, no switch removal) ✓

**Placeholder scan:** no TBDs; the only conditional (`if the forester binary path differs`, `if the lock file changed`) has explicit resolution procedures with fallback commands. ✓

**Type/name consistency:** `miya-forest`, `forester`, `js_of_ocaml`, `js_of_ocaml-ppx`, pin `(url "forester")`/`(version "5.0")`, and the binary path `_build/install/default/bin/forester` are identical across all tasks. ✓
