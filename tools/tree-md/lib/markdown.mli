val parse_inlines :
  Source.t -> string -> base_byte:int ->
  (Ir.inline list, Diagnostic.t list) result
