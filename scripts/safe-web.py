#!/usr/bin/env python3
"""Public-snapshot consumer. No vault discovery, legacy build or deployment."""
import argparse
import hashlib
import json
import os
import posixpath
import re
import stat
import subprocess
import sys
import tempfile
from datetime import date
from html import escape
from html.parser import HTMLParser
from pathlib import Path

MAX_MANIFEST = 65536
MAX_FOREST = 16 * 1024 * 1024
MAX_STRING = 1024 * 1024
MAX_JPEG = 8 * 1024 * 1024
MAX_JPEGS = 128
MAX_JPEG_TOTAL = 32 * 1024 * 1024
MAX_THEME = 64 * 1024 * 1024


def owned_asset_leak(data, *, compiled=False, css=False):
    # Only the two fixed owned CSS files may contain these complete declarations.
    # Token spans, not an entire-file waiver: serialized fields/paths/secrets
    # elsewhere in the same CSS still fail. Quoted keys never match this grammar.
    css_tokens = {(match.start(1), match.end(1)) for match in re.finditer(
        rb'(?:^|[;{}])[ \t\r\n\f]*(?:--hero-mark-|outline-)(offset\s*:)', data, re.I)} if css else set()
    for match in LEAK.finditer(data):
        # Existing js_of_ocaml runtime exception, compiled-client only.
        if compiled and re.fullmatch(rb'(?:offset|aliases)\s*[:=]', match[0], re.I):
            continue
        if (match.start(), match.end()) in css_tokens:
            continue
        return True
    return False


def site_relative(value, prefix):
    if (type(value) is not str or len(value) > 512 or
            not value.startswith(prefix) or
            any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', part) or part in {'.', '..'}
                for part in value.split('/'))):
        raise GateError('SW_THEME')
    return value


def theme_inventory(root, expected):
    """No unlisted files, links or directories in the active theme namespace."""
    required_dirs = {'theme', 'theme/assets', 'theme/styles', 'theme/layout', 'theme/client'}
    for source in expected:
        if source.startswith('theme/'):
            required_dirs.update(p.as_posix() for p in Path(source).parents if p.as_posix() != '.')
    found = set()
    for directory, dirs, names in os.walk(checked_path(root / 'theme'), followlinks=False):
        for name in dirs:
            path = checked_path(Path(directory) / name)
            if path.relative_to(root).as_posix() not in required_dirs:
                raise GateError('SW_THEME')
        for name in names:
            path = checked_path(Path(directory) / name)
            source = path.relative_to(root).as_posix()
            if source not in expected:
                raise GateError('SW_THEME')
            found.add(source)
    if found != {p for p in expected if p.startswith('theme/')}:
        raise GateError('SW_THEME')


def load_trusted_theme(config, site_root):
    """Load caller-owned site code, never a field of the public snapshot."""
    root, config = checked_path(site_root), checked_path(config)
    if config != root / 'config' / 'theme.json':
        raise GateError('SW_THEME')
    config_bytes = read_bounded(config, MAX_MANIFEST)
    spec = strict_json(config_bytes)
    object_keys(spec, {'schema', 'styles', 'client', 'layout', 'assets', 'notices'})
    if spec['schema'] != 'safe-web-theme-v1':
        raise GateError('SW_THEME')
    styles = [{'source': f'theme/styles/{name}.css', 'output': f'theme/styles/{name}.css'}
              for name in ('fonts', 'miya')]
    client = {'source': '_build/default/theme/client/hero.bc.js', 'output': 'theme/client/hero.js'}
    layout = {'home': 'theme/layout/home.html', 'navigation': 'theme/layout/navigation.html'}
    if spec['styles'] != styles or spec['client'] != client or spec['layout'] != layout:
        raise GateError('SW_THEME')
    sources = {'config/theme.json': hashlib.sha256(config_bytes).hexdigest()}
    assets = {}
    total = len(config_bytes)

    def read(source):
        nonlocal total
        path = checked_path(root / source)
        data = read_bounded(path, MAX_FOREST)
        total += len(data)
        if total > MAX_THEME:
            raise GateError('SW_SIZE')
        if owned_asset_leak(data, compiled=source == '_build/default/theme/client/hero.bc.js',
                            css=source in {'theme/styles/fonts.css', 'theme/styles/miya.css'}):
            raise GateError('SW_LEAK')
        if Path(source).suffix in {'.css', '.js', '.html', '.ml'} and re.search(
                rb'(?:reload2\.js|forester\.js|\.(?:xml|xsl)(?:["\x27\s?#<]|$))', data, re.I):
            raise GateError('SW_THEME')
        sources[source] = hashlib.sha256(data).hexdigest()
        return data

    for entry in [*styles, client, *array(spec['assets'])]:
        object_keys(entry, {'source', 'output'})
        source, output = entry['source'], entry['output']
        if entry not in styles and entry != client:
            site_relative(source, 'theme/assets/')
            if source != output or Path(source).suffix not in {'.woff', '.woff2', '.ttf', '.png', '.ico', '.svg', '.webmanifest', '.txt'}:
                raise GateError('SW_THEME')
            if (Path(source).suffix == '.txt' and source != 'theme/assets/notices/CC0-1.0.txt' and
                    not re.match(r'(?:LICENSE|NOTICE|OFL)', Path(source).name)):
                raise GateError('SW_THEME')
        if output in assets or source in sources:
            raise GateError('SW_THEME')
        data = read(source)
        assets[output] = (data, hashlib.sha256(data).hexdigest())
    home = read(layout['home']).decode('utf-8', errors='strict')
    navigation = read(layout['navigation']).decode('utf-8', errors='strict')
    for source in ['theme/client/dune', 'theme/client/hero.ml']:
        read(source)
    source_only_docs = {'theme/notices/INTEGRATION.md', 'theme/notices/PROVENANCE.json'}
    for source in array(spec['notices']):
        site_relative(source, 'theme/')
        if source in sources:
            raise GateError('SW_THEME')
        if source not in source_only_docs:
            site_relative(source, 'theme/assets/')
            if (Path(source).suffix not in {'.md', '.txt'} or
                    not re.match(r'(?:LICENSE|NOTICE|OFL|PROVENANCE)', Path(source).name)):
                raise GateError('SW_THEME')
        data = read(source)
        if source == 'theme/notices/PROVENANCE.json':
            # Provenance is bounded source-only data, never asset authority.
            try:
                strict_json(data.decode('utf-8', errors='strict'))
            except UnicodeError:
                raise GateError('SW_SCHEMA') from None
    for relative, (data, _) in assets.items():
        if relative.endswith('.svg'):
            validate_fragment(data.decode('utf-8', errors='strict'), menu=False, assets=set(assets))
        if relative.endswith('.css'):
            css = data.decode('utf-8', errors='strict')
            if re.search(r'@import\b|\\', css, re.I):
                raise GateError('SW_THEME')
            for value in re.findall(r'url\(([^)]*)\)', css, re.I):
                value = value.strip(' \t\r\n\"\x27')
                target = posixpath.normpath(posixpath.join(posixpath.dirname(relative), value)) if not value.startswith('/') else value[1:]
                if target not in assets:
                    raise GateError('SW_THEME')
    validate_fragment(home, menu=False, assets=set(assets))
    validate_fragment(navigation, menu=True, assets=set(assets))
    theme_inventory(root, sources)
    return {'root': root, 'assets': assets, 'sources': sources,
            'home': home, 'navigation': navigation}


def verify_trusted_theme(theme):
    theme_inventory(theme['root'], theme['sources'])
    for source, digest in theme['sources'].items():
        data = read_bounded(checked_path(theme['root'] / source), MAX_FOREST)
        if hashlib.sha256(data).hexdigest() != digest:
            raise GateError('SW_THEME')


class FragmentParser(HTMLParser):
    """Constrained, reviewed static fragments, not a content template engine."""
    tags = set('nav header footer section div ul ol li a button span p h1 h2 h3 h4 h5 h6 strong em small img br svg g path circle rect line polyline polygon title desc'.split())
    void = {'img', 'br'}
    reserved = {'main-wrapper', 'grid-wrapper', 'tree-container', 'home-link', 'site-shell'}
    common_attrs = {'id', 'class', 'role', 'title', 'tabindex', 'hidden', 'inert'}
    svg_attrs = set('xmlns xmlns:xlink viewbox width height fill fill-rule clip-rule stroke stroke-width stroke-linecap stroke-linejoin stroke-dasharray d cx cy r rx ry x y x1 x2 y1 y2 points transform focusable'.split())
    tag_attrs = {'a': {'href', 'rel', 'target'}, 'button': {'type', 'disabled'},
                 'img': {'src', 'alt', 'width', 'height', 'loading', 'decoding'}}

    def __init__(self, assets):
        super().__init__(convert_charrefs=True)
        self.assets, self.ids, self.targets, self.stack = assets, set(), set(), []

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags or len(dict(attrs)) != len(attrs):
            raise GateError('SW_THEME')
        for key, value in attrs:
            allowed = self.common_attrs | self.tag_attrs.get(tag, set())
            if tag in {'svg', 'g', 'path', 'circle', 'rect', 'line', 'polyline', 'polygon'}:
                allowed |= self.svg_attrs
            if key not in allowed and not re.fullmatch(r'(?:data|aria)-[a-z0-9-]+', key):
                raise GateError('SW_THEME')
            if key == 'inert' and value not in {None, '', 'inert'}:
                raise GateError('SW_THEME')
            if value and ('{{' in value or '}}' in value or re.search(r'(?:javascript|data|file|vbscript)\s*:', value, re.I)):
                raise GateError('SW_THEME')
            if value and re.search(r'url\s*\(', value, re.I) and not re.fullmatch(r'url\(#[A-Za-z0-9_-]+\)', value):
                raise GateError('SW_THEME')
            if key == 'id':
                if not value or value in self.ids or value in self.reserved:
                    raise GateError('SW_THEME')
                self.ids.add(value)
            if key in {'src', 'href', 'xlink:href'}:
                if not value or '\\' in value or '..' in value.split('/') or re.search(r'\.(?:xml|xsl)(?:$|[?#])', value, re.I):
                    raise GateError('SW_THEME')
                if key == 'src':
                    if not value.startswith('/theme/assets/') or value[1:] not in self.assets:
                        raise GateError('SW_THEME')
                elif value == '/' or value.startswith('#') or re.fullmatch(r'https://[^\s<>]+|mailto:[^\s<>]+', value):
                    pass
                elif re.fullmatch(r'/[A-Za-z0-9-]{1,128}/', value):
                    self.targets.add(value[1:-1])
                else:
                    raise GateError('SW_THEME')
        if tag not in self.void:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.stack.pop()

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise GateError('SW_THEME')

    def handle_decl(self, decl):
        raise GateError('SW_THEME')

    def handle_comment(self, text):
        if '{{' in text or '}}' in text:
            raise GateError('SW_THEME')


def validate_fragment(text, *, menu, assets):
    if len(text.encode('utf-8')) > MAX_MANIFEST or text.count('{{MENU}}') != int(menu):
        raise GateError('SW_THEME')
    inert = text.replace('{{MENU}}', '') if menu else text
    if '{{' in inert or '}}' in inert:
        raise GateError('SW_THEME')
    parser = FragmentParser(assets)
    parser.feed(text)
    parser.close()
    if parser.stack:
        raise GateError('SW_THEME')
    return parser


class NativePageParser(HTMLParser):
    """Find trusted fixed-template insertion points without reserializing DOM."""
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.lines = [0]
        self.lines.extend(match.end() for match in re.finditer('\n', text))
        self.head_end, self.body, self.main = [], [], []
        self.ids, self.scripts, self.styles = set(), [], []
        self.feed(text)
        self.close()

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'body':
            self.body.append((self.position(), self.get_starttag_text()))
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if attrs.get('id') == 'main-wrapper':
            if tag != 'div':
                raise GateError('SW_OUTPUT')
            self.main.append(self.position())
        if tag == 'script':
            self.scripts.append(attrs.get('src'))
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.styles.append(attrs.get('href'))

    def handle_endtag(self, tag):
        if tag == 'head':
            self.head_end.append(self.position())


def present_native(output, ids, home, theme, forest):
    """Decorate only audited native pages. Snapshot text is never substituted."""
    validate_forest(forest)
    if forest_ids(forest) != ids or home not in ids:
        raise GateError('SW_TARGET')
    verify_trusted_theme(theme)
    navigation = validate_fragment(theme['navigation'], menu=True, assets=set(theme['assets']))
    hero = validate_fragment(theme['home'], menu=False, assets=set(theme['assets']))
    if not (navigation.targets | hero.targets) <= ids or navigation.ids & hero.ids:
        raise GateError('SW_TARGET')
    menu = ''.join('<li><a href="/' + escape(identifier(tree['id']), quote=True) + '/">' +
                   escape(tree['title'], quote=True) + '</a></li>' for tree in forest['trees'])
    nav_text = theme['navigation'].replace('{{MENU}}', menu)
    links = ('<link rel="stylesheet" href="/theme/styles/fonts.css">'
             '<link rel="stylesheet" href="/theme/styles/miya.css">'
             '<script defer src="/theme/client/hero.js"></script>')
    page_hashes = {}
    for id in sorted(ids):
        route = identifier(id) + '/index.html'
        path = output / route
        text = read_bounded(path, MAX_FOREST).decode('utf-8', errors='strict')
        page = NativePageParser(text)
        if (len(page.head_end) != 1 or len(page.body) != 1 or len(page.main) != 1 or
                'grid-wrapper' not in page.ids or page.scripts != ['/katex.min.js', '/min.js'] or
                page.styles != ['/style.css', '/katex.min.css'] or
                page.ids & (navigation.ids | hero.ids)):
            raise GateError('SW_OUTPUT')
        is_home = id == home
        # Trusted fragment roots stay direct body siblings; the actual owned
        # client intentionally excludes nav controls nested in native content.
        shell = nav_text + (theme['home'] if is_home else '')
        body_start, body_tag = page.body[0]
        if body_tag != '<body>':
            raise GateError('SW_OUTPUT')
        body = '<body class="miya-native' + (' miya-home' if is_home else '') + '" data-site-page="' + escape(id, quote=True) + '" data-site-home="' + str(is_home).lower() + '">'
        edits = [(page.main[0], page.main[0], shell),
                 (body_start, body_start + len(body_tag), body),
                 (page.head_end[0], page.head_end[0], links)]
        for start, end, replacement in sorted(edits, reverse=True):
            text = text[:start] + replacement + text[end:]
        data = text.encode('utf-8')
        path.write_bytes(data)
        page_hashes[route] = hashlib.sha256(data).hexdigest()
    (output / 'index.html').write_bytes(read_bounded(output / home / 'index.html', MAX_FOREST))
    for relative, (data, _) in theme['assets'].items():
        destination = output / relative
        if destination.exists():
            raise GateError('SW_THEME')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    verify_trusted_theme(theme)
    return page_hashes



def checked_path(value):
    path = Path(value)
    if '..' in path.parts:
        raise GateError('SW_PATH')
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise GateError('SW_PATH')
    return path


def read_bounded(path, limit):
    mode = path.lstat()
    if not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1:
        raise GateError('SW_PATH')
    if mode.st_size > limit:
        raise GateError('SW_SIZE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (mode.st_dev, mode.st_ino):
            raise GateError('SW_PATH')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise GateError('SW_SIZE')
    return data


class GateError(Exception):
    """Errors carry constant public codes, never input or exception payloads."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def object_keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise GateError('SW_SCHEMA')


def literal(value, *, markdown=False):
    controls = '\n\t\r' if markdown else '\n\t'
    if type(value) is not str:
        raise GateError('SW_SCHEMA')
    try:
        encoded = value.encode('utf-8', errors='strict')
    except UnicodeEncodeError:
        raise GateError('SW_SCHEMA') from None
    if len(encoded) > MAX_STRING or any(ord(c) < 32 and c not in controls for c in value):
        raise GateError('SW_SCHEMA')
    # Only Markdown has CRLF line endings; lone CR stays fail closed. Other
    # metadata strings retain the original stricter control-character gate.
    if markdown and re.search(r'\r(?!\n)', value):
        raise GateError('SW_SCHEMA')
    return value


def array(value):
    if type(value) is not list or len(value) > 20000:
        raise GateError('SW_SIZE')
    return value


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', value):
        raise GateError('SW_ID')
    return value


def markdown_guard_text(text):
    """Mask only recognized literal spans, never rewrite the staged bytes.

    NUL is an internal non-whitespace sentinel: removing a span must not join
    tokens, create a blank line, or change offsets and paragraph boundaries.
    This bounded lexical guard is not a Markdown/publication authority. The
    converter still parses and independently validates every original chunk.
    """
    masked = list(text)
    lines, offset = [], 0
    # CommonMark lines are LF/CRLF here, not Python's wider Unicode
    # splitlines set (NEL/LS/PS must remain ordinary inline characters).
    for match in re.finditer(r'[^\n]*(?:\n|$)', text):
        line = match[0]
        if not line:
            continue
        lines.append((offset, offset + len(line), line.rstrip('\r\n')))
        offset += len(line)

    def mark(start, end):
        for pos in range(start, end):
            if text[pos] not in ' \t\r\n':
                masked[pos] = '\0'

    def indented(line):
        prefix = line[:len(line) - len(line.lstrip(' \t'))]
        return len(prefix.expandtabs(4)) >= 4

    def boundary(line):
        return (not line.strip(' \t') or
                re.match(r' {0,3}(?:#{1,6}(?:[ \t]|$)|>|(?:[-+*]|[0-9]{1,9}[.)])[ \t]|<)', line) or
                re.fullmatch(r' {0,3}(?:\*[ \t]*){3,}| {0,3}(?:_[ \t]*){3,}| {0,3}(?:-[ \t]*){3,}| {0,3}(?:=+|-+)[ \t]*', line))

    paragraphs, paragraph, index = [], None, 0
    unparsed_container = False
    while index < len(lines):
        start, end, line = lines[index]
        # Container-relative indentation needs a full block parser. Do not
        # misclassify list/quote continuations as top-level literal code.
        if re.match(r' {0,3}(?:>|(?:[-+*]|[0-9]{1,9}[.)])[ \t])', line):
            unparsed_container = True
        fence = re.fullmatch(r' {0,3}(`{3,}|~{3,})([^\r\n]*)', line)
        if fence and not (fence[1][0] == '`' and '`' in fence[2]):
            if paragraph is not None:
                paragraphs.append((paragraph, start))
                paragraph = None
            marker = fence[1][0]
            close = index + 1
            while close < len(lines) and not re.fullmatch(
                    r' {0,3}' + re.escape(marker) + '{' + str(len(fence[1])) + r',}[ \t]*', lines[close][2]):
                close += 1
            if close == len(lines):
                raise GateError('SW_MARKDOWN')
            mark(start, lines[close][1])
            index = close + 1
            continue
        if not unparsed_container and paragraph is None and line.strip(' \t') and indented(line):
            while index < len(lines):
                code_start, code_end, code_line = lines[index]
                if code_line.strip(' \t') and not indented(code_line):
                    break
                mark(code_start, code_end)
                index += 1
            continue
        if boundary(line):
            if paragraph is not None:
                paragraphs.append((paragraph, start))
                paragraph = None
        elif paragraph is None:
            paragraph = start
        index += 1
    if paragraph is not None:
        paragraphs.append((paragraph, len(text)))

    for start, end in paragraphs:
        runs = list(re.finditer(r'`+|\$+', text[start:end]))
        escaped = []
        for run in runs:
            pos, slashes = start + run.start(), 0
            while pos > start and text[pos - 1] == '\\':
                slashes += 1
                pos -= 1
            escaped.append(bool(slashes % 2))
        # Index closers once. Repeated unmatched runs must not cause a
        # quadratic scan of an untrusted megabyte-sized chunk.
        following, latest = {}, {}
        for index in range(len(runs) - 1, -1, -1):
            token = runs[index][0]
            following[index] = latest.get(token)
            if token[0] == '`' or (len(token) <= 2 and not escaped[index] and
                    (len(token) == 2 or (runs[index].start() > 0 and
                     not text[start + runs[index].start() - 1].isspace() and
                     (start + runs[index].end() == end or
                      not text[start + runs[index].end()].isdigit())))):
                latest[token] = index
        index = 0
        while index < len(runs):
            opening = runs[index]
            token = opening[0]
            is_math = token[0] == '$'
            if escaped[index] or (is_math and (len(token) > 2 or
                    start + opening.end() == end or
                    (len(token) == 1 and text[start + opening.end()].isspace()))):
                index += 1
                continue
            close = following[index]
            if close is not None:
                mark(start + opening.start(), start + runs[close].end())
                index = close + 1
            else:
                index += 1
    return ''.join(masked)


def dimension(value):
    if type(value) is not int or not 1 <= value <= 8192:
        raise GateError('SW_SCHEMA')
    return value


def forest_assets(forest):
    """The closed JPEG registry: strictly sorted digests, bounded count, bytes and pixels."""
    assets = forest['assets']
    if type(assets) is not list or len(assets) > MAX_JPEGS:
        raise GateError('SW_SIZE')
    registry, previous, total = {}, None, 0
    for asset in assets:
        object_keys(asset, {'sha256', 'mime', 'bytes', 'width', 'height'})
        digest = asset['sha256']
        if type(digest) is not str or not re.fullmatch(r'[0-9a-f]{64}', digest) or (previous is not None and digest <= previous):
            raise GateError('SW_SCHEMA')
        if asset['mime'] != 'image/jpeg' or type(asset['bytes']) is not int or not 1 <= asset['bytes'] <= MAX_JPEG:
            raise GateError('SW_SCHEMA')
        total += asset['bytes']
        if total > MAX_JPEG_TOTAL or dimension(asset['width']) * dimension(asset['height']) > 32000000:
            raise GateError('SW_SIZE')
        registry[digest] = asset['bytes']
        previous = digest
    return registry


def validate_forest(forest):
    object_keys(forest, {'schema', 'trees', 'assets'})
    if forest['schema'] != 'forester-public-v2':
        raise GateError('SW_SCHEMA')
    registry, used = forest_assets(forest), set()
    roots = array(forest['trees'])
    names, edges, refs = {}, {}, []
    count = 0
    properties = {'position', 'institution', 'venue', 'source', 'doi', 'orcid', 'external', 'slides', 'video', 'bibtex', 'author'}

    def attribution(item):
        if type(item) is not dict:
            raise GateError('SW_SCHEMA')
        if item.get('kind') == 'literal':
            object_keys(item, {'kind', 'value'})
            literal(item['value'])
        elif item.get('kind') == 'tree':
            object_keys(item, {'kind', 'id'})
            refs.append(identifier(item['id']))
        else:
            raise GateError('SW_SCHEMA')

    def markdown(text):
        literal(text, markdown=True)
        # Strict v2 boundary, not an authorization parser. Check executable
        # Markdown only; original code bytes still reach the real converter.
        text = markdown_guard_text(text)
        if '<' in text or '\\{' in text or '![' in text or re.search(r'^\s*#{1,6}\s|\^[-A-Za-z0-9]+\s*$', text, re.M):
            raise GateError('SW_MARKDOWN')
        links = list(re.finditer(r'\[\[([A-Za-z0-9-]+)\|([^\[\]|\\\r\n]*)\]\]', text))
        remaining = text
        for match in reversed(links):
            refs.append(identifier(match.group(1)))
            remaining = remaining[:match.start()] + remaining[match.end():]
        if '[[' in remaining or ']]' in remaining:
            raise GateError('SW_MARKDOWN')
        for destination in re.findall(r'\]\(([^)]*)\)', remaining):
            if not re.fullmatch(r'https://[^\s<>]+|mailto:[^\s<>]+', destination):
                raise GateError('SW_MARKDOWN')
        if re.search(r'^\s*\[[^\]]+\]:', remaining, re.M):
            raise GateError('SW_MARKDOWN')

    def visit(tree, depth=0):
        nonlocal count
        count += 1
        if count > 20000 or depth > 64:
            raise GateError('SW_SIZE')
        object_keys(tree, {'title', 'authors', 'dates', 'contributors', 'properties', 'citationAuthors', 'content'}, {'id', 'taxon', 'publicationYear'})
        key = 'anonymous:' + str(count)
        if 'id' in tree:
            key = identifier(tree['id'])
            folded = key.lower()
            if folded in names:
                raise GateError('SW_ID')
            names[folded] = key
        elif depth == 0:
            raise GateError('SW_ID')
        edges[key] = []
        literal(tree['title'])
        for name in ('taxon', 'publicationYear'):
            if name in tree:
                literal(tree[name])
        if 'publicationYear' in tree and not re.fullmatch(r'[0-9]{4}', tree['publicationYear']):
            raise GateError('SW_SCHEMA')
        for name in ('authors', 'contributors'):
            for item in array(tree[name]):
                attribution(item)
        for item in array(tree['citationAuthors']):
            literal(item)
        for item in array(tree['dates']):
            if type(item) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', item):
                raise GateError('SW_DATE')
            try:
                date.fromisoformat(item)
            except ValueError:
                raise GateError('SW_DATE') from None
        if type(tree['properties']) is not dict or tree['properties'].keys() - properties:
            raise GateError('SW_SCHEMA')
        for values in tree['properties'].values():
            for value in array(values):
                literal(value)
                if re.search(r'(?:javascript|data|file|vbscript)\s*:', value, re.I):
                    raise GateError('SW_SCHEMA')
        for node in array(tree['content']):
            if type(node) is not dict:
                raise GateError('SW_SCHEMA')
            kind = node.get('kind')
            if kind == 'markdown':
                object_keys(node, {'kind', 'text'})
                markdown(node['text'])
            elif kind == 'subtree':
                object_keys(node, {'kind', 'tree'})
                edges[key].append(visit(node['tree'], depth + 1))
            elif kind == 'transclude':
                object_keys(node, {'kind', 'id', 'header', 'toc'})
                target = identifier(node['id'])
                if type(node['header']) is not bool or type(node['toc']) is not bool:
                    raise GateError('SW_SCHEMA')
                refs.append(target)
                edges[key].append(target)
            elif kind == 'unavailable':
                # A fixed placeholder: no target, path or reason, only an optional literal label.
                object_keys(node, {'kind'}, {'label'})
                if 'label' in node:
                    literal(node['label'])
            elif kind == 'image':
                object_keys(node, {'kind', 'sha256', 'alt'}, {'width', 'height'})
                if node['sha256'] not in registry:
                    raise GateError('SW_SCHEMA')
                used.add(node['sha256'])
                literal(node['alt'])
                for name in ('width', 'height'):
                    if name in node:
                        dimension(node[name])
            else:
                raise GateError('SW_SCHEMA')
        return key

    for root in roots:
        visit(root)
    if used != set(registry):
        raise GateError('SW_SCHEMA')
    ids = set(names.values())
    if any(target not in ids for target in refs):
        raise GateError('SW_TARGET')
    states = {}
    def acyclic(key):
        if states.get(key) == 1:
            raise GateError('SW_CYCLE')
        if states.get(key) == 2:
            return
        states[key] = 1
        for child in edges[key]:
            acyclic(child)
        states[key] = 2
    for key in edges:
        acyclic(key)
    return len(ids)


def strict_json(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise GateError('SW_SCHEMA')
            value[key] = item
        return value
    def invalid_constant(_):
        raise GateError('SW_SCHEMA')
    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise GateError('SW_SCHEMA') from None


def stage_snapshot(snapshot, stage, expected_digest):
    if type(expected_digest) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected_digest):
        raise GateError('SW_DIGEST')
    snapshot, stage = checked_path(snapshot), checked_path(stage)
    if snapshot == stage or snapshot in stage.parents or stage in snapshot.parents:
        raise GateError('SW_PATH')
    if stage.exists():
        raise GateError('SW_FRESH')
    if {p.name for p in snapshot.iterdir()} - {'media'} != {'manifest.json', 'public-forest.json'}:
        raise GateError('SW_INVENTORY')
    manifest_bytes = read_bounded(snapshot / 'manifest.json', MAX_MANIFEST)
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_digest:
        raise GateError('SW_DIGEST')
    manifest = strict_json(manifest_bytes)
    object_keys(manifest, {'schema', 'files'})
    if manifest['schema'] != 'forester-public-snapshot-v1':
        raise GateError('SW_SCHEMA')
    if type(manifest['files']) is not dict or 'public-forest.json' not in manifest['files']:
        raise GateError('SW_SCHEMA')
    file_digest = manifest['files']['public-forest.json']
    if type(file_digest) is not str or not re.fullmatch(r'[0-9a-f]{64}', file_digest):
        raise GateError('SW_DIGEST')
    data = read_bounded(snapshot / 'public-forest.json', MAX_FOREST)
    if hashlib.sha256(data).hexdigest() != manifest['files']['public-forest.json']:
        raise GateError('SW_FILE_DIGEST')
    forest = strict_json(data)
    count = validate_forest(forest)
    registry = forest_assets(forest)
    # The manifest authenticates every published JPEG by the same digest that names it.
    media_names = {f'media/{digest}.jpg' for digest in registry}
    if manifest['files'].keys() != {'public-forest.json'} | media_names:
        raise GateError('SW_INVENTORY')
    media = {}
    if registry:
        directory = snapshot / 'media'
        if directory.is_symlink() or not directory.is_dir() or {p.name for p in directory.iterdir()} != {f'{d}.jpg' for d in registry}:
            raise GateError('SW_INVENTORY')
        for digest, size in registry.items():
            name = f'media/{digest}.jpg'
            if manifest['files'][name] != digest:
                raise GateError('SW_DIGEST')
            image = read_bounded(snapshot / name, MAX_JPEG)
            if len(image) != size or hashlib.sha256(image).hexdigest() != digest or image[:2] != b'\xff\xd8':
                raise GateError('SW_FILE_DIGEST')
            media[digest] = image
    elif (snapshot / 'media').exists():
        raise GateError('SW_INVENTORY')
    stage.mkdir()
    (stage / 'public-forest.json').write_bytes(data)
    if media:
        (stage / 'media').mkdir()
        for digest, image in media.items():
            (stage / 'media' / f'{digest}.jpg').write_bytes(image)
    return {'trees': count, 'files': 1 + len(media)}


LEAK = re.compile(rb'(?:/(?:home|Users|nix/store|tmp)/|[A-Za-z]:\\\\Users\\\\|(?:sourcePath|source_path|sourceFile|source_file|sourceLocation|source_location|filename|file_name|offset|aliases|rawSource)\s*["\x27]?\s*[:=]|(?:gh[pousr]_|github_pat_|AKIA[0-9A-Z]|-----BEGIN [A-Z ]*PRIVATE KEY-----)|SYNTHETIC_(?:PRIVATE|REVOKED)_CANARY)', re.I)


def audit_output(output, ids, theme_hashes, *, custom_hashes=None, page_hashes=None, home_copy=None, search_hash=None,
                 media=frozenset()):
    output = checked_path(output)
    routes = {f'{identifier(id)}/index.html' for id in ids}
    images = {f'media/{digest}.jpg': digest for digest in media}
    custom_hashes = custom_hashes or {}
    if set(theme_hashes) & set(custom_hashes):
        raise GateError('SW_THEME')
    for relative, digest in custom_hashes.items():
        site_relative(relative, 'theme/')
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise GateError('SW_THEME')
    if page_hashes is not None and (set(page_hashes) != routes or
            any(not re.fullmatch(r'[0-9a-f]{64}', digest) for digest in page_hashes.values())):
        raise GateError('SW_OUTPUT')
    if home_copy is not None and (home_copy not in ids or page_hashes is None):
        raise GateError('SW_OUTPUT')
    if search_hash is not None and not re.fullmatch(r'[0-9a-f]{64}', search_hash):
        raise GateError('SW_OUTPUT')
    required = routes | {'index.html', 'forest.json'} | set(theme_hashes) | set(custom_hashes) | set(images)
    allowed_dirs = {parent.as_posix() for relative in required for parent in Path(relative).parents
                    if parent.as_posix() != '.'}
    files, seen, total = 0, set(), 0
    for directory, dirs, names in os.walk(output, followlinks=False):
        for name in dirs:
            path = Path(directory) / name
            if path.is_symlink():
                raise GateError('SW_PATH')
            if path.relative_to(output).as_posix() not in allowed_dirs:
                raise GateError('SW_OUTPUT')
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(output).as_posix()
            data = read_bounded(path, MAX_FOREST)
            total += len(data)
            files += 1
            if total > 128 * 1024 * 1024 or files > 30000:
                raise GateError('SW_SIZE')
            if relative in theme_hashes:
                if hashlib.sha256(data).hexdigest() != theme_hashes[relative]:
                    raise GateError('SW_THEME')
            elif relative in images:
                if hashlib.sha256(data).hexdigest() != images[relative]:
                    raise GateError('SW_OUTPUT')
            elif relative in custom_hashes:
                if owned_asset_leak(data, compiled=relative == 'theme/client/hero.js',
                                    css=relative in {'theme/styles/fonts.css', 'theme/styles/miya.css'}):
                    raise GateError('SW_LEAK')
                if hashlib.sha256(data).hexdigest() != custom_hashes[relative]:
                    raise GateError('SW_THEME')
            elif relative in routes:
                if LEAK.search(data):
                    raise GateError('SW_LEAK')
                if page_hashes is not None and hashlib.sha256(data).hexdigest() != page_hashes[relative]:
                    raise GateError('SW_OUTPUT')
                seen.add(relative)
            elif relative == 'index.html':
                if LEAK.search(data):
                    raise GateError('SW_OUTPUT')
                if home_copy is not None:
                    home_route = home_copy + '/index.html'
                    if not (output / home_route).is_file():
                        raise GateError('SW_OUTPUT')
                    if (hashlib.sha256(data).hexdigest() != page_hashes[home_route] or
                            data != read_bounded(output / home_route, MAX_FOREST)):
                        raise GateError('SW_OUTPUT')
                elif not re.search(rb'content="0;url=(?:' + b'|'.join(re.escape(id.encode()) for id in sorted(ids)) + rb')/"', data):
                    raise GateError('SW_OUTPUT')
            elif relative == 'forest.json':
                if LEAK.search(data):
                    raise GateError('SW_LEAK')
                if search_hash is not None and hashlib.sha256(data).hexdigest() != search_hash:
                    raise GateError('SW_OUTPUT')
                entries = array(strict_json(data))
                found = set()
                for entry in entries:
                    object_keys(entry, {'title', 'uri', 'taxon', 'tags', 'route', 'metas'})
                    if entry['uri'] not in ids or entry['uri'] in found or entry['route'] != '/' + entry['uri']:
                        raise GateError('SW_OUTPUT')
                    found.add(entry['uri'])
                if found != ids:
                    raise GateError('SW_OUTPUT')
            else:
                raise GateError('SW_OUTPUT')
    if seen != routes or required != {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}:
        raise GateError('SW_OUTPUT')
    return {'files': files, 'routes': len(seen)}


FORESTER_REV = 'f8fb5f5d88923db36643cf9c20c662adff969c98'
FORESTER_FLAKE = 'git+https://tangled.org/jonmsterling.com/ocaml-forester?ref=forester-6.0-dev&rev=' + FORESTER_REV + '#legacyPackages.x86_64-linux.forester'


def run_quiet(command, cwd=None):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        raise GateError('SW_TOOL') from None
    if result.returncode:
        raise GateError('SW_TOOL')
    return result.stdout


def render_native(trees, output, binary, ids, home, *, theme=None, forest=None, media=None):
    trees, output = checked_path(trees), checked_path(output)
    if output.exists():
        raise GateError('SW_FRESH')
    if trees == output or trees in output.parents or output in trees.parents or home not in ids:
        raise GateError('SW_PATH')
    binary = Path(binary).resolve(strict=True)
    package = Path(run_quiet(['nix', 'eval', '--offline', '--impure', '--raw', '--option', 'allow-import-from-derivation', 'true', FORESTER_FLAKE + '.outPath']).decode().strip())
    if binary != package / 'bin' / 'forester' or run_quiet([str(binary), '--version']).strip() != b'6.0~dev':
        raise GateError('SW_PIN')
    native_theme = package / 'share' / 'forester' / 'themes' / 'default'
    # Keep every intermediate outside the site, and never reuse a prior output.
    with tempfile.TemporaryDirectory(prefix='safe-web-render-', dir=output.parent) as scratch:
        work = Path(scratch)
        (work / 'trees').mkdir()
        for path in trees.iterdir():
            if path.suffix != '.tree' or path.stem not in ids:
                raise GateError('SW_TREES')
            (work / 'trees' / path.name).write_bytes(read_bounded(path, MAX_FOREST))
        (work / 'forest.toml').write_text('[forest]\ntrees = ["trees"]\nassets = []\nhome = ' + json.dumps(identifier(home)) + '\nurl = "https://miya-lis.net/"\n')
        html = work / 'output'
        html.mkdir()
        theme_hashes = {}
        for path in native_theme.rglob('*'):
            if path.is_dir():
                continue
            relative = path.relative_to(native_theme)
            if path.suffix not in {'.css', '.js', '.woff', '.woff2', '.ttf', '.png', '.ico', '.webmanifest'} or path.name.startswith('legacy-'):
                continue
            data = read_bounded(path, MAX_FOREST)
            destination = html / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            theme_hashes[relative.as_posix()] = hashlib.sha256(data).hexdigest()
        run_quiet([str(binary), 'build', 'forest.toml', '--no-theme'], cwd=work)
        digests = set()
        if media is not None:
            (html / 'media').mkdir()
            for path in checked_path(media).iterdir():
                if not re.fullmatch(r'[0-9a-f]{64}\.jpg', path.name):
                    raise GateError('SW_INVENTORY')
                (html / 'media' / path.name).write_bytes(read_bounded(path, MAX_JPEG))
                digests.add(path.stem)
        counts = audit_output(html, ids, theme_hashes, media=digests)
        if theme is not None:
            if forest is None:
                raise GateError('SW_THEME')
            search_hash = hashlib.sha256(read_bounded(html / 'forest.json', MAX_FOREST)).hexdigest()
            page_hashes = present_native(html, ids, home, theme, forest)
            counts = audit_output(html, ids, theme_hashes,
                custom_hashes={p: digest for p, (_, digest) in theme['assets'].items()},
                page_hashes=page_hashes, home_copy=home, search_hash=search_hash, media=digests)
        # Move only after the complete artifact passes; failures expose nothing.
        checked_path(output)
        if output.exists():
            raise GateError('SW_FRESH')
        html.rename(output)
        return counts


def revision(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{40}', value):
        raise GateError('SW_REV')
    return value


def forest_ids(forest):
    ids = set()
    pending = list(forest['trees'])
    while pending:
        tree = pending.pop()
        if 'id' in tree:
            ids.add(tree['id'])
        pending.extend(node['tree'] for node in tree['content'] if node['kind'] == 'subtree')
    return ids


def build_snapshot(snapshot, output, digest, converter, converter_rev, converter_hash, forester, home,
                   *, theme_config=None, site_root=None):
    revision(converter_rev)
    snapshot, output = checked_path(snapshot), checked_path(output)
    if output.exists():
        raise GateError('SW_FRESH')
    if output == snapshot or snapshot in output.parents or output in snapshot.parents:
        raise GateError('SW_PATH')
    with tempfile.TemporaryDirectory(prefix='safe-web-build-', dir=output.parent) as scratch:
        scratch = Path(scratch)
        stage_snapshot(snapshot, scratch / 'snapshot', digest)
        forest = strict_json(read_bounded(scratch / 'snapshot' / 'public-forest.json', MAX_FOREST))
        ids = forest_ids(forest)
        if home not in ids:
            raise GateError('SW_ID')
        theme = None
        if theme_config is not None:
            if site_root is None:
                raise GateError('SW_THEME')
            root = checked_path(site_root)
            if snapshot == root or snapshot in root.parents:
                raise GateError('SW_PATH')
            theme = load_trusted_theme(theme_config, root)
            if any(snapshot == root / source or snapshot in (root / source).parents for source in theme['sources']):
                raise GateError('SW_PATH')
            if any(output == root / source or output in (root / source).parents for source in theme['sources']):
                raise GateError('SW_PATH')
        elif site_root is not None:
            raise GateError('SW_THEME')
        converter = checked_path(converter)
        if not re.fullmatch(r'[0-9a-f]{64}', converter_hash) or hashlib.sha256(read_bounded(converter, 64 * 1024 * 1024)).hexdigest() != converter_hash:
            raise GateError('SW_PIN')
        run_quiet([str(converter), '--public-forest', str(scratch / 'snapshot' / 'public-forest.json'), '--out-dir', str(scratch / 'trees')])
        roots = {tree['id'] + '.tree' for tree in forest['trees']}
        if {path.name for path in (scratch / 'trees').iterdir()} != roots:
            raise GateError('SW_TREES')
        media = scratch / 'snapshot' / 'media'
        return render_native(scratch / 'trees', output, forester, ids, home, theme=theme, forest=forest,
                             media=media if media.exists() else None)


def validate_pins(pins):
    object_keys(pins, {'schema', 'content_repository', 'converter_repository', 'converter_revision', 'converter_build_argv', 'converter_executable', 'forester_revision', 'forester_flake'})
    if pins['schema'] != 'safe-web-pins-v1' or pins['content_repository'] != 'ryoryoryo3838/miya-lis-public' or pins['converter_repository'] != 'ryoryoryo3838/tree-md':
        raise GateError('SW_PIN')
    if not isinstance(pins['converter_revision'], str) or not re.fullmatch(r'[0-9a-f]{40}', pins['converter_revision']):
        raise GateError('SW_PIN')
    if pins['forester_revision'] != FORESTER_REV or pins['forester_flake'] != FORESTER_FLAKE:
        raise GateError('SW_PIN')
    argv = pins['converter_build_argv']
    executable = pins['converter_executable']
    if type(argv) is not list or not argv or len(argv) > 16 or any(type(arg) is not str or len(arg) > 4096 or '\n' in arg for arg in argv):
        raise GateError('SW_PIN')
    # These are trusted reviewed SOURCE pins, never snapshot-provided commands.
    if argv[0] not in {'dune', 'nix', 'devbox', 'opam'}:
        raise GateError('SW_PIN')
    if type(executable) is not str or not executable or Path(executable).is_absolute() or '..' in Path(executable).parts or not executable.endswith(('tree_of_md', 'tree_of_md.exe')):
        raise GateError('SW_PIN')
    return pins


def ci_run(args):
    pins = validate_pins(strict_json(read_bounded(checked_path(args.pins), MAX_MANIFEST)))
    content = checked_path(args.snapshot_repository)
    converter_repo = checked_path(args.converter_repository)
    output = checked_path(args.out_dir)
    if output.exists():
        raise GateError('SW_FRESH')
    for repo, expected in ((content, args.content_rev), (converter_repo, pins['converter_revision'])):
        actual = run_quiet(['git', '-C', str(repo), 'rev-parse', 'HEAD']).decode().strip()
        if actual != expected:
            raise GateError('SW_REV')
    entries = run_quiet(['git', '-C', str(content), 'ls-tree', '-z', '--full-tree', args.content_rev]).split(b'\0')
    inventory = {}
    for entry in filter(None, entries):
        metadata, name = entry.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        if mode != b'100644' or kind != b'blob':
            raise GateError('SW_INVENTORY')
        inventory[name] = oid.decode()
    if set(inventory) != {b'manifest.json', b'public-forest.json'}:
        raise GateError('SW_INVENTORY')
    with tempfile.TemporaryDirectory(prefix='safe-web-ci-', dir=output.parent) as scratch:
        scratch = Path(scratch)
        snapshot = scratch / 'snapshot'
        snapshot.mkdir()
        for name, oid in inventory.items():
            limit = MAX_MANIFEST if name == b'manifest.json' else MAX_FOREST
            size = int(run_quiet(['git', '-C', str(content), 'cat-file', '-s', oid]))
            if size > limit:
                raise GateError('SW_SIZE')
            data = run_quiet(['git', '-C', str(content), 'cat-file', 'blob', oid])
            if len(data) != size or len(data) > limit:
                raise GateError('SW_SIZE')
            (snapshot / name.decode()).write_bytes(data)
        # Validate before compiling source or invoking the converter.
        stage_snapshot(snapshot, scratch / 'validated', args.manifest_sha256)
        run_quiet(pins['converter_build_argv'], cwd=converter_repo)
        converter = checked_path(converter_repo / pins['converter_executable'])
        converter_hash = hashlib.sha256(read_bounded(converter, 64 * 1024 * 1024)).hexdigest()
        return build_snapshot(snapshot, output, args.manifest_sha256, converter, pins['converter_revision'], converter_hash, args.forester, args.home,
                              theme_config=args.theme_config, site_root=args.site_root)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise GateError('SW_ARGS')


def main():
    parser = SafeParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=SafeParser)
    config = commands.add_parser('ci-config')
    config.add_argument('--pins', required=True)
    config.add_argument('--content-rev', required=True)
    config.add_argument('--manifest-sha256', required=True)
    config.add_argument('--github-output', required=True)
    ci = commands.add_parser('ci-run')
    for option in ('pins', 'content-rev', 'manifest-sha256', 'snapshot-repository', 'converter-repository', 'forester', 'home', 'out-dir'):
        ci.add_argument('--' + option, required=True)
    ci.add_argument('--theme-config')
    ci.add_argument('--site-root')
    for name in ('stage', 'build'):
        command = commands.add_parser(name)
        command.add_argument('--snapshot-dir', required=True)
        command.add_argument('--out-dir', required=True)
        command.add_argument('--content-rev', required=True)
        command.add_argument('--manifest-sha256', required=True)
        if name == 'build':
            command.add_argument('--converter', required=True)
            command.add_argument('--converter-rev', required=True)
            command.add_argument('--converter-sha256', required=True)
            command.add_argument('--forester', required=True)
            command.add_argument('--home', required=True)
            command.add_argument('--theme-config')
            command.add_argument('--site-root')
    try:
        args = parser.parse_args()
        revision(args.content_rev)
        if args.command == 'ci-config':
            if not re.fullmatch(r'[0-9a-f]{64}', args.manifest_sha256):
                raise GateError('SW_DIGEST')
            pins = validate_pins(strict_json(read_bounded(checked_path(args.pins), MAX_MANIFEST)))
            with checked_path(args.github_output).open('a') as output:
                output.write('converter_revision=' + pins['converter_revision'] + '\n')
            return 0
        if args.command == 'stage':
            result = stage_snapshot(args.snapshot_dir, args.out_dir, args.manifest_sha256)
        elif args.command == 'ci-run':
            result = ci_run(args)
        else:
            result = build_snapshot(args.snapshot_dir, args.out_dir, args.manifest_sha256, args.converter, args.converter_rev, args.converter_sha256, args.forester, args.home,
                                    theme_config=args.theme_config, site_root=args.site_root)
        print(json.dumps(result, sort_keys=True))
        return 0
    except GateError as exc:
        print(exc.code, file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print('SW_IO', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
