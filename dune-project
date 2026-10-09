(lang dune 3.22)
(name miya-forest)

(pin
 (url "git+https://tangled.org/jonmsterling.com/ocaml-forester#f8fb5f5d88923db36643cf9c20c662adff969c98")
 (package (name forester) (version "6.0~dev")))

(package
 (name miya-forest)
 (allow_empty)
 (depends
  (ocaml (>= 5.4))
  js_of_ocaml
  js_of_ocaml-ppx
  forester))
