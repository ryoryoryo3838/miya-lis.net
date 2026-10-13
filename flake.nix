{
  description = "Pinned Dune environment for the source-only trusted site client";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/70ce234312134a463ba7728e94da2486a1d237ac";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            # OCaml 5.5.1 and js_of_ocaml 6.4.1 use the existing dune.lock.
            packages = with pkgs; [
              dune gnumake git pkg-config python3 autoconf automake patch
            ];
          };
        });
    };
}
