#!/bin/sh
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$site_dir"

# build.sh also rewrites the root entry, so the watched preview shows the hero
# at / just like the deployed site does.
exec "$HOME/.cargo/bin/forest" watch -- \
  sh "$site_dir/build.sh"
