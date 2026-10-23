#!/usr/bin/env python3
"""Public-snapshot consumer. No vault discovery, legacy build or deployment."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

MAX_MANIFEST = 65536
MAX_FOREST = 16 * 1024 * 1024
MAX_STRING = 1024 * 1024
MAX_JPEG = 8 * 1024 * 1024
MAX_JPEGS = 128
MAX_JPEG_TOTAL = 32 * 1024 * 1024


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


def audit_output(output, ids, theme_hashes, media=frozenset()):
    output = checked_path(output)
    routes = {f'{identifier(id)}/index.html' for id in ids}
    images = {f'media/{digest}.jpg': digest for digest in media}
    files, seen, total = 0, set(), 0
    for directory, dirs, names in os.walk(output, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise GateError('SW_PATH')
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
            elif relative in routes:
                if LEAK.search(data):
                    raise GateError('SW_LEAK')
                seen.add(relative)
            elif relative == 'index.html':
                if LEAK.search(data) or not re.search(rb'content="0;url=(?:' + b'|'.join(re.escape(id.encode()) for id in sorted(ids)) + rb')/"', data):
                    raise GateError('SW_OUTPUT')
            elif relative == 'forest.json':
                if LEAK.search(data):
                    raise GateError('SW_LEAK')
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
    required = routes | {'index.html', 'forest.json'} | set(theme_hashes) | set(images)
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


def render_native(trees, output, binary, ids, home, media=None):
    trees, output = checked_path(trees), checked_path(output)
    if output.exists():
        raise GateError('SW_FRESH')
    if trees == output or trees in output.parents or output in trees.parents or home not in ids:
        raise GateError('SW_PATH')
    binary = Path(binary).resolve(strict=True)
    package = Path(run_quiet(['nix', 'eval', '--offline', '--impure', '--raw', '--option', 'allow-import-from-derivation', 'true', FORESTER_FLAKE + '.outPath']).decode().strip())
    if binary != package / 'bin' / 'forester' or run_quiet([str(binary), '--version']).strip() != b'6.0~dev':
        raise GateError('SW_PIN')
    theme = package / 'share' / 'forester' / 'themes' / 'default'
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
        for path in theme.rglob('*'):
            if path.is_dir():
                continue
            relative = path.relative_to(theme)
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
        counts = audit_output(html, ids, theme_hashes, digests)
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


def build_snapshot(snapshot, output, digest, converter, converter_rev, converter_hash, forester, home):
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
        converter = checked_path(converter)
        if not re.fullmatch(r'[0-9a-f]{64}', converter_hash) or hashlib.sha256(read_bounded(converter, 64 * 1024 * 1024)).hexdigest() != converter_hash:
            raise GateError('SW_PIN')
        run_quiet([str(converter), '--public-forest', str(scratch / 'snapshot' / 'public-forest.json'), '--out-dir', str(scratch / 'trees')])
        roots = {tree['id'] + '.tree' for tree in forest['trees']}
        if {path.name for path in (scratch / 'trees').iterdir()} != roots:
            raise GateError('SW_TREES')
        media = scratch / 'snapshot' / 'media'
        return render_native(scratch / 'trees', output, forester, ids, home, media if media.exists() else None)


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
        return build_snapshot(snapshot, output, args.manifest_sha256, converter, pins['converter_revision'], converter_hash, args.forester, args.home)


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
            result = build_snapshot(args.snapshot_dir, args.out_dir, args.manifest_sha256, args.converter, args.converter_rev, args.converter_sha256, args.forester, args.home)
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
