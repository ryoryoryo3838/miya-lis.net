(lang dune 3.22)
(name miya-forest)

; Installed with opam: opam install forester.6.0 js_of_ocaml js_of_ocaml-ppx
(package
 (name miya-forest)
 (allow_empty)
 (depends
  (ocaml (>= 5.4))
  js_of_ocaml
  js_of_ocaml-ppx
  (forester (= 6.0))))
