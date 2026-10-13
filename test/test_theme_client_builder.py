"""Locked source-only client builds. Real compiler evidence is opt-in below."""
import hashlib
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from test_safe_web import ROOT, TMP

SCRIPT = ROOT / 'scripts/build-theme-client.py'


def load_builder():
    if not SCRIPT.is_file():
        return None
    spec = importlib.util.spec_from_file_location('theme_builder', SCRIPT)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def source_fixture(base):
    root = base / 'trusted-site'
    root.mkdir()
    for name in ['dune', 'dune-project', 'dune-workspace', 'flake.nix', 'flake.lock']:
        path = ROOT / name
        if path.is_file():
            (root / name).write_bytes(path.read_bytes())
    shutil.copytree(ROOT / 'dune.lock', root / 'dune.lock')
    client = root / 'theme/client'
    client.mkdir(parents=True)
    (client / 'dune').write_text('(executable (name hero) (modes js) (libraries js_of_ocaml) (preprocess (pps js_of_ocaml-ppx)))\n')
    (client / 'hero.ml').write_text('let () = Js_of_ocaml.Dom_html.document##.documentElement##setAttribute (Js_of_ocaml.Js.string "data-synthetic-client") (Js_of_ocaml.Js.string "built")\n')
    # Poison files outside the source allowlist must never be opened or copied.
    for name in ['legacy/private.md', '.env', 'approved-content/public-forest.json', 'theme/assets/private.png']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('SYNTHETIC_PRIVATE_CANARY')
    return root


class ClientBuilderTests(unittest.TestCase):
    def setUp(self):
        self.builder = load_builder()
        self.temp = tempfile.TemporaryDirectory(prefix='client-builder-test-', dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def require_builder(self):
        self.assertIsNotNone(self.builder, 'locked source-only site client builder must exist')

    def test_copy_includes_only_explicit_root_lock_and_client_sources(self):
        self.require_builder()
        root = source_fixture(self.base)
        fresh = self.base / 'fresh'
        fresh.mkdir()
        before = self.builder.source_manifest(root)
        self.assertEqual(self.builder.copy_sources(root, fresh), before)
        expected = {'dune', 'dune-project', 'dune-workspace', 'flake.nix', 'flake.lock',
                    'theme/client/dune', 'theme/client/hero.ml'}
        self.assertEqual({p for p in before if not p.startswith('dune.lock/')}, expected)
        self.assertEqual(before, self.builder.source_manifest(fresh))
        for path in fresh.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'SYNTHETIC_PRIVATE_CANARY', path.read_bytes())
        self.assertEqual(before, self.builder.source_manifest(root))
    def test_compile_environment_contains_no_inherited_content_credentials(self):
        from unittest.mock import patch
        self.require_builder()
        self.assertTrue(callable(getattr(self.builder, 'compile_environment', None)),
                        'compiler env must be constructed from an allowlist')
        with patch.dict(os.environ, {'PUBLIC_CONTENT_TOKEN': 'SYNTHETIC_PRIVATE_CANARY',
                                     'GITHUB_TOKEN': 'SYNTHETIC_PRIVATE_CANARY',
                                     'OPAMROOT': '/private', 'DUNE_ROOT': '/wrong',
                                     'OCAMLPATH': '/private', 'NIX_CONFIG': 'access-tokens = private'}):
            env = self.builder.compile_environment(self.base)
        self.assertEqual(set(env), {'PATH', 'HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME',
                                   'XDG_DATA_HOME', 'DUNE_CACHE', 'DUNE_ROOT', 'NIX_USER_CONF_FILES',
                                   'NIX_CONFIG', 'LC_ALL', 'TZ'})
        self.assertEqual(env['DUNE_ROOT'], str(self.base / 'sources'))
        self.assertEqual(env['DUNE_CACHE'], 'disabled')
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', str(env))
        self.assertNotIn('/private', str(env))

    def test_source_manifest_rejects_unlocked_or_changed_toolchain(self):
        self.require_builder()
        root = source_fixture(self.base)
        (root / 'flake.lock').write_text('{}')
        with self.assertRaises(self.builder.BuildRefusal) as caught:
            self.builder.source_manifest(root)
        self.assertEqual(str(caught.exception), 'TC_PIN')

    @unittest.skipUnless(os.environ.get('TC_REAL_BUILD') == '1', 'explicit real locked compiler acceptance')
    def test_real_source_only_build_uses_locked_compiler_and_atomic_regular_js(self):
        self.require_builder()
        self.assertTrue(callable(getattr(self.builder, 'build', None)),
                        'client must actually compile with fixed Nix/Dune, not reuse legacy JS')
        root = source_fixture(self.base)
        before = self.builder.source_manifest(root)
        result = self.builder.build(root)
        artifact = root / '_build/default/theme/client/hero.bc.js'
        self.assertTrue(artifact.is_file())
        self.assertFalse(artifact.is_symlink())
        self.assertEqual(artifact.stat().st_nlink, 1)
        data = artifact.read_bytes()
        self.assertIn(b'data-synthetic-client', data)
        self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(result['ocaml'], '5.5.1')
        self.assertEqual(result['dune'], '3.23.1')
        self.assertEqual(result['js_of_ocaml'], '6.4.1')
        self.assertEqual(result['sources'], before)
        self.assertEqual(self.builder.source_manifest(root), before)
        self.assertFalse((root / '_build/.theme-client-driver.lock').exists())
        self.assertFalse(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()))
    def test_timeout_kills_compiler_process_group_and_keeps_errors_generic(self):
        import sys
        import time
        self.require_builder()
        marker = self.base / 'child-after-timeout'
        child = 'import time; from pathlib import Path; time.sleep(.3); Path(' + repr(str(marker)) + ').write_text("synthetic")'
        command = [sys.executable, '-c', 'import subprocess,time; subprocess.Popen([' +
                   repr(sys.executable) + ', "-c", ' + repr(child) + ']); time.sleep(3)']
        with self.assertRaises(self.builder.BuildRefusal) as caught:
            self.builder.run_tool(command, cwd=self.base, env=dict(os.environ), timeout=.1, code='TC_BUILD')
        self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
        time.sleep(.4)
        self.assertFalse(marker.exists(), 'no compiler descendants may survive a refusal')
        with self.assertRaises(self.builder.BuildRefusal) as caught:
            self.builder.run_tool([sys.executable, '-c', 'import sys; print("SYNTHETIC_PRIVATE_CANARY", file=sys.stderr); sys.exit(1)'],
                                  cwd=self.base, env=dict(os.environ), timeout=5, code='TC_BUILD')
        self.assertEqual(str(caught.exception), 'TC_BUILD')

    def test_refused_build_preserves_previous_js_and_cleans_owned_workspace(self):
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        before = self.builder.source_manifest(root)
        target = root / '_build/default/theme/client/hero.bc.js'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'/* explicitly stale synthetic fixture; never accepted as built */')
        old = target.read_bytes()
        with patch.object(self.builder, 'run_tool', side_effect=self.builder.BuildRefusal('TC_TIMEOUT')):
            with self.assertRaises(self.builder.BuildRefusal):
                self.builder.build(root)
        self.assertEqual(target.read_bytes(), old)
        self.assertEqual(self.builder.source_manifest(root), before)
        self.assertFalse((root / '_build/.theme-client-driver.lock').exists())
        self.assertFalse(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()))
    def test_client_and_lock_namespace_refuse_links_or_unknown_files_before_build(self):
        self.require_builder()
        cases = ['client-link', 'root-hardlink', 'unknown-client', 'unknown-lock']
        for number, name in enumerate(cases):
            with self.subTest(gate=name):
                case = self.base / str(number)
                case.mkdir()
                root = source_fixture(case)
                if name == 'client-link':
                    target = root / 'theme/client/hero.ml'
                    data = target.read_bytes()
                    target.unlink()
                    external = case / 'outside.ml'
                    external.write_bytes(data)
                    target.symlink_to(external)
                elif name == 'root-hardlink':
                    os.link(root / 'dune-project', case / 'second-link')
                elif name == 'unknown-client':
                    (root / 'theme/client/private.md').write_text('SYNTHETIC_PRIVATE_CANARY')
                else:
                    (root / 'dune.lock/unknown.sh').write_text('SYNTHETIC_PRIVATE_CANARY')
                with self.assertRaises(self.builder.BuildRefusal):
                    self.builder.build(root)
                self.assertFalse((root / '_build').exists())

    def test_busy_lock_and_unsafe_output_are_never_reused_or_removed(self):
        self.require_builder()
        root = source_fixture(self.base)
        base = root / '_build'
        base.mkdir()
        lock = base / '.theme-client-driver.lock'
        lock.write_text('explicit synthetic existing owner')
        with self.assertRaises(self.builder.BuildRefusal) as caught:
            self.builder.build(root)
        self.assertEqual(str(caught.exception), 'TC_BUSY')
        self.assertEqual(lock.read_text(), 'explicit synthetic existing owner')
        lock.unlink()
        external = self.base / 'elsewhere'
        external.mkdir()
        (base / 'default').symlink_to(external, target_is_directory=True)
        with self.assertRaises(self.builder.BuildRefusal) as caught:
            self.builder.build(root)
        self.assertEqual(str(caught.exception), 'TC_PATH')
        self.assertEqual(list(external.iterdir()), [])
        self.assertFalse(lock.exists())

    def test_cli_unknown_arguments_never_echo_private_values(self):
        import subprocess
        self.require_builder()
        result = subprocess.run(['python3', str(SCRIPT), '--unknown', 'SYNTHETIC_PRIVATE_CANARY'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, 'TC_ARGS\n')
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
