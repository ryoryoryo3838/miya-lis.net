type 'a located = { value : 'a; span : Span.t }
type attribution = Tree of string located | Literal of string located

type raw = {
  date : string located option;
  taxon : string located option;
  authors : attribution list;
  contributors : attribution list;
  tags : string located list;
  meta : (string located * string located) list;
}

let empty = {
  date = None;
  taxon = None;
  authors = [];
  contributors = [];
  tags = [];
  meta = [];
}

let valid_id s =
  let len = String.length s in
  if len = 0 then false
  else
    let rec loop i =
      if i >= len then true
      else
        let c = s.[i] in
        match c with
        | 'a' .. 'z' | '0' .. '9' | '-' -> loop (i + 1)
        | _ -> false
    in
    loop 0

let parse_attribution located =
  let s = located.value in
  let len = String.length s in
  if len >= 4 && s.[0] = '[' && s.[1] = '['
     && s.[len - 2] = ']' && s.[len - 1] = ']'
  then
    let inner = String.sub s 2 (len - 4) in
    if valid_id inner then
      let inner_located = { value = inner; span = located.span } in
      Ok (Tree inner_located)
    else
      let diag =
        Diagnostic.make TM205
          (Span.Source_span located.span)
          ("invalid tree id: \"" ^ inner ^ "\"")
      in
      Error diag
  else
    Ok (Literal located)

let is_leap_year y =
  (y mod 4 = 0 && y mod 100 <> 0) || (y mod 400 = 0)

let days_in_month y m =
  match m with
  | 1 | 3 | 5 | 7 | 8 | 10 | 12 -> 31
  | 4 | 6 | 9 | 11 -> 30
  | 2 -> if is_leap_year y then 29 else 28
  | _ -> 0

let is_digit c = c >= '0' && c <= '9'

let parse_two_digits s pos =
  if pos + 1 < String.length s && is_digit s.[pos] && is_digit s.[pos + 1] then
    let n =
      (Char.code s.[pos] - Char.code '0') * 10
      + (Char.code s.[pos + 1] - Char.code '0')
    in
    Some (n, pos + 2)
  else
    None

let parse_four_digits s pos =
  if pos + 3 < String.length s
     && is_digit s.[pos] && is_digit s.[pos + 1]
     && is_digit s.[pos + 2] && is_digit s.[pos + 3]
  then
    let n =
      (Char.code s.[pos] - Char.code '0') * 1000
      + (Char.code s.[pos + 1] - Char.code '0') * 100
      + (Char.code s.[pos + 2] - Char.code '0') * 10
      + (Char.code s.[pos + 3] - Char.code '0')
    in
    Some (n, pos + 4)
  else
    None

let match_char s pos expected =
  pos < String.length s && s.[pos] = expected

let valid_date s =
  let len = String.length s in
  match len with
  | 10 (* YYYY-MM-DD *) ->
    (match parse_four_digits s 0 with
     | Some (year, 4) when match_char s 4 '-' ->
       (match parse_two_digits s 5 with
        | Some (month, 7) when match_char s 7 '-' ->
          (match parse_two_digits s 8 with
           | Some (day, 10) ->
             month >= 1 && month <= 12
             && day >= 1 && day <= days_in_month year month
           | _ -> false)
        | _ -> false)
     | _ -> false)
  | 20 (* YYYY-MM-DDTHH:MM:SSZ *) ->
    (match parse_four_digits s 0 with
     | Some (year, 4) when match_char s 4 '-' ->
       (match parse_two_digits s 5 with
        | Some (month, 7) when match_char s 7 '-' ->
          (match parse_two_digits s 8 with
           | Some (day, 10) when match_char s 10 'T' ->
             month >= 1 && month <= 12
             && day >= 1 && day <= days_in_month year month
             && (match parse_two_digits s 11 with
                | Some (hour, 13) when match_char s 13 ':' ->
                  (match parse_two_digits s 14 with
                   | Some (minute, 16) when match_char s 16 ':' ->
                     (match parse_two_digits s 17 with
                      | Some (second, 19) when match_char s 19 'Z' ->
                        hour <= 23 && minute <= 59 && second <= 59
                      | _ -> false)
                   | _ -> false)
                | _ -> false)
           | _ -> false)
        | _ -> false)
     | _ -> false)
  | 25 (* YYYY-MM-DDTHH:MM:SS+HH:MM or -HH:MM *) ->
    (match parse_four_digits s 0 with
     | Some (year, 4) when match_char s 4 '-' ->
       (match parse_two_digits s 5 with
        | Some (month, 7) when match_char s 7 '-' ->
          (match parse_two_digits s 8 with
           | Some (day, 10) when match_char s 10 'T' ->
             month >= 1 && month <= 12
             && day >= 1 && day <= days_in_month year month
             && (match parse_two_digits s 11 with
                | Some (hour, 13) when match_char s 13 ':' ->
                  (match parse_two_digits s 14 with
                   | Some (minute, 16) when match_char s 16 ':' ->
                     (match parse_two_digits s 17 with
                      | Some (second, 19)
                        when (match_char s 19 '+' || match_char s 19 '-')
                        ->
                        hour <= 23 && minute <= 59 && second <= 59
                        && (match parse_two_digits s 20 with
                           | Some (off_hour, 22) when match_char s 22 ':' ->
                             (match parse_two_digits s 23 with
                              | Some (off_min, 25) ->
                                off_hour <= 23 && off_min <= 59
                              | _ -> false)
                           | _ -> false)
                      | _ -> false)
                   | _ -> false)
                | _ -> false)
           | _ -> false)
        | _ -> false)
     | _ -> false)
  | _ -> false
