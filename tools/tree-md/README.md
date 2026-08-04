# tree-md

Compile a strict Markdown dialect (`.tree.md`) into deterministic
[Forester](https://www.forester-notes.org/) `.tree` source. Markdown headings
become nested Forester subtrees, Obsidian-style embeds become direct
transclusions, and every generated file is manifest-owned and byte-deterministic.

This compiler targets the source language and CLI behavior of the official
`forester-6.0-dev` branch at commit
`30b73641cef02433ee158db6ddc77f7b49de60be` (profile below). It is independent
from the Forester library: no Forester code is linked, and the pinned external
compatibility test is a separate CI job.

## Usage

```text
tree-md check [--config PATH]
tree-md build [--config PATH]
```

- `--config PATH` — path to the configuration file. Default: `./tree-md.toml`.
  The default is read exactly from the current working directory; parent
  directories are **not** searched.
- `check` validates the whole forest and reports generated-state problems
  **without writing any file**. It exits 0 only when the generated state is
  clean.
- `build` validates first, then synchronizes generated outputs transactionally.

| Source | Output |
| --- | --- |
| `trees-md` (configured `sources`) | `generated` (configured `output`) |

Target profile:

```text
forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be
```

Exit codes:

```text
0  success; check also confirms a clean generated state
1  source, semantic, forest-consistency, or generated-state diagnostics
2  CLI usage, configuration, malformed manifest/journal, I/O, or internal failure
```

Example:

```console
$ tree-md check --config tree-md.toml      # clean workspace, silent, exit 0
$ tree-md build --config tree-md.toml      # "build: 1 created, 0 replaced, 0 deleted, 0 unchanged"
$ tree-md check                            # uses ./tree-md.toml, no parent search
```

## Configuration

```toml
version = 1
forest = "forest.toml"
sources = ["trees-md"]
output = "generated"
target = "forester-6.0-dev@30b73641cef02433ee158db6ddc77f7b49de60be"
```

`forest`, `sources`, and `output` are relative to the directory containing
`tree-md.toml`. Version, target, source roots, and output root are required;
source roots must be distinct; the output root must not overlap a source root;
any unsupported `target` value is a configuration error. The referenced
`forest.toml` supplies `[forest].trees` and `[forest].assets` (relative to the
directory containing `forest.toml`); the normalized output root must occur in
`[forest].trees`.

## Input language

Source files end exactly in `.tree.md`, must be UTF-8 without a BOM, and are
discovered recursively (no symlink following; paths with a dot-leading
component are ignored). Directory structure is mirrored: `trees-md/a/foo.tree.md`
becomes `generated/a/foo.tree`. The Forester root identity is the filename stem
(`foo`, never `a/foo`); duplicate stems are errors.

### Example

One file covering YAML front matter, an H1 root title, an H2 section, a named
subtree directive, a Wiki link, a direct embed, and inline and display math:

```markdown
---
date: 2026-08-04
taxon: Note
authors:
  - "[[miya]]"
tags:
  - compiler
---

# Root title

A paragraph with a Wiki link to [[manual]] and inline math $x^2$.

## Local section

Anonymous section body with display math:

$$y = mx + b$$

<!-- subtree: stable-id -->
## Stable section

Direct transclusion of another tree:

![[notes]]
```

produces

```tree
\title{Root title}
\date{2026-08-04}
\taxon{Note}
\author{miya}
\tag{compiler}

\p{A paragraph with a Wiki link to [[manual]] and inline math #{x^2}.}

\subtree{
  \title{Local section}
  \p{Anonymous section body with display math:}
  ##{y = mx + b}
}

\subtree[stable-id]{
  \title{Stable section}
  \p{Direct transclusion of another tree:}
  \transclude{notes}
}
```

### Supported syntax

| Markdown | Forester output |
| --- | --- |
| Paragraph | `\p{...}` |
| `**strong**` / `*emphasis*` / `` `code` `` | `\strong{...}` / `\em{...}` / `\code{...}` |
| Block quote | `\blockquote{...}` |
| Unordered / ordered lists | `\ul{\li{...}}` / `\ol{\li{...}}` (and `<html:ol>[start]` for non-1 starts) |
| `#` H1 (first block only) | root `\title` |
| `##`–`######` H2–H6 | nested `\subtree` with `\title` |
| `<!-- subtree: ID -->` before a heading | named `\subtree[ID]{...}` |
| `[[id]]` / `[[id\|alias]]` | `[[id]]` / `[alias](id)` |
| Standalone `![[id]]` | `\transclude{id}` |
| `$...$` / standalone `$$...$$` | `#{...}` / `##{...}` |
| Links, autolinks, images, thematic break, hard break | native `[label](dest)`, `<html:img>`, `<html:hr>{}`, `<html:br>{}` |
| Indented / fenced code | `\pre{\code{...}}` / `\pre` with an HTML `code` element |
| HTML comments | discarded |

The directive grammar is exactly `<!-- subtree: ID -->` (ASCII spaces). IDs and
Wiki targets follow `[A-Za-z0-9][A-Za-z0-9._-]*`. `[[target]]` resolves only
against the known local identity index (generated roots, generated named
subtrees, and handwritten tree roots); this is a closed-world rule.

#### Thematic breaks and YAML front matter

A `---` thematic break is consumed as the YAML front-matter closing delimiter
when a document has front matter, so a `---` line inside the body is not a
thematic break. Use `***` (or `___`) for thematic breaks in documents with
YAML front matter.

### Rejected syntax

Raw inline or block HTML (other than comments), GFM tables, task lists,
strikethrough, footnotes, fenced math blocks, and every unrecognized Cmarkit
extension node are rejected with a diagnostic. There is no raw Forester
pass-through escape hatch. Display math or embeds inside lists, blockquotes, or
ordinary paragraphs are errors; headings nested inside list items or
blockquotes are errors; skipped heading levels are errors; H1 in any position
other than the first block is an error; invalid, duplicate, or orphan subtree
directives are errors.

## Generated-file ownership and safety

- **Ownership warning:** only files named by the previous manifest (under
  `<output>/.tree-md-manifest.json`) are managed. `build` creates, replaces,
  and deletes **only** manifest-owned files. Unknown files are never deleted;
  an unknown file occupying an expected output path fails compilation instead
  of being overwritten.
- **Read-only `check`:** `check` never creates or locks a file. If the lock
  file exists it is opened read-only for a non-mutating lock test; an active
  writer is an exit-2 concurrency failure. Compiler-state digests are recorded
  before and after checking to detect concurrent state changes.
- **Manual-modification protection:** before replacing or deleting a managed
  file, `build` verifies its current SHA-256 matches the old manifest. A
  manually modified generated file is an error and is **never** silently
  overwritten or deleted. There is intentionally no `--force` bypass.
- **Transaction recovery:** all staged bytes are written and flushed before a
  pre-commit journal (`<output>/.tree-md-transaction.json`) is installed. After
  an interrupted commit, `check` reports the incomplete state without writing
  (TM305) and the next `build` performs a hash-checked roll-forward under the
  writer lock before compiling current source. A malformed journal or
  base-manifest mismatch is an exit-2 state failure requiring manual
  inspection.
- **Durability requirement:** the crash guarantee holds only on local
  filesystems that honor atomic same-filesystem rename and `fsync`. `build`
  flushes the journal, output-root directory, final parent directories, and the
  manifest as specified in the design; network and other filesystems without
  those semantics are outside the supported durability model.

## Development

```bash
dune runtest          # 431 Alcotest cases + cram scenarios
opam lock tree-md.opam   # regenerate tree-md.opam.locked
```

See [`VERIFICATION.md`](./VERIFICATION.md) for the mapping of design
requirements to tests and [`DEPENDENCIES.md`](./DEPENDENCIES.md) for the
resolved dependency and license audit.
