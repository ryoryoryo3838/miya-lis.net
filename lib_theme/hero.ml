open Js_of_ocaml

(* Helper: get element by id or fail *)
let get_element id =
  Js.Opt.get
    (Dom_html.document##getElementById (Js.string id))
    (fun () -> failwith ("element not found: " ^ id))

(* Helper: check if element has a CSS class *)
let has_class el cls =
  Js.to_bool (el##.classList##contains (Js.string cls))

(* Helper: add CSS class *)
let add_class el cls =
  el##.classList##add (Js.string cls)

(* Helper: remove CSS class *)
let remove_class el cls =
  el##.classList##remove (Js.string cls)

(* Helper: toggle CSS class *)
let toggle_class el cls =
  if has_class el cls then remove_class el cls else add_class el cls

(* ── Nav panel toggle ── *)
let setup_nav () =
  let period = get_element "hero-period" in
  let panel = get_element "nav-panel" in
  let overlay = get_element "nav-overlay" in

  let close_panel () =
    remove_class panel "is-open";
    remove_class overlay "is-visible";
    remove_class period "is-open"
  in

  (* Click period → toggle *)
  period##.onclick := Dom_html.handler (fun ev ->
    Dom.preventDefault ev;
    toggle_class panel "is-open";
    toggle_class overlay "is-visible";
    toggle_class period "is-open";
    Js._false
  );

  (* Click overlay → close *)
  overlay##.onclick := Dom_html.handler (fun _ev ->
    close_panel ();
    Js._false
  );

  (* Escape key → close *)
  Dom_html.addEventListener
    Dom_html.document (Dom.Event.make "keydown")
    (Dom_html.handler (fun ev ->
      if ev##.keyCode = 27 then begin
        close_panel ();
        Js._false
      end else
        Js._true
    )) Js._true
  |> ignore

(* ── Period scroll pinning: stop naturally at viewport top ── *)
let setup_period_pin () =
  let period = get_element "hero-period" in
  let hero = get_element "hero" in
  let is_fixed = ref false in
  let fixed_left = ref 0. in

  let on_scroll () =
    if not !is_fixed then begin
      let rect = period##getBoundingClientRect in
      let top = Js.to_float rect##.top in
      let height = Js.to_float rect##.height in
      (* Let .NET peek above viewport by ~15% of period height before pinning *)
      let threshold = -. (height *. 0.15) in
      if top <= threshold then begin
        (* Capture current horizontal position *)
        fixed_left := Js.to_float rect##.left;
        period##.style##.position := Js.string "fixed";
        (* Match natural visual position: period sits near x-height top, not at line top *)
        period##.style##.top := Js.string (Printf.sprintf "%.1fpx" (-.height *. 0.12));
        period##.style##.left := Js.string (Printf.sprintf "%.1fpx" !fixed_left);
        period##.style##.zIndex := Js.string "11";
        period##.classList##add (Js.string "is-fixed");
        is_fixed := true
      end
    end else begin
      let hero_rect = hero##getBoundingClientRect in
      if Js.to_float hero_rect##.bottom > 0. then begin
        period##.style##.position := Js.string "";
        period##.style##.top := Js.string "";
        period##.style##.left := Js.string "";
        period##.style##.zIndex := Js.string "";
        period##.classList##remove (Js.string "is-fixed");
        is_fixed := false
      end
    end
  in

  (* Throttled scroll handler *)
  let ticking = ref false in
  let handler _ev =
    if not !ticking then begin
      ticking := true;
      ignore (Dom_html.window##requestAnimationFrame (Js.wrap_callback (fun _ ->
        on_scroll ();
        ticking := false
      )))
    end;
    Js._true
  in
  Dom_html.addEventListener
    Dom_html.window (Dom.Event.make "scroll")
    (Dom_html.handler handler) Js._true
  |> ignore
  |> ignore

(* ── Intersection Observer: persistent header ── *)
let setup_header_observer () =
  let hero = get_element "hero" in
  let header = get_element "persistent-header" in

  (* Create IntersectionObserver via js_of_ocaml *)
  let callback entries _observer =
    let entry = Js.Optdef.get (Js.array_get entries 0) (fun () -> failwith "no entry") in
    if Js.to_bool (entry##.isIntersecting) then
      remove_class header "is-visible"
    else
      add_class header "is-visible"
  in

  let options =
    Js.Unsafe.obj [|
      ("threshold", Js.Unsafe.inject (Js.number_of_float 0.0))
    |]
  in

  let observer =
    Js.Unsafe.new_obj (Js.Unsafe.global##._IntersectionObserver)
      [| Js.Unsafe.inject (Js.wrap_callback callback); Js.Unsafe.inject options |]
  in

  ignore (observer##observe hero)

(* ── Main ── *)
let () =
  Dom_html.window##.onload := Dom_html.handler (fun _ ->
    setup_nav ();
    setup_period_pin ();
    setup_header_observer ();
    Js._false
  )
