# `.tree.md` to `.tree` Compiler Design

Date: 2026-08-02

## Summary

This document specifies an OCaml compiler that converts a strict Markdown dialect in
`.tree.md` files into deterministic Forester `.tree` source files. Markdown headings
become nested Forester subtrees, while Obsidian-style embeds become direct Forester
transclusions. The compiler is implemented as a reusable library with a thin CLI and
is integrated into this forest without migrating existing handwritten trees.

The compiler targets the source language and CLI behavior of the official
`forester-6.0-dev` branch at commit
`30b73641cef02433ee158db6ddc77f7b49de60be`. This target is experimental because the
Forester website lists a 6.0 release, but the official repository has no `6.0` tag and
the branch still identifies itself as `6.0~dev`.

## Goals

- Preserve CommonMark core semantics where Forester has a sound representation.
- Represent document hierarchy as Forester trees rather than visual-only headings.
- Support a small, explicit subset of Obsidian internal links and embeds.
- Produce safe Forester source without allowing Markdown text to become commands.
- Report precise, stable diagnostics against the original UTF-8 source.
- Validate identities, Wiki references, tree attributions, embeds, assets, and
  generated-file state across the forest.
- Keep the parser, semantic model, validator, and emitter reusable outside the CLI.
- Keep direct and linked dependencies permissively licensed so that the compiler's
  eventual license remains open.

## Non-goals

- Migrating or modifying existing `trees/index.tree`, `trees/aboutme.tree`, or other
  handwritten content.
- Full Obsidian compatibility, including heading fragments, block IDs, and attachment
  embeds.
- GFM tables, task lists, strikethrough, or footnotes.
- Raw HTML or a raw Forester pass-through escape hatch.
- Watching files, invoking Forester from `build` or `check`, or serving output.
- Supporting Forester 4.x, 5.x, or an unspecified moving 6.0 target.
- Discovering named subtrees or macro-generated identities inside handwritten `.tree`
  files.
- Providing an LSP or editor integration in the initial release.

## Key Decisions

| Area | Decision |
| --- | --- |
| Implementation | OCaml library plus a thin CLI |
| Project location | `tools/tree-md` as an independent dune project |
| Markdown parser | Cmarkit 0.4.0 with locations enabled |
| YAML parser | `yaml` 3.2.0 through its located stream API |
| TOML parser | `otoml` 1.0.5 |
| Intermediate form | Compiler-owned, located document and section IR |
| Forester integration | Textual emitter, without linking the Forester library |
| Root identity | `.tree.md` filename stem |
| Heading identity | Anonymous by default; explicit named subtree directive |
| Embed semantics | Standalone `![[id]]` becomes direct `\transclude{id}` |
| Source/output roots | `trees-md` to `generated` |
| Generated ownership | Manifest-managed files only |
| Commands | `tree-md build` and `tree-md check` |
| Initial repository scope | Tool, configuration, and integration only |

## Compatibility Target

The compiler identifies its output profile as:

```text
forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be
```

The profile uses the following verified Forester forms:

```tree
\title{Title}
\date{2026-08-02}
\taxon{Note}
\author{person-id}
\author/literal{Literal Name}
\contributor{person-id}
\contributor/literal{Literal Name}
\tag{tag}
\meta{key}{value}

\p{Paragraph}
\em{Emphasis}
\strong{Strong}
\code{Code}
\blockquote{Content}
\ul{\li{Item}}
\ol{\li{Item}}
\pre{Content}

[[target]]
[Label](target)
\transclude{target}
#{inline math}
##{display math}

\subtree[stable-id]{
  \title{Named section}
}

\subtree{
  \title{Anonymous section}
}
```

The output profile is isolated from the Markdown parser and semantic IR. A future
official Forester 6.0 release requires a new compatibility profile or an explicit
update to this profile, its golden files, and its external compatibility test.

## Architecture

The dune project contains a public `tree_md` library and a `tree-md` executable. The
core library does not read directories, mutate files, or start processes. Filesystem
coordination belongs to the workspace layer, and command-line concerns belong to the
executable.

### Components

`Source` owns original UTF-8 bytes, canonical half-open byte spans, and line indexes.
All parser-specific positions are converted into this representation.

`Frontmatter` identifies and masks the optional YAML block. It builds located YAML
values and validates the closed metadata schema.

`Markdown` adapts Cmarkit and retains locations. It supplies the custom reference
resolver used to identify Wiki-link candidates.

`Dialect` classifies Wiki links, embeds, math, and subtree directives. It rejects all
AST nodes and extensions outside the supported allowlist.

`Document` defines a small, located semantic IR for metadata, blocks, inlines, and
nested sections. No Cmarkit values escape into later compiler stages.

`Forest_index` records known root identities, generated named subtrees, Wiki targets,
and assets. It performs forest-wide validation.

`Forester_6` serializes validated IR through context-specific writers. It contains the
pinned target profile and no parser or filesystem behavior.

`Workspace` loads configuration, discovers source and handwritten files, computes
expected output, compares the manifest, and performs safe synchronization.

`Cli` exposes `build` and `check`, renders diagnostics, and maps outcomes to exit
codes.

### Data Flow

```text
source bytes
  -> UTF-8 validation and line index
  -> front-matter delimiter scan
  -> located YAML metadata
  -> equal-length front-matter mask
  -> located Cmarkit AST
  -> closed dialect validation
  -> located document IR
  -> heading stack and section IR
  -> forest-wide identity/link/asset validation
  -> Forester 6 textual serialization
  -> manifest comparison
  -> optional workspace synchronization
```

The compiler computes and validates all documents before it writes any generated
file.

## Configuration

The repository adds `tree-md.toml` with this schema:

```toml
version = 1
forest = "forest.toml"
sources = ["trees-md"]
output = "generated"
target = "forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be"
```

The CLI accepts `--config PATH` and otherwise reads exactly `./tree-md.toml`; it does
not search parent directories. The `forest`, `sources`, and `output` paths are relative
to the directory containing `tree-md.toml`. Version, target, source roots, and output
root are required. Source roots must be distinct, and the normalized output root must
not overlap any source root. Any unsupported `target` value is a configuration error.

The compiler reads `[forest].trees` and `[forest].assets` from the referenced
`forest.toml`. Those paths are relative to the directory containing `forest.toml`, not
to `tree-md.toml`. For this compiler integration they must be normalized relative
paths; absolute paths, empty segments, `.`, and `..` are configuration errors. The
normalized output root must occur in `[forest].trees`. Existing tree roots are used to
discover handwritten root identities, and asset roots are used to resolve local
images. The initial repository integration adds `generated` to `[forest].trees` but
does not alter existing handwritten `.tree` files.

## Source Discovery and Identity

Each source root is scanned recursively. The scanner does not follow symbolic links
and ignores any path with a component beginning with `.`. A source file must end
exactly in `.tree.md`.

Directory structure is mirrored in the output:

```text
trees-md/a/foo.tree.md -> generated/a/foo.tree
```

The Forester root identity is `foo`, not `a/foo`. Directory names never create an
identity namespace. Duplicate filename stems across any source or handwritten tree
directory are errors.

Root stems, explicit subtree identities, and Wiki targets use this grammar:

```text
[A-Za-z0-9][A-Za-z0-9._-]*
```

Titles and aliases may contain arbitrary valid UTF-8 text and do not determine
identity.

## Input Dialect

Input must be UTF-8 without a byte-order mark. LF and CRLF are accepted and mapped to
the same byte-span model. Output always uses LF.

### YAML Front Matter

Front matter is optional. When present, the first line is exactly `---`, and a later
unindented line exactly equal to `---` closes it. The `...` YAML document terminator
is not a compiler delimiter. An opening delimiter without a closing delimiter is an
error. Because the closing delimiter is a `---` line, a thematic break in a document
with front matter must use `***` (or `___`); a `---` line in the body is consumed as
the front-matter closing delimiter and never becomes a thematic break.

The YAML document must contain one top-level mapping. Mapping keys must be scalar
strings. Duplicate keys, anchors, aliases, custom tags, multiple YAML documents, and
unknown top-level keys are errors.

The schema is:

```yaml
date: "2026-08-02"
taxon: Note
authors:
  - "[[miya]]"
  - "Ada Lovelace"
contributors:
  - "[[reviewer]]"
tags:
  - "compiler"
meta:
  institution: "[Tsukuba](https://informatics.tsukuba.ac.jp/)"
```

`date` is optional and singular. It accepts exactly `YYYY-MM-DD` or
`YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DDTHH:MM:SS[+-]HH:MM`. Lowercase separators,
fractional seconds, and offset-free date-times are rejected because the pinned
Forester parser does not accept the full RFC 3339 grammar. The original validated
value is emitted.

`taxon` is optional, non-empty plain text.

`authors` and `contributors` are optional lists of non-empty strings. A string that
matches exactly `[[id]]` is a tree attribution. Every other string is a literal
attribution. Aliases and embeds are not allowed in attribution values.

`tags` is an optional list of non-empty strings. `meta` is an optional mapping from a
non-empty key to a string value. Tag and metadata values are parsed as inline
Markdown. They may contain supported inline markup, links, Wiki links, inline math,
and code, but not block nodes, embeds, or display math.

Inline diagnostics inside a decoded YAML scalar use the complete scalar event span as
their source location. The compiler does not claim a character-exact subspan after
YAML escape decoding.

YAML key order does not determine generated order. The emitter uses a canonical
metadata order.

### Root Title

An H1 is optional. If the first non-comment Markdown block after front matter is an
H1, its inline content becomes the root `\title` and the heading itself emits no body
node. If the first non-comment block is not H1, the filename stem becomes the title.
Any H1 in another position is an error.

Both ATX and setext headings follow this rule.

### Sections and Subtrees

H2 through H6 become nested subtrees. H2 is a direct child of the root. A heading at
level N greater than 2 requires an open parent at level N minus 1. Skipping a level is
an error. Returning to the same or a shallower level closes intervening sections in
the usual Markdown outline manner.

Only headings that are top-level document blocks participate in this outline.
Headings nested inside list items or blockquotes are errors; they are never promoted
out of their containing block.

Sections are anonymous by default:

```md
## Local section
```

```tree
\subtree{
  \title{Local section}
}
```

A named section uses an unindented, standalone directive line immediately before the
heading:

```md
<!-- subtree: stable-id -->
## Stable section
```

```tree
\subtree[stable-id]{
  \title{Stable section}
}
```

The directive grammar is exactly `<!-- subtree: ID -->`, with the ASCII spaces shown.
Only blank lines may occur between the directive and heading. A directive before H1,
an orphan directive, multiple directives for one heading, an invalid ID, or a global
identity collision is an error. Other HTML comments are discarded.

### Obsidian Links and Embeds

The supported subset is:

```md
[[target]]
[[target|plain alias]]
![[target]]
```

Targets follow the safe identity grammar. Aliases are non-empty single-line plain
text and cannot contain `[`, `]`, or `|`. Alias content is escaped as text rather than
parsed as nested Markdown.

`[[target]]` becomes a Forester title link, and `[[target|alias]]` becomes a native
labelled Forester link. `![[target]]` is valid only when it is the only non-whitespace
content in a paragraph directly inside the current root or section body. It becomes
`\transclude{target}` without an extra wrapper subtree. Embeds in list items,
blockquotes, or ordinary paragraphs are errors.

Unclosed Wiki syntax remains literal text. Closed Wiki-shaped forms with invalid
targets or aliases produce the diagnostics below. Code spans, code blocks, and
backslash-escaped brackets are protected by the CommonMark parser and are never
reinterpreted as Wiki syntax.

The closed-form classification is:

| Source | Result |
| --- | --- |
| `[[id]]` | Wiki title link |
| `[[id|alias]]` | Wiki labelled link |
| `![[id]]` as a direct standalone paragraph | Embed |
| `[[bad id]]` | Invalid-target diagnostic |
| `[[id|]]` | Empty-alias diagnostic |
| `[[id|a|b]]` | Invalid-alias diagnostic |
| `[[id]` or `[[` | Literal text |
| `[alias][[id]]` | Default CommonMark reference behavior; never Wiki |
| Wiki-like text in code or escaped text | Literal text |

### Math

`$...$` becomes inline KaTeX math `#{...}`. `$$...$$` becomes display KaTeX math
`##{...}` only when it occupies a complete paragraph directly inside the current root
or section body. Display math inside a list, blockquote, or ordinary paragraph is an
error. Unclosed dollar syntax remains literal text.

Math payload is emitted in Forester's TeX context rather than escaped as normal text.
The compiler still validates the outer delimiter classification and rejects an empty
or structurally invalid math node.

### Supported Markdown Mapping

| Markdown | Forester output |
| --- | --- |
| Paragraph | `\p{...}` |
| Emphasis | `\em{...}` |
| Strong emphasis | `\strong{...}` |
| Inline code | `\code{...}` |
| Block quote | `\blockquote{...}` |
| Unordered list | `\ul{\li{...}}` |
| Ordered list starting at 1 | `\ol{\li{...}}` |
| Ordered list starting elsewhere | `\<html:ol>[start]{N}{\li{...}}` |
| H2 through H6 | Nested `\subtree` with `\title` |
| `[[id]]` | `[[id]]` |
| `[[id\|alias]]` | `[alias](id)` |
| Standalone `![[id]]` | `\transclude{id}` |
| `$x$` | `#{x}` |
| Standalone `$$x$$` | `##{x}` |
| Ordinary link | Native `[label](destination)` |
| Autolink | Normalized native labelled link |
| Image | `\<html:img>` |
| Thematic break | `\<html:hr>{}` |
| Hard line break | `\<html:br>{}` |
| Soft line break | One ASCII space |
| Indented code block | `\pre{\code{...}}` |
| Fenced code block | `\pre` containing an HTML `code` element |
| Ordinary HTML comment | No output |

Reference-style CommonMark links are resolved before lowering and use the same output
rules as inline links.

Tight-list item paragraphs omit `\p`, matching CommonMark's rendered structure. Loose
list item paragraphs retain `\p`. Nested lists and other supported blocks remain
inside the surrounding `\li`.

Fenced code accepts either no info string or one language token matching
`[A-Za-z0-9][A-Za-z0-9_+.-]*`. A language token is preserved as an HTML class named
`language-TOKEN`. The reserved token `math` is rejected because Cmarkit classifies it
as an unsupported math block extension. Additional fence attributes or tokens are
errors.

An external Markdown image uses its normalized `http` or `https` URL directly. A
local image destination is relative to an asset root, not to the source file or
project root. It must resolve to exactly one configured asset root. The selected asset
root's path, relative to `forest.toml`, is prefixed before emission because Forester
resolves `\route-asset` from the `forest.toml` directory. For example,
`![Plot](images/x.png)` with asset root `assets` emits:

```tree
\<html:img>[src]{\route-asset{assets/images/x.png}}[alt]{Plot}{}
```

Inline alt content is flattened to escaped plain text. An optional image title becomes
an HTML `title` attribute.

Native Forester links cannot represent a CommonMark link title. A title-bearing
external link is emitted as an HTML `a` element with `href` and `title`. A
title-bearing local link is an error because converting it to raw HTML would lose the
Forester link relation and backlinks.

### Rejected Markdown

The compiler rejects raw inline and block HTML other than comments, GFM tables,
strikethrough, task markers, footnotes, fenced math blocks, and every unrecognized
Cmarkit extension node. This allowlist is required because Cmarkit's non-strict mode
enables math together with other extensions.

There is no raw Forester block or inline escape. Unsupported semantics must be added
to the compiler deliberately rather than passed through unchecked.

## Forester Serialization

The emitter writes metadata in this order:

```text
title
date
taxon
authors in source order
contributors in source order
tags in source order
meta entries in source order
body
```

The emitted source is UTF-8 with LF line endings and one final newline. Formatting is
canonical and independent of the input's incidental spacing.

Normal source text is never concatenated directly into Forester code. Separate writer
functions handle text content, identifiers, URI destinations, XML attribute values,
metadata keys, and math payloads. In text content, `%` is emitted as `\%`; each `\`,
`#`, `{`, `}`, `[`, `]`, `(`, and `)` character is emitted as
`\verbFMD|CHARFMD`. Because the payload is exactly one punctuation character, the
fixed `FMD` terminator cannot collide with it. URI and XML-attribute writers first
normalize or percent-encode their semantic value and then apply the corresponding
Forester content escaping, including escaping every literal `%` introduced by URI
encoding.

The writer preserves `<`, `>`, and `&` as Forester text nodes and relies on the pinned
renderer to HTML-escape them. Raw source strings never become XML elements or
attributes. XML nodes are constructed only from compiler-known tag and attribute
names.

Math uses a separate target-profile scanner. It preserves TeX control sequences and
balanced braces, while rejecting a payload whose braces or Forester grouping
delimiters cannot be serialized without changing the TeX expression. Such a failure
is `TM107` rather than raw pass-through.

## Forest-wide Validation

The known local identity index contains:

- Every generated root filename stem.
- Every explicit subtree ID in generated source.
- Every handwritten `.tree` filename stem in configured tree roots other than the
  generated root.

The compiler reports collisions with both definition locations. A handwritten root
location points at its path because no Forester source parser is linked.

Every Wiki link and embed must resolve in this known local identity index. This is a
closed-world rule for the Obsidian subset. Ordinary Markdown links may be external,
fragments, or safe relative destinations and are not required to name a local tree.
Every `[[id]]` value used by `authors` or `contributors` is also a closed-world tree
attribution and must resolve in the same index. Literal attributions require no target.

Named subtrees and macro-generated identities inside handwritten `.tree` files are
outside the initial index. Such a tree must be extracted to a physical root file to be
a valid Wiki target for this compiler. A future adapter may consume an external
Forester manifest without changing the semantic IR.

## URL and Path Safety

Ordinary links allow `http`, `https`, `mailto`, fragments, and validated relative
destinations. External images allow only `http` and `https`. Other explicit schemes,
including `javascript` and `data`, are errors.

Local asset destinations must be relative and use `/` separators. Absolute paths,
backslashes, NUL bytes, empty path segments, `.` segments, and `..` segments are
errors. Normalization must not permit escape from an asset root.

Output paths are derived only from normalized source-relative paths and remain under
the configured output root.

## Manifest and Generated-file Ownership

The manifest path is relative to the configured output root:

```text
<output>/.tree-md-manifest.json
```

The initial compiler and manifest format version are both `0.1.0` and `1`,
respectively. A complete manifest is:

```json
{
  "format": 1,
  "compiler": "0.1.0",
  "target": "forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be",
  "files": [
    {
      "source": "trees-md/a/foo.tree.md",
      "output": "a/foo.tree",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

`source` is a normalized path relative to the `tree-md.toml` directory. `output` is a
normalized path relative to the output root. Entries are sorted by `output` and then
`source`. SHA-256 values are 64 lowercase hexadecimal digits over the exact generated
bytes.

The manifest schema is closed. Malformed JSON, unknown fields, unsupported format
versions, duplicate source or output entries, invalid hashes, and non-normalized paths
are errors. Before trusting an entry for replacement or deletion, the compiler rejects
absolute paths, `.`, `..`, empty segments, backslashes, paths outside the output root,
non-`.tree` outputs, and output symlinks.

The output-root names `.tree-md-manifest.json`, `.tree-md-transaction.json`,
`.tree-md.lock`, and `.tree-md-stage/` are reserved for compiler state. A generated
output path may not use a component beginning with `.tree-md`. Manifest ownership
applies to final `.tree` outputs; these reserved paths are separately compiler-owned.

Only `build` takes an exclusive advisory lock on the persistent `.tree-md.lock` file.
For an ordinary build, source and semantic validation happen before creating the
output root or lock file. After acquiring the lock, `build` rechecks source and state
digests and restarts validation under the lock if an input changed. Recovery of an
existing journal is the documented exception and occurs under the lock before current
source validation.

When `build` creates the output root, it immediately flushes the directory containing
that root before creating the persistent lock or any other compiler state.

`check` never creates or locks a file. If the lock file exists, it opens it read-only
and performs a non-mutating lock test; an active writer is an exit-code 2 concurrency
failure. It records compiler-state digests before and after checking and reports a
concurrent-state failure if they differ. Thus `check` writes no project or output
files, while `build` instances remain mutually exclusive.

Only files named by the previous manifest are managed. Unknown files are never
deleted. If an unknown file occupies an expected output path, compilation fails
rather than overwriting it.

Before replacing or deleting a managed file, `build` verifies that its current hash
matches the old manifest. A manually modified generated file is an error and is not
overwritten. This behavior intentionally has no initial `--force` bypass.

### Interrupted Transaction Journal

The transaction journal path is `<output>/.tree-md-transaction.json`. After all
temporary files are complete and before the first output rename or deletion, `build`
atomically writes a journal containing the SHA-256 of the base manifest and one closed
record per sorted operation:

```json
{
  "format": 1,
  "base_manifest_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "new_manifest_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
  "new_manifest_temporary": ".tree-md-stage/txn-000001/manifest.tmp",
  "operations": [
    {
      "output": "a/foo.tree",
      "old_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "new_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "temporary": ".tree-md-stage/txn-000001/a/foo.tree.tmp"
    }
  ]
}
```

For a first build, `base_manifest_sha256` is `null`. `new_manifest_sha256` is always
the digest of the complete manifest already prepared at the output-root-relative
`new_manifest_temporary` path. For a new output, `old_sha256` is `null`; for a
deletion, `new_sha256` and `temporary` are `null`. Every temporary path is the complete
normalized path relative to the output root. Journal paths obey the same normalization
and containment checks as manifest paths.

`check` never recovers a transaction; it reports an incomplete-transaction generated
state. At the start of `build`, recovery compares the current manifest digest with the
journal. If it matches `new_manifest_sha256`, the commit had completed: recovery
verifies each output's new hash or expected absence, removes any matching temporary
files, and removes the journal.

If the current manifest matches `base_manifest_sha256`, or both are absent for a first
build, recovery deterministically rolls the recorded transaction forward. A create may
be absent or match its new hash. A replacement may match only its old or new hash. A
deletion may match its old hash or be absent. Every operation not already in its new
state requires its recorded temporary file, except deletion. Recovery verifies the
temporary hash, performs the remaining rename or deletion, installs the recorded
temporary manifest after verifying `new_manifest_sha256`, and removes the journal
last. A missing required temporary, any other manifest or output content, or any
invalid path stops recovery without deletion or replacement.

Recovery completes the previous transaction before normal `build` parses current
source. A subsequent source error therefore leaves the workspace in the previous
transaction's completed state rather than a partially updated state.

A malformed journal or base-manifest mismatch is a configuration/state failure that
requires manual inspection and returns exit code 2. Recovery never accepts output
content outside the operation-specific states recorded by the journal.

All staged bytes and their parent directories are flushed before the journal is
installed. A crash before journal installation can leave only an orphan directory
under `.tree-md-stage`. When no writer lock is active, `check` reports an orphan stage
as generated-state error `TM306`; while holding the writer lock, `build` removes only
validated, non-symlink content under that reserved directory before normal
compilation. A crash after manifest installation leaves the journal available to
verify completion. Empty stage directories are removed before the journal is removed
last.

Final output parent directories are not created during staging. After journal
installation, `build` creates only parent directories derived from journaled output
paths. Creation is idempotent, remains beneath the output root, and opens every
ancestor without following symlinks. Recovery performs the same derivation before a
remaining rename.

The crash guarantee includes process termination and machine failure on local
filesystems that honor atomic same-filesystem rename and `fsync`. `build` flushes the
journal file and output-root directory after journal installation, flushes each unique
final parent after renames, deletions, or directory creation, flushes the output root
after manifest replacement, and flushes affected directories after stage and journal
removal. Network and other filesystems that do not provide those semantics are outside
the supported durability model.

## CLI Semantics

### `tree-md build`

`build` loads configuration, discovers all inputs, parses and validates the entire
forest, serializes every expected output in memory, and computes a manifest diff. In
the absence of an existing transaction journal, any diagnostic error prevents all
writes.

Except for roll-forward recovery of a previously recorded incomplete transaction,
validation precedes all writes. When validation succeeds, `build` writes all new
content and the new manifest below the reserved staging directory, flushes the staged
state, writes the transaction journal, renames expected outputs, removes stale managed
files whose hashes still match, atomically replaces the manifest with its recorded
temporary, removes empty staging directories, and removes the journal last. Staged
files do not end in `.tree`, so Forester does not discover them.

A multi-file update cannot be atomic at the filesystem level. If an I/O failure occurs
after some renames, the journal makes the incomplete state explicit. The next `check`
reports it without writing, and the next `build` performs the hash-checked roll-forward
before compiling current source.

### `tree-md check`

`check` performs the same parsing, semantic validation, forest indexing,
serialization, and manifest comparison without writing. It reports missing,
modified, stale, and colliding outputs as errors.

`check` does not invoke Forester. Forester compatibility is verified in a dedicated
test job against the pinned commit.

### Exit Codes

```text
0  Success; `check` also confirms a clean generated state.
1  Source, semantic, forest-consistency, or generated-state diagnostics.
2  CLI usage, configuration, malformed manifest/journal, I/O, or internal failure.
```

## Diagnostics

Each diagnostic contains:

```text
severity
stable code
message
primary location: source span, path, or none
zero or more labelled secondary locations
notes and help text
```

The canonical span is a half-open UTF-8 byte range in the original source. Cmarkit's
inclusive byte locations and YAML's character indexes are converted into that model.
Line and column are calculated only for display and are 1-based Unicode scalar
positions. Tabs use a fixed width of four columns in excerpts.

The CLI prints `path:line:column`, the relevant source excerpt, a caret range, and
secondary locations. It collects independent errors across files and sorts them by
path and byte offset for deterministic output.

The initial stable diagnostic catalog is:

| Code | Meaning |
| --- | --- |
| `TM001` | Invalid UTF-8 |
| `TM002` | YAML syntax or delimiter failure |
| `TM003` | Markdown parser failure |
| `TM101` | Unknown, duplicate, empty, or incorrectly typed metadata |
| `TM102` | Unsupported Markdown or extension node |
| `TM103` | Invalid H1 placement, nested heading, or skipped heading level |
| `TM104` | Invalid, duplicate, or orphan subtree directive |
| `TM105` | Invalid closed-form Wiki syntax |
| `TM106` | Invalid embed placement |
| `TM107` | Invalid math placement or payload |
| `TM201` | Duplicate identity |
| `TM202` | Unresolved Wiki target or tree attribution |
| `TM203` | Missing asset |
| `TM204` | Ambiguous asset |
| `TM205` | Unsafe URL or path |
| `TM301` | Missing generated output |
| `TM302` | Modified generated output |
| `TM303` | Stale generated output |
| `TM304` | Unknown output collision |
| `TM305` | Incomplete transaction detected by `check` |
| `TM306` | Orphan compiler staging directory |
| `TM401` | Invalid or unsupported configuration |
| `TM402` | Invalid manifest |
| `TM403` | Invalid transaction journal or failed recovery precondition |
| `TM404` | Filesystem I/O failure |
| `TM500` | Unexpected internal failure |

Source diagnostics use a source span. Handwritten-root collisions and generated-state
diagnostics use a path location. A process-wide failure may have no location.

Unexpected exceptions are caught only at the CLI boundary and produce exit code 2.
A backtrace is printed only when `TREE_MD_BACKTRACE=1` is set.

## Parser Details

The front-matter scanner retains the original source and creates a Markdown view by
replacing every non-newline byte in the front-matter range with ASCII space. Newline
bytes, including CRLF pairs, remain unchanged. Cmarkit locations therefore remain
absolute offsets into the original file.

`Yaml.Stream` supplies start and end marks for successful events. Its character
indexes are converted to byte indexes with a UTF-8 index table and offset by the YAML
payload start. Because `yaml` 3.2.0 exposes syntax failure location only through its
low-level parser API, the project contains a small pinned adapter around the public
low-level bindings that returns the libyaml byte offset. The compiler never parses an
offset back out of a formatted error message.

Cmarkit is invoked with locations enabled and non-strict extensions enabled for
dollar math. Tagged Cmarkit 0.4.0 source establishes that an unescaped nested `[` is
not part of a link label. With a resolver for the inner label, `[[id]]` is represented
as Text `[` followed by a shortcut Link `id` followed by Text `]`. `![[id]]` begins
with Text `![` and still contains an inner ordinary shortcut Link; it is not an Image
node. Alias text arrives at the resolver as the unsplit inner label `id|alias`.

The custom resolver therefore inspects original bytes around the located inner label,
not only Cmarkit's normalized label key. It recognizes only an exact maximal
`[[BODY]]` or `![[BODY]]` envelope, parses the optional single `|` itself, and records
target, alias, embed flag, and whole-envelope span in private metadata on a synthetic
resolved label. It verifies that the outer `[` and embed `!` are unescaped according
to CommonMark's odd/even backslash rule. It rejects larger bracket runs and rejects an
envelope immediately preceded by `]`, so `[alias][[id]]` is never a Wiki link. Every
other noncandidate delegates to Cmarkit's default resolver, except that an escaped
Wiki-shaped envelope is explicitly left unresolved even when an inner CommonMark
reference definition exists. Consequently escaped Wiki syntax remains literal, while
`[alias][[id]]` follows ordinary CommonMark reference resolution and is literal only
when no applicable reference definition exists.

Cmarkit may call the resolver twice while abandoning an outer nested-bracket parse and
retrying the inner opener. The resolver is pure and idempotent and never emits a
diagnostic. During lowering, only a tagged shortcut Link with matching inner and
wrapper spans is accepted. The lowering pass consumes or splits the adjacent Text
nodes that contain the wrapper and produces one Wiki semantic node. Invalid closed
forms are diagnosed only from that surviving semantic candidate.

The independent semantic IR is built only after the complete Cmarkit AST passes the
closed dialect validator. A heading stack then constructs nested sections while
preserving source spans.

## Dependencies and Licensing

The intended direct dependency set is permissively licensed:

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| `cmarkit` | 0.4.0 | ISC | CommonMark, locations, resolver, math |
| `yaml` | 3.2.0 | ISC | Located YAML event stream |
| `otoml` | 1.0.5 | MIT | Compiler and Forester TOML configuration |
| `cmdliner` | 2.1.0 | ISC | CLI |
| `yojson` | 3.0.0 | BSD-3-Clause | Manifest JSON |
| `digestif` | 1.3.0 | MIT | SHA-256 manifest hashes |
| `alcotest` | 1.9.1 | ISC | Unit and integration tests |

The implementation plan includes producing a lockfile and auditing the complete
transitive dependency graph before release. Build tools that generate source do not
become linked runtime components, but their licenses are still recorded in the audit.

The compiler does not link the Forester library. In addition to its unstable internal
API and lack of a supported source pretty-printer, the available Forester package is
GPL-licensed and would constrain the compiler library's licensing. Forester is used
only as an external executable in the pinned compatibility test.

## Implementation Decomposition

The implementation remains one cohesive compiler plan but is divided into four
reviewable phases with verification checkpoints:

1. Located front end, closed dialect, semantic IR, section builder, Forester writer,
   and golden conversion tests.
2. TOML configuration, source discovery, forest identity index, reference and asset
   validation, and repository-independent workspace fixtures.
3. Manifest, transaction journal, recovery, `build`, `check`, diagnostics, and CLI
   integration tests.
4. Repository configuration integration, pinned external Forester compatibility job,
   lockfile, and complete license audit.

Each phase must pass its own tests before the plan proceeds. Existing forest content
migration, watch mode, and editor tooling are not hidden follow-up tasks in these
phases.

## Testing Strategy

The baseline environment is OCaml 5.3.0 and Dune 3.22. Tests use Alcotest, Dune cram
tests, and checked-in golden fixtures.

### Cmarkit Characterization Gate

Before production parser adaptation is implemented, characterization tests lock the
source-derived Cmarkit 0.4.0 contract. They record the AST kind, reference layout, raw
slice, and source span for:

```md
[[id]]
[[id|alias]]
![[id]]
[alias][[id]]
\[[id]]
`[[id]]`
```

The expected contract is Text + tagged shortcut Link + Text for the two `[[...]]`
forms, Text `![` + tagged shortcut Link + Text for the embed, ordinary literal content
for `[alias][[id]]` in the fixture with no reference definitions, literal escaped
syntax, and an inline Code node for the code-span case. A second fixture with a
matching reference definition confirms that `[alias][[id]]` follows default CommonMark
resolution but is never tagged as Wiki, while the escaped Wiki-shaped envelope remains
literal. A failure blocks implementation and returns the design to review; the
implementation does not silently switch parsers or add a source-rewriting fallback.

### Unit Tests

- UTF-8, CRLF, tabs, line indexes, half-open spans, and front-matter masking.
- YAML delimiters, schema, duplicate and unknown keys, attribution forms, dates, and
  inline metadata Markdown.
- Every supported CommonMark node and every explicitly rejected extension class.
- H1 fallback, nested headings, skipped levels, and named and anonymous sections.
- Wiki links, standalone embeds, math, protected code contexts, escapes, and malformed
  delimiter fallback.
- Wiki odd/even backslash escaping and `[alias][[id]]` with and without matching
  CommonMark reference definitions.
- Context-specific Forester escaping with all syntax punctuation, Unicode, and hostile
  command-like text.
- Global identity, Wiki target, and asset validation with multi-location diagnostics.
- URL scheme and asset traversal rejection.
- Canonical serialization and byte-identical repeated output.

### Workspace and CLI Tests

- Initial generation and manifest creation.
- A no-op second build.
- Missing, modified, stale, and unknown-collision outputs.
- Safe update and stale deletion when old hashes match.
- Protection of manually modified generated files.
- Read-only recovery detection in `check` and hash-checked roll-forward in `build` after a
  simulated interrupted commit phase.
- Refusal to recover malformed journals, base-manifest mismatches, unsafe paths, or
  output with a hash outside the recorded old/new pair.
- Exclusive lock contention and orphan-stage detection and cleanup.
- Final parent creation without symlink traversal and durability-barrier ordering.
- `build` and `check` stdout, stderr, and exit codes.
- Confirmation that failed source validation leaves existing outputs unchanged when
  no earlier transaction journal requires roll-forward.

### Forester Compatibility Test

A separate test job runs generated fixtures through the external executable pinned to
`forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be` using:

```sh
forester build --no-theme forest.toml
```

The test fails on a nonzero exit or on a Forester warning attributable to generated
source. It verifies metadata, nested subtrees, links, transclusion, math, lists, code,
images, and escaping.

## Acceptance Criteria

- Every documented supported input has a matching golden `.tree` output.
- All generated identities are globally unique against known roots and generated
  named subtrees.
- `tree-md build` creates only manifest-owned output and is byte-deterministic.
- `tree-md check` returns 0 for a clean workspace and writes no files.
- A source, semantic, reference, asset, or generated-state error returns 1 with a
  precise diagnostic and leaves existing output unchanged when no prior transaction
  requires roll-forward.
- CLI usage, unsupported target configuration, malformed manifest or journal, I/O, and
  internal failures return 2.
- Manually modified generated output is never silently overwritten or deleted.
- The pinned external Forester compatibility test passes without generated-source
  warnings.
- Existing handwritten content remains unchanged by the initial implementation.

## Risks and Mitigations

The Forester 6.0 target is not a reproducible official release. Pinning the exact
commit, isolating the output profile, and running the external compatibility test
contain this risk.

Cmarkit's Wiki adaptation depends on the pinned nested-bracket and resolver behavior.
Source-derived characterization fixtures lock that contract and block dependency
upgrades that change it.

Cmarkit's non-strict mode enables unsupported extensions together with math. A closed,
exhaustive AST validator prevents accidental acceptance.

Generated Forester text is vulnerable to command injection if writers are bypassed.
The emitter exposes only context-specific constructors and tests hostile text at every
boundary.

The compiler cannot soundly discover handwritten named subtrees without parsing
Forester. The initial known-target contract is explicit, and future manifest-based
discovery is isolated behind `Forest_index`.

Multi-file replacement is not atomic. Manifest-last updates, old-content hashes, and
the pre-commit transaction journal make interrupted states detectable and permit a
hash-checked roll-forward without deleting unknown work.

## Authoritative References

- Forester documentation index: <https://www.forester-notes.org/index/index.xml>
- Forester release notes: <https://www.forester-notes.org/005P/index.xml>
- Forester 6.0 page: <https://www.forester-notes.org/VNQB/index.xml>
- Forester tutorial: <https://www.forester-notes.org/0052/index.xml>
- Pinned Forester source tree: <https://git.sr.ht/~jonsterling/ocaml-forester/tree/30b73641cef02433ee158db6ddc77f7b49de60be>
- Pinned Forester parser grammar: <https://git.sr.ht/~jonsterling/ocaml-forester/tree/30b73641cef02433ee158db6ddc77f7b49de60be/item/lib/parser/Grammar.mly>
- Pinned Forester primitive expansion: <https://git.sr.ht/~jonsterling/ocaml-forester/tree/30b73641cef02433ee158db6ddc77f7b49de60be/item/lib/compiler/Expand.ml>
- Pinned Forester CLI: <https://git.sr.ht/~jonsterling/ocaml-forester/tree/30b73641cef02433ee158db6ddc77f7b49de60be/item/bin/forester/main.ml>
- Cmarkit documentation: <https://erratique.ch/software/cmarkit/doc/Cmarkit/index.html>
- Cmarkit 0.4.0 package: <https://opam.ocaml.org/packages/cmarkit/cmarkit.0.4.0/>
- Pinned Cmarkit nested-label parser: <https://github.com/dbuenzli/cmarkit/blob/464d913388933c5991d6e495d57411d81f4a680a/src/cmarkit_base.ml#L971-L1017>
- Pinned Cmarkit resolver API: <https://github.com/dbuenzli/cmarkit/blob/464d913388933c5991d6e495d57411d81f4a680a/src/cmarkit.mli#L455-L520>
- OCaml YAML stream API: <https://avsm.github.io/ocaml-yaml/yaml/Yaml/Stream/index.html>
- Otoml 1.0.5 package: <https://opam.ocaml.org/packages/otoml/otoml.1.0.5/>
