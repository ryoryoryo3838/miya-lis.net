#!/bin/sh
# Render icon.html into the site's icons.
#
#   sh make-icons.sh
#
# Every size is drawn at that size rather than shrunk from one master: a letter
# resampled down to 16 pixels goes soft, while one rasterised at 16 keeps its
# stems. The .ico carries 16, 32 and 48 so a browser can pick.
#
# The results are committed, so a build never needs a browser: this is run by
# hand when the icon changes. Chromium comes from Playwright, which the
# repository does not depend on — set PLAYWRIGHT_CHROMIUM to point at one, or
# install it with `npx playwright install chromium`.
set -eu

theme_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

chromium=${PLAYWRIGHT_CHROMIUM:-}
if [ -z "$chromium" ]; then
  chromium=$(
    find "$HOME/.cache/ms-playwright" -type f -name chrome -perm -u+x 2>/dev/null |
      head -n 1
  )
fi

if [ -z "$chromium" ] || [ ! -x "$chromium" ]; then
  echo "make-icons.sh: no chromium found" >&2
  echo "make-icons.sh: set PLAYWRIGHT_CHROMIUM, or npx playwright install chromium" >&2
  exit 1
fi

render() {
  size=$1
  out=$2
  # --virtual-time-budget lets the font load and the canvas draw before the
  # capture; without it the shot can land on an empty page.
  "$chromium" \
    --headless \
    --disable-gpu \
    --hide-scrollbars \
    --force-device-scale-factor=1 \
    --virtual-time-budget=4000 \
    --window-size="$size,$size" \
    --screenshot="$out" \
    "file://$theme_dir/icon.html#$size" >/dev/null 2>&1

  if [ ! -s "$out" ]; then
    echo "make-icons.sh: chromium wrote no image at ${size}px" >&2
    exit 1
  fi
}

render 16 "$work/16.png"
render 32 "$work/32.png"
render 48 "$work/48.png"
render 180 "$theme_dir/apple-touch-icon.png"
render 192 "$theme_dir/android-chrome-192x192.png"
render 512 "$theme_dir/android-chrome-512x512.png"

cp "$work/16.png" "$theme_dir/favicon-16x16.png"
cp "$work/32.png" "$theme_dir/favicon-32x32.png"

# An .ico is a small directory of images. Every browser that is still shipping
# reads PNG entries, which is what icon generators have emitted for years, so
# the sizes go in as the PNGs already rendered rather than converted to BMP.
python3 - "$theme_dir/favicon.ico" "$work/16.png" "$work/32.png" "$work/48.png" <<'PY'
import struct
import sys

target, *sources = sys.argv[1:]

images = []
for path in sources:
    with open(path, "rb") as handle:
        data = handle.read()
    width, height = struct.unpack(">II", data[16:24])
    images.append((width, height, data))

# ICONDIR, then one ICONDIRENTRY each, then the images.
header = struct.pack("<HHH", 0, 1, len(images))
offset = len(header) + 16 * len(images)

entries = b""
body = b""
for width, height, data in images:
    # 0 means 256 in this field; nothing here is that large, but the rule is
    # the format's and worth honouring.
    entries += struct.pack(
        "<BBBBHHII",
        width % 256,
        height % 256,
        0,  # palette size: not paletted
        0,  # reserved
        1,  # colour planes
        32,  # bits per pixel
        len(data),
        offset,
    )
    body += data
    offset += len(data)

with open(target, "wb") as handle:
    handle.write(header + entries + body)

print("wrote %s with %s" % (target, ", ".join("%dx%d" % (w, h) for w, h, _ in images)))
PY

echo "make-icons.sh: wrote the icon at 16, 32, 48, 180, 192 and 512"
