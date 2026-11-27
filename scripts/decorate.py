"""Dress the forest Forester rendered in the site's own shell.

    python3 decorate.py

Forester 6 renders every tree straight to HTML with its own stylesheet and
scripts. This adds what the site has on top, without touching what Forester
wrote between the tags:

- the theme's static files (icons, the web manifest, the card, fonts,
  tokens.css and miya.css), copied over Forester's own favicons;
- in every page's head, the share metadata a crawler reads (it reads the head
  only), the site name in the title, and the theme's stylesheets;
- "« MIYA-LIS.NET" in place of Forester's "« Home", shown on every page;
- the site navigation and, on narrow screens, the table of contents and each
  part of the backmatter, each in a side panel opened from a bracketed
  vertical tab at the top of the right edge, as the first children of
  #main-wrapper, so a Forester htmx swap of #main-wrapper brings this page's
  along;
- dates on the meta line in Japanese (2026年8月2日);
- the site root as a copy of the Home tree;
- a 404 page for wrangler's not_found_handling.

The navigation lists the links in the navigation tree's body, as the old XSLT
theme did, so the menu is still edited in the vault.
"""

import html
import os
import re
import shutil
import sys
from datetime import datetime
from html.parser import HTMLParser

# The forest root: scripts/ sits beside forest.toml, trees/ and output/.
site_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
output = os.path.join(site_dir, "output")
theme = os.path.join(site_dir, "theme")
layout = os.path.join(theme, "layout")

with open(os.path.join(site_dir, "forest.toml"), encoding="utf-8") as handle:
    site_url = re.search(r'^url\s*=\s*"([^"]+)"', handle.read(), re.M).group(1)

SITE_NAME = "MIYA-LIS.NET"
HOME = "index"
NAVIGATION = "navigation"
DESCRIPTION = "miyaのwebsite"
CARD = site_url.rstrip("/") + "/og.png"
CARD_W, CARD_H = "1200", "630"

# After Forester's style.css, so the theme's rules win where they overlap.
# IBM Plex Sans JP is the design system's Japanese face; its Latin face,
# Monaspace Neon, ships with the theme.
THEME_HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@300;400;700&amp;display=swap">'
    '<link rel="stylesheet" href="/tokens.css">'
    '<link rel="stylesheet" href="/miya.css">'
    '<script defer src="/side.js"></script>'
)

MAIN_WRAPPER = re.compile(r'<div\s+id="main-wrapper"')


# surrogateescape: Forester 6.0 cuts its og:description at a byte count, which
# can split a Japanese character. That tag is replaced below; the rest of the
# page is written back byte for byte.
def read(path):
    with open(path, encoding="utf-8", errors="surrogateescape") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as handle:
        handle.write(text)


# What Forester writes into the head and share_head() writes again, with the
# site's own card, description and canonical address.
FORESTER_SHARE = re.compile(
    r'<meta\s+property="og:[^"]*"\s+content="[^"]*">'
    r'|<meta\s+name="description"\s+content="[^"]*">'
    r'|<link\s+rel="(?:icon|apple-touch-icon|canonical)"[^>]*>'
)


def copy_theme():
    """Everything the pages link to; not the fragments or the scripts that
    generate the icons and the card."""
    for parent, dirs, files in os.walk(theme):
        if parent == theme:
            dirs[:] = [d for d in dirs if d != "layout"]
        for name in files:
            source = os.path.join(parent, name)
            relative = os.path.relpath(source, theme)
            if parent == theme and name.endswith((".sh", ".html")):
                continue
            destination = os.path.join(output, relative)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copyfile(source, destination)


class MenuParser(HTMLParser):
    """The links in a tree's first mainmatter, minus Forester's [slug] links."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.mainmatter = None
        self.done = False
        self.link = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in VOID:
            return
        self.depth += 1
        if self.done:
            return
        if self.mainmatter is None:
            if tag == "div" and attrs.get("class") == "mainmatter":
                self.mainmatter = self.depth
            return
        if tag == "a" and attrs.get("href") and "slug" not in (attrs.get("class") or ""):
            self.link = [attrs["href"], ""]

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag == "a" and self.link is not None:
            self.links.append((self.link[0], self.link[1].strip()))
            self.link = None
        if self.mainmatter == self.depth:
            self.done = True
        self.depth -= 1

    def handle_data(self, data):
        if self.link is not None:
            self.link[1] += data


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def menu_links():
    path = os.path.join(output, NAVIGATION, "index.html")
    if not os.path.isfile(path):
        print("decorate.py: no %s tree; the menu is empty" % NAVIGATION, file=sys.stderr)
        return []
    parser = MenuParser()
    parser.feed(read(path))
    return parser.links


def navigation(template, links, entry):
    """The navigation panel for one page, its link marked current (the first,
    when two links lead to the same tree)."""
    current = next((i for i, (href, _) in enumerate(links) if href.strip("/") == entry), None)
    items = "".join(
        '<li><a class="side-menu-link%s" href="%s"%s><span class="side-menu-bullet" aria-hidden="true">■</span>%s</a></li>' % (
            " is-current" if i == current else "",
            html.escape(href, quote=True),
            ' aria-current="page"' if i == current else "",
            html.escape(text),
        )
        for i, (href, text) in enumerate(links)
    )
    return template.replace("{{MENU}}", items)


MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
FORESTER_DATE = re.compile(r'(class="meta-item">)(%s) (\d{1,2}), (\d{4})<' % "|".join(MONTHS))
def japanese(page):
    """Meta-line dates as the design system writes them."""
    return FORESTER_DATE.sub(
        lambda m: "%s%s年%d月%d日<" % (m.group(1), m.group(4), MONTHS.index(m.group(2)) + 1, int(m.group(3))), page)


TOC = re.compile(r'<nav\s+id="toc">(.*?)</nav>', re.S)
FOOTER = re.compile(r'<footer>(.*?)</footer>', re.S)
ID = re.compile(r'\sid="[^"]*"')


def top_sections(html_text):
    """The top-level <section>s of a fragment, in order."""
    parts, depth, start = [], 0, None
    for m in re.finditer(r"<section\b|</section>", html_text):
        if m.group(0) == "</section>":
            depth -= 1
            if depth == 0:
                parts.append(html_text[start:m.end()])
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return parts


# Forester's backmatter headings, and the side panel each becomes.
BACKMATTER = ("Context", "Backlinks", "Related", "References", "Contributions")


def side_shell(page, nav_panel):
    """Bracketed vertical tabs at the top of the right edge, [Navigation]
    always and, for narrow screens, [Table of Contents] [Context]
    [Backlinks] …, each opening a side panel with that part alone. The table
    of contents and the backmatter are copies, so the wide layout keeps
    Forester's own; their ids are dropped so each anchor stays unique.
    Checkboxes open the panels, so they work without script; the checkboxes
    come first, so CSS can reach the panel of each. Returns the inputs and
    panels, and the tabs, which go beside the site name in Forester's header
    (in a row on wide screens, fixed at the right edge on narrow ones)."""
    panels = [("nav", "Navigation", nav_panel)]
    toc = TOC.search(page)
    if toc:
        panels.append(("toc", "Table of Contents",
                       '<aside class="side-panel" aria-label="Table of Contents">%s</aside>' % ID.sub("", toc.group(1))))
    footer = FOOTER.search(page)
    for section in top_sections(footer.group(1)) if footer else []:
        heading = re.search(r"<h1>(.*?)</h1>", section, re.S)
        name = re.sub(r"<[^>]+>", "", heading.group(1)).strip() if heading else ""
        if name in BACKMATTER:
            panels.append((name.lower(), name,
                           '<aside class="side-panel" aria-label="%s">%s</aside>' % (name, ID.sub("", section))))
    inputs = "".join('<input type="checkbox" id="side-%s" class="side-switch">' % key for key, _, _ in panels)
    tabs = "".join('<label for="side-%s" class="side-tab side-tab--%s">[%s]</label>' % (key, key, name)
                   for key, name, _ in panels)
    rest = "".join('<label for="side-%s" class="side-scrim side-scrim--%s" aria-hidden="true"></label>%s'
                   % (key, key, re.sub(r'<(nav|aside) ', r'<\1 id="panel-%s" ' % key, body, count=1))
                   for key, _, body in panels)
    return inputs + rest, '<div class="side-tabs">' + tabs + "</div>"


# Forester's "« Home" link becomes the site name.
LOGO = re.compile(r'<div\s+class="logo">.*?</div>', re.S)
HOME_LINK = re.compile(r'(<a\s[^>]*title="home"[^>]*>)« Home(</a>)')


def meta(kind, key, value):
    if not value:
        return ""
    return '<meta %s="%s" content="%s">' % (kind, key, html.escape(value, quote=True))


def share_head(page, canonical, title, share_title, og_type):
    """What a crawler reads off the head: a share card, a canonical address,
    the icons and the manifest."""
    authors = re.findall(r'<address\s+class="author">([^<]*)</address>', page)[:1]
    dated = re.search(r'class="meta-item">([A-Z][a-z]+ \d{1,2}, \d{4})<', page)
    published = dated and datetime.strptime(dated.group(1), "%B %d, %Y").strftime("%Y-%m-%d")

    parts = [
        '<link rel="canonical" href="%s">' % html.escape(canonical, quote=True),
        '<link rel="icon" href="/favicon.ico" sizes="any">',
        '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">',
        '<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">',
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
        # Names the 192 and 512 icons, which nothing else points at, so a page
        # kept on a phone's home screen shows the M rather than a screenshot.
        '<link rel="manifest" href="/site.webmanifest">',
        meta("name", "description", DESCRIPTION),
        meta("name", "author", ", ".join(authors)),
        meta("property", "og:type", og_type),
        meta("property", "og:site_name", SITE_NAME),
        meta("property", "og:locale", "ja_JP"),
        # og:title does not carry the site name: og:site_name is already beside
        # it in every card that renders one, and repeating it reads as a stutter.
        meta("property", "og:title", share_title),
        meta("property", "og:description", DESCRIPTION),
        meta("property", "og:url", canonical),
        meta("property", "og:image", CARD),
        meta("property", "og:image:width", CARD_W),
        meta("property", "og:image:height", CARD_H),
        meta("property", "og:image:alt", SITE_NAME),
    ]
    if og_type == "article":
        parts.append(meta("property", "article:published_time", published))
        parts += [meta("property", "article:author", author) for author in authors]
    # summary_large_image is the card the image is drawn for; without it the
    # 1200x630 is cropped to a square thumbnail.
    parts += [
        meta("name", "twitter:card", "summary_large_image"),
        meta("name", "twitter:title", share_title),
        meta("name", "twitter:description", DESCRIPTION),
        meta("name", "twitter:image", CARD),
    ]
    # <title> carries the site name because a browser tab and a search result
    # show it alone.
    return "<title>%s</title>" % html.escape(title) + "".join(parts)


def dress(page, *, canonical, title, share_title, og_type, shell, home):
    head = share_head(page, canonical, title, share_title, og_type) + THEME_HEAD
    body = '<body class="miya-native%s">' % (" miya-home" if home else "")
    end = page.find("</head>")
    page = FORESTER_SHARE.sub("", page[:end]) + page[end:]
    page, titles = re.subn(r"<title>.*?</title>", "", page, count=1, flags=re.S)
    page, heads = re.subn(r"</head>", lambda _: head + "</head>", page, count=1)
    page, bodies = re.subn(r"<body>", lambda _: body, page, count=1)
    shell, tabs = side_shell(page, shell)
    page = HOME_LINK.sub(lambda m: m.group(1) + "« " + SITE_NAME + m.group(2), page, count=1)
    page, logos = LOGO.subn(lambda m: m.group(0) + tabs, page, count=1)
    if logos != 1:
        raise SystemExit("decorate.py: no Forester home link in %s" % canonical)
    page, mains = re.subn(r'<div\s+id="main-wrapper">', lambda m: m.group(0) + shell, page, count=1)
    page = japanese(page)
    page, langs = re.subn(r'<html(?:\s+lang="[^"]*")?>', '<html lang="ja">', page, count=1)
    if (titles, heads, bodies, mains, langs) != (1, 1, 1, 1, 1):
        raise SystemExit("decorate.py: unexpected page structure for %s" % canonical)
    return page


def main():
    copy_theme()
    template = read(os.path.join(layout, "navigation.html"))
    links = menu_links()

    written = 0
    home_page = None
    for entry in sorted(os.listdir(output)):
        path = os.path.join(output, entry, "index.html")
        if not os.path.isfile(path):
            continue
        page = read(path)
        # Forester also writes redirect stubs; only rendered trees are dressed.
        if not MAIN_WRAPPER.search(page):
            continue
        tree_title = re.search(r"<title>(.*?)</title>", page, re.S)
        tree_title = html.unescape(tree_title.group(1)) if tree_title else entry
        is_home = entry == HOME
        if is_home:
            home_page = page
        # The Home tree answers at two addresses — its own route and the site
        # root — with one document. Pointing both at the root says which one is
        # meant, so a search engine indexes one page and a share of either
        # shows the same.
        canonical = site_url if is_home else "%s%s/" % (site_url, entry)
        write(path, dress(
            page,
            canonical=canonical,
            title="%s — %s" % (tree_title, SITE_NAME),
            share_title=tree_title,
            og_type="article",
            shell=navigation(template, links, entry),
            home=is_home,
        ))
        written += 1

    if home_page is None:
        raise SystemExit("decorate.py: no %s tree; site root not written" % HOME)

    write(os.path.join(output, "index.html"), dress(
        home_page,
        canonical=site_url,
        title=SITE_NAME,
        share_title=SITE_NAME,
        og_type="website",
        shell=navigation(template, links, HOME),
        home=True,
    ))

    missing = read(os.path.join(layout, "not-found.html"))
    write(os.path.join(output, "404.html"), (
        '<!DOCTYPE html>\n<html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<meta name="robots" content="noindex"><title>Not found — %s</title>'
        '<link rel="stylesheet" href="/style.css">%s</head>'
        '<body class="miya-native"><div id="main-wrapper">%s<div id="grid-wrapper">'
        "<article>%s</article></div></div></body></html>\n"
    ) % (SITE_NAME, THEME_HEAD, "".join(side_shell("", navigation(template, links, None))), missing))

    print("decorate.py: %d trees, the site root and 404.html" % written)


if __name__ == "__main__":
    main()
