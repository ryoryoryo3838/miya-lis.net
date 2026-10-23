"""Build-only trusted workflow contract, independent of production credentials."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_safe_web import ROOT, TMP, load_module, pin_fixture


class TrustedWorkflowTests(unittest.TestCase):
    def test_theme_configuration_is_explicit_and_uses_only_owned_paths(self):
        path = ROOT / 'config/theme.json'
        self.assertTrue(path.is_file(), 'strict trusted native theme config must be site code')
        data = json.loads(path.read_bytes())
        self.assertEqual(set(data), {'schema', 'styles', 'client', 'layout', 'assets', 'notices'})
        self.assertEqual(data['schema'], 'safe-web-theme-v1')
        self.assertEqual(data['client'], dict(source='_build/default/theme/client/hero.bc.js', output='theme/client/hero.js'))
        self.assertEqual(data['layout'], dict(home='theme/layout/home.html', navigation='theme/layout/navigation.html',
                                              not_found='theme/layout/not-found.html'))
        self.assertEqual(data['styles'], [dict(source=f'theme/styles/{n}.css', output=f'theme/styles/{n}.css')
                                          for n in ['fonts', 'miya']])

    def test_build_only_ci_compiles_site_client_before_content_checkout(self):
        text = (ROOT / '.github/workflows/synthetic-dry-run.yml').read_text()
        self.assertIn('--pins config/pins.json', text)
        self.assertNotIn('--pins .github/safe-web-pins.json', text)
        self.assertIn('python3 scripts/build-theme-client.py', text)
        self.assertIn('--theme-config config/theme.json', text)
        self.assertIn('--site-root .', text)
        self.assertLess(text.index('python3 scripts/build-theme-client.py'), text.index('repository: ryoryoryo3838/miya-lis-public'))
        self.assertEqual(text.count('${{ secrets.PUBLIC_CONTENT_TOKEN }}'), 1)
        self.assertIn('contents: read', text)
        for forbidden in ['wrangler deploy', 'wrangler pages', 'actions/cache@', 'deploy-pages@', 'contents: write', 'id-token: write', 'site/build.sh', 'site/output']:
            self.assertNotIn(forbidden, text)

    def test_synthetic_null_pins_refuse_before_theme_or_output_access(self):
        # Refusal is independent of the reviewed pins in the code-only checkout.
        safe = load_module()
        with tempfile.TemporaryDirectory(prefix='workflow-test-', dir=TMP) as directory:
            path = Path(directory) / 'null-pins.json'
            path.write_text(json.dumps(pin_fixture(safe)))
            github_output = Path(directory) / 'output'
            result = subprocess.run(['python3', str(ROOT / 'scripts/safe-web.py'), 'ci-config',
                     '--pins', str(path), '--content-rev', 'a' * 40, '--manifest-sha256', 'b' * 64,
                     '--github-output', str(github_output)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, 'SW_PIN\n')
            self.assertEqual(result.stdout, '')
            self.assertFalse(github_output.exists())


if __name__ == '__main__':
    unittest.main()
