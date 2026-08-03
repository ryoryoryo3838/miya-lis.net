let is_local_image dest =
  let len = String.length dest in
  not ((len >= 7 && String.sub dest 0 7 = "http://")
    || (len >= 8 && String.sub dest 0 8 = "https://"))

let rec collect_inline_refs inlines acc_refs acc_assets =
  List.fold_left (fun (refs, assets) (il : Ir.inline) ->
    match il.Ir.node with
    | Ir.Wiki_link { target; _ } ->
      ({ Ir.kind = Ir.Wiki; target; span = il.Ir.span } :: refs, assets)
    | Ir.Wiki_embed target ->
      ({ Ir.kind = Ir.Embed; target; span = il.Ir.span } :: refs, assets)
    | Ir.Image { destination; _ } ->
      let assets' =
        if is_local_image destination then
          { Parsed_document.destination; span = il.Ir.span } :: assets
        else assets
      in
      (refs, assets')
    | Ir.Emphasis inlines ->
      collect_inline_refs inlines refs assets
    | Ir.Strong inlines ->
      collect_inline_refs inlines refs assets
    | Ir.Link { label; _ } ->
      collect_inline_refs label refs assets
    | _ -> (refs, assets)
  ) (acc_refs, acc_assets) inlines

and collect_block_refs blocks acc_refs acc_assets =
  List.fold_left (fun (refs, assets) (b : Ir.block) ->
    match b.Ir.bnode with
    | Ir.Paragraph inlines ->
      collect_inline_refs inlines refs assets
    | Ir.Blockquote inner ->
      collect_block_refs inner refs assets
    | Ir.List { items; _ } ->
      List.fold_left (fun (r, a) (item : Ir.list_item) ->
        collect_block_refs item.Ir.item_blocks r a
      ) (refs, assets) items
    | Ir.Block_embed target ->
      ({ Ir.kind = Ir.Embed; target; span = b.Ir.bspan } :: refs, assets)
    | Ir.Heading { title; _ } ->
      collect_inline_refs title refs assets
    | _ -> (refs, assets)
  ) (acc_refs, acc_assets) blocks

and collect_section_refs (sections : Outline.section list) acc_refs acc_assets =
  List.fold_left (fun (refs, assets) (sec : Outline.section) ->
    let refs', assets' = collect_block_refs sec.Outline.body refs assets in
    let refs'', assets'' =
      collect_section_refs sec.Outline.children refs' assets'
    in
    (refs'', assets'')
  ) (acc_refs, acc_assets) sections

let collect_meta_refs (meta : Ir.inline list Metadata.t) =
  let from_attributions kind attrs =
    List.filter_map (fun (attr : Metadata.attribution) ->
      match attr with
      | Metadata.Tree { Metadata.value = target; span } ->
        Some { Ir.kind; target; span }
      | Metadata.Literal _ -> None
    ) attrs
  in
  let author_refs = from_attributions Ir.Attribution meta.Metadata.authors in
  let contrib_refs = from_attributions Ir.Attribution meta.Metadata.contributors in
  author_refs @ contrib_refs

let parse ~root_id source =
  match Frontmatter.parse source with
  | Error fm_diags ->
    Error (List.sort Diagnostic.compare fm_diags)
  | Ok fm ->
    let raw_metadata = fm.Frontmatter.metadata in
    match Markdown.parse source ~masked_markdown:fm.Frontmatter.masked_markdown raw_metadata with
    | Error md_diags ->
      Error (List.sort Diagnostic.compare md_diags)
    | Ok doc ->
      let meta = doc.Ir.metadata in
      match Outline.build ~root_id doc with
      | Error ol_diags ->
        Error (List.sort Diagnostic.compare ol_diags)
      | Ok tree ->
        let defs = Outline.definitions tree in
        let body_refs, body_assets = collect_block_refs tree.Outline.body [] [] in
        let section_refs, section_assets =
          collect_section_refs tree.Outline.sections [] [] in
        let meta_refs = collect_meta_refs meta in
        let refs = meta_refs @ body_refs @ section_refs in
        let assets = body_assets @ section_assets in
        Ok {
          Parsed_document.outline = tree;
          definitions = defs;
          references = refs;
          local_assets = assets;
        }

let emit ~resolution (doc : Parsed_document.t) =
  Forester_6.emit ~resolution doc.outline
