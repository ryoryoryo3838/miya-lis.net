"""Explicit synthetic trusted site code; never a snapshot theme or fake renderer."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from test_safe_web import TMP, load_module, tree


def trusted_fixture(base):
    site = base / 'site-code'
    files = {
        'theme/styles/fonts.css': b'/* synthetic self-hosted typography */',
        'theme/styles/miya.css': b'.miya-native { color: black; }',
        'theme/layout/home.html': b'<section id="site-hero"><h1>Synthetic home</h1></section>',
        'theme/layout/navigation.html': b'<nav id="site-navigation"><ul>{{MENU}}</ul></nav>',
        'theme/layout/not-found.html': b'<section id="site-missing"><h1>Synthetic missing</h1></section>',
        'theme/client/dune': b'(executable (name hero) (modes js) (libraries js_of_ocaml))\n',
        'theme/client/hero.ml': b'let () = ()\n',
        # This loader unit fixture is not compiler/native/browser output evidence.
        '_build/default/theme/client/hero.bc.js': b'/* synthetic loader fixture, not built JS */',
    }
    for relative, data in files.items():
        path = site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (site / 'theme/assets').mkdir()
    config = dict(schema='safe-web-theme-v1',
                  styles=[dict(source=f'theme/styles/{name}.css', output=f'theme/styles/{name}.css')
                          for name in ['fonts', 'miya']],
                  client=dict(source='_build/default/theme/client/hero.bc.js', output='theme/client/hero.js'),
                  layout=dict(home='theme/layout/home.html', navigation='theme/layout/navigation.html',
                              not_found='theme/layout/not-found.html'),
                  assets=[], notices=[])
    path = site / 'config/theme.json'
    path.parent.mkdir()
    path.write_text(json.dumps(config))
    return site, path, config, files


def reviewed_ui_fixture(base):
    root = Path(__file__).resolve().parents[1]
    site, path, _, _ = trusted_fixture(base)
    config = json.loads((root / 'config/theme.json').read_bytes())
    relatives = [entry['source'] for entry in config['styles'] + config['assets']]
    relatives += list(config['layout'].values()) + config['notices']
    relatives += ['theme/client/dune', 'theme/client/hero.ml']
    for relative in relatives:
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / relative).read_bytes())
    # The compiled-client placeholder remains explicitly synthetic loader input.
    path.write_bytes((root / 'config/theme.json').read_bytes())
    return site, path, config


class TrustedThemeTests(unittest.TestCase):
    def setUp(self):
        self.safe = load_module()
        self.temp = tempfile.TemporaryDirectory(prefix='native-theme-test-', dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def require_loader(self):
        self.assertTrue(callable(getattr(self.safe, 'load_trusted_theme', None)),
                        'trusted theme loader must enforce source and output inventory')

    def test_trusted_theme_loads_exact_owned_assets_with_source_hashes(self):
        self.require_loader()
        site, config_path, _, files = trusted_fixture(self.base)
        theme = self.safe.load_trusted_theme(config_path, site)
        self.assertEqual(set(theme['assets']), {'theme/styles/fonts.css', 'theme/styles/miya.css',
                                             'theme/client/hero.js'})
        for output, (data, digest) in theme['assets'].items():
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, output)
        for source, data in files.items():
            self.assertEqual(theme['sources'][source], hashlib.sha256(data).hexdigest(), source)
        self.assertEqual(theme['sources']['config/theme.json'],
                         hashlib.sha256(config_path.read_bytes()).hexdigest())
        self.assertEqual(theme['navigation'], '<nav id="site-navigation"><ul>{{MENU}}</ul></nav>')
        self.assertEqual(theme['home'], '<section id="site-hero"><h1>Synthetic home</h1></section>')
    def test_theme_rejects_unknown_inventory_and_unsafe_mapping(self):
        self.require_loader()
        cases = [
            ('native-collision', lambda c, s: c['styles'][0].update(output='style.css')),
            ('duplicate', lambda c, s: c['assets'].append(dict(c['styles'][0]))),
            ('outside-source', lambda c, s: c['styles'][0].update(source='config/theme.json')),
            ('absolute-source', lambda c, s: c['styles'][0].update(source=str(s / 'theme/styles/fonts.css'))),
            ('dot-source', lambda c, s: c['styles'][0].update(source='theme/styles/./fonts.css')),
            ('output-traversal', lambda c, s: c['styles'][0].update(output='theme/../style.css')),
            ('non-web-asset', lambda c, s: c['assets'].append(dict(source='theme/assets/private.md', output='theme/assets/private.md'))),
            ('extra-file', lambda c, s: (s / 'theme/assets/unlisted.png').write_bytes(b'synthetic')),
            ('extra-dir', lambda c, s: (s / 'theme/assets/unknown').mkdir()),
            ('symlink-dir', lambda c, s: (s / 'theme/assets/link').symlink_to(s / 'theme/styles', target_is_directory=True)),
            ('source-field', lambda c, s: (s / 'theme/styles/miya.css').write_bytes(b'/* sourcePath: SYNTHETIC_PRIVATE_CANARY */')),
        ]
        for number, (name, mutate) in enumerate(cases):
            with self.subTest(gate=name):
                case = self.base / str(number)
                case.mkdir()
                site, path, config, _ = trusted_fixture(case)
                if name == 'non-web-asset':
                    (site / 'theme/assets/private.md').write_bytes(b'synthetic not a web asset')
                mutate(config, site)
                path.write_text(json.dumps(config))
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)

    def test_theme_rechecks_sources_and_inventory_after_loading(self):
        self.require_loader()
        self.assertTrue(callable(getattr(self.safe, 'verify_trusted_theme', None)),
                        'source and namespace changes must abort publication')
        site, path, _, _ = trusted_fixture(self.base)
        theme = self.safe.load_trusted_theme(path, site)
        self.safe.verify_trusted_theme(theme)
        (site / 'theme/styles/miya.css').write_bytes(b'/* changed after loading */')
        with self.assertRaises(self.safe.GateError):
            self.safe.verify_trusted_theme(theme)
    def test_declared_source_only_notices_keep_symlink_bounds_and_unlisted_inventory_gates(self):
        site, path, config, _ = trusted_fixture(self.base)
        integration = site / 'theme/notices/INTEGRATION.md'
        integration.parent.mkdir()
        integration.write_bytes(b'# Synthetic trusted source-only notice\n')
        config['notices'] = ['theme/notices/INTEGRATION.md']
        path.write_text(json.dumps(config))
        theme = self.safe.load_trusted_theme(path, site)
        original = integration.read_bytes()
        integration.unlink()
        integration.symlink_to(site / 'theme/styles/fonts.css')
        with self.assertRaises(self.safe.GateError):
            self.safe.load_trusted_theme(path, site)
        with self.assertRaises(self.safe.GateError):
            self.safe.verify_trusted_theme(theme)
        integration.unlink()
        integration.write_bytes(original)
        for relative, directory in [('theme/notices/PROVENANCE.json', False),
                                    ('theme/notices/UNKNOWN.md', False), ('theme/notices/unlisted', True)]:
            with self.subTest(unlisted=relative):
                extra = site / relative
                if directory:
                    extra.mkdir()
                else:
                    extra.write_bytes(b'{}')
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)
                with self.assertRaises(self.safe.GateError):
                    self.safe.verify_trusted_theme(theme)
                if directory:
                    extra.rmdir()
                else:
                    extra.unlink()
        self.safe.verify_trusted_theme(theme)
        integration.write_bytes(b'x' * (self.safe.MAX_FOREST + 1))
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.load_trusted_theme(path, site)
        self.assertEqual(caught.exception.code, 'SW_SIZE')

    def test_reviewed_ui_inventory_is_explicit_complete_and_hash_bound(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / 'config/theme.json').read_bytes())
        provenance = json.loads((root / 'theme/notices/PROVENANCE.json').read_bytes())
        assets = provenance['assets']
        expected = sorted((dict(source=entry['path'], output=entry['path']) for entry in assets),
                          key=lambda entry: entry['source'])
        self.assertEqual(len(assets), 256)
        self.assertEqual(config['assets'], expected, 'only the 256 reviewed UI assets may be explicitly published')
        self.assertEqual(config['notices'], ['theme/notices/INTEGRATION.md', 'theme/notices/PROVENANCE.json'])
        self.assertEqual(sum(entry['path'].endswith('.woff2') for entry in assets), 254)
        self.assertEqual({entry['path'] for entry in assets if entry['path'].endswith('.txt')},
                         {'theme/assets/notices/OFL-1.1.txt', 'theme/assets/notices/CC0-1.0.txt'})
        site, path, _ = reviewed_ui_fixture(self.base)
        theme = self.safe.load_trusted_theme(path, site)
        self.assertEqual(set(theme['assets']), {entry['path'] for entry in assets} |
                         {'theme/styles/fonts.css', 'theme/styles/miya.css', 'theme/client/hero.js'})
        self.assertTrue(set(config['notices']).isdisjoint(theme['assets']))
        for entry in assets:
            data, digest = theme['assets'][entry['path']]
            self.assertEqual(len(data), entry['bytes'], entry['path'])
            self.assertEqual(digest, entry['sha256'], entry['path'])
        self.safe.verify_trusted_theme(theme)

    def test_cc0_published_notice_requires_exact_explicit_owned_path(self):
        site, path, config, _ = trusted_fixture(self.base)
        relative = 'theme/assets/notices/CC0-1.0.txt'
        notice = site / relative
        notice.parent.mkdir()
        notice.write_bytes(b'Synthetic CC0 license loader fixture, not a real license.')
        config['assets'] = [dict(source=relative, output=relative)]
        path.write_text(json.dumps(config))
        try:
            theme = self.safe.load_trusted_theme(path, site)
        except self.safe.GateError as error:
            self.fail('exact declared CC0 notice asset must load: ' + error.code)
        self.assertEqual(theme['assets'][relative][0], notice.read_bytes())
        for number, other in enumerate(['theme/assets/CC0-1.0.txt', 'theme/assets/fonts/CC0-1.0.txt',
                                        'theme/assets/notices/CC0-2.0.txt', 'theme/assets/notices/private.txt']):
            with self.subTest(path=other):
                case = self.base / str(number)
                case.mkdir()
                site, path, config, _ = trusted_fixture(case)
                (site / other).parent.mkdir(parents=True, exist_ok=True)
                (site / other).write_bytes(b'Synthetic refused arbitrary text.')
                config['assets'] = [dict(source=other, output=other)]
                path.write_text(json.dumps(config))
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)

    def test_exact_source_only_ui_notices_are_hashed_not_published(self):
        site, path, config, _ = trusted_fixture(self.base)
        docs = {'theme/notices/INTEGRATION.md': b'# Trusted synthetic integration document\n',
                'theme/notices/PROVENANCE.json': b'{"schema":"native-theme-provenance-v1","assets":[]}'}
        config['notices'] = list(docs)
        for relative, data in docs.items():
            (site / relative).parent.mkdir(parents=True, exist_ok=True)
            (site / relative).write_bytes(data)
        path.write_text(json.dumps(config))
        try:
            theme = self.safe.load_trusted_theme(path, site)
        except self.safe.GateError as error:
            self.fail('exact declared UI source notices must load: ' + error.code)
        self.assertTrue(set(docs).isdisjoint(theme['assets']))
        for relative, data in docs.items():
            self.assertEqual(theme['sources'][relative], hashlib.sha256(data).hexdigest())
            original = (site / relative).read_bytes()
            (site / relative).write_bytes(original + b' ')
            with self.assertRaises(self.safe.GateError):
                self.safe.verify_trusted_theme(theme)
            (site / relative).write_bytes(original)
        self.safe.verify_trusted_theme(theme)

    def test_source_only_notices_reject_undeclared_other_paths_and_non_strict_json(self):
        for number, relative in enumerate(['theme/notices/UNKNOWN.md', 'theme/notices/PROVENANCE.md',
                                          'theme/notices/OTHER.json', 'theme/assets/notices/PROVENANCE.json']):
            with self.subTest(path=relative):
                case = self.base / str(number)
                case.mkdir()
                site, path, config, _ = trusted_fixture(case)
                (site / relative).parent.mkdir(parents=True, exist_ok=True)
                (site / relative).write_bytes(b'{}')
                config['notices'] = [relative]
                path.write_text(json.dumps(config))
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)
        case = self.base / 'json'
        case.mkdir()
        site, path, config, _ = trusted_fixture(case)
        provenance = site / 'theme/notices/PROVENANCE.json'
        provenance.parent.mkdir()
        config['notices'] = ['theme/notices/PROVENANCE.json']
        path.write_text(json.dumps(config))
        for data in [b'{"key":1,"key":2}', b'{"number":NaN}', b'{"number":Infinity}',
                     b'not JSON', b'{"value":"\xff"}', '{}'.encode('utf-16')]:
            with self.subTest(json=data):
                provenance.write_bytes(data)
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)

    def test_static_navigation_accepts_only_safe_boolean_inert(self):
        for spelling in ['inert', 'inert=""', 'inert="inert"']:
            with self.subTest(boolean=spelling):
                fragment = '<nav hidden ' + spelling + '>{{MENU}}</nav>'
                self.safe.validate_fragment(fragment, menu=True, assets=set())
        for attribute in ['inert="false"', 'inert="true"', 'inert="unknown"',
                          'inert="javascript:run()"', 'inert inert',
                          'inert onclick="run()"', 'inert style="color:red"',
                          'inert unknown="value"', 'inert id="main-wrapper"']:
            with self.subTest(hostile=attribute):
                with self.assertRaises(self.safe.GateError):
                    self.safe.validate_fragment('<nav ' + attribute + '>{{MENU}}</nav>',
                                                menu=True, assets=set())
        with self.assertRaises(self.safe.GateError):
            self.safe.validate_fragment('<nav inert>{{MENU}}<img src="https://external.invalid/x.png"></nav>',
                                        menu=True, assets=set())

    def test_static_fragments_are_bounded_inert_and_have_one_menu_marker(self):
        self.require_loader()
        cases = [
            ('navigation', '<nav>no marker</nav>'),
            ('navigation', '<nav>{{MENU}}{{MENU}}</nav>'),
            ('navigation', '<nav>{{MENU}}{{PRIVATE}}</nav>'),
            ('navigation', '<script>eval("private")</script><nav>{{MENU}}</nav>'),
            ('navigation', '<nav onclick="run()">{{MENU}}</nav>'),
            ('navigation', '<nav>{{MENU}}<a href="javascript:run()">bad</a></nav>'),
            ('home', '<section>{{MENU}}</section>'),
            ('home', '<div id="main-wrapper">duplicate native ID</div>'),
            ('home', '<section><iframe src="https://external.invalid/"></iframe></section>'),
            ('home', '<section><img src="../../private.png"></section>'),
            ('home', '<section><script src="/reload2.js"></script></section>'),
            ('home', '<section><img srcset="https://external.invalid/a.png 1x"></section>'),
            ('home', '<section><a href="/" ping="https://external.invalid/collect">link</a></section>'),
            ('home', '<svg><path d="M0 0" fill="url(https://external.invalid/a.svg#fill)"/></svg>'),
            ('home', '<section unknown="private">not an approved static attribute</section>'),
        ]
        for number, (name, fragment) in enumerate(cases):
            with self.subTest(fragment=number):
                case = self.base / str(number)
                case.mkdir()
                site, path, _, _ = trusted_fixture(case)
                (site / f'theme/layout/{name}.html').write_text(fragment)
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)

    def test_synthetic_shell_is_body_sibling_before_byte_identical_native_main(self):
        site, path, _, _ = trusted_fixture(self.base)
        theme = self.safe.load_trusted_theme(path, site)
        output = self.base / 'synthetic-native-seam'
        output.mkdir()
        forest = dict(schema='forester-public-v2', trees=[tree(), tree('PUBLICB')], assets=[])
        native_main = ('<div id="main-wrapper"><header class="header">Native header</header>'
                       '<div id="grid-wrapper"><article id="tree-container">Native article</article>'
                       '<nav id="native-toc"><a href="#section">TOC</a></nav>'
                       '<footer id="native-backmatter">Native backmatter</footer></div></div></body></html>')
        native = ('<!doctype html><html><head><link rel="stylesheet" href="/style.css">'
                  '<link rel="stylesheet" href="/katex.min.css"><script src="/katex.min.js"></script>'
                  '<script src="/min.js"></script></head><body>' + native_main)
        for identifier in ['PUBLICA', 'PUBLICB']:
            (output / identifier).mkdir()
            (output / identifier / 'index.html').write_text(native)
        preserved = {'forest.json': b'[]', 'min.js': b'/* synthetic native seam asset */',
                     'style.css': b'/* synthetic native seam asset */'}
        for relative, data in preserved.items():
            (output / relative).write_bytes(data)
        hashes = self.safe.present_native(output, {'PUBLICA', 'PUBLICB'}, 'PUBLICA', theme, forest)
        for identifier in ['PUBLICA', 'PUBLICB']:
            decorated = (output / identifier / 'index.html').read_text()
            self.assertTrue(decorated.endswith(native_main), 'native main start and every inner byte must remain')
            self.assertLess(decorated.index('id="site-navigation"'), decorated.index('id="main-wrapper"'))
            self.assertRegex(decorated, r'<body[^>]*><nav id="site-navigation">', 'owned controls must be direct body children for the actual client selector')
            self.assertEqual('id="site-hero"' in decorated, identifier == 'PUBLICA')
            self.assertEqual(hashes[identifier + '/index.html'],
                             hashlib.sha256(decorated.encode()).hexdigest())
        self.assertEqual((output / 'index.html').read_bytes(), (output / 'PUBLICA/index.html').read_bytes())
        for relative, data in preserved.items():
            self.assertEqual((output / relative).read_bytes(), data)
        missing = (output / '404.html').read_text()
        self.assertEqual(hashes['404.html'], hashlib.sha256(missing.encode()).hexdigest())
        self.assertIn('id="site-missing"', missing)
        self.assertIn('id="site-navigation"', missing)
        self.assertNotIn('Native', missing, 'the miss page carries no native or snapshot text')
        self.assertNotIn('id="site-hero"', missing)

    def test_only_backmatter_bodies_start_folded(self):
        page = ('<html><head></head><body><div id="main-wrapper"><div id="grid-wrapper"><article>'
                '<section class="block"><div class="mainmatter">article</div></section>'
                '<footer><section class="block"><header><h1>Context</h1></header><div class="mainmatter">'
                '<img src="/x.jpg" alt=""><section class="block"><div class="mainmatter">nested</div></section>'
                '</div></section><section class="block"><div class="mainmatter">backlinks</div></section></footer>'
                '</article></div></div></body></html>')
        parsed = self.safe.NativePageParser(page)
        self.assertEqual([page[start:start + len(tag)] for start, tag in parsed.backmatter],
                         ['<div class="mainmatter">'] * 2)
        self.assertEqual([start for start, _ in parsed.backmatter],
                         [page.index('<div class="mainmatter"><img'), page.index('<div class="mainmatter">backlinks')])
        for broken in ['<html><body><div></span></body></html>', '<html><body><div/></body></html>']:
            with self.subTest(broken=broken), self.assertRaises(self.safe.GateError):
                self.safe.NativePageParser(broken)

    def test_audit_accepts_only_the_presented_404_page(self):
        from test_safe_web import web_fixture
        output = self.base / 'web-404'
        web_fixture(output)
        page = (output / 'PUBLICA/index.html').read_bytes()
        (output / 'index.html').write_bytes(page)
        (output / '404.html').write_bytes(b'<!DOCTYPE html><p>missing</p>')
        hashes = {'PUBLICA/index.html': hashlib.sha256(page).hexdigest(),
                  '404.html': hashlib.sha256(b'<!DOCTYPE html><p>missing</p>').hexdigest()}
        self.assertEqual(self.safe.audit_output(output, {'PUBLICA'}, {}, page_hashes=hashes, home_copy='PUBLICA')['routes'], 1)
        (output / '404.html').write_bytes(b'<!DOCTYPE html><p>tampered</p>')
        with self.assertRaises(self.safe.GateError):
            self.safe.audit_output(output, {'PUBLICA'}, {}, page_hashes=hashes, home_copy='PUBLICA')
        (output / '404.html').unlink()
        with self.assertRaises(self.safe.GateError):
            self.safe.audit_output(output, {'PUBLICA'}, {}, page_hashes=hashes, home_copy='PUBLICA')

    def test_real_pinned_native_build_adds_owned_shell_without_content_eval(self):
        import inspect
        from test_safe_web import fixture
        self.assertIn('theme_config', inspect.signature(self.safe.build_snapshot).parameters,
                      'build must explicitly opt into a trusted site-owned theme')
        if not os.environ.get('SW_PUBLIC_CONVERTER') or not os.environ.get('SW_NATIVE_FORESTER'):
            self.skipTest('explicit SW_PUBLIC_CONVERTER and SW_NATIVE_FORESTER required for native integration')
        converter = Path(os.environ['SW_PUBLIC_CONVERTER'])
        binary = Path(os.environ['SW_NATIVE_FORESTER'])
        if not converter.is_file() or not binary.is_file():
            self.skipTest('real pinned converter/native renderer unavailable')
        site, config, _, _ = trusted_fixture(self.base)
        parent = tree(text='Body contains literal `{{MENU}}`, not a template. $x < y$')
        parent['title'] = 'Public " & <script>not executable</script>'
        child = tree('NESTED', 'Native nested body.')
        parent['content'].append(dict(kind='subtree', tree=child))
        other = tree('PUBLICB', 'Native non-home body.')
        forest = dict(schema='forester-public-v2', trees=[parent, other], assets=[])
        # CI checks out the public-only snapshot beside site code, never inside theme.
        snapshot = site / 'approved-content'
        digest = fixture(snapshot, forest)
        output = self.base / 'html'
        result = self.safe.build_snapshot(snapshot, output, digest, converter,
                 'a98f2800a88748381fcf9821d64e713925a0a027',
                 hashlib.sha256(converter.read_bytes()).hexdigest(),
                 binary, 'PUBLICA', theme_config=config, site_root=site)
        self.assertEqual(result['routes'], 3)
        plain = self.base / 'plain-native-html'
        self.safe.build_snapshot(snapshot, plain, digest, converter,
                 'a98f2800a88748381fcf9821d64e713925a0a027',
                 hashlib.sha256(converter.read_bytes()).hexdigest(),
                 binary, 'PUBLICA')
        self.assertEqual((plain / 'forest.json').read_bytes(), (output / 'forest.json').read_bytes())
        home = (output / 'PUBLICA/index.html').read_bytes()
        self.assertEqual((output / 'index.html').read_bytes(), home)
        for id in ['PUBLICA', 'PUBLICB', 'NESTED']:
            text = (output / id / 'index.html').read_text()
            native = (plain / id / 'index.html').read_text()
            # Byte-preserve native article/TOC/backmatter and native attributes,
            # except that each top-level backmatter body starts folded.
            folded = native
            for start, tag in reversed(self.safe.NativePageParser(native).backmatter):
                folded = folded[:start] + '<div class="mainmatter collapsed">' + folded[start + len(tag):]
            self.assertEqual(text[text.index('<div id="main-wrapper"'):],
                             folded[folded.index('<div id="main-wrapper"'):])
            self.assertEqual(text.count('mainmatter collapsed'),
                             native.count('mainmatter collapsed') + len(self.safe.NativePageParser(native).backmatter))
            self.assertIn('id="main-wrapper"', text)
            self.assertIn('<article', text)
            self.assertIn('id="grid-wrapper"', text)
            self.assertIn('/min.js', text)
            self.assertIn('/katex.min.js', text)
            self.assertIn('/theme/styles/miya.css', text)
            self.assertIn('/theme/client/hero.js', text)
            self.assertIn('id="site-navigation"', text)
            self.assertEqual('id="site-hero"' in text, id == 'PUBLICA')
            self.assertIn('/PUBLICA/', text)
            self.assertIn('/PUBLICB/', text)
            # Nested sections are routes, not automatic global menu entries.
            nav = text.split('<nav id="site-navigation">')[1].split('</nav>')[0]
            self.assertNotIn('/NESTED/', nav)
            self.assertIn('&lt;script&gt;not executable&lt;/script&gt;', nav)
            self.assertNotIn('<script>', nav)
        self.assertIn('{{MENU}}', home.decode())
        package = binary.resolve().parents[1]
        for asset in ['style.css', 'min.js', 'katex.min.css', 'katex.min.js']:
            self.assertEqual((output / asset).read_bytes(),
                             (package / 'share/forester/themes/default' / asset).read_bytes())
        native_hashes = {p.relative_to(plain).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in plain.rglob('*') if p.is_file() and p.suffix != '.html' and p.name != 'forest.json'}
        owned = self.safe.load_trusted_theme(config, site)
        custom_hashes = {p: digest for p, (_, digest) in owned['assets'].items()}
        pages = {f'{id}/index.html': hashlib.sha256((output / id / 'index.html').read_bytes()).hexdigest()
                 for id in ['PUBLICA', 'PUBLICB', 'NESTED']}
        pages['404.html'] = hashlib.sha256((output / '404.html').read_bytes()).hexdigest()
        inventory = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in output.rglob('*') if p.is_file()}
        search_hash = inventory['forest.json']
        def audit(path, home_copy='PUBLICA'):
            return self.safe.audit_output(path, {'PUBLICA', 'PUBLICB', 'NESTED'}, native_hashes,
                      custom_hashes=custom_hashes, page_hashes=pages, home_copy=home_copy,
                      search_hash=search_hash)
        self.assertEqual(audit(output)['files'], len(inventory))
        for number, relative in enumerate(sorted(inventory)):
            import shutil
            copy = self.base / f'omission-{number}'
            shutil.copytree(output, copy)
            (copy / relative).unlink()
            with self.subTest(omission=relative):
                with self.assertRaises(self.safe.GateError):
                    audit(copy)
            shutil.rmtree(copy)
        root_bytes = (output / 'index.html').read_bytes()
        (output / 'index.html').write_bytes((output / 'PUBLICB/index.html').read_bytes())
        with self.assertRaises(self.safe.GateError):
            audit(output)
        (output / 'index.html').write_bytes(root_bytes)
        with self.assertRaises(self.safe.GateError):
            audit(output, home_copy='PRIVATE')
        with self.assertRaises(self.safe.GateError):
            self.safe.audit_output(output, {'PUBLICA', 'PUBLICB', 'NESTED'}, native_hashes,
                                   custom_hashes=custom_hashes)  # no implicit home-copy permission
        for relative in ['theme/styles/miya.css', 'PUBLICB/index.html', 'min.js']:
            path = output / relative
            original = path.read_bytes()
            path.write_bytes(original + b'/* changed */')
            with self.subTest(tampered=relative):
                with self.assertRaises(self.safe.GateError):
                    audit(output)
            path.write_bytes(original)
        self.assertEqual(inventory, {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in output.rglob('*') if p.is_file()})
        with self.assertRaises(self.safe.GateError) as caught:
            self.safe.build_snapshot(snapshot, output, digest, converter,
                 'a98f2800a88748381fcf9821d64e713925a0a027',
                 hashlib.sha256(converter.read_bytes()).hexdigest(),
                 binary, 'PUBLICA', theme_config=config, site_root=site)
        self.assertEqual(caught.exception.code, 'SW_FRESH')

    def test_theme_rejects_misplaced_menu_and_legacy_or_remote_dependencies(self):
        self.require_loader()
        cases = [
            ('theme/layout/navigation.html', b'<nav><!-- {{MENU}} --></nav>'),
            ('theme/styles/miya.css', b'@import "https://private.invalid/style.css";'),
            ('theme/styles/fonts.css', b'@font-face { src: url(https://external.invalid/font.woff2); }'),
            ('_build/default/theme/client/hero.bc.js', b'fetch("/navigation.xml")'),
            ('_build/default/theme/client/hero.bc.js', b'fetch("/index.xml")'),
            ('_build/default/theme/client/hero.bc.js', b'load("/reload2.js")'),
            ('_build/default/theme/client/hero.bc.js', b'load("/forester.js")'),
        ]
        for number, (relative, data) in enumerate(cases):
            with self.subTest(dependency=number):
                case = self.base / str(number)
                case.mkdir()
                site, path, _, _ = trusted_fixture(case)
                (site / relative).write_bytes(data)
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)

    def test_owned_presentation_audit_requires_exact_search_hash(self):
        import inspect
        self.assertIn('search_hash', inspect.signature(self.safe.audit_output).parameters,
                      'search title and metadata must not drift after native presentation')
        from test_safe_web import web_fixture
        output = self.base / 'html'
        web_fixture(output)
        route = 'PUBLICA/index.html'
        home = (output / route).read_bytes()
        (output / 'index.html').write_bytes(home)
        pages = {route: hashlib.sha256(home).hexdigest()}
        digest = hashlib.sha256((output / 'forest.json').read_bytes()).hexdigest()
        self.safe.audit_output(output, {'PUBLICA'}, {}, page_hashes=pages,
                               home_copy='PUBLICA', search_hash=digest)
        data = json.loads((output / 'forest.json').read_bytes())
        data[0]['title'] = 'Unauthorized changed title'
        (output / 'forest.json').write_text(json.dumps(data))
        with self.assertRaises(self.safe.GateError):
            self.safe.audit_output(output, {'PUBLICA'}, {}, page_hashes=pages,
                                   home_copy='PUBLICA', search_hash=digest)
    def test_cli_theme_input_is_explicit_and_errors_remain_generic(self):
        import subprocess
        from test_safe_web import fixture, SCRIPT
        site, config_path, config, _ = trusted_fixture(self.base)
        config['sourcePath'] = 'SYNTHETIC_PRIVATE_CANARY'
        config_path.write_text(json.dumps(config))
        snapshot = self.base / 'snapshot'
        digest = fixture(snapshot)
        output = self.base / 'html'
        result = subprocess.run(['python3', str(SCRIPT), 'build', '--snapshot-dir', str(snapshot),
                 '--out-dir', str(output), '--content-rev', 'a' * 40, '--manifest-sha256', digest,
                 '--converter', '/not-invoked', '--converter-rev', 'b' * 40,
                 '--converter-sha256', 'c' * 64, '--forester', '/not-invoked', '--home', 'PUBLICA',
                 '--theme-config', str(config_path), '--site-root', str(site)],
                 capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, 'SW_SCHEMA\n')
        self.assertEqual(result.stdout, '')
        self.assertFalse(output.exists())
    def test_declared_svg_asset_is_static_not_an_executable_dependency(self):
        self.require_loader()
        cases = [b'<svg xmlns="http://www.w3.org/2000/svg"><script>run()</script></svg>',
                 b'<svg onload="run()"></svg>',
                 b'<svg><foreignObject><iframe src="https://external.invalid/"></iframe></foreignObject></svg>']
        for number, data in enumerate(cases):
            with self.subTest(svg=number):
                case = self.base / str(number)
                case.mkdir()
                site, path, config, _ = trusted_fixture(case)
                config['assets'] = [dict(source='theme/assets/icon.svg', output='theme/assets/icon.svg')]
                (site / 'theme/assets/icon.svg').write_bytes(data)
                path.write_text(json.dumps(config))
                with self.assertRaises(self.safe.GateError):
                    self.safe.load_trusted_theme(path, site)
    def test_compiled_client_runtime_identifiers_do_not_authorize_source_metadata(self):
        self.require_loader()
        site, path, _, _ = trusted_fixture(self.base)
        client = site / '_build/default/theme/client/hero.bc.js'
        # Lexical loader unit fixture, NOT claimed as compiler output.
        client.write_bytes(b'var offset = 0; var aliases = [];')
        try:
            self.safe.load_trusted_theme(path, site)
        except self.safe.GateError as error:
            self.fail('trusted compiled JS must accept ordinary runtime identifiers: ' + error.code)
        for data in [b'{"offset":123}', b'{"aliases":["private"]}', b'var sourcePath = "private.md";',
                     b'var filename = "private.md";', b'"SYNTHETIC_PRIVATE_CANARY"']:
            client.write_bytes(data)
            with self.subTest(metadata=data):
                with self.assertRaises(self.safe.GateError) as caught:
                    self.safe.load_trusted_theme(path, site)
                self.assertEqual(caught.exception.code, 'SW_LEAK')
    def test_long_compiled_runtime_literals_are_checked_in_bounded_time(self):
        import subprocess
        import sys
        self.require_loader()
        site, config, _, _ = trusted_fixture(self.base)
        # Lexical performance fixture, not fabricated compiler output.
        (site / '_build/default/theme/client/hero.bc.js').write_bytes(b'var literal = "' + b'a' * 200000 + b'";')
        probe = ('import importlib.util; from pathlib import Path; '
                 'spec=importlib.util.spec_from_file_location("safe_web",' + repr(str(self.safe.__file__)) + '); '
                 'm=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); '
                 'm.load_trusted_theme(Path(' + repr(str(config)) + '), Path(' + repr(str(site)) + '))')
        try:
            result = subprocess.run([sys.executable, '-c', probe], capture_output=True, timeout=2)
        except subprocess.TimeoutExpired:
            self.fail('legacy-dependency scan must not rescan every suffix of runtime string literals')
        self.assertEqual(result.returncode, 0, result.stderr)
    def test_late_theme_source_change_aborts_after_real_native_build_without_publication(self):
        from unittest.mock import patch
        from test_safe_web import fixture
        self.require_loader()
        if not os.environ.get('SW_PUBLIC_CONVERTER') or not os.environ.get('SW_NATIVE_FORESTER'):
            self.skipTest('explicit SW_PUBLIC_CONVERTER and SW_NATIVE_FORESTER required for native integration')
        converter = Path(os.environ['SW_PUBLIC_CONVERTER'])
        binary = Path(os.environ['SW_NATIVE_FORESTER'])
        if not converter.is_file() or not binary.is_file():
            self.skipTest('real pinned converter/native renderer unavailable')
        site, config, _, _ = trusted_fixture(self.base)
        snapshot = self.base / 'snapshot'
        digest = fixture(snapshot)
        output = self.base / 'not-published'
        original = self.safe.run_quiet
        native_calls = []
        def real_then_change(command, cwd=None):
            data = original(command, cwd=cwd)  # never fabricate a successful native result
            if len(command) > 1 and command[1] == 'build' and Path(command[0]).name == 'forester':
                native_calls.append(command)
                (site / 'theme/styles/miya.css').write_bytes(b'/* source changed after actual renderer */')
            return data
        with patch.object(self.safe, 'run_quiet', side_effect=real_then_change):
            with self.assertRaises(self.safe.GateError) as caught:
                self.safe.build_snapshot(snapshot, output, digest, converter,
                    'a98f2800a88748381fcf9821d64e713925a0a027',
                    hashlib.sha256(converter.read_bytes()).hexdigest(),
                    binary, 'PUBLICA', theme_config=config, site_root=site)
        self.assertEqual(caught.exception.code, 'SW_THEME')
        self.assertEqual(len(native_calls), 1)
        self.assertFalse(output.exists())
        self.assertFalse(any(path.name.startswith('safe-web-') for path in self.base.iterdir()))


if __name__ == '__main__':
    unittest.main()
