"""Owned native-theme contracts; no private content or legacy builders."""
from html.parser import HTMLParser
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FragmentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class NativeThemeAssetsTest(unittest.TestCase):
    def test_trusted_fragments_keep_home_and_navigation_separate(self):
        fragments = {}
        for name in ("home", "navigation"):
            path = ROOT / "theme/layout" / (name + ".html")
            self.assertTrue(path.is_file(), f"missing trusted {name} fragment")
            text = path.read_text(encoding="utf-8")
            parsed = FragmentParser()
            parsed.feed(text)
            fragments[name] = (text, parsed.elements)
            for tag, attrs in parsed.elements:
                self.assertNotIn(tag, {"html", "head", "body", "article", "script", "iframe", "object", "ninja-keys"})
                self.assertFalse(any(key.startswith("on") or key == "style" for key in attrs))
                self.assertFalse(set(attrs) & {"data-base-url", "data-tex", "data-target", "hx-boost"})
                for key in ("href", "src"):
                    if key in attrs:
                        self.assertTrue(attrs[key].startswith(("#", "/")), attrs[key])
        home, navigation = fragments["home"], fragments["navigation"]
        home_ids = {attrs.get("id") for _, attrs in home[1]} - {None}
        navigation_ids = {attrs.get("id") for _, attrs in navigation[1]} - {None}
        self.assertEqual(home_ids, {"hero", "hero-period", "hero-period-placeholder", "persistent-header"})
        self.assertEqual(navigation_ids, {"nav-toggle-global", "nav-overlay", "nav-panel", "nav-close"})
        self.assertFalse(home_ids & navigation_ids)
        self.assertNotIn("{{", home[0])
        self.assertEqual(navigation[0].count("{{MENU}}"), 1)
        self.assertEqual(navigation[0].count("{{"), 1)
        self.assertIn('href="#grid-wrapper"', home[0])
        self.assertIn('href="#hero"', home[0])
        for tag, attrs in home[1] + navigation[1]:
            if "nav-toggle" in attrs.get("class", "").split():
                self.assertEqual(tag, "button")
                self.assertEqual(attrs.get("type"), "button")
                self.assertEqual(attrs.get("aria-controls"), "nav-panel")
                self.assertEqual(attrs.get("aria-expanded"), "false")
                self.assertTrue(attrs.get("aria-label"))
        panel = next(attrs for _, attrs in navigation[1] if attrs.get("id") == "nav-panel")
        self.assertIn("hidden", panel)
        self.assertIn("inert", panel)
        self.assertEqual(panel.get("aria-label"), "Site navigation")


    def test_self_hosted_fonts_keep_all_licensed_original_bytes(self):
        path = ROOT / "theme/styles/fonts.css"
        self.assertTrue(path.is_file(), "missing owned self-hosted font declarations")
        css = path.read_text(encoding="utf-8")
        self.assertNotIn("https:", css)
        self.assertNotIn("@import", css)
        faces = re.findall(r"@font-face\s*\{([^}]+)\}", css)
        records = []
        for face in faces:
            fields = dict(re.findall(r"([a-z-]+)\s*:\s*([^;]+);", face))
            records.append(fields)
            self.assertEqual(fields["font-display"], "swap")
        weights = Counter((record["font-family"].strip("'\""), record["font-weight"], record["font-style"]) for record in records)
        self.assertEqual(weights[("BIZ UDMincho", "400", "normal")], 124)
        self.assertEqual(weights[("BIZ UDMincho", "700", "normal")], 124)
        self.assertEqual(sum(weights.values()), 254)
        font_urls = re.findall(r"url\('([^']+)'\)", css)
        self.assertEqual(len(font_urls), len(set(font_urls)))
        resolved_fonts = set()
        for url in font_urls:
            self.assertTrue(url.startswith("../assets/fonts/"), url)
            font = (path.parent / url).resolve()
            self.assertTrue(ROOT / "theme/assets/fonts" in font.parents)
            self.assertTrue(font.is_file())
            self.assertFalse(font.is_symlink())
            self.assertEqual(font.read_bytes()[:4], b"wOF2", font.name)
            resolved_fonts.add(font.relative_to(ROOT).as_posix())
        provenance_path = ROOT / "theme/notices/PROVENANCE.json"
        self.assertTrue(provenance_path.is_file(), "font provenance is not optional")
        provenance = json.loads(provenance_path.read_text())
        self.assertEqual(provenance["source_commit"], "bb66098a6e040a2ec94b47e627ae38c817ee1d71")
        listed = set()
        for item in provenance["assets"]:
            asset = ROOT / item["path"]
            self.assertTrue(asset.is_file())
            self.assertFalse(asset.is_symlink())
            self.assertEqual(asset.stat().st_nlink, 1)
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            self.assertEqual(digest, item["sha256"])
            self.assertEqual(digest, item["original_sha256"], "copied asset bytes must not be rewritten")
            self.assertTrue(item["original_path"].startswith("site/theme/"))
            listed.add(item["path"])
        self.assertEqual(resolved_fonts, {name for name in listed if name.endswith(".woff2")})
        license_text = (ROOT / "theme/assets/notices/OFL-1.1.txt").read_text()
        self.assertIn("Copyright 2017 The Inria Sans Project Authors", license_text)
        self.assertIn("Copyright 2022 The BIZ UDMincho Project Authors", license_text)
        self.assertIn("SIL OPEN FONT LICENSE Version 1.1", license_text)
        self.assertIn("theme/assets/notices/OFL-1.1.txt", listed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
