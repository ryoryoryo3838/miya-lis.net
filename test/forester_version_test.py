"""Regression gate for the site's fixed Forester 6 dependency."""
from pathlib import Path
import sys
import unittest

ROOT = Path(sys.argv.pop(1)) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else Path(__file__).resolve().parents[1]
REVISION = 'f8fb5f5d88923db36643cf9c20c662adff969c98'


class ForesterVersionTests(unittest.TestCase):
    def test_project_selects_fixed_forester_6(self):
        text = (ROOT / 'dune-project').read_text()
        self.assertIn('#' + REVISION, text)
        self.assertRegex(text, r'\(package\s+\(name forester\)\s+\(version "6\.0~dev"\)\)')
        self.assertRegex(text, r'\(ocaml\s+\(>=\s+5\.4\)\)')
        self.assertNotIn('#5.0', text)

    def test_resolved_lock_has_no_forester_5(self):
        files = list((ROOT / 'dune.lock').glob('forester.*.pkg'))
        self.assertEqual(len(files), 1)
        text = files[0].read_text()
        self.assertRegex(text, r'\(version\s+6\.0~dev\)')
        self.assertIn('#' + REVISION, text)
        self.assertIn('grace', text)
        self.assertIn('saturn', text)
        self.assertNotIn('(version 5.0)', text)


if __name__ == '__main__':
    unittest.main()
