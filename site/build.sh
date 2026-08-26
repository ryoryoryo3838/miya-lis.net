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
  # Everything, not only *.tree.md. A note embeds the image kept beside it —
  # ![[CYCL-01.jpg]] finds DAILY/assets/CYCL-01.jpg — and an attachment that
  # was never copied here cannot be resolved, let alone published. Copying it
  # is not publishing it: tree-md.toml's [assets].into is what carries the
  # attachments a published tree embeds into assets/, and nothing else in the
  # vault reaches the site.
  #
  # Hidden paths are pruned: .git is the checkout's own history and .obsidian
  # is the editor's settings. tree-md ignores both, so copying them is waste,
  # and `.?*` rather than `.*` is what keeps find from pruning the directory
  # it starts in.
  (cd "$content" && find . -name '.?*' -prune -o -type f -print) |
  while IFS= read -r rel; do
    mkdir -p "trees-md/$(dirname "$rel")"
    cp "$content/$rel" "trees-md/$rel"
  done
}

# generated/*.tree is not committed — it is rebuilt from trees-md/ on every
# build, here and in CI — so there is nothing to fall back on: without an
# executable there is no forest at all, and carrying on would build a site with
# no pages in it. TREE_MD names the one to use, and CI sets it to the binary it
# installed; failing that whatever is on PATH; failing that the working copy
# this is developed against, so a local build picks up an uncommitted change in
# tree-md without being told about it.
compile_md() {
  tree_md=${TREE_MD:-$(command -v tree-md || true)}
  if [ -z "$tree_md" ]; then
    dev=$HOME/Documents/OCaml/tree-md/_build/default/bin/main.exe
    [ -x "$dev" ] && tree_md=$dev || true
  fi
  if [ -z "$tree_md" ]; then
    echo "build.sh: no tree-md executable found; set TREE_MD" >&2
    exit 1
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
