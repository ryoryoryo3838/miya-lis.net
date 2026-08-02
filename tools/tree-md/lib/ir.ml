type link = { label : inline list; destination : string; title : string option }
and image = { alt : inline list; destination : string; title : string option }
and inline = { node : inline_node; span : Span.t }
and inline_node =
  | Text of string
  | Emphasis of inline list
  | Strong of inline list
  | Code of string
  | Link of link
  | Image of image
  | Wiki_link of { target : string; alias : string option }
  | Wiki_embed of string
  | Math of { tex : string; display : bool }
  | Hard_break
  | Soft_break

type reference_kind = Wiki | Embed | Attribution
type reference = { kind : reference_kind; target : string; span : Span.t }
