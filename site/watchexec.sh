#!/bin/sh
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$site_dir/.." && pwd)
cd "$repo_dir"

exec watchexec \
  --watch "$site_dir/contents" \
  --filter '**/*.tree.md' \
  --debounce 200ms \
  --on-busy-update queue \
  --shell=none \
  -- \
  tree-md build \
    --config "$site_dir/tree-md.toml"
