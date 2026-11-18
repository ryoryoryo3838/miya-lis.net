#!/bin/sh
# Compile contents/*.tree.md into generated/*.tree whenever a Markdown source
# changes. Run alongside watch.sh, which rebuilds the forest from the result.
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$site_dir"

TREE_OF_MD=~/Documents/OCaml/tree-md/_build/bin/main.exe

exec watchexec \
  --watch "$site_dir/contents" \
  --filter '**/*.tree.md' \
  --debounce 200ms \
  --on-busy-update queue \
  --shell=none \
  -- sh "$site_dir/build.sh" md
