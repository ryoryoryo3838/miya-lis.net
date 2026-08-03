val parse : root_id:string -> Source.t -> (Parsed_document.t, Diagnostic.t list) result

val emit :
  resolution:Resolution.t -> Parsed_document.t ->
  (string, Diagnostic.t list) result
