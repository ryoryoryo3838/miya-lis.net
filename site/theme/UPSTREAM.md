# Theme provenance

This is a vendored copy of Forester's own theme, customized in place. The
upstream repository, path and commit are recorded in [`UPSTREAM`](./UPSTREAM);
`upstream-diff.sh` reads them.

The pinned commit is the same one `tree-md`'s target profile names, so the theme
and the `.tree` source it renders agree on which Forester they are for. If one
moves, move the other: `target` in [`../tree-md.toml`](../tree-md.toml).

## What is changed

| File | State |
| --- | --- |
| `core.xsl` | byte-identical to upstream |
| `default.xsl` | byte-identical to upstream |
| `links.xsl` | byte-identical to upstream |
| `metadata.xsl` | byte-identical to upstream |
| `tree.xsl` | +74 / −4 — hero section, persistent header, nav panel and overlay, the `hero.js` and hot-reload script tags |
| `style.css` | +229 / −10 — Inria Sans and Honoka Shin Mincho `@font-face`, hero / nav-panel / persistent-header rules; upstream's `nav.nav` docs-button styling dropped |

Every file upstream ships is present here. `forester.js`, `javascript-source/`,
`bundle-js.sh` and `fonts/` are additions of ours.

## Why vendored rather than forked

The theme lives inside the Forester compiler's own repository, so a submodule
would have to carry the whole compiler to reach one directory, and git cannot
submodule a subdirectory. Only two of the six upstream files differ, and both
differ almost entirely by addition, so `upstream-diff.sh` gives what a fork
would give — a diff against the recorded base whenever upstream moves — without
maintaining a fork of the compiler.

## Rebasing onto a newer Forester

```sh
./upstream-diff.sh                 # diff against the recorded commit
./upstream-diff.sh <new-commit>    # diff against a newer one
```

Re-apply the changes in the table onto the new files, then update `commit` in
[`UPSTREAM`](./UPSTREAM) and the `target` in `../tree-md.toml`.
