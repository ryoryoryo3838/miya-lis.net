# Unified Forester Site Build Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the published site from current Markdown sources and always invoke the production Forester through the root Dune artifact at `_build/install/default/bin/forester`.

**Architecture:** Keep `tools/tree-md` as an independent Dune project and run its CLI before the root site's Forester binary. The deployment workflow installs only tree-md's dependencies, generates `generated/*.tree`, then uses the already-built root Forester 5.0 executable. The separate tree-md compatibility workflow continues to use its pinned Forester 6.0-dev executable.

**Tech Stack:** GitHub Actions, `ocaml-dune/setup-dune@v2`, Dune 3.22.2, the independent `tools/tree-md` project, Forester 5.0 from the root Dune package, Forester 6.0-dev for compatibility fixtures.

## Global Constraints

- Site generation must invoke `_build/install/default/bin/forester build forest.toml`.
- Do not invoke bare `forester`, `opam exec -- forester`, or `opam exec -- which forester` in the production site path.
- The deployment order is tree-md compilation, root Forester build, hero-route verification, then Cloudflare deployment.
- Keep `tree-md.yml`'s pinned `forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be` compatibility target unchanged.
- Keep `tools/tree-md` independent from the root Dune project.
- Do not modify `devbox.json`, `trees/index.tree`, `trees-md/test.tree.md`, `generated/test.tree`, or the existing generated manifest changes made outside this task.
- Do not modify historical design documents or implementation plans.
- Do not run `dune clean` or an ad-hoc `dune build` during implementation; use the repository's existing background build and focused verification commands.
- Do not commit changes unless the user explicitly requests a commit.

---

### Task 1: Document the Production-Equivalent Local Build

**Files:**
- Modify: `tools/tree-md/README.md` after the existing CLI usage section

**Interfaces:**
- Consumes: the repository root `tree-md.toml` and `forest.toml`.
- Produces: a copy-pasteable local sequence that cannot select the old opam Forester.

- [ ] **Step 1: Add the local site-build section**

Add a section named `Building the Existing Forest Site` with this exact flow:

```bash
# Run from the repository root.
dune exec --root tools/tree-md ./bin/main.exe -- build \
  --config "$PWD/tree-md.toml"
_build/install/default/bin/forester build forest.toml
```

Explain that the first command writes `generated/*.tree` and the second command
writes `output/**`. State that `tree-md check` is read-only and should be used
after `tree-md build` to confirm the generated state. State that the production
site command must not be replaced with `forester build`, because an opam switch
may provide an older CLI.

- [ ] **Step 2: Verify the documentation does not advertise a bare site Forester command**

Run:

```bash
git diff --check
```

Expected: no whitespace errors. Search the edited section and confirm its only
site-build executable is `_build/install/default/bin/forester`.

### Task 2: Compile Markdown During Deployment

**Files:**
- Modify: `.github/workflows/deploy.yml` after the `ocaml-dune/setup-dune@v2` step and before `Build forester site`

**Interfaces:**
- Consumes: root Dune build artifacts, `tools/tree-md`, `tree-md.toml`, and tracked `trees-md/**/*.tree.md` sources.
- Produces: generated `.tree` files in `generated/`, then the final site in `output/`.

- [ ] **Step 1: Install only the independent tree-md dependencies**

Add this workflow step after the setup-dune step:

```yaml
      - name: Install tree-md dependencies
        run: opam install ./tools/tree-md --deps-only
```

This step must not install or pin Forester. The root setup-dune step already
provides the root project's pinned Forester dependency and binary.

- [ ] **Step 2: Run tree-md against the repository configuration**

Add this step immediately after the dependency step:

```yaml
      - name: Compile Markdown trees
        run: |
          opam exec -- dune exec ./bin/main.exe -- build \
            --config "$GITHUB_WORKSPACE/tree-md.toml"
        working-directory: tools/tree-md
```

The absolute configuration path is intentional: tree-md resolves its default
configuration relative to the process working directory, and this step runs
inside `tools/tree-md`.

- [ ] **Step 3: Keep the root Forester site command explicit**

Keep the existing site step exactly as:

```yaml
      - name: Build forester site
        run: |
          _build/install/default/bin/forester build forest.toml
```

The Markdown compilation step must appear before it. Do not change the existing
hero JavaScript copy, redirect, route check, or Cloudflare deployment steps.

- [ ] **Step 4: Check workflow ordering and command paths**

Run:

```bash
git diff --check
```

Inspect `.github/workflows/deploy.yml` and verify this order:

```text
setup-dune build
Install tree-md dependencies
Compile Markdown trees
Build forester site using _build/install/default/bin/forester
Mark home entry for HERO
Deploy to Cloudflare Pages
```

Expected: no bare `forester` command occurs in `deploy.yml`, and the only
production Forester invocation is the root `_build` path.

### Task 3: Focused Verification

**Files:**
- Verify: `tools/tree-md/README.md`
- Verify: `.github/workflows/deploy.yml`
- Verify: `forest.toml`
- Verify: `tree-md.toml`

**Interfaces:**
- Consumes: the local and CI build sequence from Tasks 1 and 2.
- Produces: evidence that Markdown output is consumed by Forester and that the
  separate compatibility target remains unchanged.

- [ ] **Step 1: Verify the tree root configuration**

Confirm that `forest.toml` still contains:

```toml
trees = ["trees", "generated"]
```

Confirm that `tree-md.toml` still contains:

```toml
sources = ["trees-md"]
output = "generated"
```

- [ ] **Step 2: Run the tree-md checks without mutating output**

From the repository root, run:

```bash
dune exec --root tools/tree-md ./bin/main.exe -- check \
  --config "$PWD/tree-md.toml"
```

Expected: exit 0 only when the checked-in/generated state is clean. If the
workspace contains intentionally new Markdown without generated output, run
the documented `build` command first, then rerun `check`.

- [ ] **Step 3: Verify the site build with the root binary**

Only after the worktree/build policy permits a site build, run:

```bash
_build/install/default/bin/forester build forest.toml
test -f output/index/index.xml
sh test/hero-route.sh
```

For a source `trees-md/test.tree.md`, also verify:

```bash
test -f generated/test.tree
test -f output/test/index.xml
```

Expected: the generated Markdown tree is available as a standalone output and
the existing hero route still passes.

- [ ] **Step 4: Verify the compatibility boundary was not changed**

Confirm that `.github/workflows/tree-md.yml` still pins the 6.0-dev Forester
commit and that `tools/tree-md/test/forester_compat.sh` still checks
`6.0~dev`. Do not substitute the root 5.0 binary in this job.
