let target = "forester-6.0"

(* ── Escaping ── *)

let escape_char buf c =
  match c with
  | '%' -> Buffer.add_char buf '\\'; Buffer.add_char buf '%'
  | '\\' -> Buffer.add_string buf "\\verbFMD|\\FMD"
  | '#' -> Buffer.add_string buf "\\verbFMD|#FMD"
  | '{' -> Buffer.add_string buf "\\verbFMD|{FMD"
  | '}' -> Buffer.add_string buf "\\verbFMD|}FMD"
  | '[' -> Buffer.add_string buf "\\verbFMD|[FMD"
  | ']' -> Buffer.add_string buf "\\verbFMD|]FMD"
  | '(' -> Buffer.add_string buf "\\verbFMD|(FMD"
  | ')' -> Buffer.add_string buf "\\verbFMD|)FMD"
  | _ -> Buffer.add_char buf c

let escape_string s =
  let buf = Buffer.create (String.length s * 2) in
  String.iter (escape_char buf) s;
  Buffer.contents buf

let escape_text_for_test = escape_string

(* ── TeX validation ── *)

let validate_tex tex =
  let len = String.length tex in
  let depth = ref 0 in
  let i = ref 0 in
  while !i < len do
    match tex.[!i] with
    | '\\' when !i + 1 < len ->
      incr i;
      (match tex.[!i] with
       | '{' | '}' -> incr i
       | c when (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ->
         incr i;
         while !i < len && ((tex.[!i] >= 'A' && tex.[!i] <= 'Z')
                         || (tex.[!i] >= 'a' && tex.[!i] <= 'z')) do
           incr i
         done
       | _ -> incr i)
    | '{' -> incr depth; incr i
    | '}' -> decr depth; incr i
    | _ -> incr i
  done;
  !depth = 0

(* ── Writer record ── *)

type writer = {
  errors : Diagnostic.t list ref;
  resolution : Resolution.t;
  text : Buffer.t -> string -> unit;
  safe_id : Buffer.t -> string -> unit;
  uri_text : Buffer.t -> string -> unit;
  xml_attr : Buffer.t -> string -> (Buffer.t -> unit) -> unit;
  meta_key : Buffer.t -> string -> unit;
  tex : Span.t -> Buffer.t -> string -> unit;
}

let make_writer errors resolution =
  let text buf s = String.iter (escape_char buf) s in
  let safe_id buf s = String.iter (fun c -> Buffer.add_char buf c) s in
  let uri_text buf s = String.iter (escape_char buf) s in
  let xml_attr buf name write_value =
    Buffer.add_char buf '[';
    safe_id buf name;
    Buffer.add_char buf ']';
    Buffer.add_char buf '{';
    write_value buf;
    Buffer.add_char buf '}'
  in
  let meta_key buf s = safe_id buf s in
  let tex span buf s =
    if validate_tex s then
      safe_id buf s
    else begin
      let msg = "unbalanced TeX braces" in
      let diag = Diagnostic.make TM107 (Span.Source_span span) msg in
      errors := diag :: !errors;
      safe_id buf s
    end
  in
  { errors; resolution; text; safe_id; uri_text; xml_attr; meta_key; tex }

(* ── Inline emission ── *)

let rec emit_inlines (w : writer) buf (inlines : Ir.inline list) =
  List.iter (fun (il : Ir.inline) ->
    emit_inline_node w buf il.node il.span
  ) inlines

and emit_inline_node (w : writer) buf (node : Ir.inline_node) span =
  match node with
  | Ir.Text s -> w.text buf s
  | Ir.Emphasis inlines ->
    Buffer.add_string buf "\\em{";
    emit_inlines w buf inlines;
    Buffer.add_char buf '}'
  | Ir.Strong inlines ->
    Buffer.add_string buf "\\strong{";
    emit_inlines w buf inlines;
    Buffer.add_char buf '}'
  | Ir.Code s ->
    Buffer.add_string buf "\\code{";
    w.safe_id buf s;
    Buffer.add_char buf '}'
  | Ir.Link { label; destination; title } ->
    emit_link w buf label destination title span
  | Ir.Wiki_link { target; alias } ->
    (match alias with
     | Some a ->
       Buffer.add_string buf "\\link[";
       w.text buf a;
       Buffer.add_string buf "]{";
       w.safe_id buf target;
       Buffer.add_char buf '}'
     | None ->
       Buffer.add_string buf "\\link{";
       w.safe_id buf target;
       Buffer.add_char buf '}')
  | Ir.Wiki_embed target ->
    Buffer.add_string buf "\\transclude{";
    w.safe_id buf target;
    Buffer.add_char buf '}'
  | Ir.Math { tex; display = _ } ->
    Buffer.add_string buf "\\math{";
    w.tex span buf tex;
    Buffer.add_char buf '}'
  | Ir.Image { alt; destination; title } ->
    emit_image w buf alt destination title span
  | Ir.Hard_break ->
    Buffer.add_string buf "\\break\n"
  | Ir.Soft_break ->
    Buffer.add_char buf ' '

and emit_link w buf label destination title span =
  let is_external =
    String.length destination >= 7
    && (String.sub destination 0 7 = "http://"
     || String.length destination >= 8 && String.sub destination 0 8 = "https://"
     || String.length destination >= 7 && String.sub destination 0 7 = "mailto:")
  in
  if is_external then begin
    Buffer.add_string buf "\\<html:a>";
    w.xml_attr buf "href" (fun b -> w.uri_text b destination);
    (match title with
     | Some t ->
       Buffer.add_string buf "[title]{";
       w.text buf t;
       Buffer.add_char buf '}'
     | None -> ());
    Buffer.add_char buf '{';
    emit_inlines w buf label;
    Buffer.add_char buf '}'
  end else begin
    let msg = "local link in Forester emission (use wiki link syntax)" in
    let diag = Diagnostic.make TM106 (Span.Source_span span) msg in
    let errs = w.errors in
    errs := diag :: !errs;
    Buffer.add_char buf '{';
    emit_inlines w buf label;
    Buffer.add_char buf '}'
  end

and emit_image w buf alt destination title span =
  let is_external =
    String.length destination >= 8
    && String.sub destination 0 8 = "https://"
  in
  if is_external then begin
    Buffer.add_string buf "\\<html:img>";
    w.xml_attr buf "src" (fun b -> w.uri_text b destination);
    let alt_text = flatten_alt w alt in
    Buffer.add_string buf "[alt]{";
    w.text buf alt_text;
    Buffer.add_char buf '}';
    (match title with
     | Some t ->
       Buffer.add_string buf "[title]{";
       w.text buf t;
       Buffer.add_char buf '}'
     | None -> ())
  end else begin
    match Resolution.asset_route w.resolution span with
    | Some routed ->
      Buffer.add_string buf "\\route-asset{";
      w.text buf routed;
      Buffer.add_char buf '}'
    | None ->
      let msg = "unresolved local image (no route-asset mapping)" in
      let diag = Diagnostic.make TM106 (Span.Source_span span) msg in
      let errs = w.errors in
      errs := diag :: !errs
  end

and flatten_alt (w : writer) (inlines : Ir.inline list) : string =
  let buf = Buffer.create 64 in
  let rec go = function
    | [] -> ()
    | { Ir.node = Ir.Text s; _ } :: rest ->
      w.text buf s;
      go rest
    | { Ir.node = Ir.Code s; _ } :: rest ->
      w.safe_id buf s;
      go rest
    | { Ir.node = Ir.Emphasis is; _ } :: rest ->
      go (is @ rest)
    | { Ir.node = Ir.Strong is; _ } :: rest ->
      go (is @ rest)
    | { Ir.node = Ir.Link { label; _ }; _ } :: rest ->
      go (label @ rest)
    | { Ir.node = Ir.Wiki_link { target; alias }; _ } :: rest ->
      (match alias with
       | Some a -> w.text buf a
       | None -> w.text buf target);
      go rest
    | { Ir.node = Ir.Math { tex; _ }; _ } :: rest ->
      w.text buf tex;
      go rest
    | { Ir.node = (Ir.Hard_break | Ir.Soft_break); _ } :: rest ->
      Buffer.add_char buf ' ';
      go rest
    | { Ir.node = Ir.Image _; Ir.span = ispan } :: _ ->
      let msg = "nested image in alt text" in
      let diag = Diagnostic.make TM106 (Span.Source_span ispan) msg in
      let errs = w.errors in
      errs := diag :: !errs
    | { Ir.node = Ir.Wiki_embed _; Ir.span = wspan } :: _ ->
      let msg = "wiki embed in alt text" in
      let diag = Diagnostic.make TM106 (Span.Source_span wspan) msg in
      let errs = w.errors in
      errs := diag :: !errs
  in
  go inlines;
  Buffer.contents buf

(* ── Block emission ── *)

let rec emit_block (w : writer) buf (block : Ir.block) =
  match block.Ir.bnode with
  | Ir.Paragraph inlines ->
    Buffer.add_string buf "\\p{";
    emit_inlines w buf inlines;
    Buffer.add_char buf '}'
  | Ir.Blockquote blocks ->
    Buffer.add_string buf "\\blockquote{";
    emit_blocks_body w buf blocks;
    Buffer.add_char buf '}'
  | Ir.List { kind; tight; items } ->
    emit_list w buf kind tight items
  | Ir.Code_block { info; code } ->
    emit_code_block w buf info code
  | Ir.Thematic_break ->
    Buffer.add_string buf "---"
  | Ir.Heading { level = _; title = _ } ->
    ()
  | Ir.Subtree_directive _ ->
    ()
  | Ir.Block_embed id ->
    Buffer.add_string buf "\\transclude{";
    w.safe_id buf id;
    Buffer.add_char buf '}'
  | Ir.Display_math tex ->
    Buffer.add_string buf "\\\\[";
    w.tex block.Ir.bspan buf tex;
    Buffer.add_char buf ']'

and emit_blocks_body (w : writer) buf (blocks : Ir.block list) =
  let rec loop = function
    | [] -> ()
    | [b] -> emit_block w buf b
    | b :: rest ->
      emit_block w buf b;
      Buffer.add_string buf "\n\n";
      loop rest
  in
  loop blocks

and emit_list (w : writer) buf kind tight (items : Ir.list_item list) =
  let start_attr = match kind with
    | Ir.Ordered n when n <> 1 -> Some n
    | _ -> None
  in
  let rec emit_items b sep first items =
    match items with
    | [] -> ()
    | [item] ->
      if not first then Buffer.add_string b sep;
      emit_list_item w b tight item.Ir.item_blocks
    | item :: rest ->
      if not first then Buffer.add_string b sep;
      emit_list_item w b tight item.Ir.item_blocks;
      emit_items b sep false rest
  in
  match start_attr with
  | Some n ->
    Buffer.add_string buf "\\<html:ol>";
    Buffer.add_string buf "[start]{";
    Buffer.add_string buf (string_of_int n);
    Buffer.add_string buf "}{";
    emit_items buf "" true items;
    Buffer.add_char buf '}'
  | None ->
    emit_items buf "\n" true items

and emit_list_item (w : writer) buf tight (blocks : Ir.block list) =
  Buffer.add_string buf "\\li{";
  (match blocks with
   | [Ir.{ bnode = Ir.Paragraph inlines; _ }] when tight ->
     emit_inlines w buf inlines
   | _ ->
     emit_blocks_inside_li w buf tight blocks);
  Buffer.add_char buf '}'

and emit_blocks_inside_li (w : writer) buf tight (blocks : Ir.block list) =
  let rec loop = function
    | [] -> ()
    | [Ir.{ bnode = Ir.Paragraph inlines; _ }] when not tight ->
      Buffer.add_string buf "\\p{";
      emit_inlines w buf inlines;
      Buffer.add_char buf '}'
    | [b] -> emit_block w buf b
    | Ir.{ bnode = Ir.Paragraph inlines; _ } :: rest when not tight ->
      Buffer.add_string buf "\\p{";
      emit_inlines w buf inlines;
      Buffer.add_char buf '}';
      Buffer.add_string buf "\n";
      loop rest
    | b :: rest ->
      emit_block w buf b;
      Buffer.add_string buf "\n";
      loop rest
  in
  loop blocks

and emit_code_block (w : writer) buf info code =
  Buffer.add_string buf "\\<html:pre>";
  (match info with
   | Ir.Language lang ->
     Buffer.add_string buf "[class]{language-";
     w.text buf lang;
     Buffer.add_char buf '}'
   | Ir.No_info -> ());
  Buffer.add_string buf "{\\<html:code>{";
  w.safe_id buf code;
  Buffer.add_string buf "}}"

(* ── Metadata emission ── *)

let emit_attribution_inline w buf (attr : Metadata.attribution) =
  match attr with
  | Metadata.Literal { Metadata.value = name; _ } ->
    w.text buf name
  | Metadata.Tree { Metadata.value = id; _ } ->
    Buffer.add_string buf "\\tree{";
    w.safe_id buf id;
    Buffer.add_char buf '}'

let emit_title_inlines w buf (inlines : Ir.inline list) =
  Buffer.add_string buf "\\title{";
  emit_inlines w buf inlines;
  Buffer.add_char buf '}';
  Buffer.add_char buf '\n'

let emit_metadata (w : writer) buf (meta : Ir.inline list Metadata.t) =
  (match meta.Metadata.date with
   | Some { Metadata.value = d; _ } ->
     Buffer.add_string buf "\\date{";
     w.text buf d;
     Buffer.add_string buf "}\n"
   | None -> ());
  (match meta.Metadata.taxon with
   | Some { Metadata.value = t; _ } ->
     Buffer.add_string buf "\\taxon{";
     w.text buf t;
     Buffer.add_string buf "}\n"
   | None -> ());
  List.iter (fun attr ->
    Buffer.add_string buf "\\author{";
    emit_attribution_inline w buf attr;
    Buffer.add_string buf "}\n"
  ) meta.Metadata.authors;
  List.iter (fun attr ->
    Buffer.add_string buf "\\contributor{";
    emit_attribution_inline w buf attr;
    Buffer.add_string buf "}\n"
  ) meta.Metadata.contributors;
  List.iter (fun { Metadata.value = inlines; _ } ->
    Buffer.add_string buf "\\tag{";
    emit_inlines w buf inlines;
    Buffer.add_string buf "}\n"
  ) meta.Metadata.tags;
  List.iter (fun ({ Metadata.value = key; _ },
                  { Metadata.value = inlines; _ }) ->
    Buffer.add_string buf "\\meta{";
    w.meta_key buf key;
    Buffer.add_string buf "}{";
    emit_inlines w buf inlines;
    Buffer.add_string buf "}\n"
  ) meta.Metadata.meta

(* ── Section emission ── *)

let rec emit_sections (w : writer) buf (sections : Outline.section list) =
  let rec loop first remaining =
    match remaining with
    | [] -> ()
    | s :: rest ->
      if not first then Buffer.add_char buf '\n';
      emit_section w buf s;
      Buffer.add_char buf '\n';
      loop false rest
  in
  loop true sections

and emit_section (w : writer) buf (sec : Outline.section) =
  Buffer.add_string buf "\\section{";
  (match sec.Outline.id with
   | Some id ->
     w.safe_id buf id;
     Buffer.add_string buf "}{";
     emit_inlines w buf sec.Outline.title;
     Buffer.add_string buf "}{"
   | None ->
     emit_inlines w buf sec.Outline.title;
     Buffer.add_string buf "}{");
  let has_content = sec.Outline.body <> [] || sec.Outline.children <> [] in
  if has_content then begin
    Buffer.add_char buf '\n';
    let first = ref true in
    List.iter (fun b ->
      if !first then first := false
      else Buffer.add_string buf "\n\n";
      emit_block w buf b
    ) sec.Outline.body;
    List.iter (fun child ->
      if not (sec.Outline.body = []) || not !first then
        Buffer.add_string buf "\n\n";
      first := false;
      emit_section w buf child
    ) sec.Outline.children;
    Buffer.add_char buf '\n'
  end;
  Buffer.add_char buf '}'

(* ── Top-level block emission ── *)

let emit_blocks_top (w : writer) buf (blocks : Ir.block list) =
  let rec loop first remaining =
    match remaining with
    | [] -> ()
    | b :: rest ->
      if not first then Buffer.add_char buf '\n';
      emit_block w buf b;
      Buffer.add_char buf '\n';
      loop false rest
  in
  loop true blocks

(* ── Main emit ── *)

let emit ~(resolution : Resolution.t) (tree : Outline.t) =
  let errors = ref [] in
  let w = make_writer errors resolution in
  let buf = Buffer.create 4096 in

  emit_title_inlines w buf tree.Outline.title;

  let has_meta =
    tree.Outline.metadata.Metadata.date <> None
    || tree.Outline.metadata.Metadata.taxon <> None
    || tree.Outline.metadata.Metadata.authors <> []
    || tree.Outline.metadata.Metadata.contributors <> []
    || tree.Outline.metadata.Metadata.tags <> []
    || tree.Outline.metadata.Metadata.meta <> []
  in
  emit_metadata w buf tree.Outline.metadata;

  let has_body = tree.Outline.body <> [] in
  let has_sections = tree.Outline.sections <> [] in
  if has_body || has_sections then begin
    if has_meta then Buffer.add_char buf '\n';
    if has_body then emit_blocks_top w buf tree.Outline.body;
    if has_sections then begin
      if has_body then Buffer.add_char buf '\n';
      emit_sections w buf tree.Outline.sections
    end
  end;

  let out = Buffer.contents buf in
  let errs = List.rev !errors in
  if errs = [] then Ok out
  else Error errs
