#!/bin/sh
# Compile contents/*.tree.md, build the forest, and write the site root entry,
# so a local build routes exactly like the deployed one.
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$site_dir/.." && pwd)
cd "$site_dir"

# Prefer an explicit FORESTER, then the installed layout used by CI, then the
# executable produced by dune's package management.
forester=${FORESTER:-}
if [ -z "$forester" ]; then
  if [ -x "$repo_dir/_build/install/default/bin/forester" ]; then
    forester="$repo_dir/_build/install/default/bin/forester"
  else
    forester=$(
      find "$repo_dir/_build/_private" -path '*/forester.*/target/bin/forester' \
        -type f -perm -u+x 2>/dev/null | head -n 1
    )
  fi
fi

if [ -z "$forester" ] || [ ! -x "$forester" ]; then
  echo "build.sh: no forester executable found; run 'dune build' first" >&2
  exit 1
fi

# Markdown sources are compiled into generated/*.tree, which is committed.
# Without a tree-md executable the previously generated trees are reused.
tree_md=${TREE_MD:-$(command -v tree-md || true)}
if [ -n "$tree_md" ]; then
  "$tree_md" build --config tree-md.toml
else
  echo "build.sh: no tree-md executable found; reusing generated/" >&2
fi

"$forester" build forest.toml
sh "$site_dir/mark-hero-entry.sh"
