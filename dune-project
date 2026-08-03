(lang dune 3.22)
(name miya-forest)

(pin
 (url "forester")
 (package (name forester) (version "5.0")))

(package
 (name miya-forest)
 (depends
  (ocaml (>= 5.3))
  js_of_ocaml
  js_of_ocaml-ppx
  forester))
