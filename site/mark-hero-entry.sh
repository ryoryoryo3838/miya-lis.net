#!/bin/sh
# Write the site root entry.
#
# Forester generates output/index.html as a plain redirect to the Home tree.
# The hero is shown only when the entry carries the #hero fragment, so the
# root entry is rewritten here while internal links to /index/ keep landing
# on Home content.
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$site_dir"

printf '%s\n' \
  '<!DOCTYPE html>' \
  '<html>' \
  '  <head>' \
  '    <meta http-equiv="refresh" content="0;url=/index/index.xml#hero" />' \
  '  </head>' \
  '</html>' > output/index.html
