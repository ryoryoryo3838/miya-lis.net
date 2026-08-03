# Tree Markdown Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an OCaml library and `tree-md` CLI that compile the approved strict `.tree.md` dialect into deterministic, safe Forester 6.0-dev `.tree` source.

**Architecture:** A located front end masks and parses YAML, adapts Cmarkit into a compiler-owned IR, and builds nested sections. A separate forest resolver validates global identities and assets before a pinned textual Forester emitter runs; workspace code then manages deterministic output through a versioned manifest and crash-safe roll-forward journal.

**Tech Stack:** OCaml 5.3.0, Dune 3.22, Cmarkit 0.4.0, yaml 3.2.0, Otoml 1.0.5, Cmdliner 2.1.0, Yojson 3.0.0, Digestif 1.3.0, Alcotest 1.9.1

**Spec:** `docs/superpowers/specs/2026-08-02-tree-markdown-compiler-design.md`

## Global Constraints

- Target exactly `forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be`.
- Place the independent project under `tools/tree-md`; do not merge it into the root dune project.
- Use OCaml 5.3.0 and Dune 3.22 as the baseline.
- Pin direct package versions exactly as listed in the Tech Stack.
- Do not link the Forester library; invoke the pinned executable only in the final compatibility test.
- Keep direct and linked dependencies permissively licensed; do not choose or add a project license in this implementation.
- Accept only the dialect in the approved spec; do not add raw Forester, raw HTML, GFM, watch mode, or extra Obsidian syntax.
- Keep `trees/index.tree`, `trees/aboutme.tree`, and all existing handwritten content unchanged.
- Generate from `trees-md` into `generated`; final identity is always the `.tree.md` filename stem.
- Preserve exact UTF-8 source byte spans and deterministic diagnostic ordering.
- `check` must not write project or output files.
- All generated output must be canonical UTF-8 with LF line endings and one final newline.
- Never run `dune clean` or `dune build`. Use focused `dune runtest` and `dune exec` commands from `tools/tree-md`.
- Before every `dune runtest`, compatibility command, or commit, show `git status --short` and `git diff --stat`. If the execution worktree has unrelated changes, stop for explicit approval.
- At execution start, use an isolated worktree and obtain explicit approval to run tests with the task-local uncommitted red/green changes.
- Stage only paths named by the current task. Never stage the repository's unrelated theme, hero, `.omo`, or build-artifact changes.

---

## File Structure

### Project and Public Entry Points

| Path | Responsibility |
| --- | --- |
| `tools/tree-md/dune-project` | Independent package, version, and exact dependencies |
| `tools/tree-md/lib/dune` | Wrapped public `tree_md` library |
| `tools/tree-md/bin/dune` | Installed `tree-md` executable |
| `tools/tree-md/bin/main.ml` | Cmdliner evaluation only |
| `tools/tree-md/test/dune` | Focused Alcotest executables and cram tests |

### Located Front End

| Path | Responsibility |
| --- | --- |
| `tools/tree-md/lib/span.{ml,mli}` | Canonical source and path locations |
| `tools/tree-md/lib/source.{ml,mli}` | UTF-8 validation, byte/character indexes, excerpts |
| `tools/tree-md/lib/diagnostic.{ml,mli}` | Stable codes, sorting, rendering |
| `tools/tree-md/lib/metadata.{ml,mli}` | Located raw and lowered metadata |
| `tools/tree-md/lib/frontmatter.{ml,mli}` | YAML delimiters, masking, stream parsing, schema |
| `tools/tree-md/lib/wiki.{ml,mli}` | Cmarkit resolver metadata and wrapper recognition |
| `tools/tree-md/lib/safe_uri.{ml,mli}` | URI scheme validation and Forester-safe normalization |
| `tools/tree-md/lib/ir.{ml,mli}` | Compiler-owned inline and block IR |
| `tools/tree-md/lib/markdown.{ml,mli}` | Closed Cmarkit lowering and extension rejection |
| `tools/tree-md/lib/outline.{ml,mli}` | Root title and heading-to-subtree hierarchy |
| `tools/tree-md/lib/forester_6.{ml,mli}` | Context writers and pinned textual emitter |

### Forest and Workspace

| Path | Responsibility |
| --- | --- |
| `tools/tree-md/lib/path_safe.{ml,mli}` | Relative path normalization and containment |
| `tools/tree-md/lib/config.{ml,mli}` | `tree-md.toml` and `forest.toml` parsing |
| `tools/tree-md/lib/discovery.{ml,mli}` | Recursive source, tree, and asset discovery |
| `tools/tree-md/lib/forest_index.{ml,mli}` | Global definitions and reference validation |
| `tools/tree-md/lib/resolution.{ml,mli}` | Per-document routed asset lookup |
| `tools/tree-md/lib/parsed_document.{ml,mli}` | Cycle-free parsed document shared by compiler and forest index |
| `tools/tree-md/lib/compiler.{ml,mli}` | Pure source-to-expected-output orchestration |
| `tools/tree-md/lib/manifest.{ml,mli}` | Closed JSON schema, hashes, expected-state diff |
| `tools/tree-md/lib/transaction.{ml,mli}` | Pure journal state machine and recovery actions |
| `tools/tree-md/lib/workspace_fs.{ml,mli}` | Lock, fsync, no-symlink operations, atomic rename |
| `tools/tree-md/lib/workspace.{ml,mli}` | `build` and read-only `check` workflows |
| `tools/tree-md/lib/cli.{ml,mli}` | Cmdliner terms, diagnostics, exit-code mapping |

### Tests and Fixtures

Each implementation module has a matching `tools/tree-md/test/*_test.ml`. Golden inputs live under `tools/tree-md/test/fixtures/markdown/`, generated trees under `tools/tree-md/test/fixtures/forester/`, workspace cases under `tools/tree-md/test/fixtures/workspaces/`, and CLI cram tests under `tools/tree-md/test/cli.t/`.

Keep one plural Dune `tests` stanza in `tools/tree-md/test/dune`. Whenever a task adds a test module, append that module's filename without `.ml` to the stanza's `names` field in the same commit. Task 17 additionally adds `(cram (deps %{bin:tree-md}))`, which discovers `cli.t/run.t`.

---

## Phase 1: Located Front End and Forester Emitter

### Task 1: Project Skeleton, Source Spans, and Diagnostics

**Files:**
- Create: `tools/tree-md/dune-project`
- Create: `tools/tree-md/tree-md.opam` through Dune opam generation
- Create: `tools/tree-md/lib/dune`
- Create: `tools/tree-md/lib/span.ml`
- Create: `tools/tree-md/lib/span.mli`
- Create: `tools/tree-md/lib/source.ml`
- Create: `tools/tree-md/lib/source.mli`
- Create: `tools/tree-md/lib/diagnostic.ml`
- Create: `tools/tree-md/lib/diagnostic.mli`
- Create: `tools/tree-md/test/dune`
- Create: `tools/tree-md/test/source_test.ml`
- Create: `tools/tree-md/test/diagnostic_test.ml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Span.t`, `Source.t`, UTF-8 validation, byte-to-line/column lookup, `Diagnostic.t`, stable code rendering.
- Consumes: OCaml stdlib only.

- [ ] **Step 1: Add the independent dune project and focused test stanzas**

Create `tools/tree-md/dune-project`:

```lisp
(lang dune 3.22)
(name tree_md)
(version 0.1.0)
(generate_opam_files true)

(package
 (name tree-md)
 (synopsis "Compile strict Markdown into Forester tree source")
 (depends
  (ocaml (= 5.3.0))
  (dune (= 3.22.2))
  (cmarkit (= 0.4.0))
  (yaml (= 3.2.0))
  (otoml (= 1.0.5))
  (cmdliner (= 2.1.0))
  (yojson (= 3.0.0))
  (digestif (= 1.3.0))
  (alcotest (= 1.9.1) :with-test)))
```

Create `tools/tree-md/lib/dune`:

```lisp
(library
 (name tree_md)
 (public_name tree-md)
 (libraries cmarkit yaml yaml.ffi yaml.types otoml yojson digestif unix))
```

Create `tools/tree-md/test/dune`:

```lisp
(tests
 (names source_test diagnostic_test)
 (libraries tree-md alcotest))
```

Append `_build/` to `.gitignore`; the pattern covers root and nested dune build directories.

- [ ] **Step 2: Define the foundation interfaces**

Create `span.mli`:

```ocaml
type t = {
  path : string;
  start_byte : int;
  end_byte : int;
}

type location = Source_span of t | Path of string | No_location

val make : path:string -> start_byte:int -> end_byte:int -> (t, string) result
val compare : t -> t -> int
```

Create `source.mli`:

```ocaml
type t
type utf8_error = { byte : int }

val of_string : path:string -> string -> (t, utf8_error) result
val path : t -> string
val text : t -> string
val length : t -> int
val span : t -> start_byte:int -> end_byte:int -> (Span.t, string) result
val slice : t -> Span.t -> (string, string) result
val line_col : t -> byte:int -> (int * int, string) result
val character_to_byte : t -> character:int -> int option
val excerpt : t -> Span.t -> (string * string, string) result
```

Create `diagnostic.mli` with the complete stable code set from the spec:

```ocaml
type severity = Error

type code =
  | TM001 | TM002 | TM003
  | TM101 | TM102 | TM103 | TM104 | TM105 | TM106 | TM107
  | TM201 | TM202 | TM203 | TM204 | TM205
  | TM301 | TM302 | TM303 | TM304 | TM305 | TM306
  | TM401 | TM402 | TM403 | TM404 | TM500

type labelled_location = { label : string; location : Span.location }

type t = {
  severity : severity;
  code : code;
  message : string;
  primary : Span.location;
  secondary : labelled_location list;
  notes : string list;
}

val make :
  ?secondary:labelled_location list ->
  ?notes:string list ->
  code -> Span.location -> string -> t
val code_string : code -> string
val compare : t -> t -> int
val render : sources:(string * Source.t) list -> t -> string
```

- [ ] **Step 3: Write failing source and diagnostic tests**

`source_test.ml` must assert all of these cases:

```ocaml
let test_utf8_and_locations () =
  let source =
    Result.get_ok (Tree_md.Source.of_string ~path:"note.tree.md" "a\r\n日\tb")
  in
  Alcotest.(check (pair int int)) "Japanese starts line 2 column 1"
    (2, 1) (Result.get_ok (Tree_md.Source.line_col source ~byte:3));
  Alcotest.(check int) "character index maps to byte"
    3 (Option.get (Tree_md.Source.character_to_byte source ~character:3));
  Alcotest.(check int) "byte length" 8 (Tree_md.Source.length source)

let test_invalid_utf8 () =
  match Tree_md.Source.of_string ~path:"bad.tree.md" "\xFF" with
  | Error { byte = 0 } -> ()
  | _ -> Alcotest.fail "expected invalid UTF-8 at byte 0"
```

`diagnostic_test.ml` must render a tab-containing excerpt with a four-column tab stop, assert `TM103`, and verify path/byte sorting before path-only and no-location diagnostics.

- [ ] **Step 4: Run the tests to verify the red state**

From `tools/tree-md`, after the required status/diff approval:

```bash
dune exec ./test/source_test.exe
dune exec ./test/diagnostic_test.exe
```

Expected: FAIL because `Span`, `Source`, and `Diagnostic` are not implemented.

- [ ] **Step 5: Implement UTF-8 indexing and deterministic diagnostics**

Implement one strict UTF-8 scan in `Source.of_string`. Record every Unicode scalar's starting byte and every line start. Treat CRLF as one newline for line numbering, reject overlong encodings, surrogates, truncated sequences, and values above `U+10FFFF`. `line_col` returns 1-based Unicode-scalar columns; `Diagnostic.render` expands tabs to four display columns only while drawing excerpts.

Implement `Span.make` with these exact checks:

```ocaml
if start_byte < 0 then Error "start byte is negative"
else if end_byte < start_byte then Error "end byte precedes start byte"
else Ok { path; start_byte; end_byte }
```

Sort diagnostics by source path, start byte, code, then message; `Path` locations sort after spans for the same path and `No_location` sorts last.

- [ ] **Step 6: Run focused and full tests**

```bash
dune exec ./test/source_test.exe
dune exec ./test/diagnostic_test.exe
dune runtest
```

Expected: PASS, with two test executables and no failures.

- [ ] **Step 7: Commit the foundation**

```bash
git add .gitignore tools/tree-md/dune-project tools/tree-md/tree-md.opam tools/tree-md/lib tools/tree-md/test/dune tools/tree-md/test/source_test.ml tools/tree-md/test/diagnostic_test.ml
git commit -m "feat(tree-md): add located source foundation"
```

### Task 2: YAML Front Matter and Metadata Schema

**Files:**
- Create: `tools/tree-md/lib/metadata.ml`
- Create: `tools/tree-md/lib/metadata.mli`
- Create: `tools/tree-md/lib/frontmatter.ml`
- Create: `tools/tree-md/lib/frontmatter.mli`
- Create: `tools/tree-md/test/frontmatter_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: `Source.t`, `Span.t`, `Diagnostic.t`.
- Produces: `Metadata.raw`, an equal-byte-length masked Markdown view, and YAML diagnostics located in the original source.

- [ ] **Step 1: Define located metadata and front-matter result types**

Create `metadata.mli`:

```ocaml
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

val empty : raw
val valid_id : string -> bool
val parse_attribution : string located -> (attribution, Diagnostic.t) result
val valid_date : string -> bool
```

Create `frontmatter.mli`:

```ocaml
type t = {
  metadata : Metadata.raw;
  masked_markdown : string;
}

val parse : Source.t -> (t, Diagnostic.t list) result
```

- [ ] **Step 2: Write the failing schema and masking tests**

Add these explicit cases to `frontmatter_test.ml`:

```ocaml
let valid =
  "---\r\n" ^
  "date: \"2026-08-02T09:30:00+09:00\"\r\n" ^
  "taxon: Note\r\n" ^
  "authors: [\"[[miya]]\", \"Ada Lovelace\"]\r\n" ^
  "tags: [\"**compiler**\"]\r\n" ^
  "meta: { institution: \"[Tsukuba](https://example.test/)\" }\r\n" ^
  "---\r\n# Title\r\n"
```

Assert that the masked string has exactly the same byte length, preserves every CR and LF byte, contains spaces elsewhere in the front matter, and still contains `# Title`. Assert `Tree "miya"`, `Literal "Ada Lovelace"`, metadata source order, and exact scalar spans.

Add failing cases for duplicate keys, unknown keys, YAML aliases, multiple documents, missing closing `---`, lowercase `t`/`z`, fractional seconds, invalid calendar dates, `[[bad id]]` attribution, and a UTF-8 YAML scalar whose event character index must map back to the correct byte.

- [ ] **Step 3: Run the focused test to verify failure**

```bash
dune exec ./test/frontmatter_test.exe
```

Expected: FAIL with unbound `Tree_md.Frontmatter`.

- [ ] **Step 4: Implement delimiter scanning and `Yaml.Stream` lowering**

Recognize only a byte-zero opening line `---` and the next unindented exact `---` line. Replace each non-newline byte from the opening delimiter through the closing delimiter with ASCII space.

Build a located YAML tree from `Yaml.Stream` events. Reject aliases, anchors, tags, non-scalar keys, duplicate keys, multiple documents, and every top-level key outside `date`, `taxon`, `authors`, `contributors`, `tags`, and `meta`. Use the low-level `yaml.ffi`/`yaml.types` parser offset for syntax failures; never parse a formatted error string.

Implement date validation against exactly these lexical forms before calendar validation:

```text
YYYY-MM-DD
YYYY-MM-DDTHH:MM:SSZ
YYYY-MM-DDTHH:MM:SS+HH:MM
YYYY-MM-DDTHH:MM:SS-HH:MM
```

Validate leap years, month lengths, `00..23` hours, `00..59` minutes and seconds, and `00..23:59` offsets.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/frontmatter_test.exe
dune runtest
git add tools/tree-md/lib/metadata.ml tools/tree-md/lib/metadata.mli tools/tree-md/lib/frontmatter.ml tools/tree-md/lib/frontmatter.mli tools/tree-md/test/dune tools/tree-md/test/frontmatter_test.ml
git commit -m "feat(tree-md): parse located YAML front matter"
```

Expected: all tests PASS; the commit contains only Task 2 files.

### Task 3: Cmarkit Wiki Resolver Contract

**Files:**
- Create: `tools/tree-md/lib/wiki.ml`
- Create: `tools/tree-md/lib/wiki.mli`
- Create: `tools/tree-md/test/wiki_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: original `Source.t`, Cmarkit label metadata and source locations.
- Produces: pure/idempotent resolver metadata and normalized Wiki candidates.

Create `wiki.mli`:

```ocaml
type kind = Link | Embed

type candidate = {
  kind : kind;
  target : string;
  alias : string option;
  whole_span : Span.t;
  inner_span : Span.t;
}

type shape =
  | Text_shape of Span.t
  | Code_shape of Span.t
  | Shortcut_shape of candidate
  | Ordinary_link_shape of Span.t

val resolver : Source.t -> Cmarkit.Label.resolver
val shapes_for_test : Source.t -> string -> (shape list, Diagnostic.t list) result
```

- [ ] **Step 1: Write the pinned Cmarkit characterization tests**

Test these no-definition inputs and inclusive Cmarkit ranges converted to half-open spans:

```text
[[id]]             Text[0,1], Wiki-Link target=id whole=[0,6], Text[5,6]
[[id|alias]]       Text[0,1], Wiki-Link target=id alias=alias whole=[0,12], Text[11,12]
![[id]]            Text[0,2], Wiki-Embed target=id whole=[0,7], Text[6,7]
[alias][[id]]      ordinary CommonMark/literal nodes, never Wiki
\[[id]]            literal nodes, never Wiki
`[[id]]`           Code[0,8]
```

Add definitions `[id]: /ordinary` and verify `[alias][[id]]` follows default CommonMark resolution while `\[[id]]` remains literal. Add odd/even backslash fixtures and larger runs `[[[id]]]`.

- [ ] **Step 2: Run the test to verify the red state**

```bash
dune exec ./test/wiki_test.exe
```

Expected: FAIL with unbound `Tree_md.Wiki`.

- [ ] **Step 3: Implement the source-aware resolver**

Use Cmarkit's label location to inspect original bytes around the inner shortcut label. Accept only maximal `[[BODY]]` and `![[BODY]]`. Attach the raw BODY and wrapper metadata even when the closed form has an invalid ID, empty alias, or multiple `|` characters; validation belongs to normalization so those forms produce `TM105` rather than falling back to literal text.

Before tagging, apply these guards in order:

```text
1. Outer opening bracket exists in the same source.
2. Outer opening bracket and embed bang have an even backslash count before them.
3. The envelope is not part of a larger bracket run.
4. The byte immediately before a normal envelope is not `]`.
5. Closing wrapper byte exists and belongs to the same paragraph source range.
```

Return an explicitly unresolved label for an escaped Wiki-shaped envelope, delegate all other noncandidates to `Cmarkit.Label.default_resolver`, and attach private metadata only to the synthetic shortcut label. Emit no diagnostics in the resolver because Cmarkit may call it twice.

- [ ] **Step 4: Normalize surviving wrapper nodes and report closed-form errors**

Accept only a tagged `Ref (`Shortcut, source_label, tagged_meta)` whose inner and wrapper spans match the candidate. Split BODY on exactly one unescaped `|`, validate target with `Metadata.valid_id`, and reject empty or bracket-containing aliases. Consume/split the adjacent Text nodes and return one `Shortcut_shape` only for a valid form. Diagnose `[[bad id]]`, `[[id|]]`, and `[[id|a|b]]` as `TM105`; leave unclosed forms literal.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/wiki_test.exe
dune runtest
git add tools/tree-md/lib/wiki.ml tools/tree-md/lib/wiki.mli tools/tree-md/test/dune tools/tree-md/test/wiki_test.ml
git commit -m "feat(tree-md): recognize Obsidian wiki syntax"
```

Expected: all characterization and regression cases PASS.

### Task 4: Safe URI Validation and Inline IR Lowering

**Files:**
- Create: `tools/tree-md/lib/safe_uri.ml`
- Create: `tools/tree-md/lib/safe_uri.mli`
- Create: `tools/tree-md/lib/ir.ml`
- Create: `tools/tree-md/lib/ir.mli`
- Create: `tools/tree-md/lib/markdown.ml`
- Create: `tools/tree-md/lib/markdown.mli`
- Create: `tools/tree-md/test/inline_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: masked Markdown, raw metadata, Cmarkit/Wiki adapter.
- Produces: located compiler-owned inline nodes and URI diagnostics; no Cmarkit values cross the interface.

Create the initial `ir.mli` inline model:

```ocaml
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
```

Create `safe_uri.mli`:

```ocaml
type purpose = Link | Image

val validate : purpose -> Span.t -> string -> (string, Diagnostic.t) result
val percent_encode : string -> string
```

Create the first `markdown.mli` entry point:

```ocaml
val parse_inlines :
  Source.t -> string -> base_byte:int ->
  (Ir.inline list, Diagnostic.t list) result
```

- [ ] **Step 1: Write failing inline and URI tests**

Cover text, emphasis, strong, nested emphasis, code, standard links, autolinks, images, Wiki links and aliases, `$x$`, hard breaks, soft breaks, escaped delimiters, and Unicode spans. Assert rejection of raw inline HTML, strikethrough, `javascript:`, `data:` images, unsafe explicit schemes, and title-bearing local links.

Assert these URI outcomes:

```text
https://example.test/a b -> https://example.test/a%20b
mailto:a@example.test -> accepted for links
#section -> accepted for links
note -> accepted relative link
javascript:alert(1) -> TM205
data:image/png;base64,x -> TM205 for image
```

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/inline_test.exe
```

Expected: FAIL because the IR and lowering entry point do not exist.

- [ ] **Step 3: Implement the closed inline lowerer**

Parse with `Cmarkit.Doc.of_string ~locs:true ~strict:false ~resolver:(Wiki.resolver source)`. Convert inclusive Cmarkit locations to half-open `Span.t`. Lower only the constructors named in `Ir.inline_node`; reject every raw HTML or unrecognized extension with `TM102`. Accept only Cmarkit's dollar math span extension for `Math`.

For URI validation, parse a scheme only when the prefix matches `[A-Za-z][A-Za-z0-9+.-]*:`. Apply the exact purpose allowlists from the spec, reject control characters and NUL, preserve fragments, and percent-encode bytes outside the URI-safe ASCII set using uppercase hexadecimal.

- [ ] **Step 4: Parse YAML tag/meta inline values through the same lowerer**

Add a generic lowered metadata type to `metadata.mli`; keeping it polymorphic avoids a `Metadata`/`Ir` module cycle:

```ocaml
type 'inline t = {
  date : string located option;
  taxon : string located option;
  authors : attribution list;
  contributors : attribution list;
  tags : 'inline located list;
  meta : (string located * 'inline located) list;
}

val lower_inline_values :
  parse:(string located -> ('inline, Diagnostic.t list) result) ->
  raw -> ('inline t, Diagnostic.t list) result
```

Use the complete YAML scalar span as the location when decoded inline syntax fails.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/inline_test.exe
dune runtest
git add tools/tree-md/lib/safe_uri.ml tools/tree-md/lib/safe_uri.mli tools/tree-md/lib/ir.ml tools/tree-md/lib/ir.mli tools/tree-md/lib/markdown.ml tools/tree-md/lib/markdown.mli tools/tree-md/lib/metadata.ml tools/tree-md/lib/metadata.mli tools/tree-md/test/dune tools/tree-md/test/inline_test.ml
git commit -m "feat(tree-md): lower safe inline Markdown"
```

Expected: all inline, metadata-inline, URI, and prior tests PASS.

### Task 5: Block Lowering and Closed Markdown Dialect

**Files:**
- Modify: `tools/tree-md/lib/ir.ml`
- Modify: `tools/tree-md/lib/ir.mli`
- Modify: `tools/tree-md/lib/markdown.ml`
- Modify: `tools/tree-md/lib/markdown.mli`
- Create: `tools/tree-md/test/block_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: Task 4 inline lowering and `Metadata.t`.
- Produces: complete located block IR, standalone embed/display-math classification, and closed-dialect diagnostics.

- [ ] **Step 1: Extend the IR with every supported block constructor**

Add to `ir.mli`:

```ocaml
type list_kind = Unordered | Ordered of int
type code_info = No_info | Language of string
type list_item = { blocks : block list; span : Span.t }
and block = { node : block_node; span : Span.t }
and block_node =
  | Paragraph of inline list
  | Blockquote of block list
  | List of {
      kind : list_kind;
      tight : bool;
      items : list_item list;
    }
  | Code_block of { info : code_info; code : string }
  | Thematic_break
  | Heading of { level : int; title : inline list }
  | Subtree_directive of string
  | Embed of string
  | Display_math of string

type document = {
  metadata : Ir.inline list Metadata.t;
  blocks : block list;
  span : Span.t;
}
```

Extend `markdown.mli`:

```ocaml
val parse :
  Source.t -> masked_markdown:string -> Metadata.raw ->
  (Ir.document, Diagnostic.t list) result
```

- [ ] **Step 2: Write failing block tests**

Add explicit fixtures for paragraphs, nested blockquotes, tight and loose lists, nested lists, ordered starts `1` and `7`, indented code, fenced code with no language, fenced `ocaml`, thematic breaks, ATX/setext headings, and ordinary discarded comments.

Add diagnostics for raw block HTML, GFM table, task marker, footnote, strikethrough, fenced `math`, multi-token fence info, invalid language token, nested heading, inline embed, embed in list/blockquote, inline `$$x$$`, and display math in list/blockquote.

Assert these normalizations:

```text
paragraph containing only ![[note]] -> Embed "note"
paragraph containing only $$x+y$$ -> Display_math "x+y"
paragraph containing text and ![[note]] -> TM106
paragraph containing text and $$x$$ -> TM107
```

- [ ] **Step 3: Run the focused test to verify failure**

```bash
dune exec ./test/block_test.exe
```

Expected: FAIL because block constructors and `Markdown.parse` are missing.

- [ ] **Step 4: Implement exhaustive Cmarkit block lowering**

Lower only the block constructors listed in `Ir.block_node`. Preserve Cmarkit's tight/loose flag and ordered start. For code fence info, accept empty or one token matching `[A-Za-z0-9][A-Za-z0-9_+.-]*`, but reject exactly `math`. Convert exact standalone `<!-- subtree: ID -->` HTML comments into `Subtree_directive`; discard all other comments; reject all other HTML.

After inline lowering, normalize a paragraph to `Embed` or `Display_math` only when it contains that one semantic node plus whitespace; `Display_math` requires `Math { display = true }`. Keep `Math { display = false }` inline. Track container depth and report `TM103`, `TM106`, or `TM107` when headings, embeds, or display math occur below the document block level.

Pattern-match every Cmarkit extension constructor explicitly; use a final unsupported case that emits `TM102` rather than silently dropping it.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/block_test.exe
dune runtest
git add tools/tree-md/lib/ir.ml tools/tree-md/lib/ir.mli tools/tree-md/lib/markdown.ml tools/tree-md/lib/markdown.mli tools/tree-md/test/dune tools/tree-md/test/block_test.ml
git commit -m "feat(tree-md): lower the closed block dialect"
```

Expected: all block fixtures and all prior tests PASS.

### Task 6: Root Titles, Directives, and Nested Subtrees

**Files:**
- Create: `tools/tree-md/lib/outline.ml`
- Create: `tools/tree-md/lib/outline.mli`
- Create: `tools/tree-md/test/outline_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: `root_id`, lowered `Ir.document`.
- Produces: a root tree with ordered body blocks and recursively nested sections; collects named subtree definitions.

Create `outline.mli`:

```ocaml
type section = {
  id : string option;
  title : Ir.inline list;
  body : Ir.block list;
  children : section list;
  span : Span.t;
}

type t = {
  root_id : string;
  title : Ir.inline list;
  metadata : Ir.inline list Metadata.t;
  body : Ir.block list;
  sections : section list;
  span : Span.t;
}

type definition = { id : string; span : Span.t }

val build : root_id:string -> Ir.document -> (t, Diagnostic.t list) result
val definitions : t -> definition list
```

- [ ] **Step 1: Write failing outline tests**

Cover these exact outlines:

```text
H1 first -> root title, no section
no H1 -> filename stem Text node as root title
H2, H3, H3, H2 -> two root sections; first has two children
H2 followed by H4 -> TM103 at H4
paragraph followed by H1 -> TM103
second H1 -> TM103
directive then H2 -> named section
directive, blank lines, H2 -> named section
directive then paragraph -> TM104
two directives before H2 -> TM104
directive before H1 -> TM104
```

Assert that paragraphs after an H3 stay in that H3 until a same/shallower heading closes it.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/outline_test.exe
```

Expected: FAIL with unbound `Tree_md.Outline`.

- [ ] **Step 3: Implement the heading stack**

Consume an optional first H1 before ordinary body blocks. Generate fallback title as one `Ir.Text root_id` node located at the source path with a zero-width byte-0 span. Treat H2 as level 2 under the root. Before adding level N, require an open level N-1 section; pop while the current level is greater than or equal to N.

Hold at most one pending `Subtree_directive`. Blank lines do not exist as block IR and therefore do not clear it; every non-heading block clears it with `TM104`. Apply the ID only to H2-H6 and record its comment span as the definition span.

Build immutable child lists in source order; reverse accumulator lists exactly once at each completed section.

- [ ] **Step 4: Run tests and commit**

```bash
dune exec ./test/outline_test.exe
dune runtest
git add tools/tree-md/lib/outline.ml tools/tree-md/lib/outline.mli tools/tree-md/test/dune tools/tree-md/test/outline_test.ml
git commit -m "feat(tree-md): build nested Forester outlines"
```

Expected: all hierarchy and directive cases PASS.

### Task 7: Forester 6 Text Writers and Emitter

**Files:**
- Create: `tools/tree-md/lib/resolution.ml`
- Create: `tools/tree-md/lib/resolution.mli`
- Create: `tools/tree-md/lib/forester_6.ml`
- Create: `tools/tree-md/lib/forester_6.mli`
- Create: `tools/tree-md/test/forester_6_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: `Outline.t` and span-keyed routed assets.
- Produces: canonical Forester source or located serialization diagnostics.

Create `resolution.mli`:

```ocaml
type t

val empty : t
val add_asset : Span.t -> routed_path:string -> t -> t
val asset_route : t -> Span.t -> string option
```

Create `forester_6.mli`:

```ocaml
val target : string
val escape_text_for_test : string -> string
val emit :
  resolution:Resolution.t -> Outline.t ->
  (string, Diagnostic.t list) result
```

- [ ] **Step 1: Write hostile escaping and complete mapping tests**

Assert this exact plain-text escaping:

```text
%       -> \%
\       -> \verbFMD|\FMD
#       -> \verbFMD|#FMD
{       -> \verbFMD|{FMD
}       -> \verbFMD|}FMD
[       -> \verbFMD|[FMD
]       -> \verbFMD|]FMD
(       -> \verbFMD|(FMD
)       -> \verbFMD|)FMD
<>&日本 -> unchanged text characters
```

Test metadata order, paragraphs, emphasis, strong, code, blockquotes, tight/loose lists, ordered start 7, code language class, Wiki links, transclusion, inline/display math, hard breaks, thematic breaks, external images, routed local images, named/anonymous sections, canonical blank lines, LF normalization, and one final newline.

Add `TM107` tests for unbalanced math grouping and an error when a local image has no `Resolution.asset_route`.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/forester_6_test.exe
```

Expected: FAIL with unbound `Tree_md.Forester_6`.

- [ ] **Step 3: Implement context-specific writers**

Use an internal writer record with separate functions for text, safe IDs, normalized URIs, XML attributes, metadata keys, and TeX. Never expose `Buffer.add_string` to lowering code. Apply the exact single-character `FMD` verbatim algorithm from the spec and escape every percent sign introduced by URI percent encoding.

Validate TeX grouping in one pass: preserve control sequences and balanced braces, account for escaped braces, and emit `TM107` before writing an unbalanced payload.

- [ ] **Step 4: Emit canonical Forester structure**

Emit metadata in this exact order: title, date, taxon, authors, contributors, tags, meta, body. Emit direct `\transclude{id}` for embeds and never add an extra subtree. Emit tight list paragraphs without `\p`, loose list paragraphs with `\p`, and non-1 ordered lists through `\<html:ol>[start]{N}{\li{item}}`.

For a local image, look up its source span in `Resolution.t` and emit `\route-asset{ROOT/PATH}`. For an external title-bearing link, emit an HTML anchor; reject a local title-bearing link before emission.

Flatten image alt text recursively: preserve Text and Code payloads, recurse through Emphasis/Strong/Link labels, use Wiki alias or target, preserve math TeX, and turn hard/soft breaks into one space. Reject a nested Image or any transient `Wiki_embed` that escaped block normalization.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/forester_6_test.exe
dune runtest
git add tools/tree-md/lib/resolution.ml tools/tree-md/lib/resolution.mli tools/tree-md/lib/forester_6.ml tools/tree-md/lib/forester_6.mli tools/tree-md/test/dune tools/tree-md/test/forester_6_test.ml
git commit -m "feat(tree-md): emit canonical Forester 6 source"
```

Expected: all emitter and hostile-text tests PASS.

### Task 8: Pure Compiler Pipeline and Phase 1 Golden Tests

**Files:**
- Create: `tools/tree-md/lib/parsed_document.ml`
- Create: `tools/tree-md/lib/parsed_document.mli`
- Create: `tools/tree-md/lib/compiler.ml`
- Create: `tools/tree-md/lib/compiler.mli`
- Create: `tools/tree-md/test/compiler_test.ml`
- Create: `tools/tree-md/test/fixtures/markdown/complete.tree.md`
- Create: `tools/tree-md/test/fixtures/forester/complete.tree`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: one source, root ID, and a `Resolution.t` supplied by the caller.
- Produces: parsed outline, definitions, references, local asset requests, and emitted source.

Create `parsed_document.mli`:

```ocaml
type local_asset = { destination : string; span : Span.t }

type t = {
  outline : Outline.t;
  definitions : Outline.definition list;
  references : Ir.reference list;
  local_assets : local_asset list;
}
```

Create `compiler.mli`:

```ocaml
val parse : root_id:string -> Source.t -> (Parsed_document.t, Diagnostic.t list) result
val emit :
  resolution:Resolution.t -> Parsed_document.t ->
  (string, Diagnostic.t list) result

```

- [ ] **Step 1: Add one complete source/output golden pair**

`complete.tree.md` must include YAML date/taxon/tree and literal authors, tags/meta inline Markdown, optional H1, named H2, anonymous H3, paragraph markup, standard/Wiki links, standalone embed, inline/display math, tight and loose lists, ordered start 7, quote, code span/fence, thematic/hard breaks, external image, and `![Plot](images/x.png)`.

The expected `.tree` fixture must use routed path `assets/images/x.png` and every exact mapping approved in the spec.

- [ ] **Step 2: Write the failing orchestration test**

Load the source through `Source.of_string`, call `Compiler.parse ~root_id:"complete"`, locate its local-image span, add the test route to `Resolution.empty`, emit, and compare the full string byte-for-byte with the golden `.tree` file. Parse the same source twice and assert identical definitions, references, and output.

- [ ] **Step 3: Run the focused test to verify failure**

```bash
dune exec ./test/compiler_test.exe
```

Expected: FAIL with unbound `Tree_md.Compiler`.

- [ ] **Step 4: Implement pure orchestration**

Run `Frontmatter.parse`, `Markdown.parse`, and `Outline.build` in order. Accumulate all independent diagnostics before returning `Error`, sort them with `Diagnostic.compare`, and do not invoke the emitter after any error. Collect generated root and named-subtree definitions, Wiki/embed/attribution references, and local images by traversing the compiler-owned structures.

- [ ] **Step 5: Run the Phase 1 checkpoint and commit**

```bash
dune exec ./test/compiler_test.exe
dune runtest
git add tools/tree-md/lib/parsed_document.ml tools/tree-md/lib/parsed_document.mli tools/tree-md/lib/compiler.ml tools/tree-md/lib/compiler.mli tools/tree-md/test/dune tools/tree-md/test/compiler_test.ml tools/tree-md/test/fixtures/markdown/complete.tree.md tools/tree-md/test/fixtures/forester/complete.tree
git commit -m "feat(tree-md): complete the pure compiler pipeline"
```

Expected: the complete golden conversion and every Phase 1 test PASS.

---

## Phase 2: Configuration, Discovery, and Forest Resolution

### Task 9: Safe Paths and Configuration Loading

**Files:**
- Create: `tools/tree-md/lib/path_safe.ml`
- Create: `tools/tree-md/lib/path_safe.mli`
- Create: `tools/tree-md/lib/config.ml`
- Create: `tools/tree-md/lib/config.mli`
- Create: `tools/tree-md/test/config_test.ml`
- Create: `tools/tree-md/test/fixtures/config/valid/tree-md.toml`
- Create: `tools/tree-md/test/fixtures/config/valid/forest.toml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: a literal config path selected by CLI.
- Produces: normalized absolute operational paths plus original forest-relative path strings needed by `\route-asset`.

Create `path_safe.mli`:

```ocaml
type relative

val relative : string -> (relative, string) result
val to_string : relative -> string
val append : relative -> relative -> relative
val basename : relative -> string
val resolve : base:string -> relative -> string
val is_within : root:string -> string -> bool
```

Create `config.mli`:

```ocaml
type forest = {
  path : string;
  directory : string;
  tree_roots : (Path_safe.relative * string) list;
  asset_roots : (Path_safe.relative * string) list;
}

type t = {
  path : string;
  directory : string;
  forest : forest;
  source_roots : (Path_safe.relative * string) list;
  output_root : Path_safe.relative * string;
  target : string;
}

val load : path:string -> (t, Diagnostic.t list) result
```

Each pair stores the config-relative representation and resolved filesystem path.

- [ ] **Step 1: Write failing path/config tests**

Test a valid config from a working directory different from the fixture directory. Assert that `forest`, `sources`, and `output` resolve against `tree-md.toml`, while forest tree/asset paths resolve against `forest.toml`.

Add `TM401` cases for missing file, wrong `version`, unknown field, missing field, unsupported target, absolute path, empty segment, `.`, `..`, backslash, source/output overlap, duplicate source root, output absent from `[forest].trees`, and a non-string tree/asset list member.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/config_test.exe
```

Expected: FAIL with unbound `Tree_md.Config`.

- [ ] **Step 3: Implement lexical path safety and Otoml decoding**

`Path_safe.relative` accepts `/`-separated non-empty segments, rejects absolute and platform-backslash forms, and never normalizes away `.` or `..`; those are errors. Resolve only after lexical validation.

Read TOML bytes directly, call `Otoml.Parser.from_string_result`, prefix syntax errors with the file path, and reject duplicate/unknown keys through a closed schema. Require exactly `version = 1` and the pinned target string. Compare normalized resolved paths when enforcing overlap and forest-tree membership.

- [ ] **Step 4: Run tests and commit**

```bash
dune exec ./test/config_test.exe
dune runtest
git add tools/tree-md/lib/path_safe.ml tools/tree-md/lib/path_safe.mli tools/tree-md/lib/config.ml tools/tree-md/lib/config.mli tools/tree-md/test/dune tools/tree-md/test/config_test.ml tools/tree-md/test/fixtures/config
git commit -m "feat(tree-md): load safe compiler configuration"
```

Expected: valid path-base assertions and all invalid-config diagnostics PASS.

### Task 10: Recursive Discovery and Address Derivation

**Files:**
- Create: `tools/tree-md/lib/discovery.ml`
- Create: `tools/tree-md/lib/discovery.mli`
- Create: `tools/tree-md/test/discovery_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: validated `Config.t` and an on-disk fixture tree.
- Produces: deterministically sorted source files, handwritten roots, and asset candidates without following symlinks.

Create `discovery.mli`:

```ocaml
type source_file = {
  source_root : string;
  path : string;
  config_relative : Path_safe.relative;
  source_relative : Path_safe.relative;
  output_relative : Path_safe.relative;
  root_id : string;
}

type handwritten_root = { id : string; path : string }

type t = {
  sources : source_file list;
  handwritten_roots : handwritten_root list;
}

val scan : Config.t -> (t, Diagnostic.t list) result
val asset_matches : Config.forest -> Path_safe.relative -> string list
```

- [ ] **Step 1: Write failing discovery tests in temporary directories**

Create runtime fixture directories with:

```text
trees-md/a/foo.tree.md
trees-md/b/bar.tree.md
trees-md/ignored.md
trees-md/.hidden.tree.md
trees-md/.hidden/note.tree.md
trees/manual.tree
generated/old.tree
assets/images/x.png
assets-alt/images/x.png
```

Add symlinks to a source file, directory, tree, and outside asset when the platform supports them. Assert sorted `bar`, `foo`; mirrored outputs `b/bar.tree`, `a/foo.tree`; hidden and symlink entries ignored; handwritten `manual` included; generated roots excluded from handwritten discovery.

Add `TM201` or `TM205` cases for invalid root stems, duplicate stems across source roots, and a path that changes type during scanning.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/discovery_test.exe
```

Expected: FAIL with unbound `Tree_md.Discovery`.

- [ ] **Step 3: Implement deterministic no-symlink scanning**

Use `Unix.lstat`, never `Unix.stat`, before descending or opening discovered entries. Ignore a path when any relative component starts with `.`. Accept only regular files ending exactly `.tree.md` for sources and `.tree` for handwritten roots. Strip the complete `.tree.md` suffix for identity, validate with `Metadata.valid_id`, and preserve source-relative directories when deriving output.

Sort directory entries before descent and sort final records by normalized path. Exclude the configured generated root from handwritten discovery by resolved path equality.

- [ ] **Step 4: Run tests and commit**

```bash
dune exec ./test/discovery_test.exe
dune runtest
git add tools/tree-md/lib/discovery.ml tools/tree-md/lib/discovery.mli tools/tree-md/test/dune tools/tree-md/test/discovery_test.ml
git commit -m "feat(tree-md): discover forest sources safely"
```

Expected: discovery, hidden-path, symlink, and ordering tests PASS.

### Task 11: Global Identity, Reference, and Asset Resolution

**Files:**
- Create: `tools/tree-md/lib/forest_index.ml`
- Create: `tools/tree-md/lib/forest_index.mli`
- Modify: `tools/tree-md/lib/resolution.ml`
- Modify: `tools/tree-md/lib/resolution.mli`
- Create: `tools/tree-md/test/forest_index_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: parsed generated documents, handwritten physical roots, configured asset roots.
- Produces: one global definition index and one `Resolution.t` per source document.

Create `forest_index.mli`:

```ocaml
type definition_kind = Generated_root | Generated_subtree | Handwritten_root
type definition = {
  id : string;
  kind : definition_kind;
  location : Span.location;
}

type t

val build :
  handwritten:Discovery.handwritten_root list ->
  generated:Parsed_document.t list ->
  (t, Diagnostic.t list) result

val resolve :
  Config.forest -> t ->
  documents:Parsed_document.t list ->
  ((string * Resolution.t) list, Diagnostic.t list) result
```

The string key returned by `resolve` is `document.outline.root_id`.

- [ ] **Step 1: Write failing forest-wide validation tests**

Cover duplicate generated roots, root versus named subtree, two named subtrees, generated versus handwritten root, unresolved Wiki link, unresolved embed, unresolved author/contributor tree attribution, successful literal attribution, and an ordinary safe relative Markdown link that is intentionally not checked against the identity index.

For assets, test zero matches (`TM203`), two roots with the same relative file (`TM204`), one regular match, symlink escape (`TM205`), and exact routed path `assets/images/x.png` relative to `forest.toml`.

Assert duplicate diagnostics have the first definition as primary and every later definition as labelled secondary locations, sorted by source path and byte.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/forest_index_test.exe
```

Expected: FAIL with unbound `Tree_md.Forest_index`.

- [ ] **Step 3: Implement global definition and reference validation**

Insert generated roots, generated named subtrees, and handwritten stems into one string map. Never inspect named subtrees inside handwritten source. Validate every `Ir.reference` of kind `Wiki`, `Embed`, or `Attribution` against that map and emit `TM202` at its original source span.

Resolve each local image relative to every configured asset root. Require exactly one regular file after `lstat`; resolve real paths only to confirm containment and reject symlink components. Store the forest-config-relative root prefix plus local destination in the document's `Resolution.t`.

- [ ] **Step 4: Run tests and commit**

```bash
dune exec ./test/forest_index_test.exe
dune runtest
git add tools/tree-md/lib/forest_index.ml tools/tree-md/lib/forest_index.mli tools/tree-md/lib/resolution.ml tools/tree-md/lib/resolution.mli tools/tree-md/test/dune tools/tree-md/test/forest_index_test.ml
git commit -m "feat(tree-md): validate global forest references"
```

Expected: all collision, unresolved-reference, and asset routing tests PASS.

### Task 12: Multi-document Pure Compilation Checkpoint

**Files:**
- Modify: `tools/tree-md/lib/compiler.ml`
- Modify: `tools/tree-md/lib/compiler.mli`
- Create: `tools/tree-md/test/forest_compile_test.ml`
- Create: `tools/tree-md/test/fixtures/workspaces/compile/trees-md/index.tree.md`
- Create: `tools/tree-md/test/fixtures/workspaces/compile/trees-md/child.tree.md`
- Create: `tools/tree-md/test/fixtures/workspaces/compile/trees/manual.tree`
- Create: `tools/tree-md/test/fixtures/workspaces/compile/assets/images/x.png`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: `Config.t` plus `Discovery.t`.
- Produces: sorted expected output records with bytes and SHA-256; performs no writes.

Extend `compiler.mli`:

```ocaml
type expected = {
  source_path : string;
  source_config_relative : Path_safe.relative;
  output_relative : Path_safe.relative;
  bytes : string;
  sha256 : string;
}

val compile_forest :
  Config.t -> Discovery.t -> (expected list, Diagnostic.t list) result
```

- [ ] **Step 1: Write the failing multi-document test**

Use `index.tree.md` to link to and embed `child`, attribute `manual`, and include the local image. Assert two output records sorted by output path, exact config-relative source and output-relative names, 64 lowercase SHA-256 digits, the routed asset path, and byte-identical output across two calls.

Add one bad fixture containing collisions, unresolved references, and a missing asset; assert all independent diagnostics are returned in deterministic order and no expected records are returned.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/forest_compile_test.exe
```

Expected: FAIL because `Compiler.compile_forest` is absent.

- [ ] **Step 3: Implement pure forest orchestration**

Read each discovered source only after confirming it remains a regular non-symlink file. Parse every source and retain valid documents while collecting all parse diagnostics. Build a provisional global index from valid documents so independent collision/reference/asset diagnostics are still reported. Return no expected outputs when any diagnostic exists; otherwise resolve every document, emit it, and hash exact bytes with `Digestif.SHA256` lowercase hex.

Sort expected records by output-relative path then source path. Do not inspect or mutate the output root.

- [ ] **Step 4: Run the Phase 2 checkpoint and commit**

```bash
dune exec ./test/forest_compile_test.exe
dune runtest
git add tools/tree-md/lib/compiler.ml tools/tree-md/lib/compiler.mli tools/tree-md/test/dune tools/tree-md/test/forest_compile_test.ml tools/tree-md/test/fixtures/workspaces/compile
git commit -m "feat(tree-md): compile complete forests purely"
```

Expected: the multi-document fixture compiles deterministically and every Phase 2 test PASS.

---

## Phase 3: Manifest, Transactions, Workspace, and CLI

### Task 13: Versioned Manifest and Expected-state Diff

**Files:**
- Create: `tools/tree-md/lib/manifest.ml`
- Create: `tools/tree-md/lib/manifest.mli`
- Create: `tools/tree-md/test/manifest_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: sorted `Compiler.expected` records and current output hashes supplied by the caller.
- Produces: canonical manifest JSON and pure create/replace/delete/unchanged operations.

Create `manifest.mli`:

```ocaml
type entry = {
  source : Path_safe.relative;
  output : Path_safe.relative;
  sha256 : string;
}

type t = {
  format : int;
  compiler : string;
  target : string;
  files : entry list;
}

type operation =
  | Create of entry
  | Replace of { old_entry : entry; new_entry : entry }
  | Delete of entry
  | Unchanged of entry

val current_version : string
val of_expected : Compiler.expected list -> t
val encode : t -> string
val decode : path:string -> string -> (t, Diagnostic.t list) result
val diff : old:t option -> next:t -> operation list
val sha256 : string -> string
```

- [ ] **Step 1: Write failing canonical-schema tests**

Assert this exact field order and final newline:

```json
{
  "format": 1,
  "compiler": "0.1.0",
  "target": "forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be",
  "files": []
}
```

Test sorted entries, encode/decode round trip, exact lowercase SHA-256, and each diff constructor. Add `TM402` cases for malformed JSON, unknown/missing fields, format 2, wrong compiler/target type, duplicate source/output, uppercase/short hash, absolute/dot/dot/backslash path, non-`.tree` output, and a component beginning `.tree-md`.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/manifest_test.exe
```

Expected: FAIL with unbound `Tree_md.Manifest`.

- [ ] **Step 3: Implement closed Yojson decoding and canonical encoding**

Decode JSON objects by consuming each known key exactly once and rejecting leftovers. Validate source paths end in `.tree.md`, output paths end in `.tree`, and both are normalized `Path_safe.relative` values. Sort files by output then source during both construction and encoding.

Build JSON with ordered association lists and serialize through `Yojson.Safe.pretty_to_string ~std:true`; append exactly one LF after stripping any serializer trailing LF.

- [ ] **Step 4: Run tests and commit**

```bash
dune exec ./test/manifest_test.exe
dune runtest
git add tools/tree-md/lib/manifest.ml tools/tree-md/lib/manifest.mli tools/tree-md/test/dune tools/tree-md/test/manifest_test.ml
git commit -m "feat(tree-md): define the generated-file manifest"
```

Expected: schema, canonical-byte, and diff tests PASS.

### Task 14: Pure Transaction Journal State Machine

**Files:**
- Create: `tools/tree-md/lib/transaction.ml`
- Create: `tools/tree-md/lib/transaction.mli`
- Create: `tools/tree-md/test/transaction_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: a manifest diff, base/new manifest hashes, and observed file hashes.
- Produces: closed journal JSON plus a deterministic roll-forward action list; performs no I/O.

Create `transaction.mli`:

```ocaml
type operation = {
  output : Path_safe.relative;
  old_sha256 : string option;
  new_sha256 : string option;
  temporary : Path_safe.relative option;
}

type t = {
  format : int;
  base_manifest_sha256 : string option;
  new_manifest_sha256 : string;
  new_manifest_temporary : Path_safe.relative;
  operations : operation list;
}

type observed = Missing | Hash of string
type action =
  | Ensure_parent of Path_safe.relative
  | Install_output of { temporary : Path_safe.relative; output : Path_safe.relative; sha256 : string }
  | Delete_output of { output : Path_safe.relative; old_sha256 : string }
  | Install_manifest of { temporary : Path_safe.relative; sha256 : string }
  | Remove_stage of Path_safe.relative
  | Remove_journal

val create :
  transaction_id:string -> old_manifest:Manifest.t option ->
  new_manifest:Manifest.t -> Manifest.operation list -> t
val encode : t -> string
val decode : path:string -> string -> (t, Diagnostic.t list) result
val roll_forward :
  t -> current_manifest:observed ->
  output:(Path_safe.relative -> observed) ->
  temporary:(Path_safe.relative -> observed) ->
  (action list, Diagnostic.t list) result
```

- [ ] **Step 1: Write the complete state-table tests**

Cover every allowed state:

```text
create: output missing/new
replace: output old/new
delete: output old/missing
manifest: base/new
```

For each not-yet-complete create/replace, require a temporary with the new hash. Require the temporary manifest when current manifest is base. Assert ordered actions: ensure parent, install outputs/deletes, install manifest, remove stage, remove journal.

Add `TM403` cases for output with a third hash, missing replacement output, missing/wrong temporary, wrong current manifest, unsafe/duplicate paths, malformed/unknown JSON fields, inconsistent null combinations, and a journal path outside `.tree-md-stage/txn-ID/`.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/transaction_test.exe
```

Expected: FAIL with unbound `Tree_md.Transaction`.

- [ ] **Step 3: Implement canonical journal creation and decoding**

Derive one operation from every non-`Unchanged` manifest diff. Use output-root-relative staged names:

```text
.tree-md-stage/txn-ID/manifest.tmp
.tree-md-stage/txn-ID/PATH.tree.tmp
```

Require transaction IDs to match `[A-Za-z0-9_-]+`. Canonically sort operations by output. Enforce the same closed JSON and path rules as the manifest.

- [ ] **Step 4: Implement deterministic roll-forward planning**

If current manifest equals the new hash, verify every output is in its new state and return cleanup actions only. If it equals the base hash, map the exact state table to actions. Return all validation diagnostics before returning any action; never produce a partial action list alongside errors.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/transaction_test.exe
dune runtest
git add tools/tree-md/lib/transaction.ml tools/tree-md/lib/transaction.mli tools/tree-md/test/dune tools/tree-md/test/transaction_test.ml
git commit -m "feat(tree-md): model crash-safe transactions"
```

Expected: all state-machine and malformed-journal cases PASS.

### Task 15: Filesystem Locking, Staging, Durability, and Recovery

**Files:**
- Create: `tools/tree-md/lib/workspace_fs.ml`
- Create: `tools/tree-md/lib/workspace_fs.mli`
- Create: `tools/tree-md/test/workspace_fs_test.ml`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: validated output root, journal, staged bytes, and pure `Transaction.action` values.
- Produces: no-symlink, same-filesystem durable operations and non-mutating state snapshots.

Create `workspace_fs.mli`:

```ocaml
type snapshot = {
  manifest : string option;
  journal : string option;
  stage_entries : string list;
}

type fault_point =
  | After_stage
  | After_journal
  | After_output of int
  | After_manifest

exception Injected_fault of fault_point

val snapshot : output_root:string -> (snapshot, Diagnostic.t list) result
val with_build_lock : output_root:string -> (unit -> 'a) -> ('a, Diagnostic.t list) result
val writer_active : output_root:string -> (bool, Diagnostic.t list) result
val stage :
  ?inject:(fault_point -> unit) -> output_root:string ->
  journal:Transaction.t -> files:(Path_safe.relative * string) list ->
  manifest_bytes:string -> (unit, Diagnostic.t list) result
val execute :
  ?inject:(fault_point -> unit) -> output_root:string ->
  Transaction.action list -> (unit, Diagnostic.t list) result
val remove_orphan_stage : output_root:string -> (unit, Diagnostic.t list) result
```

The fault-injection parameters are used only by tests; production callers omit them.
Each `stage` file key is the exact output-root-relative `operation.temporary` path from the journal; `manifest_bytes` is written at `journal.new_manifest_temporary`.

- [ ] **Step 1: Write failing lock and crash-boundary tests**

In temporary directories, test exclusive build-lock contention, read-only `writer_active`, and that snapshot changes are observable without writes. Test refusal of symlink output roots, symlink ancestors, symlink final outputs, and cross-root paths.

Inject faults after stage, journal, first output, and manifest. Restart through `Transaction.roll_forward` and assert the final manifest/output hashes equal the intended new state at every boundary. Assert an orphan stage before journal is reported to `check` and removable by `build` only.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/workspace_fs_test.exe
```

Expected: FAIL with unbound `Tree_md.Workspace_fs`.

- [ ] **Step 3: Implement lock and no-symlink path traversal**

Open every path component with `lstat` checks immediately before use. Create the output root only in `with_build_lock`; after creation, fsync its parent before creating `.tree-md.lock`. Hold `Unix.lockf fd F_TLOCK 0` for the callback and translate contention to `TM403`. `writer_active` opens an existing lock read-only and uses a non-mutating lock test; absence means no writer.

Create final parent directories only after journal installation and only from journaled outputs. Reject any component that becomes a symlink or non-directory.

- [ ] **Step 4: Implement staging and durability barriers**

Write staged output and manifest files with `O_CREAT|O_EXCL`, mode `0o600`, fsync each file, then fsync each stage directory bottom-up. Install and fsync the journal and output-root directory before the first final operation.

After each unique final parent receives a mkdir, rename, or delete, fsync it. After manifest rename, fsync the output root. Remove empty stage directories, fsync their parents, remove the journal last, and fsync the output root again. Use rename only within the same output filesystem.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/workspace_fs_test.exe
dune runtest
git add tools/tree-md/lib/workspace_fs.ml tools/tree-md/lib/workspace_fs.mli tools/tree-md/test/dune tools/tree-md/test/workspace_fs_test.ml
git commit -m "feat(tree-md): execute durable workspace transactions"
```

Expected: lock, symlink, orphan-stage, and every injected crash recovery test PASS.

### Task 16: Read-only Check and Transactional Build Workflows

**Files:**
- Create: `tools/tree-md/lib/workspace.ml`
- Create: `tools/tree-md/lib/workspace.mli`
- Create: `tools/tree-md/test/workspace_test.ml`
- Create: `tools/tree-md/test/fixtures/workspaces/clean/tree-md.toml`
- Create: `tools/tree-md/test/fixtures/workspaces/clean/forest.toml`
- Create: `tools/tree-md/test/fixtures/workspaces/clean/trees-md/index.tree.md`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: config path and all pure/compiler/filesystem services.
- Produces: sorted diagnostics and a summary; `check` never writes, `build` owns only manifest and reserved state.

Create `workspace.mli`:

```ocaml
type summary = {
  created : int;
  replaced : int;
  deleted : int;
  unchanged : int;
}

type result = { summary : summary; diagnostics : Diagnostic.t list }

val check : config_path:string -> result
val build : config_path:string -> result
```

- [ ] **Step 1: Write failing end-to-end workspace tests**

Test first check reports missing manifest/output without creating the output root; first build creates output and manifest; second build is a no-op; clean check has zero diagnostics and identical pre/post filesystem snapshots.

Test source edit replacement, source deletion stale cleanup, missing output, manually modified output protection, unknown collision, malformed manifest, active writer, orphan stage, interrupted valid journal roll-forward, and source error leaving established output unchanged.

Assert summary counts and exact diagnostic codes for every state.

- [ ] **Step 2: Run the focused test to verify failure**

```bash
dune exec ./test/workspace_test.exe
```

Expected: FAIL with unbound `Tree_md.Workspace`.

- [ ] **Step 3: Implement read-only `check`**

Load config, test writer activity, and capture a start snapshot. Discover and compile expected files, decode manifest without creating any path, hash existing outputs through no-symlink reads, and report `TM301`-`TM306` differences. Capture an end snapshot; if compiler state changed, replace success with an exit-code 2 concurrency diagnostic. Never call lock, recovery, orphan removal, mkdir, or write functions.

- [ ] **Step 4: Implement transactional `build`**

For no journal and no orphan stage, compile and validate before creating output state. Acquire the exclusive writer lock, recheck source/config digests, and restart compilation under lock if they changed. If an orphan stage or existing journal is present, acquire the lock first; remove only a validated orphan stage or execute the validated roll-forward, then compile current source.

Verify current managed hashes against the old manifest before staging. Reject modified/unknown files. Build next manifest, pure diff, journal, staged outputs, then execute the transaction. Return summary counts only after journal removal.

- [ ] **Step 5: Run tests and commit**

```bash
dune exec ./test/workspace_test.exe
dune runtest
git add tools/tree-md/lib/workspace.ml tools/tree-md/lib/workspace.mli tools/tree-md/test/dune tools/tree-md/test/workspace_test.ml tools/tree-md/test/fixtures/workspaces/clean
git commit -m "feat(tree-md): add build and check workflows"
```

Expected: all workspace lifecycle and read-only guarantees PASS.

### Task 17: Cmdliner CLI, Exit Codes, and Cram Tests

**Files:**
- Create: `tools/tree-md/lib/cli.ml`
- Create: `tools/tree-md/lib/cli.mli`
- Create: `tools/tree-md/bin/dune`
- Create: `tools/tree-md/bin/main.ml`
- Create: `tools/tree-md/test/cli_test.ml`
- Create: `tools/tree-md/test/cli.t/run.t`
- Modify: `tools/tree-md/test/dune`

**Interfaces:**
- Consumes: `Workspace.check/build`, source map, structured diagnostics.
- Produces: installed `tree-md`, exact human output, exit codes 0/1/2.

Create `cli.mli`:

```ocaml
val command : Cmdliner.Cmd.Exit.code Cmdliner.Cmd.t
val exit_code : Workspace.result -> Cmdliner.Cmd.Exit.code

module For_test : sig
  val render_unexpected :
    backtrace_enabled:bool -> exn -> Printexc.raw_backtrace -> string * int
end
```

Create `bin/main.ml`:

```ocaml
let () = exit (Cmdliner.Cmd.eval' Tree_md.Cli.command)
```

Create `bin/dune`:

```lisp
(executable
 (name main)
 (public_name tree-md)
 (libraries tree-md cmdliner))
```

- [ ] **Step 1: Write failing cram scenarios**

Add test aliases/dependencies for `%{bin:tree-md}` and fixture copies. Cover:

```text
tree-md --help
tree-md --version
tree-md check --config PATH
tree-md build --config PATH
default ./tree-md.toml with no upward search
source diagnostic -> exit 1
generated-state diagnostic -> exit 1
unsupported target/config -> exit 2
```

Normalize temporary paths through a cram environment variable; do not normalize diagnostic codes, line/column, or messages.

In `cli_test.ml`, call `Cli.For_test.render_unexpected` with `Exit` and a captured raw backtrace. Assert exit 2, no backtrace when false, and a backtrace section when true. Separately assert that `Out_of_memory` and `Sys.Break` are reraised by the top-level exception filter.

- [ ] **Step 2: Run the cram test to verify failure**

```bash
dune runtest test/cli.t
```

Expected: FAIL because the executable and command terms do not exist.

- [ ] **Step 3: Implement Cmdliner terms and rendering**

Define one root command with `build` and `check` subcommands. Both accept `--config PATH`, default exactly `./tree-md.toml`, and never search parents. Print diagnostics sorted through `Diagnostic.render` to stderr. Print a one-line build summary to stdout only on success; clean `check` is silent.

Map source/semantic/generated diagnostics to 1 and usage/config/manifest/journal/I/O/internal failures to 2. Catch unexpected exceptions only in `Cli`, print a backtrace only when `TREE_MD_BACKTRACE=1`, and never catch `Out_of_memory` or `Sys.Break` as ordinary diagnostics.

- [ ] **Step 4: Run tests and commit**

```bash
dune runtest test/cli.t
dune runtest
git add tools/tree-md/lib/cli.ml tools/tree-md/lib/cli.mli tools/tree-md/bin tools/tree-md/test/dune tools/tree-md/test/cli_test.ml tools/tree-md/test/cli.t
git commit -m "feat(tree-md): expose build and check CLI"
```

Expected: every CLI scenario has the documented stdout, stderr, and exit code; all Phase 3 tests PASS.

---

## Phase 4: Repository Integration and Compatibility Gates

### Task 18: Integrate Empty Source and Generated Roots into This Forest

**Files:**
- Create: `tree-md.toml`
- Create: `trees-md/.gitkeep`
- Create: `generated/.gitkeep`
- Create: `generated/.tree-md-manifest.json` through `tree-md build`
- Modify: `forest.toml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the completed CLI and current forest configuration.
- Produces: a usable but initially empty Markdown source root; does not migrate handwritten trees.

- [ ] **Step 1: Snapshot handwritten content before integration**

From the repository root, record every existing handwritten tree path and hash outside the worktree:

```bash
rg --files trees -g '*.tree' | LC_ALL=C sort | while IFS= read -r path; do
  sha256sum "$path"
done > /tmp/tree-md-handwritten.before
```

Verify the snapshot contains `trees/index.tree` and `trees/aboutme.tree` before continuing.

- [ ] **Step 2: Add compiler configuration and roots**

Create root `tree-md.toml`:

```toml
version = 1
forest = "forest.toml"
sources = ["trees-md"]
output = "generated"
target = "forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be"
```

Change only the tree-root line in `forest.toml`:

```toml
trees = ["trees", "generated"]
```

Create `.gitkeep` in both new directories. Append these exact internal-state ignores to `.gitignore`:

```gitignore
/generated/.tree-md.lock
/generated/.tree-md-transaction.json
/generated/.tree-md-stage/
```

Do not ignore generated `.tree` files or `.tree-md-manifest.json`; they are reviewable generated state.

- [ ] **Step 3: Run the failing read-only check**

From `tools/tree-md`:

```bash
dune exec tree-md -- check --config ../../tree-md.toml
```

Expected: exit 1 with `TM301` because the manifest has not been generated; no root/output files change.

- [ ] **Step 4: Build the empty manifest and re-check**

```bash
dune exec tree-md -- build --config ../../tree-md.toml
dune exec tree-md -- check --config ../../tree-md.toml
```

Expected: build reports zero created/replaced/deleted tree files and writes the version-1 empty manifest; check is silent and exits 0.

- [ ] **Step 5: Verify handwritten hashes and commit integration only**

```bash
rg --files trees -g '*.tree' | LC_ALL=C sort | while IFS= read -r path; do
  sha256sum "$path"
done > /tmp/tree-md-handwritten.after
diff -u /tmp/tree-md-handwritten.before /tmp/tree-md-handwritten.after
dune runtest test/cli.t
git diff --check
git add .gitignore forest.toml tree-md.toml trees-md/.gitkeep generated/.gitkeep generated/.tree-md-manifest.json
git commit -m "chore(tree-md): integrate compiler roots"
```

Expected: handwritten hash assertion PASS; the commit contains no existing `.tree` changes.

### Task 19: Pinned Forester 6 Compatibility Fixture and CI Job

**Files:**
- Create: `tools/tree-md/test/fixtures/compat/tree-md.toml`
- Create: `tools/tree-md/test/fixtures/compat/forest.toml`
- Create: `tools/tree-md/test/fixtures/compat/trees-md/index.tree.md`
- Create: `tools/tree-md/test/fixtures/compat/trees/manual.tree`
- Create: `tools/tree-md/test/fixtures/compat/assets/images/x.svg`
- Create: `tools/tree-md/test/forester_compat.sh`
- Create: `.github/workflows/tree-md.yml`

**Interfaces:**
- Consumes: built `tree-md` executable and external Forester pinned at the approved commit.
- Produces: a CI compatibility gate; never links Forester into the library.

- [ ] **Step 1: Add the complete compatibility fixture**

The source must exercise date/taxon/authors/contributors/tags/meta, named and anonymous nested subtrees, native and Wiki links, direct transclusion, inline/display math, quote, tight/loose/started lists, inline/fenced code with hostile punctuation, hard/thematic breaks, external/local images, and Unicode text. Include physical `manual.tree` for an attribution/reference target.

Use a minimal forest configuration with tree roots `generated` and `trees`, asset root `assets`, home `index`, and URL `http://forest.local/`.

- [ ] **Step 2: Write the failing compatibility script**

Create executable `forester_compat.sh`:

```sh
#!/bin/sh
set -eu

: "${TREE_MD:?TREE_MD must name the compiler executable}"
: "${FORESTER:?FORESTER must name the pinned Forester executable}"

version=$("$FORESTER" --version)
if test "$version" != "6.0~dev"; then
  printf '%s\n' "expected Forester 6.0~dev, got $version" >&2
  exit 1
fi

fixture=$1
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM
cp -R "$fixture"/. "$tmp"/

"$TREE_MD" build --config "$tmp/tree-md.toml"
"$TREE_MD" check --config "$tmp/tree-md.toml"

if ! (cd "$tmp" && "$FORESTER" build --no-theme forest.toml) 2>"$tmp/forester.err"; then
  sed -n '1,200p' "$tmp/forester.err" >&2
  exit 1
fi

if grep -Eiq 'warning|unknown binding' "$tmp/forester.err"; then
  exit 1
fi

test -f "$tmp/output/index.html"
```

Run it first with the currently installed Forester 5.0 only to verify the test does not falsely claim 6.0 compatibility. Expected: the gate is not accepted until CI installs the pinned executable.

- [ ] **Step 3: Add the pinned GitHub Actions job**

Create `.github/workflows/tree-md.yml` with these fixed stages:

```yaml
name: tree-md

on:
  push:
    paths:
      - "tools/tree-md/**"
      - "tree-md.toml"
      - "forest.toml"
      - ".github/workflows/tree-md.yml"
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: false
      - uses: ocaml/setup-ocaml@v3
        with:
          ocaml-compiler: "5.3.0"
      - run: opam install ./tools/tree-md --deps-only --with-test
      - run: opam exec -- dune runtest
        working-directory: tools/tree-md
      - run: opam pin add -yn forester git+https://git.sr.ht/~jonsterling/ocaml-forester#30b73641cef02433ee158db6ddc77f7b49de60be
      - run: opam install -y forester
      - run: |
          TREE_MD="$(pwd)/tools/tree-md/_build/default/bin/main.exe" \
          FORESTER="$(opam exec -- which forester)" \
          tools/tree-md/test/forester_compat.sh tools/tree-md/test/fixtures/compat
```

- [ ] **Step 4: Run the fixture locally only with a pinned executable**

When a pinned executable is available, first build the compiler through its test suite and invoke the script directly:

```bash
dune runtest
TREE_MD="$PWD/_build/default/bin/main.exe" \
FORESTER="$(command -v forester)" \
test/forester_compat.sh test/fixtures/compat
```

Expected: pinned Forester reports `6.0~dev`, exits 0, emits no warning/unknown-binding line attributable to generated source, and produces `output/index.html` in the temporary fixture.

- [ ] **Step 5: Commit the compatibility gate**

```bash
git add .github/workflows/tree-md.yml tools/tree-md/test/forester_compat.sh tools/tree-md/test/fixtures/compat
git commit -m "test(tree-md): pin Forester 6 compatibility"
```

Expected: normal tests remain independent of Forester; CI owns the pinned compatibility proof.

### Task 20: Lockfile, Dependency Audit, Usage Documentation, and Final Verification

**Files:**
- Create: `tools/tree-md/tree-md.opam.locked`
- Create: `tools/tree-md/DEPENDENCIES.md`
- Create: `tools/tree-md/README.md`
- Create: `tools/tree-md/VERIFICATION.md`
- Modify: `tools/tree-md/tree-md.opam` if generated metadata needs canonical ordering only

**Interfaces:**
- Consumes: completed project and compatibility job.
- Produces: reproducible dependency resolution, license evidence, operator documentation, and final acceptance evidence.

- [ ] **Step 1: Generate and inspect package metadata and lockfile**

From `tools/tree-md`:

```bash
dune runtest
opam lock tree-md.opam
```

Expected: `tree-md.opam` reflects the exact dune-project constraints and `tree-md.opam.locked` is created. Do not hand-relax any pinned version.

- [ ] **Step 2: Write the complete dependency audit**

Install the local package into the isolated switch, then enumerate its closure:

```bash
opam install . --with-test
opam list --installed --required-by tree-md --recursive
```

`DEPENDENCIES.md` must list every reported package, its resolved version, license expression from `opam show`, source URL, and runtime/build/test classification. It must explicitly confirm that no linked dependency is AGPL/GPL/LGPL and separately record build tools whose licenses do not propagate to generated code.

Fail this task and revisit dependencies if any linked package is not permissive. Do not add a compiler project license as part of the audit.

- [ ] **Step 3: Document exact usage and constraints**

`README.md` must include:

```text
tree-md check [--config PATH]
tree-md build [--config PATH]
default config: ./tree-md.toml, no parent search
source/output: trees-md -> generated
target: forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be
exit codes: 0 success, 1 source/state diagnostics, 2 usage/config/I/O/internal
```

Include one YAML/H1/H2/subtree/Wiki/embed/math example, the supported/rejected syntax summary, generated-file ownership warning, read-only `check` guarantee, manual-modification protection, transaction recovery behavior, and the local-filesystem atomic-rename/fsync durability requirement.

- [ ] **Step 4: Run full fresh verification**

After the required status/diff approval, run from `tools/tree-md`:

```bash
dune runtest
dune exec tree-md -- check --config ../../tree-md.toml
git diff --check
```

Run the compatibility script only with a verified pinned Forester 6.0-dev executable:

```bash
TREE_MD="$PWD/_build/default/bin/main.exe" \
FORESTER="$(command -v forester)" \
test/forester_compat.sh test/fixtures/compat
```

Expected: all Alcotest and cram suites PASS; repository `check` exits 0 without writing; diff check is silent; compatibility build exits 0 with no generated-source warning.

- [ ] **Step 5: Verify acceptance criteria against the spec**

Read `docs/superpowers/specs/2026-08-02-tree-markdown-compiler-design.md` section by section and create `VERIFICATION.md` mapping each requirement to an exact test executable, cram scenario, or compatibility-fixture assertion. Confirm all 26 stable diagnostic codes are exercised, every supported mapping has a golden assertion, every rejected syntax class has a diagnostic assertion, and existing handwritten-tree hashes are unchanged.

- [ ] **Step 6: Commit final reproducibility and docs**

```bash
git add tools/tree-md/tree-md.opam tools/tree-md/tree-md.opam.locked tools/tree-md/DEPENDENCIES.md tools/tree-md/README.md tools/tree-md/VERIFICATION.md
git commit -m "docs(tree-md): document reproducible compiler usage"
```

Expected: the final commit contains only package metadata and documentation; implementation is complete only with fresh verification output from Step 4.
