#!/bin/sh
# Serve the forest on http://localhost:8080 and rebuild it whenever a tree
# changes.
#
# Compiling Markdown is watchexec.sh's job. forest only watches *.tree files,
# so the trees watchexec.sh writes into generated/ are what triggers a rebuild
# here.
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$site_dir"

# forest always spawns `forester` from PATH with the options given after `--`,
# which would pick up the ambient opam CLI and skip the root entry rewrite.
# Shim it so every rebuild runs this site's build instead.
shim_dir=$(mktemp -d)
trap 'rm -rf "$shim_dir"' EXIT INT TERM

cat > "$shim_dir/forester" <<EOF
#!/bin/sh
exec sh "$site_dir/build.sh" forest
EOF
chmod +x "$shim_dir/forester"

PATH="$shim_dir:$PATH" "$HOME/.cargo/bin/forest" watch -- "build forest.toml"
