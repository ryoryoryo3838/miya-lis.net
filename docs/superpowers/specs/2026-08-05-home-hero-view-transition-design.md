# Home Hero View Transition Design

## Goal

Make the site root entry open the Home hero while keeping the internal `/index/` page focused on Home content. Let the `︽ Top` link move from Home content to the hero without a reload, using the View Transition API, scroll positioning, and focus management.

## Requirements

- `/index.html` (the normal Home entry) opens `/index/index.xml#hero`.
- `/index/` and `/index/index.xml` open Home content without a fragment.
- `?hero=1` is removed from the route, runtime, deployment step, and route test.
- Home content starts in the content state unless the initial URL contains `#hero`.
- Clicking `︽ Top` changes to the hero state in the same document.
- The browser Back action returns to the prior Home content state and restores its scroll position and focus when available.
- View Transition API, smooth scrolling, and focus behavior degrade safely when unsupported or reduced motion is requested.
- Non-root pages keep their existing `« Home` behavior.

## Architecture

The existing `lib_theme/hero.ml` remains the single runtime controller. It will own a two-state Home presentation model:

- `content`: hide `#hero`, remove `hero-page` from `body`, and show Home content.
- `hero`: show `#hero`, add `hero-page` to `body`, and position the viewport at the top.

The initial state is selected from the temporary `#hero` fragment. The runtime replaces the initial history entry after reading the fragment, removing the fragment from the visible URL. This preserves a clean URL after the root entry while still distinguishing the root entry from internal `/index/` navigation.

In-page transitions add a same-URL history entry with `history.pushState`. `popstate` applies the target state without loading a new document. The route remains the same, so switching between Home content and hero never crosses a reload boundary.

## Components

### Runtime (`lib_theme/hero.ml`)

- Detect the initial `#hero` fragment.
- Register the root `︽ Top` trigger.
- Track current presentation state, saved content scroll position, and the previously focused element.
- Apply state changes through `document.startViewTransition` when available.
- Scroll the viewport to `top: 0` and focus `#hero` with `preventScroll: true` in hero state.
- Restore the saved scroll position and focus when returning to content.
- Handle `popstate` using the same transition path.
- Fall back to direct DOM updates, scroll, and focus when the API is unavailable.

### Markup (`theme/tree.xsl`)

- Give the root `︽ Top` link a stable runtime identifier.
- Keep the existing non-root `« Home` link unchanged.
- Add `tabindex="-1"` to `#hero` so it can receive programmatic focus without entering the normal tab order.

### Animation (`theme/style.css`)

Use document-level `::view-transition-old(root)` and `::view-transition-new(root)` animations. The content-to-hero and hero-to-content transitions use a restrained fade combined with a small vertical movement over approximately 250–350ms. A `prefers-reduced-motion: reduce` media query disables the animated movement.

### Entry route and verification (`.github/workflows/deploy.yml`, `test/hero-route.sh`)

The deployment rewrite for `output/index.html` will target `/index/index.xml#hero`. The generated `/index/index.html` redirect remains unmarked. The route test will assert the fragment-based root entry, the fragment-free internal entry, the root XML marker, and the absence of `?hero=1`.

Generated `theme/hero.js` and `assets/hero.js` remain build artifacts produced from `lib_theme/hero.ml`; they are not hand-edited.

## Interaction Flow

1. A visitor enters through `/index.html`.
2. The redirect lands on `/index/index.xml#hero`.
3. Runtime initialization reads the fragment, replaces the history URL without the fragment, and enters hero state.
4. A visitor enters through `/index/` or an internal `[index]` link.
5. Runtime initialization finds no fragment and enters content state.
6. The visitor clicks `︽ Top` from content.
7. Runtime saves scroll and focus, pushes a same-URL hero history state, and starts the View Transition.
8. The DOM state changes, the viewport moves to the top, and `#hero` receives focus.
9. Browser Back pops the hero state, runs the reverse transition, and restores the saved content position and focus.

## Error Handling and Accessibility

- Missing View Transition support uses direct state changes and retains the required navigation behavior.
- Reduced-motion users receive no animated movement while retaining state, scroll, and focus behavior.
- Focus restoration checks that the saved element is still connected before using it; otherwise focus remains on the document without throwing.
- `#hero` is programmatically focusable but excluded from the normal tab sequence with `tabindex="-1"`.
- The root-only trigger is optional at runtime, so non-root pages do not fail if the element is absent.

## Verification

- Run `sh test/hero-route.sh` after generation.
- Run `dune test` for the existing OCaml test suite.
- Confirm generated JS artifacts contain no `?hero=1` marker.
- Confirm `/index/` starts in content state and `/index.html` starts in hero state in a browser.
- Confirm `︽ Top` changes state without a document reload, moves the viewport to the top, and focuses `#hero`.
- Confirm browser Back restores content scroll position and focus.
- Confirm View Transition API fallback and reduced-motion behavior remain usable.
