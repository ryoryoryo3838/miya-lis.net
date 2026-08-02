module SpanMap = Map.Make(Span)

type t = string SpanMap.t

let empty : t = SpanMap.empty

let add_asset (span : Span.t) ~routed_path (m : t) : t =
  SpanMap.add span routed_path m

let asset_route (m : t) (span : Span.t) : string option =
  SpanMap.find_opt span m
