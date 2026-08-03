#!/bin/sh
set -eu

grep -Fq 'url=/index/index.xml?hero=1' output/index.html
grep -Fq 'url=/index/index.xml' output/index/index.html
! grep -Fq '?hero=1' output/index/index.html
grep -Fq 'root="true"' output/index/index.xml
