"""Lexical source-field guards must not confuse reviewed CSS properties with payload fields."""
import tempfile
import unittest
from pathlib import Path
from test_native_theme import trusted_fixture
from test_safe_web import TMP, load_module


class OwnedCssLeakTests(unittest.TestCase):
    def setUp(self):
        self.safe = load_module()
        assert self.safe is not None
        self.temp = tempfile.TemporaryDirectory(prefix='owned-css-guard-', dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def fixture(self, data):
        site, config, _, _ = trusted_fixture(self.base)
        (site / 'theme/styles/miya.css').write_bytes(data)
        return site, config

    def test_reviewed_offset_css_declarations_keep_source_and_asset_hashes(self):
        css = b'.miya-native {\n --hero-mark-offset: calc(2px + 1rem);\n outline-offset: 2px;\n}\n.x {outline-offset:-3px;}'
        site, config = self.fixture(css)
        try:
            theme = self.safe.load_trusted_theme(config, site)
        except self.safe.GateError as error:
            self.fail('Reviewed CSS property was mistaken for serialized source offset: ' + str(error))
        self.assertEqual(theme['assets']['theme/styles/miya.css'][0], css)
        self.safe.verify_trusted_theme(theme)

    def test_css_property_suffix_exception_keeps_payload_and_path_rejection(self):
        # Every specimen first uses an accepted legitimate declaration, then a
        # forbidden field/path/canary. No entire-file or field-name waiver.
        blocked = [b'offset: 1', b'offset=1', b'"offset":1', b"'offset': 1",
                   b'aliases: []', b'"sourcePath":"x"', b'filename="x"',
                   b'rawSource: "x"', b'/home/private/file.md',
                   b'SYNTHETIC_PRIVATE_CANARY', b'github_pat_SYNTHETIC_NOT_A_TOKEN',
                   b'custom-offset: 1', b'"outline-offset": 1']
        for index, payload in enumerate(blocked):
            with self.subTest(payload=payload):
                base = self.base / str(index)
                base.mkdir()
                site, config, _, _ = trusted_fixture(base)
                (site / 'theme/styles/miya.css').write_bytes(b'.miya-native {outline-offset:2px; ' + payload + b';}')
                with self.assertRaisesRegex(self.safe.GateError, '^SW_LEAK$'):
                    self.safe.load_trusted_theme(config, site)

    def test_other_owned_sources_cannot_use_the_css_declaration_exception(self):
        for index, relative in enumerate(['theme/client/hero.ml', 'theme/layout/home.html']):
            with self.subTest(relative=relative):
                base = self.base / str(index)
                base.mkdir()
                site, config, _, _ = trusted_fixture(base)
                (site / relative).write_bytes(b'outline-offset: 3px;')
                with self.assertRaisesRegex(self.safe.GateError, '^SW_LEAK$'):
                    self.safe.load_trusted_theme(config, site)


if __name__ == '__main__':
    unittest.main()
