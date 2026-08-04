# Devbox Forester PATH Design

Date: 2026-08-04

## Summary

Update the Devbox shell initialization so commands installed by Cargo and
Forester binaries produced by Dune are available by name inside the Devbox
shell.

## Scope

- Modify `devbox.json` only for the implementation.
- Preserve the existing `init_hook` commands and unrelated uncommitted changes.
- Add these directories to `PATH`:
  - `$HOME/.cargo/bin`
  - `$PWD/_build/default/forester/bin/forester`
  - `$PWD/_build/install/default/bin`

## Design

Add one `export PATH=...` command after `source ~/.zshrc` in the Devbox
`init_hook`:

```sh
export PATH="$HOME/.cargo/bin:$PWD/_build/default/forester/bin/forester:$PWD/_build/install/default/bin:$PATH"
```

Appending the existing PATH last preserves all pre-existing command lookup
locations. Placing the export after `.zshrc` prevents the existing shell
configuration from removing these project-specific entries.

The `$PWD`-relative entries match the repository's current Dune output paths
and are intentionally added even when their build artifacts do not yet exist;
the entries become usable as soon as the corresponding Dune target is built.

## Verification

- Parse `devbox.json` as JSON.
- Confirm the init hook contains all three directories in the export command.
- Confirm the export follows `source ~/.zshrc`.
- Do not run a Dune build or modify generated build output for this change.
