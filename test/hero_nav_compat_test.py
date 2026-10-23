"""Compile the real legacy hero, then exercise it in Chromium.

Run: python3 test/hero_nav_compat_test.py
Requires dune on PATH, Node, playwright-core and Chromium. Set
PLAYWRIGHT_MODULE and HYBRID_CHROMIUM for externally installed browser tools.
No vault input, site generation, deployment or network access is needed.
"""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HeroNavCompatibilityTest(unittest.TestCase):
    def test_real_hero_compiles_and_preserves_navigation(self):
        dune = shutil.which("dune")
        if dune is None:
            self.fail("dune must be available on PATH")
        compiled = subprocess.run(
            [dune, "build", "theme/client/hero.bc.js", "-j2", "--stop-on-first-error"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=180,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stdout)
        node = shutil.which("node")
        if node is None:
            self.fail("Node must be available on PATH")
        browser = subprocess.run(
            [node, str(ROOT / "test/hero_nav_compat_test.mjs"),
             str(ROOT / "_build/default/theme/client/hero.bc.js")],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=90,
        )
        self.assertEqual(browser.returncode, 0, browser.stdout)
        print(browser.stdout, end="")


if __name__ == "__main__":
    unittest.main(verbosity=2)
