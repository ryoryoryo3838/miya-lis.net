# Home Top Link Design

## Goal

Show `︽ Top` in the same header position as `« Home` on the root Home page (`index.xml`). Keep `« Home` unchanged on every non-root page.

## Context

The shared page template is `theme/tree.xsl`. It currently emits the `header.header` navigation only when the rendered tree is not the root tree, so the Home page has no equivalent link in that position.

## Design

Change the shared header template so it is emitted for both root and non-root pages. Within the existing logo link:

- Root pages use `href="#"`, `title="Top"`, and the text `︽ Top`.
- Non-root pages keep the existing base URL link, `title="Home"`, and `« Home` text.

The existing `header`, `nav`, `logo`, and link classes remain unchanged. No source tree files or generated output files are edited, and no CSS changes are needed.

## Rendering Flow

The XSLT tests `/f:tree[@root='true']` to select the root-page branch. The browser resolves `#` to the document top, so the Home link acts as a top-of-page link without introducing a new anchor or script.

## Error Handling

There is no new runtime failure path. If the root attribute is absent, the existing non-root Home link behavior is used. The literal `︽` is emitted as text and relies on the existing page font fallback behavior.

## Verification

After implementation, inspect the generated Home XML and a non-root XML page to confirm:

- Home contains `︽ Top` in the shared header with `href="#"`.
- Non-root pages still contain `« Home` with the existing index link.
- No generated output file was manually changed.
