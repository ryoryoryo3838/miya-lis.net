"""Devbox is only a pinned Dune bootstrap, not the project orchestrator."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DUNE_PACKAGE = 'github:NixOS/nixpkgs/70ce234312134a463ba7728e94da2486a1d237ac#dune'


class DevboxBootstrapTests(unittest.TestCase):
    def test_documentation_keeps_client_handoff_distinct_from_unchanged_native_and_converter_nix(self):
        path = ROOT / 'docs/devbox-bootstrap.md'
        self.assertTrue(path.is_file(), 'bootstrap boundary documentation must be distributed')
        text = path.read_text(encoding='utf-8')
        for token in ['0.18.4', '3.23.1', '70ce234312134a463ba7728e94da2486a1d237ac',
                      'python3 scripts/build-theme-client.py --site-root . --diagnostics',
                      'Native Forester', 'converter', 'Nix', '1800', '600',
                      'bootstrap_seconds', 'compile_seconds', 'total_seconds']:
            self.assertIn(token, text)

    def test_devbox_only_installs_pinned_dune_without_hooks_or_scripts(self):
        config = json.loads((ROOT / 'devbox.json').read_text(encoding='utf-8'))
        self.assertEqual(config['packages'], [DUNE_PACKAGE])
        self.assertEqual(set(config), {'$schema', 'packages'})


if __name__ == '__main__':
    unittest.main()
