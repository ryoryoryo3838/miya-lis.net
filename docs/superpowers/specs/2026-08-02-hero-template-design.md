# Hero Template Design for Forester

Date: 2026-08-02
Status: Approved

## Overview

Reproduce the miya-lis.net hero screen within the Forester static site generator. The hero is a full-viewport typographic landing displaying "MIYA-LIS" / ".NET" in enormous responsive type, with the period serving as a navigation trigger that detaches on scroll.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  forest repo (hero-theme branch)                     │
│                                                     │
│  trees/              .tree source files              │
│  trees/navigation.tree  Nav link definitions         │
│  lib_theme/          OCaml → JS (js_of_ocaml)        │
│  theme/              XSLT + CSS (forester-base-theme fork) │
│  assets/             Static assets (hero.js output)   │
│  forest.toml         Config                           │
│                                                     │
│  dune build          → lib_theme/ → hero.js          │
│  forester build      → output/ (XML + assets)         │
│                                                     │
│  GitHub Actions      → dune build + forester build    │
│                      → output/ → Cloudflare Deploy    │
└─────────────────────────────────────────────────────┘
```

- No modification to forester core. Everything lives in the user's forest repo.
- `lib_theme/`: OCaml project compiled to JS via `js_of_ocaml`.
- Generated `hero.js` placed in `assets/`, copied to `output/` by forester.

## Component Design

### 1. XSLT Template (`theme/tree.xsl`)

Add a branch at the root template level:

```xml
<xsl:template match="/f:tree">
  <xsl:choose>
    <!-- Top page: render hero + content -->
    <xsl:when test="f:frontmatter/f:addr = 'index'">
      <html>
        <head><!-- existing head content --></head>
        <body class="hero-page">
          <section id="hero" class="hero">
            <div class="hero-title">
              <span class="hero-line">MIYA-LIS</span>
              <span class="hero-line hero-line--net">
                <a class="hero-period" id="hero-period" href="#">.</a>
                <span class="hero-period-placeholder">.</span>NET
              </span>
            </div>
          </section>
          <header id="persistent-header" class="persistent-header">...</header>
          <main>
            <!-- existing tree content rendering -->
            <xsl:apply-templates select="f:mainmatter" />
          </main>
          <!-- nav panel (static HTML, JS controls visibility) -->
          <nav id="nav-panel" class="nav-panel">
            <!-- populated from navigation.tree -->
          </nav>
        </body>
      </html>
    </xsl:when>
    <!-- Other pages: existing layout -->
    <xsl:otherwise>
      <!-- existing template unchanged -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>
```

**Files to modify:**
- `theme/tree.xsl`: Add branch logic + hero/nav sections
- Other XSL files (`core.xsl`, `links.xsl`, `metadata.xsl`): No changes

### 2. Navigation (`trees/navigation.tree`)

A standard `.tree` file defining navigation links:

```forester
\title{Navigation}
\taxon{navigation}

\p{\link{aboutme}{About}}
\p{\link{grad-research}{卒業研究}}
\p{\link{dev/0001}{開発ノート}}
```

The XSLT reads this tree at build time and generates the `<nav id="nav-panel">` HTML. Edits to navigation only require `forester build` — no JS rebuild needed.

### 3. CSS (`theme/style.css` additions)

```css
/* Hero section */
.hero {
  height: 100vh;
  width: 100vw;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}

.hero-title {
  margin: 0;
  width: 100%;
  font-family: "Inria Sans", sans-serif;
  font-size: clamp(6rem, 19.5vw, 28rem);
  font-weight: 900;
  line-height: 0.85;
  text-align: left;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.02em;
}

.hero-line {
  display: inline-block;
  white-space: nowrap;
}

.hero-line--net {
  position: relative;
}

/* Period: navigation trigger */
.hero-period {
  color: inherit;
  text-decoration: none;
  cursor: pointer;
  user-select: none;
}

.hero-period.is-fixed {
  position: fixed;
  top: -0.5em;
  left: var(--size-fluid-2, 1rem);
  z-index: 11;
  pointer-events: auto;
}

.hero-period-placeholder {
  display: none;
  visibility: hidden;
}

.hero-period.is-fixed + .hero-period-placeholder {
  display: inline;
  visibility: hidden;
}

/* Persistent header */
.persistent-header {
  position: fixed;
  top: 0;
  width: 100%;
  background: var(--gray-0);
  z-index: 10;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.persistent-header.is-visible {
  opacity: 1;
  pointer-events: auto;
}

/* Nav panel */
.nav-panel {
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 30;
  background: var(--gray-12);
  color: var(--gray-0);
  border-radius: 0.5rem;
  padding: 1.5rem;
  transform: scale(0);
  transform-origin: top left;
  transition: transform 0.25s ease, opacity 0.2s ease;
  opacity: 0;
}

.nav-panel.is-open {
  transform: scale(1);
  opacity: 1;
}

/* Overlay */
.nav-overlay {
  position: fixed;
  inset: 0;
  z-index: 25;
  background: var(--gray-12);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.nav-overlay.is-visible {
  opacity: 0.1;
  pointer-events: auto;
}
```

**Integration**: Append to existing `theme/style.css`. No CSS framework dependency — use existing forester CSS variables and Inria Sans font.

### 4. JavaScript (`lib_theme/` — OCaml via js_of_ocaml)

**Functionality:**
1. **Period pinning**: On scroll, when period reaches viewport top, add `.is-fixed` class (fixed positioning). Remove on scroll back. Use `requestAnimationFrame` for throttling.
2. **Nav panel**: Click hero period → toggle `.is-open` on nav panel + `.is-visible` on overlay. Click overlay / press Escape → close.
3. **Intersection Observer**: When hero section leaves viewport → show persistent header (`.is-visible`).

**Structure:**

```
lib_theme/
├── dune
├── hero.ml          # Main entry point
├── period_pin.ml    # Scroll-based period fixed positioning
├── nav_panel.ml     # Nav panel open/close logic
└── header_obs.ml    # Intersection Observer for persistent header
```

**dune file:**
```
(executable
 (name hero)
 (modes js)
 (libraries js_of_ocaml))
```

**Build output**: `_build/default/lib_theme/hero.bc.js` → copy to `assets/hero.js`.

**HTML integration**: XSLT generates `<script src="hero.js"></script>` in the top-page head.

### 5. CI/CD

```yaml
# .github/workflows/deploy.yml
steps:
  - uses: actions/checkout@v4
    with:
      submodules: true
  - run: opam install forester js_of_ocaml
  - run: dune build lib_theme/
  - run: cp _build/default/lib_theme/hero.bc.js assets/hero.js
  - run: forester build forest.toml
  - uses: cloudflare/wrangler-action@v3
    with:
      command: pages deploy output/
```

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `theme/tree.xsl` | Modify | Add top-page branch with hero/nav |
| `theme/style.css` | Append | Hero, nav panel, header CSS |
| `trees/navigation.tree` | Create | Nav link definitions |
| `lib_theme/*.ml` | Create | OCaml → JS (hero dynamics) |
| `lib_theme/dune` | Create | Dune build config |
| `assets/hero.js` | Generated | Compiled JS output |
| `.github/workflows/deploy.yml` | Create/Modify | CI/CD pipeline |
| `trees/index.tree` | No change | Already exists with transclude |
| `theme/core.xsl` | No change | — |
| `theme/links.xsl` | No change | — |
| `theme/metadata.xsl` | No change | — |

## Constraints

- Forester's existing features (transclusion, KaTeX, ninja-keys, backlinks) must continue working
- Non-top pages must render identically to before
- `navigation.tree` must be a valid forester tree (visible in search, linkable)
- JS should degrade gracefully — without JS, the hero is static text (no nav panel)
- Build must work in GitHub Actions with `ubuntu-latest`

## Open Questions

1. **XPath for top-page detection**: The condition `f:frontmatter/f:addr = 'index'` needs verification against actual forester XML output. The addr value may differ (e.g., `index.xml` or `/`).
2. **CSS variables**: Forester doesn't use Open Props. Replace `--gray-0`, `--gray-12`, `--size-fluid-2` with literal values or define custom properties.
3. **hero.js loading**: Must verify whether forester's existing `forester.js` bundle approach (esbuild) can be extended to include hero.js, or if a separate `<script>` tag is needed.
