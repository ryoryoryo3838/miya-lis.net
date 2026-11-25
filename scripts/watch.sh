#!/bin/sh
# Serve the forest on http://localhost:8080 and rebuild it whenever a tree
# changes.
#
# forest only watches *.tree files, so `build.sh snapshot DIR` rewriting
# trees/ is what triggers a rebuild here.
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$script_dir/.."

# forest always spawns `forester` from PATH with the options given after `--`,
# which would pick up the ambient opam CLI and skip decorate.py. Shim it so
# every rebuild runs this site's build instead. build.sh also finds forester on
# PATH, so it is told the real one first, or it would find the shim.
FORESTER=${FORESTER:-$(command -v forester || true)}
export FORESTER
shim_dir=$(mktemp -d)
trap 'rm -rf "$shim_dir"' EXIT INT TERM

cat > "$shim_dir/forester" <<EOF
#!/bin/sh
exec sh "$script_dir/build.sh" forest
EOF
chmod +x "$shim_dir/forester"

PATH="$shim_dir:$PATH" "$HOME/.cargo/bin/forest" watch -- "build forest.toml"
