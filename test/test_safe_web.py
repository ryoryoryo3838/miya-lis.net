"""Synthetic fixtures only; never discover or open a vault."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'safe-web.py'
TMP = Path(os.environ['TMPDIR']) if os.environ.get('TMPDIR') else None


def load_module():
    if not SCRIPT.exists():
        return None
    spec = importlib.util.spec_from_file_location('safe_web', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tree(id='PUBLICA', text='Approved synthetic text.'):
    return dict(id=id, title='Public fixture', authors=[], dates=[], contributors=[],
                properties={}, citationAuthors=[], content=[dict(kind='markdown', text=text)])


def fixture(path, forest=None, *, ensure_ascii=False):
    path.mkdir()
    data = json.dumps(forest or dict(schema='forester-public-v2', trees=[tree()], assets=[]),
                      ensure_ascii=ensure_ascii).encode('utf-8')
    (path / 'public-forest.json').write_bytes(data)
    manifest = json.dumps(dict(schema='forester-public-snapshot-v1', files={
        'public-forest.json': hashlib.sha256(data).hexdigest()})).encode()
    (path / 'manifest.json').write_bytes(manifest)
    return hashlib.sha256(manifest).hexdigest()


def web_fixture(output):
    output.mkdir()
    (output / 'PUBLICA').mkdir()
    (output / 'PUBLICA/index.html').write_text('<!doctype html><title>Public fixture</title><p>approved</p>')
    (output / 'index.html').write_text('<!doctype html><meta http-equiv="refresh" content="0;url=PUBLICA/">')
    (output / 'forest.json').write_text(json.dumps([dict(title='Public fixture', uri='PUBLICA',
                                                       taxon=None, tags=[], route='/PUBLICA', metas={})]))


def pin_fixture(safe, *, ready=False):
    pins: dict = dict(schema='safe-web-pins-v1', content_repository='ryoryoryo3838/miya-lis-public',
                converter_repository='ryoryoryo3838/tree-md', converter_revision=None,
                converter_build_argv=None, converter_executable=None,
                forester_revision=safe.FORESTER_REV, forester_flake=safe.FORESTER_FLAKE)
    if ready:
        # Test-only syntax placeholders, not real revision/build provenance.
        pins.update(converter_revision='a' * 40,
                    converter_build_argv=['dune', 'build', 'bin/test-only/tree_of_md.exe'],
                    converter_executable='_build/default/bin/test-only/tree_of_md.exe')
    return pins


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.safe = load_module()
        self.assertIsNotNone(self.safe, 'safe snapshot consumer must exist')
        self.temp = tempfile.TemporaryDirectory(prefix='safe-web-test-', dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_literal_code_survives_snapshot_staging(self):
        # The real producer emits these ordinary code examples unchanged.
        text = ('Code stays literal: `![[missing-code-target]]` and '
                '`{ref:[[missing-code-citation]]}`.\n\n'
                '```markdown\n## Example heading, not a tree\n'
                '![[missing-code-target]] %%ht%%\n'
                '<img src="private.png"> \\{\\import{secret}}\n'
                '[file](../../private.md)\n^not-a-declaration\n```')
        forest = dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[])
        snapshot, stage = self.base / 'snapshot', self.base / 'stage'
        digest = fixture(snapshot, forest)
        self.assertEqual(self.safe.stage_snapshot(snapshot, stage, digest),
                         {'trees': 1, 'files': 1})
        self.assertEqual((stage / 'public-forest.json').read_bytes(),
                         (snapshot / 'public-forest.json').read_bytes())

    def test_indented_code_only_starts_at_a_block_boundary(self):
        payload = '<img src="private.png"> ![[missing]] [file](private.md) \\{raw}\n'
        for indent in ['    ', '\t', ' \t']:
            with self.subTest(indent=repr(indent)):
                text = 'Intro.\n\n' + indent + payload + '\n' + indent + '^example\n\nAfter.'
                forest = dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[])
                snapshot = self.base / ('snapshot-' + str(len(list(self.base.iterdir()))))
                stage = snapshot.with_name(snapshot.name + '-stage')
                digest = fixture(snapshot, forest)
                self.assertEqual(self.safe.stage_snapshot(snapshot, stage, digest)['trees'], 1)
        # Four spaces do not interrupt an already open paragraph.
        forest = dict(schema='forester-public-v2', trees=[tree(text='Intro.\n    ' + payload)], assets=[])
        snapshot, stage = self.base / 'unsafe', self.base / 'unsafe-stage'
        digest = fixture(snapshot, forest)
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.stage_snapshot(snapshot, stage, digest)
        self.assertEqual(caught.exception.code, 'SW_MARKDOWN')
        self.assertFalse(stage.exists())

    def test_literal_math_survives_snapshot_staging(self):
        text = 'Inline $x < y$ and $\\{x\\}$ are TeX.\n\n$$\nx < y\n\\frac{1}{2}\n$$'
        forest = dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[])
        snapshot, stage = self.base / 'snapshot', self.base / 'stage'
        digest = fixture(snapshot, forest)
        self.assertEqual(self.safe.stage_snapshot(snapshot, stage, digest), {'trees': 1, 'files': 1})
        self.assertEqual((stage / 'public-forest.json').read_bytes(), (snapshot / 'public-forest.json').read_bytes())

    def test_code_masks_do_not_hide_unparsed_container_html(self):
        for number, text in enumerate(['- item\n    <img src="private.png">',
                                       '- item\n\n    <img src="private.png">',
                                       '> quoted\n    <img src="private.png">']):
            with self.subTest(container=number):
                snapshot, stage = self.base / f'snapshot-{number}', self.base / f'stage-{number}'
                digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[]))
                with self.assertRaises(self.safe.GateError) as caught:
                    self.safe.stage_snapshot(snapshot, stage, digest)
                self.assertEqual(caught.exception.code, 'SW_MARKDOWN')
                self.assertFalse(stage.exists())

    def test_literal_masks_preserve_offsets_lf_crlf_and_blank_lines(self):
        original = '日本語 ``<example> `literal` ``\n\n   ~~~md\n# Example\n   \n![[missing]]\n   ~~~~\n\n$x < y$\n'
        for number, newline in enumerate(['\n', '\r\n']):
            text = original.replace('\n', newline)
            with self.subTest(newline=repr(newline)):
                mask = self.safe.markdown_guard_text(text)
                self.assertEqual(len(mask), len(text))
                self.assertEqual([i for i, c in enumerate(mask) if c in '\r\n'],
                                 [i for i, c in enumerate(text) if c in '\r\n'])
                self.assertEqual([not line.strip(' \t') for line in mask.splitlines()],
                                 [not line.strip(' \t') for line in text.splitlines()])
                snapshot, stage = self.base / f'snapshot-{number}', self.base / f'stage-{number}'
                digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[]))
                self.assertEqual(self.safe.stage_snapshot(snapshot, stage, digest)['trees'], 1)
                self.assertEqual((stage / 'public-forest.json').read_bytes(), (snapshot / 'public-forest.json').read_bytes())
        with self.assertRaises(self.safe.GateError):
            self.safe.validate_forest(dict(schema='forester-public-v2', trees=[tree(text='`code`\r<img>')], assets=[]))

    def test_inline_code_uses_exact_run_lengths_and_soft_breaks(self):
        for number, text in enumerate(['```<img>```', '``one ` tick <img>``',
                                       'Text `<img>\n![[missing]]` end.',
                                       '`$x < y$` outside.']):
            with self.subTest(example=number):
                snapshot, stage = self.base / f'snapshot-{number}', self.base / f'stage-{number}'
                digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[]))
                self.assertEqual(self.safe.stage_snapshot(snapshot, stage, digest)['trees'], 1)

    def test_raw_versus_protected_payloads_fail_closed_before_write(self):
        payloads = ['<img src="private.png">', r'\{\import{secret}}', '![[MISSING]]',
                    '[file](../../private.md)', '## Unaccounted ^CLAIM', '^CLAIM',
                    '[ref]: private.md']
        serial = 0
        for payload in payloads:
            for text, allowed in [(payload, False), ('`' + payload + '`', True),
                                  ('~~~md\n' + payload + '\n~~~', True),
                                  ('`safe`\n\n' + payload, False),
                                  ('```md\nexample\n```\n\n' + payload, False)]:
                with self.subTest(case=serial, allowed=allowed):
                    snapshot, stage = self.base / f'snapshot-{serial}', self.base / f'stage-{serial}'
                    digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[]))
                    if allowed:
                        self.assertEqual(self.safe.stage_snapshot(snapshot, stage, digest)['trees'], 1)
                    else:
                        with self.assertRaises(self.safe.GateError):
                            self.safe.stage_snapshot(snapshot, stage, digest)
                        self.assertFalse(stage.exists())
                serial += 1

    def test_malformed_literals_cannot_mask_other_blocks_or_chunks(self):
        cases = ['`<img>``', r'\`<img>`', '```md\n<img>\n~~~',
                 '~~~~md\n<img>\n~~~', '```bad`info\n<img>\n```',
                 '`start\n\n<img>`', '`start\n* * *\n<img>`',
                 '`start\n## Heading\n<img>`', '`start\n> <img>`',
                 '$x < y', '$ x < y$', r'$x < y\$', '$x\n\n<img>$',
                 '$$x < y$', '$$\nx < y\n$$\n<img>', '$`x$ <img> `',
                 r'\$x < y$', '`safe` [[MISSING|target]]']
        for number, text in enumerate(cases):
            with self.subTest(example=number):
                snapshot, stage = self.base / f'snapshot-{number}', self.base / f'stage-{number}'
                digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[tree(text=text)], assets=[]))
                with self.assertRaises(self.safe.GateError):
                    self.safe.stage_snapshot(snapshot, stage, digest)
                self.assertFalse(stage.exists())
        separate = tree()
        separate['content'] = [dict(kind='markdown', text='`<img>'), dict(kind='markdown', text='`')]
        with self.assertRaises(self.safe.GateError):
            self.safe.validate_forest(dict(schema='forester-public-v2', trees=[separate], assets=[]))

    def test_unicode_separators_do_not_create_markdown_block_boundaries(self):
        for separator in ['\u2028', '\u2029', '\x85']:
            with self.subTest(separator=repr(separator)):
                text = 'Text `x' + separator + '<img>` end.'
                self.assertEqual(self.safe.validate_forest(dict(schema='forester-public-v2',
                                 trees=[tree(text=text)], assets=[])), 1)

    def test_string_limits_use_utf8_bytes_before_staging(self):
        japanese = '日' * 400000
        self.assertEqual(len(japanese.encode('utf-8')), 1200000)
        for field in ['markdown', 'title', 'author']:
            for number, value in enumerate([japanese, 'a' * (1024 * 1024 + 1)]):
                with self.subTest(field=field, example=number):
                    node = tree(text=value if field == 'markdown' else 'Approved.')
                    if field == 'title':
                        node['title'] = value
                    if field == 'author':
                        node['authors'] = [dict(kind='literal', value=value)]
                    snapshot = self.base / f'{field}-{number}'
                    stage = snapshot.with_name(snapshot.name + '-stage')
                    digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[node], assets=[]))
                    original = (snapshot / 'public-forest.json').read_bytes()
                    with self.assertRaises(self.safe.GateError) as caught:
                        self.safe.stage_snapshot(snapshot, stage, digest)
                    self.assertEqual(caught.exception.code, 'SW_SCHEMA')
                    self.assertFalse(stage.exists())
                    self.assertEqual((snapshot / 'public-forest.json').read_bytes(), original)

    def test_utf8_string_byte_boundary_preserves_exact_input(self):
        limit = 1024 * 1024
        examples = ['a' * limit, '日' * (limit // 3) + 'a' * (limit % 3),
                    '😀' * (limit // 4), '\ufeff日本語 e\u0301\r\n']
        for number, value in enumerate(examples):
            with self.subTest(example=number):
                self.assertLessEqual(len(value.encode('utf-8')), limit)
                self.assertEqual(self.safe.literal(value, markdown=True), value)
                snapshot, stage = self.base / f'snapshot-{number}', self.base / f'stage-{number}'
                digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[tree(text=value)], assets=[]))
                original = (snapshot / 'public-forest.json').read_bytes()
                self.assertEqual(self.safe.stage_snapshot(snapshot, stage, digest), {'trees': 1, 'files': 1})
                self.assertEqual((stage / 'public-forest.json').read_bytes(), original)

    def test_escaped_non_scalar_strings_fail_before_staging(self):
        for field in ['markdown', 'title', 'author']:
            for number, value in enumerate(['\ud800', '\udfff', 'safe\x00', 'safe\x01']):
                with self.subTest(field=field, example=number):
                    node = tree(text=value if field == 'markdown' else 'Approved.')
                    if field == 'title':
                        node['title'] = value
                    if field == 'author':
                        node['authors'] = [dict(kind='literal', value=value)]
                    snapshot = self.base / f'{field}-{number}'
                    stage = snapshot.with_name(snapshot.name + '-stage')
                    digest = fixture(snapshot, dict(schema='forester-public-v2', trees=[node], assets=[]),
                                     ensure_ascii=True)
                    with self.assertRaises(self.safe.GateError) as caught:
                        self.safe.stage_snapshot(snapshot, stage, digest)
                    self.assertEqual(caught.exception.code, 'SW_SCHEMA')
                    self.assertFalse(stage.exists())

    def test_digest_checked_before_fresh_staging(self):
        snapshot = self.base / 'snapshot'
        digest = fixture(snapshot)
        stage = self.base / 'stage'
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.stage_snapshot(snapshot, stage, '0' * 64)
        self.assertEqual(caught.exception.code, 'SW_DIGEST')
        self.assertFalse(stage.exists())
        counts = self.safe.stage_snapshot(snapshot, stage, digest)
        self.assertEqual(counts, {'trees': 1, 'files': 1})
        self.assertEqual((stage / 'public-forest.json').read_bytes(), (snapshot / 'public-forest.json').read_bytes())
        self.assertEqual({p.name for p in stage.iterdir()}, {'public-forest.json'})

    def test_snapshot_namespace_is_allowlisted_and_stage_is_fresh(self):
        snapshot = self.base / 'snapshot'
        digest = fixture(snapshot)
        stage = self.base / 'stage'
        (snapshot / 'unapproved.md').write_text('SYNTHETIC_PRIVATE_CANARY')
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.stage_snapshot(snapshot, stage, digest)
        self.assertEqual(caught.exception.code, 'SW_INVENTORY')
        self.assertFalse(stage.exists())
        (snapshot / 'unapproved.md').unlink()
        original = (snapshot / 'public-forest.json').read_bytes()
        (snapshot / 'public-forest.json').unlink()
        external = self.base / 'outside.json'
        external.write_bytes(original)
        (snapshot / 'public-forest.json').symlink_to(external)
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.stage_snapshot(snapshot, stage, digest)
        self.assertEqual(caught.exception.code, 'SW_PATH')
        self.assertFalse(stage.exists())
        (snapshot / 'public-forest.json').unlink()
        (snapshot / 'public-forest.json').write_bytes(original)
        for unsafe in [snapshot / 'stage', self.base / 'missing' / '..' / 'stage']:
            with self.subTest(kind='overlap-or-traversal'):
                with self.assertRaises(self.safe.GateError):
                    self.safe.stage_snapshot(snapshot, unsafe, digest)
        link = self.base / 'link'
        link.symlink_to(snapshot, target_is_directory=True)
        with self.assertRaises(self.safe.GateError):
            self.safe.stage_snapshot(link, stage, digest)
        link.unlink()
        link.symlink_to(self.base / 'missing', target_is_directory=True)
        with self.assertRaises(self.safe.GateError):
            self.safe.stage_snapshot(snapshot, link / 'stage', digest)
        stage.mkdir()
        (stage / 'revoked.html').write_text('SYNTHETIC_REVOKED_CANARY')
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.stage_snapshot(snapshot, stage, digest)
        self.assertEqual(caught.exception.code, 'SW_FRESH')
        self.assertEqual((stage / 'revoked.html').read_text(), 'SYNTHETIC_REVOKED_CANARY')

    def test_untrusted_schema_and_graph_fail_before_any_write(self):
        cases = []
        def add(name, mutate):
            forest = dict(schema='forester-public-v2', trees=[tree()], assets=[])
            mutate(forest)
            cases.append((name, forest))
        add('source-metadata', lambda f: f['trees'][0].update(sourcePath='SYNTHETIC_PRIVATE_CANARY'))
        add('root-unknown', lambda f: f.update(run='sh attacker'))
        add('traversal-id', lambda f: f['trees'][0].update(id='../PRIVATE'))
        add('unicode-id', lambda f: f['trees'][0].update(id='ＰＵＢＬＩＣ'))
        add('case-collision', lambda f: f['trees'].append(tree('publica')))
        add('assets', lambda f: f['assets'].append('private.png'))
        add('invalid-date', lambda f: f['trees'][0]['dates'].append('2026-02-30'))
        add('missing-target', lambda f: f['trees'][0]['content'].append(dict(kind='transclude', id='MISSING', header=True, toc=True)))
        add('cycle', lambda f: f['trees'][0]['content'].append(dict(kind='transclude', id='PUBLICA', header=True, toc=True)))
        add('bad-flag', lambda f: f['trees'][0]['content'].append(dict(kind='transclude', id='PUBLICA', header=1, toc=True)))
        add('unknown-node', lambda f: f['trees'][0]['content'].append(dict(kind='raw', text='private')))
        add('unsafe-html', lambda f: f['trees'][0]['content'].append(dict(kind='markdown', text='<img src="private.png">')))
        add('unsafe-local-link', lambda f: f['trees'][0]['content'].append(dict(kind='markdown', text='[label](../../private.md)')))
        add('raw-forester', lambda f: f['trees'][0]['content'].append(dict(kind='markdown', text='\\\\{\\\\import{secret}}')))
        for number, (name, forest) in enumerate(cases):
            with self.subTest(gate=name):
                snapshot = self.base / f'snapshot-{number}'
                digest = fixture(snapshot, forest)
                stage = self.base / f'stage-{number}'
                with self.assertRaises(self.safe.GateError):
                    self.safe.stage_snapshot(snapshot, stage, digest)
                self.assertFalse(stage.exists())

    def test_manifest_is_exact_json_and_files_are_bounded(self):
        mutations = [
            lambda p: (p / 'manifest.json').write_text('{"schema":"forester-public-snapshot-v1","files":{"../public-forest.json":"' + 'a' * 64 + '"}}'),
            lambda p: (p / 'manifest.json').write_text('{"schema":"forester-public-snapshot-v1","files":{"public-forest.json":"' + hashlib.sha256((p / 'public-forest.json').read_bytes()).hexdigest() + '"},"run":"evil"}'),
            lambda p: (p / 'public-forest.json').write_text('{"schema":"forester-public-v2","schema":"forester-public-v2","trees":[],"assets":[]}'),
            lambda p: (p / 'manifest.json').write_bytes(b' ' * (self.safe.MAX_MANIFEST + 1)),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(gate=number):
                snapshot = self.base / f'bad-{number}'
                fixture(snapshot)
                mutate(snapshot)
                if number == 2:
                    data = (snapshot / 'public-forest.json').read_bytes()
                    (snapshot / 'manifest.json').write_text(json.dumps(dict(schema='forester-public-snapshot-v1', files={'public-forest.json': hashlib.sha256(data).hexdigest()})))
                digest = hashlib.sha256((snapshot / 'manifest.json').read_bytes()).hexdigest()
                with self.assertRaises(self.safe.GateError):
                    self.safe.stage_snapshot(snapshot, self.base / f'out-{number}', digest)
                self.assertFalse((self.base / f'out-{number}').exists())
        snapshot = self.base / 'tampered'
        digest = fixture(snapshot)
        (snapshot / 'public-forest.json').write_text('SYNTHETIC_TAMPER')
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.stage_snapshot(snapshot, self.base / 'tampered-out', digest)
        self.assertEqual(caught.exception.code, 'SW_FILE_DIGEST')

    def test_artifact_gate_rejects_source_secrets_and_extra_routes(self):
        self.assertTrue(hasattr(self.safe, 'audit_output'), 'HTML artifact audit must exist')
        output = self.base / 'html'
        web_fixture(output)
        page = output / 'PUBLICA' / 'index.html'
        self.assertEqual(self.safe.audit_output(output, {'PUBLICA'}, {}), {'files': 3, 'routes': 1})
        for text in ['<p>/home/example/private.md</p>', '{"sourcePath":"secret.md"}', '<p>github_pat_SYNTHETIC_CANARY</p>']:
            page.write_text(text)
            with self.subTest(gate='leak'):
                with self.assertRaises(self.safe.GateError) as caught:
                    self.safe.audit_output(output, {'PUBLICA'}, {})
                self.assertEqual(caught.exception.code, 'SW_LEAK')
        page.write_text('<title>Public fixture</title>')
        for relative in ['private.json', 'PRIVATE/index.html', 'PUBLICA/source.md', '.git/config']:
            extra = output / relative
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text('SYNTHETIC_PRIVATE_CANARY')
            with self.subTest(gate=relative):
                with self.assertRaises(self.safe.GateError):
                    self.safe.audit_output(output, {'PUBLICA'}, {})
            extra.unlink()
            if extra.parent != output and not list(extra.parent.iterdir()):
                extra.parent.rmdir()
        theme_file = output / 'style.css'
        theme_file.write_text('body { color: black; }')
        hashes = {'style.css': hashlib.sha256(theme_file.read_bytes()).hexdigest()}
        self.safe.audit_output(output, {'PUBLICA'}, hashes)
        theme_file.write_text('body { color: red; }')
        with self.assertRaises(self.safe.GateError):
            self.safe.audit_output(output, {'PUBLICA'}, hashes)

    def test_artifact_gate_requires_root_search_routes_and_pinned_assets(self):
        output = self.base / 'html'
        web_fixture(output)
        (output / 'style.css').write_text('body { color: black; }')
        hashes = {'style.css': hashlib.sha256((output / 'style.css').read_bytes()).hexdigest()}
        self.assertEqual(self.safe.audit_output(output, {'PUBLICA'}, hashes), {'files': 4, 'routes': 1})
        for relative in ['index.html', 'forest.json', 'PUBLICA/index.html', 'style.css']:
            path = output / relative
            original = path.read_bytes()
            path.unlink()
            try:
                with self.subTest(missing=relative):
                    with self.assertRaises(self.safe.GateError) as caught:
                        self.safe.audit_output(output, {'PUBLICA'}, hashes)
                    self.assertEqual(caught.exception.code, 'SW_OUTPUT')
            finally:
                path.write_bytes(original)

    def test_pinned_native_render_builds_routes_in_fresh_isolation(self):
        self.assertTrue(hasattr(self.safe, 'render_native'), 'isolated native renderer must exist')
        if not os.environ.get('SW_NATIVE_FORESTER'):
            self.skipTest('explicit SW_NATIVE_FORESTER required for native integration')
        binary = Path(os.environ['SW_NATIVE_FORESTER'])
        if not binary.exists():
            self.skipTest('fixed Forester binary unavailable; gate tests remain active')
        trees = self.base / 'trees'
        trees.mkdir()
        (trees / 'PUBLICA.tree').write_text(r'\title{Synthetic public parent}\p{Approved synthetic body.}\subtree[NESTED]{\title{Synthetic child}\p{Approved child.}}' + '\n')
        output = self.base / 'public-html'
        counts = self.safe.render_native(trees, output, binary, {'PUBLICA', 'NESTED'}, 'PUBLICA')
        self.assertEqual(counts['routes'], 2)
        self.assertIn('Approved synthetic body.', (output / 'PUBLICA' / 'index.html').read_text())
        self.assertIn('Approved child.', (output / 'NESTED' / 'index.html').read_text())
        self.assertFalse(any(p.suffix in {'.tree', '.md', '.xml', '.sqlite'} for p in output.rglob('*')))
        # Every required omission is checked on a copy of genuine pinned HTML.
        hashes = {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.rglob('*') if p.is_file() and p.suffix != '.html' and p.name != 'forest.json'
        }
        original_hashes = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in output.rglob('*') if p.is_file()}
        for number, relative in enumerate(sorted(original_hashes)):
            copy = self.base / f'without-{number}'
            shutil.copytree(output, copy)
            (copy / relative).unlink()
            with self.subTest(missing_native=relative):
                with self.assertRaises(self.safe.GateError) as caught:
                    self.safe.audit_output(copy, {'PUBLICA', 'NESTED'}, hashes)
                self.assertEqual(caught.exception.code, 'SW_OUTPUT')
            shutil.rmtree(copy)
        self.assertEqual(original_hashes, {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in output.rglob('*') if p.is_file()})
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.render_native(trees, output, binary, {'PUBLICA', 'NESTED'}, 'PUBLICA')
        self.assertEqual(caught.exception.code, 'SW_FRESH')

    def test_cli_errors_are_codes_only_and_revision_is_immutable(self):
        import subprocess
        snapshot = self.base / 'snapshot'
        digest = fixture(snapshot)
        output = self.base / 'stage'
        def cli(revision, expected):
            return subprocess.run(['python3', str(SCRIPT), 'stage', '--snapshot-dir', str(snapshot),
                                   '--out-dir', str(output), '--content-rev', revision,
                                   '--manifest-sha256', expected], capture_output=True, text=True)
        result = cli('main', digest)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), 'SW_REV')
        self.assertFalse(output.exists())
        result = cli('a' * 40, '0' * 64)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), 'SW_DIGEST')
        self.assertNotIn(str(snapshot), result.stderr + result.stdout)
        result = cli('a' * 40, digest)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {'trees': 1, 'files': 1})
        self.assertEqual(result.stderr, '')

    def test_build_never_invokes_converter_before_snapshot_gate(self):
        self.assertTrue(hasattr(self.safe, 'build_snapshot'), 'safe adapter build must exist')
        snapshot = self.base / 'snapshot'
        digest = fixture(snapshot)
        marker = self.base / 'converter-called'
        converter = self.base / 'converter'
        converter.write_text('#!/bin/sh\nprintf called > "' + str(marker) + '"\nprintf SYNTHETIC_PRIVATE_CANARY >&2\nexit 1\n')
        converter.chmod(0o700)
        converter_hash = hashlib.sha256(converter.read_bytes()).hexdigest()
        output = self.base / 'html'
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.build_snapshot(snapshot, output, '0' * 64, converter, 'a' * 40, converter_hash, Path('/not-used'), 'PUBLICA')
        self.assertEqual(caught.exception.code, 'SW_DIGEST')
        self.assertFalse(marker.exists())
        self.assertFalse(output.exists())
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.build_snapshot(snapshot, output, digest, converter, 'main', converter_hash, Path('/not-used'), 'PUBLICA')
        self.assertEqual(caught.exception.code, 'SW_REV')
        self.assertFalse(marker.exists())
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.build_snapshot(snapshot, output, digest, converter, 'a' * 40, converter_hash, Path('/not-used'), 'PUBLICA')
        self.assertEqual(caught.exception.code, 'SW_TOOL')
        self.assertTrue(marker.exists())
        self.assertNotIn('CANARY', str(caught.exception))
        self.assertFalse(output.exists())

    def test_ci_blocks_unreviewed_converter_pins_before_content_fetch(self):
        self.assertTrue(hasattr(self.safe, 'validate_pins'), 'reviewed CI pin gate must exist')
        pins = pin_fixture(self.safe)
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.validate_pins(pins)
        self.assertEqual(caught.exception.code, 'SW_PIN')
        pins = pin_fixture(self.safe, ready=True)
        self.safe.validate_pins(pins)
        pins['converter_revision'] = 'main'
        with self.assertRaises(self.safe.GateError):
            self.safe.validate_pins(pins)
        pins['converter_revision'] = 'a' * 40
        pins['forester_revision'] = 'main'
        with self.assertRaises(self.safe.GateError):
            self.safe.validate_pins(pins)

    def test_ci_preflight_is_blocked_with_synthetic_null_pins(self):
        import subprocess
        pins = self.base / 'null-pins.json'
        pins.write_text(json.dumps(pin_fixture(self.safe)))
        github_output = self.base / 'github-output'
        result = subprocess.run(['python3', str(SCRIPT), 'ci-config', '--pins', str(pins),
                                 '--content-rev', 'a' * 40, '--manifest-sha256', 'b' * 64,
                                 '--github-output', str(github_output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), 'SW_PIN')
        self.assertEqual(result.stdout, '')
        self.assertFalse(github_output.exists())

    def test_ci_preflight_accepts_synthetic_ready_pins(self):
        import subprocess
        values = pin_fixture(self.safe, ready=True)
        self.assertEqual(self.safe.validate_pins(values), values)
        pins = self.base / 'ready-pins.json'
        pins.write_text(json.dumps(values))
        github_output = self.base / 'github-output'
        result = subprocess.run(['python3', str(SCRIPT), 'ci-config', '--pins', str(pins),
                                 '--content-rev', 'a' * 40, '--manifest-sha256', 'b' * 64,
                                 '--github-output', str(github_output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, '')
        self.assertEqual(github_output.read_text(), 'converter_revision=' + values['converter_revision'] + '\n')

    def test_ci_run_is_blocked_before_checkouts_or_outputs_are_read(self):
        import subprocess
        pins = self.base / 'null-pins.json'
        pins.write_text(json.dumps(pin_fixture(self.safe)))
        # No content/output attributes exist: touching any before pins fails.
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.ci_run(SimpleNamespace(pins=pins))
        self.assertEqual(caught.exception.code, 'SW_PIN')
        output = self.base / 'html'
        result = subprocess.run(['python3', str(SCRIPT), 'ci-run', '--pins', str(pins),
                                 '--content-rev', 'a' * 40, '--manifest-sha256', 'b' * 64,
                                 '--snapshot-repository', str(self.base / 'absent-content'),
                                 '--converter-repository', str(self.base / 'absent-converter'),
                                 '--forester', str(self.base / 'absent-forester'), '--home', 'PUBLICA',
                                 '--theme-config', str(self.base / 'absent-theme'),
                                 '--site-root', str(self.base / 'absent-site'),
                                 '--out-dir', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), 'SW_PIN')
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
