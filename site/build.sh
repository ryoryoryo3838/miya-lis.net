#!/bin/sh
# Build the site.
#
#   build.sh          compile the Markdown sources, then build the forest
#   build.sh md       sync the Markdown repository into trees-md/, then compile
#                     trees-md/*.tree.md into generated/*.tree
#   build.sh forest   build the forest and write the site root entry
#
# The two stages are split so the watchers can own one each: watchexec.sh runs
# the md stage on Markdown changes, and the trees it regenerates are part of the
# forest, so watch.sh picks them up and runs the forest stage.
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$site_dir/.." && pwd)
cd "$site_dir"

# The Markdown sources live in their own repository — the Obsidian vault — so
# that notes are edited and versioned independently of the site. tree-md rejects
# absolute and `..` source roots, so the notes are copied into trees-md/ rather
# than referenced in place. Set FOREST_CONTENT to point at a different checkout.
#
# The whole vault is synced, not the published folder alone, because a page may
# link to a note kept anywhere in it — MIYA-LIS.NET/notes links to notes/frege.
# What is published is settled by tree-md.toml's [publish].from rather than by
# what is copied: it names MIYA-LIS.NET/** and pulls in whatever those reach,
# so nothing else in the vault reaches the site.
sync_md() {
  content=${FOREST_CONTENT:-$HOME/wiki.miya-lis.net}
  if [ ! -d "$content" ]; then
    echo "build.sh: Markdown sources not found at $content" >&2
    echo "build.sh: set FOREST_CONTENT to the directory holding *.tree.md" >&2
    exit 1
  fi

  rm -rf trees-md
  mkdir -p trees-md
  # Only .tree.md is a source; the vault also holds notes that are not trees.
  (cd "$content" && find . -type f -name '*.tree.md') | while IFS= read -r rel; do
    mkdir -p "trees-md/$(dirname "$rel")"
    cp "$content/$rel" "trees-md/$rel"
  done
}

# Markdown sources are compiled into generated/*.tree, which is committed.
# Without a tree-md executable the previously generated trees are reused.
compile_md() {
  # tree_md=${TREE_MD:-$(command -v tree-md || true)}
  tree_md=~/Documents/OCaml/tree-md/_build/default/bin/main.exe
  if [ -z "$tree_md" ]; then
    echo "build.sh: no tree-md executable found; reusing generated/" >&2
    return 0
  fi
  sync_md
  "$tree_md" build --config tree-md.toml
}

build_forest() {
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

  "$forester" build forest.toml
  sh "$site_dir/write-entries.sh"
}

case "${1:-all}" in
  all) compile_md; build_forest ;;
  md) compile_md ;;
  forest) build_forest ;;
  *)
    echo "usage: build.sh [all|md|forest]" >&2
    exit 2
    ;;
esac
