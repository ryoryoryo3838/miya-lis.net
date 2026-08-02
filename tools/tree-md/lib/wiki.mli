type kind = Link | Embed

type candidate = {
  kind : kind;
  target : string;
  alias : string option;
  whole_span : Span.t;
  inner_span : Span.t;
}

type shape =
  | Text_shape of Span.t
  | Code_shape of Span.t
  | Shortcut_shape of candidate
  | Ordinary_link_shape of Span.t

val resolver : Source.t -> Cmarkit.Label.resolver
val shapes_for_test : Source.t -> string -> ((shape list * Diagnostic.t list), Diagnostic.t list) result
