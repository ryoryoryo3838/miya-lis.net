#!/bin/sh
set -eu

# set -e does not stop on a negated command, so absence is checked with this.
absent() {
  if grep -rq "$@"; then
    echo "hero-route.sh: unexpected match: $*" >&2
    exit 1
  fi
}

# The site is plain HTML now: nothing may still point a browser at XSLT.
absent 'xml-stylesheet' output
absent 'index\.xml' output --include='*.html'

# The root is the Home tree with the hero; /index/ is the same tree without it.
grep -Fq 'class="miya-native miya-home"' output/index.html
grep -Fq 'id="hero"' output/index.html
grep -Fq 'class="miya-native miya-home"' output/index/index.html
grep -Fq '<link rel="canonical" href="https://miya-lis.net/">' output/index/index.html

# Every other tree carries the navigation but not the hero.
grep -Fq 'id="nav-panel"' output/aboutme/index.html
absent -F 'id="hero"' output/aboutme/index.html
grep -Fq 'property="og:title" content="私について"' output/aboutme/index.html

test -s output/hero.js
grep -Fq '"#hero"' output/hero.js
test -s output/404.html
