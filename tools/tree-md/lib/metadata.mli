type 'a located = { value : 'a; span : Span.t }
type attribution = Tree of string located | Literal of string located

type raw = {
  date : string located option;
  taxon : string located option;
  authors : attribution list;
  contributors : attribution list;
  tags : string located list;
  meta : (string located * string located) list;
}

val empty : raw
val valid_id : string -> bool
val parse_attribution : string located -> (attribution, Diagnostic.t) result
val valid_date : string -> bool
