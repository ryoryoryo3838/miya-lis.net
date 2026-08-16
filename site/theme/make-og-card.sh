#!/bin/sh
# Render og-card.html into og.png, the card every page is shared with.
#
#   sh make-og-card.sh
#
# The .png is committed, so a build never needs a browser: this is run by hand
# when the card changes, not by build.sh. Chromium comes from Playwright, which
# the repository does not depend on — set PLAYWRIGHT_CHROMIUM to point at one,
# or install it with `npx playwright install chromium`.
set -eu

theme_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

chromium=${PLAYWRIGHT_CHROMIUM:-}
if [ -z "$chromium" ]; then
  chromium=$(
    find "$HOME/.cache/ms-playwright" -type f -name chrome -perm -u+x 2>/dev/null |
      head -n 1
  )
fi

if [ -z "$chromium" ] || [ ! -x "$chromium" ]; then
  echo "make-og-card.sh: no chromium found" >&2
  echo "make-og-card.sh: set PLAYWRIGHT_CHROMIUM, or npx playwright install chromium" >&2
  exit 1
fi

# Headless Chrome renders a file:// page and captures the viewport. --hide-
# scrollbars keeps the 1200x630 box from being cropped by a gutter, and
# --force-device-scale-factor=1 keeps the pixels at exactly that size.
"$chromium" \
  --headless \
  --disable-gpu \
  --hide-scrollbars \
  --force-device-scale-factor=1 \
  --window-size=1200,630 \
  --screenshot="$theme_dir/og.png" \
  "file://$theme_dir/og-card.html" >/dev/null 2>&1

if [ ! -s "$theme_dir/og.png" ]; then
  echo "make-og-card.sh: chromium wrote no image" >&2
  exit 1
fi

echo "wrote $theme_dir/og.png"
