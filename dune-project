(lang dune 3.22)
(name miya-forest)

(pin
 (url "git+https://git.sr.ht/~jonsterling/ocaml-forester#5.0")
 (package (name forester) (version "5.0")))

(package
 (name miya-forest)
 (allow_empty)
 (depends
  (ocaml (>= 5.3))
  js_of_ocaml
  js_of_ocaml-ppx
  forester))
