(* Convert Cmarkit's inclusive Textloc to half-open Span.t *)
let textloc_to_span source_path base_byte tloc =
  let fb = Cmarkit.Textloc.first_byte tloc + base_byte in
  let lb = Cmarkit.Textloc.last_byte tloc + base_byte in
  match Span.make ~path:source_path ~start_byte:fb ~end_byte:(lb + 1) with
  | Ok span -> span
  | Error _ ->
    { Span.path = source_path; start_byte = fb; end_byte = lb + 1 }

let meta_span source_path base_byte meta =
  let tloc = Cmarkit.Meta.textloc meta in
  if Cmarkit.Textloc.is_none tloc then
    { Span.path = source_path; start_byte = 0; end_byte = 0 }
  else
    textloc_to_span source_path base_byte tloc

let node_text (n : string Cmarkit.node) : string = fst n

(* Make a span from raw byte positions *)
let make_span source_path base_byte first last =
  match Span.make ~path:source_path
          ~start_byte:(first + base_byte)
          ~end_byte:(last + 1 + base_byte) with
  | Ok s -> s
  | Error _ ->
    { Span.path = source_path;
      start_byte = first + base_byte;
      end_byte = last + 1 + base_byte }

(* Extract destination string from link definition *)
let link_dest (def : Cmarkit.Link_definition.t) : string =
  match Cmarkit.Link_definition.dest def with
  | Some dest_node -> node_text dest_node
  | None -> ""

(* Extract title string from link definition *)
let link_title (def : Cmarkit.Link_definition.t) : string option =
  match Cmarkit.Link_definition.title def with
  | Some lines ->
    let s = String.concat " " (List.map (fun (str, _layout) -> str) lines) in
    if s = "" then None else Some s
  | None -> None

(* Construct an empty link definition for unresolved references *)
let empty_link_def () =
  Cmarkit.Link_definition.make ()

(* Resolve a reference link against doc defs *)
let resolve_link_ref defs link =
  match Cmarkit.Inline.Link.reference_definition defs link with
  | Some (Cmarkit.Link_definition.Def def_node) ->
    Some (fst def_node)
  | _ -> None

let rec lower_inlines source_path base_byte defs inline acc_inlines acc_diags =
  match inline with
  | Cmarkit.Inline.Inlines (inlines, _meta) ->
    List.fold_left (fun (ins, diags) i ->
      lower_inlines source_path base_byte defs i ins diags
    ) (acc_inlines, acc_diags) inlines

  | Cmarkit.Inline.Text (_text, meta) ->
    let span = meta_span source_path base_byte meta in
    let text = node_text (_text, meta) in
    let node = Ir.Text text in
    if text = "" then
      (acc_inlines, acc_diags)
    else
      ({ Ir.node; span } :: acc_inlines, acc_diags)

  | Cmarkit.Inline.Code_span (cs, meta) ->
    let span = meta_span source_path base_byte meta in
    let code = Cmarkit.Inline.Code_span.code cs in
    let node = Ir.Code code in
    ({ Ir.node; span } :: acc_inlines, acc_diags)

  | Cmarkit.Inline.Emphasis (em, meta) ->
    let span = meta_span source_path base_byte meta in
    let inner = Cmarkit.Inline.Emphasis.inline em in
    let children, diags = lower_inlines source_path base_byte defs inner [] [] in
    let node = Ir.Emphasis (List.rev children) in
    ({ Ir.node; span } :: acc_inlines, acc_diags @ diags)

  | Cmarkit.Inline.Strong_emphasis (em, meta) ->
    let span = meta_span source_path base_byte meta in
    let inner = Cmarkit.Inline.Emphasis.inline em in
    let children, diags = lower_inlines source_path base_byte defs inner [] [] in
    let node = Ir.Strong (List.rev children) in
    ({ Ir.node; span } :: acc_inlines, acc_diags @ diags)

  | Cmarkit.Inline.Link (link, meta) ->
    let span = meta_span source_path base_byte meta in
    let link_text = Cmarkit.Inline.Link.text link in
    let children, diags = lower_inlines source_path base_byte defs link_text [] [] in
    begin match Cmarkit.Inline.Link.reference link with
    | `Ref (`Shortcut, _source_label, def_label) ->
      let def_meta = Cmarkit.Label.meta def_label in
      (match Cmarkit.Meta.find Wiki.wiki_meta_key def_meta with
       | Some info ->
         let target, alias = Wiki.parse_wiki_body info.Wiki.wiki_body in
         let ws = make_span source_path base_byte
                    info.Wiki.whole_first_byte
                    info.Wiki.whole_last_byte in
         begin match info.Wiki.wiki_kind with
         | Wiki.Link ->
           let node = Ir.Wiki_link { target; alias } in
           ({ Ir.node; span = ws } :: acc_inlines, acc_diags @ diags)
         | Wiki.Embed ->
           let node = Ir.Wiki_embed target in
           ({ Ir.node; span = ws } :: acc_inlines, acc_diags @ diags)
         end
       | None ->
         (match resolve_link_ref defs link with
          | Some def ->
            let dest = link_dest def in
            let title = link_title def in
            let node = Ir.Link { label = List.rev children; destination = dest; title } in
            ({ Ir.node; span } :: acc_inlines, acc_diags @ diags)
          | None ->
            let node = Ir.Link { label = List.rev children; destination = ""; title = None } in
            ({ Ir.node; span } :: acc_inlines, acc_diags @ diags))
      )
    | `Ref _ ->
      (match resolve_link_ref defs link with
       | Some def ->
         let dest = link_dest def in
         let title = link_title def in
         let node = Ir.Link { label = List.rev children; destination = dest; title } in
         ({ Ir.node; span } :: acc_inlines, acc_diags @ diags)
       | None ->
         let node = Ir.Link { label = List.rev children; destination = ""; title = None } in
         ({ Ir.node; span } :: acc_inlines, acc_diags @ diags))
    | `Inline def_node ->
      let def = fst def_node in
      let dest = link_dest def in
      let title = link_title def in
      let node = Ir.Link { label = List.rev children; destination = dest; title } in
      ({ Ir.node; span } :: acc_inlines, acc_diags @ diags)
    end

  | Cmarkit.Inline.Image (link, meta) ->
    let span = meta_span source_path base_byte meta in
    let alt_inline = Cmarkit.Inline.Link.text link in
    let alt_children, diags = lower_inlines source_path base_byte defs alt_inline [] [] in
    let def =
      match Cmarkit.Inline.Link.reference link with
      | `Inline def_node -> fst def_node
      | `Ref _ ->
        (match resolve_link_ref defs link with
         | Some def -> def
         | None -> empty_link_def ())
    in
    let dest = link_dest def in
    let title = link_title def in
    let node = Ir.Image { alt = List.rev alt_children; destination = dest; title } in
    ({ Ir.node; span } :: acc_inlines, acc_diags @ diags)

  | Cmarkit.Inline.Autolink (al, meta) ->
    let span = meta_span source_path base_byte meta in
    let url = node_text (Cmarkit.Inline.Autolink.link al) in
    let dest = if Cmarkit.Inline.Autolink.is_email al then "mailto:" ^ url else url in
    let label_node = Ir.Text url in
    let lbl_span = span in
    let node = Ir.Link { label = [{ Ir.node = label_node; span = lbl_span }]; destination = dest; title = None } in
    ({ Ir.node; span } :: acc_inlines, acc_diags)

  | Cmarkit.Inline.Break (br, meta) ->
    let span = meta_span source_path base_byte meta in
    let node = match Cmarkit.Inline.Break.type' br with
      | `Hard -> Ir.Hard_break
      | `Soft -> Ir.Soft_break
    in
    ({ Ir.node; span } :: acc_inlines, acc_diags)

  | Cmarkit.Inline.Ext_math_span (ms, meta) ->
    let span = meta_span source_path base_byte meta in
    let tex = Cmarkit.Inline.Math_span.tex ms in
    let display = Cmarkit.Inline.Math_span.display ms in
    let node = Ir.Math { tex; display } in
    ({ Ir.node; span } :: acc_inlines, acc_diags)

  | Cmarkit.Inline.Raw_html (_html, meta) ->
    let span = meta_span source_path base_byte meta in
    let diag = Diagnostic.make TM102 (Span.Source_span span)
      "raw HTML is not supported" in
    (acc_inlines, diag :: acc_diags)

  | Cmarkit.Inline.Ext_strikethrough (_st, meta) ->
    let span = meta_span source_path base_byte meta in
    let diag = Diagnostic.make TM102 (Span.Source_span span)
      "strikethrough is not supported" in
    (acc_inlines, diag :: acc_diags)

  (* Any unrecognized extension inline: reject with TM102 *)
  | _ ->
    let diag = Diagnostic.make TM102 Span.No_location
      "unsupported Markdown extension" in
    (acc_inlines, diag :: acc_diags)

(* Filter out Text nodes that are fully contained within wiki/embed spans.
   These are the `[` and `]` wrapper characters from the raw source
   that surround wiki shortcut links in the Cmarkit AST. *)
let filter_wiki_wrappers inlines =
  let wiki_spans = List.filter_map (fun i ->
    match i.Ir.node with
    | Ir.Wiki_link _ | Ir.Wiki_embed _ -> Some i.Ir.span
    | _ -> None
  ) inlines in
  let is_within_wiki span =
    List.exists (fun ws ->
      span.Span.start_byte >= ws.Span.start_byte
      && span.Span.end_byte <= ws.Span.end_byte
    ) wiki_spans
  in
  List.filter (fun i ->
    match i.Ir.node with
    | Ir.Text _ ->
      not (is_within_wiki i.Ir.span)
    | _ -> true
  ) inlines

(* Walk block-level AST to extract all inlines *)
let rec extract_inlines source_path base_byte defs block acc_inlines acc_diags =
  match block with
  | Cmarkit.Block.Blocks (blocks, _meta) ->
    List.fold_left (fun (ins, diags) b ->
      extract_inlines source_path base_byte defs b ins diags
    ) (acc_inlines, acc_diags) blocks

  | Cmarkit.Block.Paragraph (p, _meta) ->
    let inline = Cmarkit.Block.Paragraph.inline p in
    lower_inlines source_path base_byte defs inline acc_inlines acc_diags

  | Cmarkit.Block.Heading (h, _meta) ->
    let inline = Cmarkit.Block.Heading.inline h in
    lower_inlines source_path base_byte defs inline acc_inlines acc_diags

  | Cmarkit.Block.Block_quote (bq, _meta) ->
    let inner = Cmarkit.Block.Block_quote.block bq in
    extract_inlines source_path base_byte defs inner acc_inlines acc_diags

  | Cmarkit.Block.List (l, _meta) ->
    let items = Cmarkit.Block.List'.items l in
    List.fold_left (fun (ins, diags) item_node ->
      let item, _meta = item_node in
      let inner = Cmarkit.Block.List_item.block item in
      extract_inlines source_path base_byte defs inner ins diags
    ) (acc_inlines, acc_diags) items

  | _ ->
    (acc_inlines, acc_diags)

let parse_inlines source text ~base_byte =
  let doc =
    Cmarkit.Doc.of_string ~locs:true ~strict:false
      ~resolver:(Wiki.resolver source) text
  in
  let block = Cmarkit.Doc.block doc in
  let defs = Cmarkit.Doc.defs doc in
  let path = Source.path source in
  let inlines, diags = extract_inlines path base_byte defs block [] [] in
  let filtered = filter_wiki_wrappers inlines in
  let sorted_inlines = List.rev filtered in
  let sorted_diags = List.rev diags in
  if sorted_diags = [] then
    Ok sorted_inlines
  else
    Error sorted_diags
