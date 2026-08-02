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
  Dom_html.document##.onkeydown := Dom_html.handler (fun ev ->
    if ev##.keyCode = 27 then begin
      close_panel ();
      Js._false
    end else
      Js._true
  )

(* ── Period scroll pinning ── *)
let setup_period_pin () =
  let period = get_element "hero-period" in

  let on_scroll () =
    let period_rect = period##getBoundingClientRect in
    (* Pin the period when its top reaches the viewport top *)
    if Js.to_float period_rect##.top <= 0. then begin
      add_class period "is-fixed"
    end else begin
      remove_class period "is-fixed"
    end
  in

  (* Throttled scroll handler *)
  let ticking = ref false in
  Dom_html.window##.onscroll := Dom_html.handler (fun _ev ->
    if not !ticking then begin
      ticking := true;
      ignore (Dom_html.window##requestAnimationFrame (Js.wrap_callback (fun _ ->
        on_scroll ();
        ticking := false
      )))
    end;
    Js._true
  )

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
