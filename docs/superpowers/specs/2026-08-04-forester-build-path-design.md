# Unified Forester Build Path Design

Date: 2026-08-04

## Summary

Make the production and local site build use the Forester executable produced by
the root Dune project at `_build/install/default/bin/forester`. The deployment
pipeline will compile `trees-md/*.tree.md` into `generated/*.tree` before it
runs that executable, so the published site is built from the current Markdown
sources.

The tree-md compatibility test remains separate. It validates the compiler
against the pinned `forester-6.0-dev` executable, while the site uses the root
project's pinned Forester 5.0 executable. These are different compatibility
targets and must not be silently substituted for one another.

## Goals

- Use the root Dune-built Forester for local and production site generation.
- Compile Markdown sources before the Forester site build in CI.
- Prevent a bare `forester` from selecting an unrelated opam installation in
  the production path.
- Preserve the existing Forester 6.0-dev compatibility test target.
- Keep existing user content and generated-state safety behavior unchanged.

## Non-goals

- Do not change the root Forester version from 5.0.
- Do not retarget the tree-md compiler or its compatibility fixtures.
- Do not modify historical design documents or implementation plans.
- Do not merge the independent `tools/tree-md` Dune project into the root
  Dune project.

## Current State

- `forest.toml` already includes both `trees` and `generated` as tree roots.
- `.github/workflows/deploy.yml` already invokes
  `_build/install/default/bin/forester build`, but it does not run tree-md
  compilation first.
- `.github/workflows/tree-md.yml` installs a separate pinned Forester 6.0-dev
  executable for its compatibility test.
- A bare `forester` resolves to an older opam installation in the local
  environment and has a different CLI.

## Design

### Local Build Flow

The documented production-equivalent flow is:

```text
tree-md build
  -> generated/*.tree
_build/install/default/bin/forester build forest.toml
  -> output/**
```

The tree-md executable is built from its independent Dune project. The site
Forester executable is always referenced by its root `_build` path. No fallback
to `command -v forester` or `opam exec -- forester` is permitted in the site
path.

### Deployment Flow

After `ocaml-dune/setup-dune` builds the root project and its dependencies, the
deployment job installs only the independent tree-md project's dependencies,
builds/runs its CLI, and passes the repository `tree-md.toml` explicitly. The
job then invokes the root Dune-built Forester binary and continues with the
existing hero-route check and Cloudflare deployment.

The required order is:

1. Build the root Dune project, including the Forester executable.
2. Build and run the independent tree-md compiler against `tree-md.toml`.
3. Run `_build/install/default/bin/forester build forest.toml`.
4. Apply the existing home-entry redirect and verify the route.
5. Deploy `output/`.

If tree-md compilation fails, the workflow stops before Forester or Cloudflare
deployment. Generated files are CI workspace state and do not need to be
committed solely for deployment.

### Compatibility Boundary

The tree-md workflow keeps its pinned 6.0-dev Forester installation because
`forester_compat.sh` checks the exact `6.0~dev` version and exercises the
compiler's declared output profile. Replacing it with the root 5.0 binary would
turn that test into a different test and could hide compatibility regressions.

## Verification

- Confirm the site workflow contains no bare Forester invocation.
- Confirm tree-md compilation runs before the site build.
- Confirm the site build uses `_build/install/default/bin/forester`.
- Confirm a Markdown source produces its corresponding `generated/*.tree` and
  `output/<id>/index.xml` in the deployment workspace.
- Run the existing `test/hero-route.sh` after the site build.
- Keep the separate tree-md compatibility workflow passing against its pinned
  6.0-dev executable.

## Acceptance Criteria

- A deployment from a clean checkout includes current `trees-md` content in
  `output/` without relying on previously committed generated files.
- A local user following the documented commands cannot accidentally invoke the
  old opam Forester for site generation.
- Existing handwritten trees, theme behavior, and the tree-md compatibility
  target remain unchanged.
