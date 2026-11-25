#!/bin/sh
# Build the site.
#
#   build.sh snapshot DIR   check DIR against public-snapshot, then convert its
#                           public-forest.json into trees/*.tree
#   build.sh forest         build the forest and dress it in the site's shell
#
# The site is built only from an approved public snapshot: manifest.json and
# public-forest.json, projected from the vault's PUBLIC/ by the Forester
# hybrid plugin, reviewed, and committed on their own to miya-lis-public. The
# vault itself never reaches this build. public-snapshot names the approved
# one; changing it is what approves a new snapshot.
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# The forest is the repository root, laid out as `forester init` makes one.
cd "$script_dir/.."

# The manifest's own digest is the approval: it binds the exact bytes of the
# forest. Anything else in the directory, or any byte that differs, is refused.
check_snapshot() {
  . ./public-snapshot
  python3 - "$1" "$manifest_sha256" <<'PY'
import hashlib
import json
import os
import sys

snapshot, approved = sys.argv[1], sys.argv[2]


def digest(name):
    with open(os.path.join(snapshot, name), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def refuse(reason):
    sys.exit("build.sh: snapshot refused: " + reason)


names = sorted(n for n in os.listdir(snapshot) if not n.startswith("."))
if names != ["manifest.json", "public-forest.json"]:
    refuse("expected exactly manifest.json and public-forest.json, found %s" % names)
for name in names:
    if os.path.islink(os.path.join(snapshot, name)):
        refuse("%s is a symlink" % name)
if digest("manifest.json") != approved:
    refuse("manifest.json is not the one public-snapshot approves")
with open(os.path.join(snapshot, "manifest.json"), encoding="utf-8") as handle:
    manifest = json.load(handle)
if manifest != {"schema": "forester-public-snapshot-v1",
                "files": {"public-forest.json": digest("public-forest.json")}}:
    refuse("public-forest.json does not match its manifest")
PY
}

# tree_of_md's public mode validates the forest again and refuses what it does
# not know. TREE_OF_MD names the executable; failing that, the one on PATH.
convert_snapshot() {
  tree_of_md=${TREE_OF_MD:-$(command -v tree_of_md || true)}
  if [ -z "$tree_of_md" ]; then
    echo "build.sh: no tree_of_md executable found; set TREE_OF_MD" >&2
    exit 1
  fi
  check_snapshot "$1"
  rm -rf trees
  "$tree_of_md" --public-forest "$1/public-forest.json" --out-dir trees
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
  snapshot) convert_snapshot "${2:?usage: build.sh snapshot DIR}" ;;
  forest) build_forest ;;
  *)
    echo "usage: build.sh snapshot DIR | build.sh forest" >&2
    exit 2
    ;;
esac
