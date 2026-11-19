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

(* Only a trusted home shell can make the root entry a landing page. Direct
   links to the configured home remain content pages unless #hero is explicit. *)
let is_home_mode () =
  let body = Dom_html.document##.body in
  let path = Js.to_string Dom_html.window##.location##.pathname in
  Js.to_string Dom_html.window##.location##.hash = "#hero"
  || (has_class body "miya-home" && (path = "/" || path = "/index.html"))

let disable_hero () =
  let hero = get_element "hero" in
  let body = Dom_html.document##.body in
  hero##.style##.display := Js.string "none";
  remove_class body "hero-page"

(* ── Nav panel toggle ── *)
let focus element =
  ignore (Js.Unsafe.meth_call element "focus" [||])

let nav_toggles () =
  let selector =
    if has_class Dom_html.document##.body "miya-native" then
      "body > #nav-toggle-global.nav-toggle, #hero-period.nav-toggle"
    else ".nav-toggle"
  in
  Dom.list_of_nodeList
    (Dom_html.document##querySelectorAll (Js.string selector))

let setup_nav () =
  let panel = get_element "nav-panel" in
  let overlay = get_element "nav-overlay" in
  let toggles = nav_toggles () in
  let opener = ref None in
  let set_open ?(restore_focus = true) open_ =
    let update element class_name =
      if open_ then add_class element class_name else remove_class element class_name
    in
    update panel "is-open";
    update overlay "is-visible";
    List.iter (fun toggle ->
      update toggle "is-open";
      toggle##setAttribute (Js.string "aria-expanded") (Js.string (string_of_bool open_));
      toggle##setAttribute (Js.string "aria-label")
        (Js.string (if open_ then "Close navigation" else "Open navigation"))) toggles;
    panel##setAttribute (Js.string "aria-hidden") (Js.string (string_of_bool (not open_)));
    if open_ then begin
      panel##removeAttribute (Js.string "hidden");
      panel##removeAttribute (Js.string "inert");
      let first = panel##querySelector (Js.string "button, a[href]") in
      Js.Opt.iter first focus
    end else begin
      panel##setAttribute (Js.string "hidden") (Js.string "");
      panel##setAttribute (Js.string "inert") (Js.string "");
      if restore_focus then Option.iter focus !opener
    end
  in
  List.iter (fun toggle ->
    toggle##.onclick := Dom_html.handler (fun ev ->
      Dom.preventDefault ev;
      opener := Some toggle;
      set_open (not (has_class panel "is-open"));
      Js._false)) toggles;
  overlay##.onclick := Dom_html.handler (fun _ -> set_open false; Js._false);
  Js.Opt.iter (Dom_html.document##getElementById (Js.string "nav-close"))
    (fun close -> close##.onclick := Dom_html.handler (fun _ -> set_open false; Js._false));
  Dom.list_of_nodeList (panel##querySelectorAll (Js.string "a[href]"))
  |> List.iter (fun link ->
      link##.onclick := Dom_html.handler (fun _ ->
        set_open ~restore_focus:false false;
        Js._true));
  ignore (Dom_html.addEventListener Dom_html.document (Dom.Event.make "keydown")
    (Dom_html.handler (fun ev ->
      if (ev##.keyCode = 27 || Js.to_string ev##.key = "Escape")
         && has_class panel "is-open" then begin
        Dom.preventDefault ev;
        set_open false;
        Js._false
      end else Js._true)) Js._true);
  set_open ~restore_focus:false false

(* ── Period scroll pinning: stop naturally at viewport top ── *)
let setup_period_pin () =
  let period = get_element "hero-period" in
  let is_fixed = ref false in

  let on_scroll () =
    if not !is_fixed then begin
      let rect = period##getBoundingClientRect in
      let top = Js.to_float rect##.top in
      let height = Js.to_float rect##.height in
      (* Let .NET peek above viewport before pinning *)
      let threshold = -. (height *. 0.7) in
      if top <= threshold then begin
        period##.style##.position := Js.string "fixed";
        (* 45° from top-left corner *)
        period##.style##.top := Js.string "0.5rem";
        period##.style##.left := Js.string "0.5rem";
        period##.style##.zIndex := Js.string "11";
        period##.classList##add (Js.string "is-fixed");
        is_fixed := true
      end
    end else begin
      Js.Opt.iter
        (Dom_html.document##getElementById (Js.string "hero-period-placeholder"))
        (fun placeholder ->
          let placeholder_rect = placeholder##getBoundingClientRect in
          let placeholder_height = Js.to_float placeholder_rect##.height in
          let threshold = -. (placeholder_height *. 0.7) in
          if Js.to_float placeholder_rect##.top > threshold then begin
            period##.style##.position := Js.string "";
            period##.style##.top := Js.string "";
            period##.style##.left := Js.string "";
            period##.style##.zIndex := Js.string "";
            period##.classList##remove (Js.string "is-fixed");
            is_fixed := false
          end)
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
(* The header is what HOME turns into on the way up, so it arrives exactly as
   HOME leaves. Watching the whole hero instead made it arrive later, once the
   last of the wordmark had gone, leaving a stretch with neither on screen.
   Falls back to the hero if the link is ever absent.

   What the observer is asked is where HOME is, not whether it can be seen.
   "Not intersecting" is true of a link that has scrolled off the top and
   equally of one a phone's toolbar is sitting on top of — Safari measures
   against the unobscured part of the window — so on a phone the header
   arrived over a hero that had not moved. The rect says which of the two it
   is: HOME has left upwards only when its bottom edge is at or above the top
   of the viewport. *)
let setup_header_observer () =
  let header = get_element "persistent-header" in
  let hero =
    match
      Dom.list_of_nodeList
        (Dom_html.document##querySelectorAll (Js.string ".hero-home"))
    with
    | home :: _ -> home
    | [] -> get_element "hero"
  in

  (* Create IntersectionObserver via js_of_ocaml *)
  let callback entries _observer =
    let entry = Js.Optdef.get (Js.array_get entries 0) (fun () -> failwith "no entry") in
    let bottom = Js.to_float entry##.boundingClientRect##.bottom in
    if bottom <= 0. then
      add_class header "is-visible"
    else
      remove_class header "is-visible"
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
let element_exists id =
  Js.Opt.test (Dom_html.document##getElementById (Js.string id))

let init () =
  let body = Dom_html.document##.body in
  (* [hero-page] is the retired owned-shell marker used by the legacy
     compatibility fixture. Native pages require [miya-native]. *)
  let owned = has_class body "miya-native" || has_class body "hero-page" in
  let initialized = Js.to_bool (body##hasAttribute (Js.string "data-miya-client-ready")) in
  let toggles = Dom.list_of_nodeList
    (Dom_html.document##querySelectorAll (Js.string ".nav-toggle")) in
  if owned && not initialized && element_exists "nav-panel"
     && element_exists "nav-overlay" && toggles <> [] then begin
    body##setAttribute (Js.string "data-miya-client-ready") (Js.string "true");
    setup_nav ();
    if element_exists "hero" then begin
      let enabled = ref false in
      let enable () =
        if not !enabled then begin
          enabled := true;
          (get_element "hero")##.style##.display := Js.string "";
          add_class body "hero-page";
          if element_exists "hero-period" then setup_period_pin ();
          if element_exists "persistent-header" then setup_header_observer ()
        end
      in
      if is_home_mode () then enable () else disable_hero ();
      if has_class body "miya-home" then
        ignore (Dom_html.addEventListener Dom_html.window (Dom.Event.make "hashchange")
          (Dom_html.handler (fun _ ->
            if Js.to_string Dom_html.window##.location##.hash = "#hero" then begin
              enable ();
              ignore (Js.Unsafe.meth_call (get_element "hero") "scrollIntoView" [||])
            end;
            Js._true)) Js._false)
    end
  end

let () =
  let ready = Js.to_string Dom_html.document##.readyState in
  if ready = "complete" || ready = "interactive" then
    init ()
  else
    ignore (Dom_html.addEventListener Dom_html.window (Dom.Event.make "DOMContentLoaded")
      (Dom_html.handler (fun _ -> init (); Js._false)) Js._true)
