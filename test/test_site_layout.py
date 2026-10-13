"""Code-only distribution boundaries, independent of the private archive or Git index."""
import json
from pathlib import Path
import re
import stat
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SiteLayoutTests(unittest.TestCase):
    def test_documentation_describes_only_the_synthetic_code_only_entry_point(self):
        for name in ['SAFE-WEB.md', 'docs/layout.md']:
            with self.subTest(document=name):
                text = (ROOT / name).read_text(encoding='utf-8')
                for token in ['code-only', 'ci/synthetic-dry-run-*', 'config/synthetic-inputs.json',
                              'SW_SYNTHETIC_INPUT', 'PUBLIC_CONTENT_TOKEN']:
                    self.assertIn(token, text)
                self.assertNotIn('byte-identical null converter pins', text)
                self.assertNotIn('legacy/README.md', text)

    def test_source_tree_omits_retired_content_state_and_acceptance_files(self):
        for name in ['legacy', 'site', 'assets', 'lib_theme', '.wrangler', '.obsidian',
                     'vault', 'wiki', 'content', 'public-forest.json', 'manifest.json',
                     'REPORT.json', 'evidence']:
            self.assertFalse((ROOT / name).exists(), f'not distributed: {name}')
        for directory in ['config', 'docs', 'scripts', 'test', 'theme', 'dune.lock']:
            for path in (ROOT / directory).rglob('*'):
                info = path.lstat()
                self.assertTrue(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'owned source remains regular')
                if path.is_file():
                    self.assertEqual(info.st_nlink, 1)
                    self.assertNotIn(path.suffix, {'.tree', '.sqlite', '.db', '.pyc', '.pyo', '.key', '.pem'})
                    self.assertNotIn(path.name, {'public-forest.json', 'manifest.json', '.env'})

    def test_distributed_text_has_no_machine_specific_acceptance_or_binary_anchors(self):
        prohibited = [b'/home/' + b'miyax/', b'forester-' + b'verification/',
                      b'reaccept-' + b'current-', b'continuation-' + b'verdict.json',
                      b'706fe1714ce419e29' + b'fe9b025633abaacc1f574fbe9a8864a5e3e9990cccb8595']
        sources = [ROOT / 'SAFE-WEB.md', *sorted((ROOT / 'docs').rglob('*.md')),
                   *sorted((ROOT / 'scripts').glob('*.py')), *sorted((ROOT / 'test').glob('*.py')),
                   *sorted((ROOT / 'test').glob('*.mjs')), *sorted((ROOT / 'theme/notices').glob('*'))]
        for path in sources:
            with self.subTest(source=path.relative_to(ROOT).as_posix()):
                data = path.read_bytes()
                self.assertFalse(any(pattern in data for pattern in prohibited), 'local-only anchors must stay outside the code tree')

    def test_generated_outputs_and_input_copies_have_explicit_ignore_rules(self):
        ignored = set((ROOT / '.gitignore').read_text().splitlines())
        for pattern in ['_build/', '/dist/', '.wrangler/', '__pycache__/', '*.py[cod]',
                        '/public-forest.json', '/manifest.json', '/snapshot/', '/content/', '/vault/']:
            self.assertIn(pattern, ignored)
        tokens = re.findall(r'[^\s()]+', (ROOT / 'dune').read_text())
        self.assertEqual(tokens[:3], ['dirs', ':standard', '\\'])
        self.assertIn('legacy', tokens[3:])
        for name in ['dune-project', 'dune-workspace', 'devbox.json', 'flake.nix', 'flake.lock', 'dune.lock/lock.dune']:
            self.assertTrue((ROOT / name).is_file())

    def test_inert_workers_configuration_still_names_only_dist(self):
        # Configuration is retained as code, never invoked by synthetic Actions.
        text = (ROOT / 'wrangler.jsonc').read_text(encoding='utf-8')
        data = json.loads(re.sub(r'(?m)^\s*//[^\n]*$', '', text))
        self.assertEqual(data['assets']['directory'], './dist')
        self.assertEqual(data['assets']['not_found_handling'], 'none')


if __name__ == '__main__':
    unittest.main()
