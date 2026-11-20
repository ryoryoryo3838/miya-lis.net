#!/bin/bash
set -euo pipefail
if command -v nix >/dev/null; then
  printf '%s\n' 'Nix must not be installed for this smoke test.' >&2
  exit 1
fi
sudo apt-get update -qq
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg-config libev-dev libgmp-dev libffi-dev libzstd-dev zlib1g-dev libyaml-dev nodejs python3
opam install -y dune.3.23.1
export PATH="$(opam var bin):$PATH"
mkdir "$HOME/smoke"
cd "$HOME/smoke"
cp -r /input/dune /input/dune-project /input/dune-workspace /input/dune.lock /input/theme /input/scripts .

content_revision=b61b25ed47dd8dd1562e2136c939b67bac70602a
manifest_sha=38f2e180be25a809f61b64cd27c4896e6ff139f56b76d90709ee5cd80d85c9db
test "$(git -c safe.directory=/input/approved-content -C /input/approved-content rev-parse HEAD)" = "$content_revision"
test "$(git -c safe.directory=/input/approved-content -C /input/approved-content ls-tree -r --name-only HEAD)" = "$(printf '%s\n' manifest.json public-forest.json)"
mkdir snapshot
for name in manifest.json public-forest.json; do
  test -f "/input/approved-content/$name" && test ! -L "/input/approved-content/$name" || exit 1
  cp "/input/approved-content/$name" snapshot/
done
python3 scripts/safe-web.py stage --snapshot-dir snapshot --out-dir checked-snapshot --content-rev "$content_revision" --manifest-sha256 "$manifest_sha"

converter_revision=924168cb248b6406ad56214aabd401c192170778
mkdir converter
git -C converter init -q
git -C converter fetch -q --depth=1 https://github.com/ryoryoryo3838/tree-md.git "$converter_revision"
git -C converter checkout -q --detach FETCH_HEAD
test "$(git -C converter rev-parse HEAD)" = "$converter_revision"
(cd converter; dune pkg lock --root .; dune build --root . --pkg=enabled -j 4 bin/public_main.exe)

# Use the same Forester commit; Tangled's Git endpoint refused the fetch.
sed -i 's|https://tangled.org/jonmsterling.com/ocaml-forester|https://git.sr.ht/~jonsterling/ocaml-forester|' dune-project
# shortcut: solve from fixed repositories for the smoke test; review and commit the refreshed lock before production CI.
printf '%s\n' \
  '(lock_dir (repositories pinned-overlay pinned-opam) (constraints (ocaml (= 5.5.1))))' \
  '(repository (name pinned-overlay) (url "git+https://github.com/ocaml-dune/opam-overlays.git#99fc2e18c45b4761ed5f6d282910c03c97e32bce"))' \
  '(repository (name pinned-opam) (url "git+https://github.com/ocaml/opam-repository.git#004f42ac81dbaf0262946589840f847f1c8a82a4"))' >> dune-workspace
dune pkg lock
dune build --pkg=enabled -j 4 @install
forester=$(find "$PWD/_build/_private" -type f -path '*/forester.*/target/bin/forester' -print -quit)
test -x "$forester"
mkdir -p tools/forester/bin tools/forester/share/forester/themes
cp "$forester" tools/forester/bin/forester
cp -R "${forester%/bin/forester}/share/forester/themes/default" tools/forester/share/forester/themes/
cp converter/_build/default/bin/public_main.exe tools/tree_of_md
python3 scripts/safe-web.py build --snapshot-dir snapshot --out-dir output \
  --content-rev "$content_revision" \
  --manifest-sha256 "$manifest_sha" \
  --converter tools/tree_of_md --converter-rev "$converter_revision" \
  --converter-sha256 "$(sha256sum tools/tree_of_md | cut -d ' ' -f1)" \
  --forester tools/forester/bin/forester --home E94855
grep -qF 'content="0;url=E94855/"' output/index.html
test -s output/E94855/index.html
test -s output/forest.json
test -s output/style.css
