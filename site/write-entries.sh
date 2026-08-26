#!/bin/sh
# Write the HTML entry for every route, and for the site root.
#
#   sh write-entries.sh
#
# Forester renders trees into XML that a browser transforms with tree.xsl, and
# writes next to each one an index.html that redirects to it. That redirect is
# what the web actually fetches for https://miya-lis.net/aboutme/ — and what a
# crawler fetches, and no crawler runs XSLT. So a page shared to Slack, to
# Mastodon, to a search engine, was a document with no title, no description,
# no image and no icon: everything the theme knows lives on the far side of a
# transform none of them perform.
#
# This rewrites those redirects into real HTML documents. They still redirect,
# so a reader lands on the tree as before; they now also carry the metadata,
# read back out of the XML the tree was rendered into, so it cannot drift from
# the page it describes.
#
# The root entry is a special case twice over: it is not a tree of its own, so
# it borrows the Home tree's metadata, and it keeps the #hero fragment, which
# is what makes the entry show the hero rather than the Home content.
set -eu

site_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$site_dir"

python3 - "$site_dir" <<'PY'
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

site_dir = sys.argv[1]
output = os.path.join(site_dir, "output")

FR = "{http://www.forester-notes.org}"
XHTML = "{http://www.w3.org/1999/xhtml}"

# Every canonical URL the trees carry is built from this, so the cards have to
# agree with it rather than hardcode a second copy of the domain.
with open(os.path.join(site_dir, "forest.toml"), encoding="utf-8") as handle:
    site_url = re.search(r'^url\s*=\s*"([^"]+)"', handle.read(), re.M).group(1)

SITE_NAME = "MIYA-LIS.NET"
CARD = site_url.rstrip("/") + "/og.png"
CARD_W, CARD_H = "1200", "630"

# A preview is cut off well before this; the limit is here so a long opening
# paragraph does not travel whole.
DESCRIPTION_LIMIT = 200


def text_of(element):
    """Every character of it, with the markup dropped and the spacing tidied."""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def first_paragraph(tree):
    """The opening paragraph, wherever it sits.

    A tree's body is often entirely inside its subtrees — a note whose whole
    content is one `## Heading` has nothing at the top level — so this looks
    through the whole document rather than only at its own children.
    """
    for element in tree.iter(XHTML + "p"):
        body = text_of(element)
        if body:
            return body
    return None


def shorten(body, limit):
    if body is None or len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def child_text(parent, tag):
    element = parent.find(FR + tag)
    return None if element is None else text_of(element)


def read(xml_path):
    """What the tree knows about itself."""
    tree = ET.parse(xml_path).getroot()
    front = tree.find(FR + "frontmatter")
    if front is None:
        return None

    title_el = front.find(FR + "title")
    title = None
    if title_el is not None:
        title = title_el.get("text") or text_of(title_el)

    date = front.find(FR + "date")
    published = None
    if date is not None:
        parts = [child_text(date, part) for part in ("year", "month", "day")]
        if all(parts):
            published = "%04d-%02d-%02d" % tuple(int(part) for part in parts)

    return {
        "title": title,
        "uri": child_text(front, "uri"),
        "route": child_text(front, "route"),
        "taxon": child_text(front, "taxon"),
        "authors": [text_of(a) for a in front.iter(FR + "author")],
        "published": published,
        "description": "miyaのwebsite",
        "is_root": tree.get("root") == "true",
    }


def meta(kind, key, value):
    if not value:
        return []
    return ['<meta %s="%s" content="%s" />' % (kind, key, html.escape(value, quote=True))]


def document(page, canonical, target, page_title, og_type, share_title=None):
    # <title> carries the site name because a browser tab and a search result
    # show it alone. og:title does not: og:site_name is already beside it in
    # every card that renders one, and repeating it reads as a stutter.
    share_title = share_title or page_title
    lines = [
        "<!DOCTYPE html>",
        '<html lang="ja">',
        "<head>",
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width" />',
        "<title>%s</title>" % html.escape(page_title),
        '<link rel="canonical" href="%s" />' % html.escape(canonical, quote=True),
        '<link rel="icon" href="/favicon.ico" sizes="any" />',
        '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />',
        '<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />',
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png" />',
        # Names the 192 and 512 icons, which nothing else points at, so a page
        # kept on a phone's home screen shows the M rather than a screenshot.
        '<link rel="manifest" href="/site.webmanifest" />',
    ]

    lines += meta("name", "description", page["description"])
    lines += meta("name", "author", ", ".join(page["authors"]))

    lines += meta("property", "og:type", og_type)
    lines += meta("property", "og:site_name", SITE_NAME)
    lines += meta("property", "og:locale", "ja_JP")
    lines += meta("property", "og:title", share_title)
    lines += meta("property", "og:description", page["description"])
    lines += meta("property", "og:url", canonical)
    lines += meta("property", "og:image", CARD)
    lines += meta("property", "og:image:width", CARD_W)
    lines += meta("property", "og:image:height", CARD_H)
    lines += meta("property", "og:image:alt", SITE_NAME)

    if og_type == "article":
        lines += meta("property", "article:published_time", page["published"])
        for author in page["authors"]:
            lines += meta("property", "article:author", author)

    # summary_large_image is the card the image is drawn for; without it the
    # 1200x630 is cropped to a square thumbnail.
    lines += meta("name", "twitter:card", "summary_large_image")
    lines += meta("name", "twitter:title", share_title)
    lines += meta("name", "twitter:description", page["description"])
    lines += meta("name", "twitter:image", CARD)

    # Last, so a crawler reading the head in order has the metadata before it
    # meets the instruction to go elsewhere.
    lines += ['<meta http-equiv="refresh" content="0;url=%s" />' % html.escape(target, quote=True)]

    # A refresh of 0 is not instant: the browser finishes the document and
    # paints what it has while the next one is on its way, so every link
    # followed inside the site flashed this page's fallback link — an unstyled
    # "私について — MIYA-LIS.NET" on white — before the tree arrived.
    # location.replace() leaves during the head, before the body is parsed, so
    # there is nothing to paint; it replaces rather than pushes, so the entry
    # does not become a history stop the Back button has to walk through.
    lines += ["<script>location.replace(%s)</script>" % json.dumps(target)]

    # Something to land on if the redirect does not happen — a reader with
    # scripting or refreshes turned off would otherwise get a blank page. It
    # is held back a second so that it appears only when it is the answer,
    # rather than in front of every reader on the way past.
    lines += [
        "<style>",
        "body { margin: 0; padding: 2rem; font-family: sans-serif }",
        "p { opacity: 0; animation: entry-fallback 0.2s linear 1s forwards }",
        "@keyframes entry-fallback { from { opacity: 0 } to { opacity: 1 } }",
        "</style>",
        "</head>",
        "<body>",
        '<p><a href="%s">%s</a></p>' % (html.escape(target, quote=True), html.escape(page_title)),
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(lines)


def write(path, body):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)


written = 0
home = None

for entry in sorted(os.listdir(output)):
    xml_path = os.path.join(output, entry, "index.xml")
    if not os.path.isfile(xml_path):
        continue

    page = read(xml_path)
    if page is None or not page["uri"] or not page["route"]:
        print("write-entries.sh: skipping %s: no frontmatter" % xml_path, file=sys.stderr)
        continue

    if page["is_root"]:
        home = page

    title = page["title"] or page["route"].strip("/")
    page_title = "%s — %s" % (title, SITE_NAME)

    # The Home tree answers at two addresses — its own route and the site root
    # — with one document. Pointing both at the root says which one is meant,
    # so a search engine indexes one page and a share of either shows the same.
    canonical = site_url if page["is_root"] else page["uri"]

    write(
        os.path.join(output, entry, "index.html"),
        document(page, canonical, page["route"] + "index.xml", page_title, "article", title),
    )
    written += 1

if home is None:
    print("write-entries.sh: no tree is marked root; site root not written", file=sys.stderr)
    sys.exit(1)

# The hero is shown only when the entry carries the #hero fragment, so internal
# links to /index/ keep landing on Home content while the root entry does not.
write(
    os.path.join(output, "index.html"),
    document(home, site_url, home["route"] + "index.xml#hero", SITE_NAME, "website"),
)

print("write-entries.sh: %d routes and the site root" % written)
PY
