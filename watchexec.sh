watchexec \
  --watch trees-md \
  --filter 'site/contents/**/*.tree.md' \
  --debounce 200ms \
  --on-busy-update queue \
  --shell=none \
  -- \
  "$HOME/.opam/forester/bin/md-tree build \
    --config tree-md.toml"
