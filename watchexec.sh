watchexec \
  --watch trees-md \
  --filter 'trees-md/**/*.tree.md' \
  --debounce 200ms \
  --on-busy-update queue \
  --shell=none \
  -- \
  dune exec --root tools/tree-md ./bin/main.exe -- build \
    --config tree-md.toml
