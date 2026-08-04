type t

val empty : t
val add_asset : Span.t -> routed_path:string -> t -> t
val asset_route : t -> Span.t -> string option
