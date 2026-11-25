"""Dress the forest Forester rendered in the site's own shell.

    python3 decorate.py

Forester 6 renders every tree straight to HTML with its own stylesheet and
scripts. This adds what the site has on top, without touching what Forester
wrote between the tags:

- the theme's static files (icons, the web manifest, the card, fonts, miya.css
  and hero.js), copied over Forester's own favicons;
- in every page's head, the share metadata a crawler reads (it reads the head
  only), the site name in the title, and the theme's stylesheets and script;
- the navigation panel before #main-wrapper, and on the Home tree the hero
  too, so Forester's htmx swaps of #main-wrapper leave them in place;
- the site root as a copy of the Home tree, which hero.js shows as the hero;
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

site_dir = os.path.dirname(os.path.abspath(__file__))
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
THEME_HEAD = (
    '<link rel="stylesheet" href="/fonts-biz-udmincho.css">'
    '<link rel="stylesheet" href="/miya.css">'
    '<script defer src="/hero.js"></script>'
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


def menu():
    path = os.path.join(output, NAVIGATION, "index.html")
    if not os.path.isfile(path):
        print("decorate.py: no %s tree; the menu is empty" % NAVIGATION, file=sys.stderr)
        return ""
    parser = MenuParser()
    parser.feed(read(path))
    return "".join(
        '<a href="%s">%s</a>' % (html.escape(href, quote=True), html.escape(text))
        for href, text in parser.links
    )


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
    page, mains = MAIN_WRAPPER.subn(lambda m: shell + m.group(0), page, count=1)
    page, langs = re.subn(r'<html(?:\s+lang="[^"]*")?>', '<html lang="ja">', page, count=1)
    if (titles, heads, bodies, mains, langs) != (1, 1, 1, 1, 1):
        raise SystemExit("decorate.py: unexpected page structure for %s" % canonical)
    return page


def main():
    copy_theme()
    navigation = read(os.path.join(layout, "navigation.html")).replace("{{MENU}}", menu())
    hero = read(os.path.join(layout, "home.html"))

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
            shell=navigation + (hero if is_home else ""),
            home=is_home,
        ))
        written += 1

    if home_page is None:
        raise SystemExit("decorate.py: no %s tree; site root not written" % HOME)

    # hero.js shows the hero only at the site root, so an internal link to
    # /index/ keeps landing on Home content.
    write(os.path.join(output, "index.html"), dress(
        home_page,
        canonical=site_url,
        title=SITE_NAME,
        share_title=SITE_NAME,
        og_type="website",
        shell=navigation + hero,
        home=True,
    ))

    missing = read(os.path.join(layout, "not-found.html"))
    write(os.path.join(output, "404.html"), (
        '<!DOCTYPE html>\n<html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<meta name="robots" content="noindex"><title>Not found — %s</title>'
        '<link rel="stylesheet" href="/style.css">%s</head>'
        '<body class="miya-native">%s<div id="main-wrapper"><div id="grid-wrapper">'
        "<article>%s</article></div></div></body></html>\n"
    ) % (SITE_NAME, THEME_HEAD, navigation, missing))

    print("decorate.py: %d trees, the site root and 404.html" % written)


if __name__ == "__main__":
    main()
