# Make Forester Build Inputs Self-Contained

## Context

The repository currently has no `theme/` submodule, although the deployment
workflow copies the generated hero asset into `theme/hero.js` and the
Forester output depends on the theme files. The previous `theme` gitlink was
removed in commit `208944e`.

The current `site/watch.sh` invokes `forester --dev`, but the installed
Forester CLI rejects `--dev`. The site configuration and source files live
under `site/`, while the deployment workflow still uses repository-root
paths.

## Design

Vendor the Forester base theme as ordinary tracked files in `site/theme/`, based on
the upstream `5.0` tag. The original Hero-customized submodule commit is no
longer reachable from the configured upstream, so preserve the current Hero
behavior by applying the existing generated `site/output/tree.xsl` and
`site/output/style.css` as the local theme overlay. Keep generated
`site/theme/hero.js` ignored while tracking the static theme sources.

Replace the local-path Forester pin with a direct immutable Dune package pin to
the upstream `ocaml-forester` repository at commit
`5ceee0e7d20febc0552caad0f71aa01750574d43` (the `5.0` tag). Remove the
submodule declarations and make the deployment checkout independent of
submodule initialization.

Make the local watcher run from `site/` and invoke the Forester executable
provided by the Dune installation rather than the ambient opam executable. The
script will resolve its own directory before starting `forest watch`, so it
behaves consistently whether called from the repository root or from `site/`.

Update the deployment workflow to use ordinary repository files, pass
`site/tree-md.toml`, build from `site/forest.toml`, copy the hero asset into
`site/theme/` and `assets/`, and deploy `site/output/`. Keep the existing generated
redirect and route test, but run the test with `site/` as its working directory
or update its paths consistently.

Fix the separate Markdown watcher path and executable invocation so it also
runs from the repository root without referring to the nonexistent
`$HOME/miyac` path.

## Verification

- Confirm `theme/` is ordinary tracked content and contains the upstream
  sources plus the Hero overlay.
- Confirm `dune-project` uses the immutable Forester commit pin and no
  `forester/` submodule is required.
- Run the Forester build from `site/` and confirm `site/output/index/index.xml`
  and theme-generated assets exist.
- Run the route test after the redirect is written.
- Validate the watcher command with a short timeout and inspect its initial
  build output; do not run `dune clean` or `dune build`.
- Check the workflow paths against the repository layout.

## Non-goals

- Creating a separate theme fork.
- Making `tree-md` self-contained in this change. The current local
  `tree-md` package is expected to become available through GitHub/opam and
  will be integrated separately.
- Refactoring the Dune project or changing the generated site format.
- Changing unrelated content or hero behavior.
