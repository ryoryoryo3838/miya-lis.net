#!/bin/sh
set -eu

grep -Fq 'url=/index/index.xml#hero' output/index.html
grep -Fq 'url=/index/index.xml' output/index/index.html
! grep -Fq '?hero=1' output/index.html
! grep -Fq '?hero=1' output/index/index.html
grep -Fq 'root="true"' output/index/index.xml
grep -Fq '"#hero"' output/hero.js
! grep -Fq '?hero=1' output/hero.js

# Internal "« Home" goes to the tree route, never through the hero entry.
grep -Fq '{/f:tree/@base-url}index/" title="Home"' output/tree.xsl
! grep -Fq 'index.html' output/tree.xsl
