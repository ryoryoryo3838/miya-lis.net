#!/bin/sh
# Diff this theme against the upstream Forester theme it was derived from.
#
#   ./upstream-diff.sh [COMMIT]
#
# With no argument the commit recorded in UPSTREAM is used, so a clean run means
# the vendored copy still matches its recorded base. Pass a newer commit to see
# what upstream changed before re-applying our customizations onto it.
#
# Only the files upstream ships are compared; our additions are ignored.
set -eu

theme_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$theme_dir/UPSTREAM"

target=${1:-$commit}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT INT TERM

git init -q "$work"
git -C "$work" remote add origin "$repo"
if ! git -C "$work" fetch -q --depth 1 origin "$target"; then
  echo "upstream-diff.sh: cannot fetch $target from $repo" >&2
  exit 1
fi
git -C "$work" checkout -q FETCH_HEAD

upstream="$work/$path"
if [ ! -d "$upstream" ]; then
  echo "upstream-diff.sh: $path does not exist at $target" >&2
  exit 1
fi

status=0
for file in "$upstream"/*; do
  [ -f "$file" ] || continue
  name=$(basename "$file")
  case "$name" in
  *.png | *.ico | *.woff2 | *.ttf | *.woff) continue ;;
  esac

  if [ ! -f "$theme_dir/$name" ]; then
    echo "only upstream: $name"
    status=1
  elif ! diff -u "$file" "$theme_dir/$name" \
    --label "upstream/$name" --label "ours/$name"; then
    status=1
  fi
done

if [ "$status" -eq 0 ]; then
  echo "identical to $repo@$target:$path"
fi
exit "$status"
