#!/bin/sh
# Build the site.
#
#   build.sh project VAULT  project the vault's public trees into
#                           .projection/public-forest.json
#   build.sh convert        convert that projection into trees/*.tree
#   build.sh forest         build the forest and dress it in the site's shell
#
# project needs only Node, so CI can compare the projection with the last
# deployed one before it installs anything else.
#
# The vault is private. What leaves it is settled by the Forester hybrid
# plugin's public projection (PROJECTOR names its dist/project-public.mjs):
# the notes under PUBLIC_SCOPE that the folder, file and heading markers make
# public, plus bibliographic records of the literature they cite. The
# projection is fail-closed and prints only a status and diagnostic codes,
# never note text or paths, because this repository's CI logs are public.
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# The forest is the repository root, laid out as `forester init` makes one.
cd "$script_dir/.."

# projection.json decides where publication starts: publicFolders are public
# unless a #private marker says otherwise, and only the folders in scope are
# projected at all. Markers inside the vault (#public/#private tags, folder
# notes) refine that; nothing outside the scope is ever published, except
# bibliographic records of literature that a public tree cites.
project_vault() {
  vault=$1
  projector=${PROJECTOR:?build.sh: set PROJECTOR to dist/project-public.mjs of the Forester plugin}
  rm -rf .projection
  mkdir .projection
  set -- $(python3 -c 'import json; print(" ".join("--scope " + f for f in json.load(open("projection.json"))["scope"]))')
  node "$projector" --vault "$vault" --out "$PWD/.projection/public-forest.json" \
    --config projection.json --format forest "$@"
}

# tree_of_md's public mode validates the projection again and refuses what it
# does not know. TREE_OF_MD names the executable; failing that, the one on PATH.
convert_projection() {
  tree_of_md=${TREE_OF_MD:-$(command -v tree_of_md || true)}
  if [ -z "$tree_of_md" ]; then
    echo "build.sh: no tree_of_md executable found; set TREE_OF_MD" >&2
    exit 1
  fi
  rm -rf trees
  "$tree_of_md" --public-forest .projection/public-forest.json --out-dir trees
}

# Forester is installed with opam (`opam install forester.6.0`), so it is on
# PATH; FORESTER names a different one.
build_forest() {
  forester=${FORESTER:-$(command -v forester || true)}
  if [ -z "$forester" ] || [ ! -x "$forester" ]; then
    echo "build.sh: no forester executable found; opam install forester.6.0, or set FORESTER" >&2
    exit 1
  fi

  # Forester only adds to output/, so a tree that was renamed or unpublished
  # would otherwise stay on the site.
  rm -rf output
  "$forester" build forest.toml
  python3 "$script_dir/decorate.py"
}

case "${1:-}" in
  project) project_vault "${2:?usage: build.sh project VAULT}" ;;
  convert) convert_projection ;;
  forest) build_forest ;;
  *)
    echo "usage: build.sh project VAULT | build.sh convert | build.sh forest" >&2
    exit 2
    ;;
esac
