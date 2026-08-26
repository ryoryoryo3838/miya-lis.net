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

(* The root entry (/index.html) lands on /index/index.xml#hero; internal links
   to [index] land on /index/ without the fragment and stay on Home content.
   The fragment stays in the URL so that a reload — including the one the watch
   server triggers after every rebuild — keeps showing the hero. *)
let is_home_mode () =
  Js.to_string Dom_html.window##.location##.hash = "#hero"

let disable_hero () =
  let hero = get_element "hero" in
  let body = Dom_html.document##.body in
  hero##.style##.display := Js.string "none";
  remove_class body "hero-page"

(* ── Nav panel toggle ── *)
let setup_nav () =
  let panel = get_element "nav-panel" in
  let overlay = get_element "nav-overlay" in
  let toggles =
    Dom.list_of_nodeList
      (Dom_html.document##getElementsByClassName (Js.string "nav-toggle"))
  in

  let set_open open_ =
    let update element class_name =
      if open_ then add_class element class_name
      else remove_class element class_name
    in
    update panel "is-open";
    update overlay "is-visible";
    List.iter (fun toggle -> update toggle "is-open") toggles
  in

  List.iter
    (fun toggle ->
      toggle##.onclick := Dom_html.handler (fun ev ->
        Dom.preventDefault ev;
        set_open (not (has_class panel "is-open"));
        Js._false
      ))
    toggles;

  overlay##.onclick := Dom_html.handler (fun _ev ->
    set_open false;
    Js._false
  );

  Dom_html.addEventListener
    Dom_html.document (Dom.Event.make "keydown")
    (Dom_html.handler (fun ev ->
      if ev##.keyCode = 27 then begin
        set_open false;
        Js._false
      end else
        Js._true
    )) Js._true
  |> ignore

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
        (Dom_html.document##getElementsByClassName (Js.string "hero-home"))
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
let init () =
  setup_nav ();
  let home_mode = is_home_mode () in
  let hero_present = ref false in
  Js.Opt.iter
    (Dom_html.document##getElementById (Js.string "hero"))
    (fun _ -> hero_present := true);
  if !hero_present then begin
    if home_mode then begin
      setup_period_pin ();
      setup_header_observer ()
    end else
      disable_hero ()
  end

let () =
  let ready = Js.to_string Dom_html.document##.readyState in
  if ready = "complete" || ready = "interactive" then
    init ()
  else
    ignore (Dom_html.addEventListener Dom_html.window (Dom.Event.make "DOMContentLoaded")
      (Dom_html.handler (fun _ -> init (); Js._false)) Js._true)
