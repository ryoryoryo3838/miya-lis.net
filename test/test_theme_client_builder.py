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
    def test_default_cli_exact_legacy_outputs_and_success_json(self):
        import contextlib
        import io
        import json
        import sys
        from unittest.mock import patch
        self.require_builder()
        cases = [(self.builder.BuildRefusal('TC_TIMEOUT'), 2, 'TC_TIMEOUT\n'),
                 (OSError(13, 'SYNTHETIC_PRIVATE_CANARY bearer=fake'), 2, 'TC_IO\n'),
                 (ValueError('SYNTHETIC_PRIVATE_CANARY'), 2, 'TC_IO\n'),
                 (KeyError('SYNTHETIC_PRIVATE_CANARY'), 2, 'TC_IO\n'),
                 (TypeError('SYNTHETIC_PRIVATE_CANARY'), 2, 'TC_IO\n'),
                 (KeyboardInterrupt('SYNTHETIC_PRIVATE_CANARY'), 130, 'TC_INTERRUPTED\n')]
        for error, expected_code, expected_stderr in cases:
            with self.subTest(error=type(error).__name__):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(sys, 'argv', ['builder', '--site-root', str(self.base)]), \
                     patch.object(self.builder, 'build', side_effect=error), \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = self.builder.main()
                self.assertEqual((code, stdout.getvalue(), stderr.getvalue()),
                                 (expected_code, '', expected_stderr))
        result = {'sha256': 'a' * 64, 'sources': {'synthetic': 'b' * 64}, 'dune': '3.23.1'}
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['builder', '--site-root', str(self.base)]), \
             patch.object(self.builder, 'build', return_value=result), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.builder.main()
        self.assertEqual((code, stdout.getvalue(), stderr.getvalue()),
                         (0, json.dumps(result, sort_keys=True) + '\n', ''))

    def test_explicit_cli_diagnostics_classifies_without_error_payloads(self):
        import contextlib
        import io
        import json
        import sys
        from unittest.mock import patch
        self.require_builder()
        payload = 'SYNTHETIC_PRIVATE_CANARY bearer=fake password=fake /private/content --private-argv'
        unknown = type('SYNTHETIC_PRIVATE_CANARY', (OSError,), {})
        cases = [(OSError(13, payload, '/private/content'), 'PermissionError', 13, 'none', 2, 'TC_IO'),
                 (FileNotFoundError(2, payload, '/private/content'), 'FileNotFoundError', 2, 'none', 2, 'TC_IO'),
                 (ValueError(payload), 'ValueError', None, 'none', 2, 'TC_IO'),
                 (KeyError(payload), 'KeyError', None, 'none', 2, 'TC_IO'),
                 (TypeError(payload), 'TypeError', None, 'none', 2, 'TC_IO'),
                 (self.builder.BuildRefusal('TC_TIMEOUT'), 'BuildRefusal', None, 'TC_TIMEOUT', 2, 'TC_TIMEOUT'),
                 (KeyboardInterrupt(payload), 'KeyboardInterrupt', None, 'none', 130, 'TC_INTERRUPTED'),
                 (unknown(13, payload), 'other', None, 'none', 2, 'TC_IO')]
        for number, (error, expected_class, expected_errno, expected_tc, expected_code, generic) in enumerate(cases):
            with self.subTest(case=number):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(sys, 'argv', ['builder', '--diagnostics', '--site-root', str(self.base)]), \
                     patch.object(self.builder, 'build', side_effect=error), \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = self.builder.main()
                lines = stderr.getvalue().splitlines()
                records = [json.loads(line[len('TC_DIAG '):]) for line in lines if line.startswith('TC_DIAG ')]
                self.assertEqual(len(records), 2, 'explicit opt-in must emit CLI start/end classifications')
                self.assertEqual((code, stdout.getvalue(), lines[-1]), (expected_code, '', generic))
                self.assertEqual(records[0]['event'], 'start')
                self.assertEqual(records[-1], dict(phase='cli', event='end', outcome='failure',
                    exception_class=expected_class, errno=expected_errno, tc_code=expected_tc))
                self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
                for private in ['bearer=', 'password=', '/private', '--private-argv', str(self.base)]:
                    self.assertNotIn(private, stderr.getvalue())
                self.assertEqual(stdout.getvalue(), '')
    def fake_successful_tool(self, command, *, cwd, env, timeout, code, **kwargs):
        # This is a deterministic tool-boundary fixture, never compiler evidence.
        self.assertNotIn('PUBLIC_CONTENT_TOKEN', env)
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', str(env))
        if command[-2:] == ['dune', '--version']:
            self.assertEqual(timeout, 120)
            return b'3.23.1'
        if command[-3:] == ['dune', 'build', 'theme/client/hero.bc.js']:
            self.assertEqual(timeout, 600)
            self.assertEqual(code, 'TC_BUILD')
            target = Path(cwd) / self.builder.TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(b'/* synthetic tool fixture, not compiled JS */\n')
            return b''
        self.assertEqual(timeout, 120)
        if command[-2:] == ['ocamlc', '-version']:
            return b'5.5.1'
        if command[-2:] == ['js_of_ocaml', '--version']:
            return b'6.4.1'
        self.fail('unexpected synthetic tool boundary')

    def test_success_build_records_phase_boundaries_and_fresh_publication(self):
        import contextlib
        import io
        import json
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        before = self.builder.source_manifest(root)
        target = root / self.builder.TARGET
        target.parent.mkdir(parents=True)
        target.write_bytes(b'/* stale synthetic fixture */')
        stderr, stdout = io.StringIO(), io.StringIO()
        with patch.object(self.builder, 'run_tool', side_effect=self.fake_successful_tool), \
             patch.dict(os.environ, {'PUBLIC_CONTENT_TOKEN': 'SYNTHETIC_PRIVATE_CANARY'}), \
             contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            result = self.builder.build(root, diagnostics=self.builder.Diagnostics())
        records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
        required = {'source_validation', 'output_validation', 'lock_acquire', 'workspace_create',
                    'workspace_setup', 'source_copy', 'environment_setup', 'shell_setup',
                    'dune_version', 'client_build', 'ocaml_version', 'jsoo_version',
                    'source_recheck', 'publication', 'build_work'}
        starts = {record['phase'] for record in records if record['event'] == 'start'}
        ends = {record['phase'] for record in records if record['event'] == 'end'}
        self.assertTrue(required <= starts, 'all source/tool/publication phases must have a start')
        self.assertTrue(required <= ends, 'all completed source/tool/publication phases must have an end')
        self.assertTrue(all(record['outcome'] == 'success' for record in records if record['event'] == 'end'))
        self.assertEqual(stdout.getvalue(), '')
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
        self.assertNotIn(str(root), stderr.getvalue())
        self.assertNotIn('hero.bc.js', stderr.getvalue())
        self.assertEqual(target.read_bytes(), b'/* synthetic tool fixture, not compiled JS */\n')
        self.assertEqual(target.stat().st_nlink, 1)
        self.assertFalse(target.is_symlink())
        self.assertEqual(result['sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertEqual(result['sources'], before)
        self.assertEqual(self.builder.source_manifest(root), before)
        self.assertFalse((root / '_build/.theme-client-driver.lock').exists())
        self.assertFalse(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()))
    def test_workspace_and_lock_cleanup_observe_masking_without_changing_it(self):
        import contextlib
        import io
        import json
        import sys
        from unittest.mock import patch
        self.require_builder()
        original_cleanup = self.builder.tempfile.TemporaryDirectory.cleanup
        original_unlink = Path.unlink
        original_build = self.builder.build
        payload = 'SYNTHETIC_PRIVATE_CANARY password=fake /private/content'
        variants = [(True, True, False), (True, False, True), (True, True, True),
                    (False, True, False), (False, False, True)]
        for number, (primary_fails, workspace_fails, lock_fails) in enumerate(variants):
            for optin in [False, True]:
                with self.subTest(case=number, optin=optin):
                    case = self.base / (str(number) + '-' + str(optin))
                    case.mkdir()
                    root = source_fixture(case)
                    primary = self.builder.BuildRefusal('TC_TIMEOUT')
                    workspace_error = PermissionError(13, payload, '/private/content')
                    lock_error = OSError(5, payload, '/private/content')
                    winning = lock_error if lock_fails else workspace_error
                    seen = []
                    def observe_build(*args, **kwargs):
                        try:
                            return original_build(*args, **kwargs)
                        except BaseException as error:
                            seen.append(error)
                            raise
                    def cleanup(workspace):
                        original_cleanup(workspace)
                        if workspace_fails:
                            raise workspace_error
                    def unlink(path, *args, **kwargs):
                        if path == root / '_build/.theme-client-driver.lock' and lock_fails:
                            raise lock_error
                        return original_unlink(path, *args, **kwargs)
                    stdout, stderr = io.StringIO(), io.StringIO()
                    argv = ['builder', '--site-root', str(root)] + (['--diagnostics'] if optin else [])
                    effect = primary if primary_fails else self.fake_successful_tool
                    with patch.object(sys, 'argv', argv), \
                         patch.object(self.builder, 'build', side_effect=observe_build), \
                         patch.object(self.builder, 'run_tool', side_effect=effect), \
                         patch.object(self.builder.tempfile.TemporaryDirectory, 'cleanup', cleanup), \
                         patch.object(Path, 'unlink', unlink), \
                         contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = self.builder.main()
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout.getvalue(), '')
                    self.assertEqual(len(seen), 1)
                    self.assertIs(seen[0], winning, 'diagnostics must NOT restore the masked primary error')
                    if primary_fails and workspace_fails:
                        self.assertIs(workspace_error.__context__, primary)
                    if lock_fails:
                        self.assertIs(lock_error.__context__, workspace_error if workspace_fails else primary if primary_fails else None)
                    if not optin:
                        self.assertEqual(stderr.getvalue(), 'TC_IO\n')
                        continue
                    lines = stderr.getvalue().splitlines()
                    self.assertEqual(lines[-1], 'TC_IO')
                    records = [json.loads(line[len('TC_DIAG '):]) for line in lines[:-1]]
                    ends = {record['phase']: record for record in records if record['event'] == 'end'}
                    self.assertIn('workspace_cleanup', ends, 'workspace cleanup needs its own outcome')
                    self.assertIn('lock_cleanup', ends, 'lock cleanup needs a separate outcome')
                    self.assertEqual(ends['build_work']['tc_code'], 'TC_TIMEOUT' if primary_fails else 'none')
                    self.assertEqual(ends['workspace_cleanup']['outcome'], 'failure' if workspace_fails else 'success')
                    self.assertEqual(ends['lock_cleanup']['outcome'], 'failure' if lock_fails else 'success')
                    self.assertEqual(ends['workspace_cleanup']['errno'], 13 if workspace_fails else None)
                    self.assertEqual(ends['lock_cleanup']['errno'], 5 if lock_fails else None)
                    self.assertEqual(ends['cli']['exception_class'], 'OSError' if lock_fails else 'PermissionError')
                    self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
                    self.assertNotIn('password=', stderr.getvalue())
                    self.assertNotIn('/private', stderr.getvalue())
                    self.assertNotIn(str(root), stderr.getvalue())
    def test_tool_outcomes_distinguish_timeout_nonzero_spawn_and_interrupt_safely(self):
        import contextlib
        import inspect
        import io
        import json
        import signal
        import subprocess
        from unittest.mock import Mock, patch
        self.require_builder()
        self.assertIn('diagnostics', inspect.signature(self.builder.run_tool).parameters,
                      'tool boundary must accept explicit diagnostics without argv logging')
        payload = 'SYNTHETIC_PRIVATE_CANARY bearer=fake /private/content --private-argv'
        command = ['/private/tool', payload]
        variants = ['nonzero', 'spawn', 'timeout', 'interrupt', 'timeout-kill-error', 'timeout-drain-error', 'success']
        for name in variants:
            with self.subTest(outcome=name):
                process = Mock(pid=4321, returncode=0 if name == 'success' else 3)
                timeout_error = subprocess.TimeoutExpired(command, 120, output=payload.encode(), stderr=payload.encode())
                interrupt = KeyboardInterrupt(payload)
                if name.startswith('timeout'):
                    process.communicate.side_effect = [timeout_error,
                        OSError(5, payload) if name == 'timeout-drain-error' else (payload.encode(), payload.encode())]
                elif name == 'interrupt':
                    process.communicate.side_effect = [interrupt, (payload.encode(), payload.encode())]
                else:
                    process.communicate.return_value = (payload.encode(), payload.encode())
                spawn_error = PermissionError(13, payload, '/private/content')
                kill_error = PermissionError(13, payload) if name == 'timeout-kill-error' else None
                stderr, stdout = io.StringIO(), io.StringIO()
                with patch.object(self.builder.subprocess, 'Popen', side_effect=spawn_error if name == 'spawn' else None,
                                  return_value=process) as popen, \
                     patch.object(self.builder.os, 'killpg', side_effect=kill_error) as killpg, \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    if name == 'success':
                        result = self.builder.run_tool(command, cwd=self.base, env={'TEST': payload},
                            timeout=120, code='TC_BUILD', diagnostics=self.builder.Diagnostics())
                        self.assertEqual(result, payload.encode())
                    else:
                        expected_type = KeyboardInterrupt if name == 'interrupt' else OSError if name in {'timeout-kill-error', 'timeout-drain-error'} else self.builder.BuildRefusal
                        with self.assertRaises(expected_type) as caught:
                            self.builder.run_tool(command, cwd=self.base, env={'TEST': payload},
                                timeout=120, code='TC_BUILD', diagnostics=self.builder.Diagnostics())
                        if name == 'interrupt':
                            self.assertIs(caught.exception, interrupt)
                        elif expected_type is self.builder.BuildRefusal:
                            self.assertEqual(str(caught.exception), 'TC_TIMEOUT' if name == 'timeout' else 'TC_BUILD')
                    self.assertTrue(popen.call_args.kwargs['start_new_session'])
                    self.assertIs(popen.call_args.kwargs['stdout'], subprocess.PIPE)
                    self.assertIs(popen.call_args.kwargs['stderr'], subprocess.PIPE)
                    if name.startswith('timeout') or name == 'interrupt':
                        killpg.assert_called_once_with(4321, signal.SIGKILL)
                        self.assertEqual(process.communicate.call_count, 1 if name == 'timeout-kill-error' else 2)
                    else:
                        killpg.assert_not_called()
                records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
                events = [record['event'] for record in records]
                expected_event = 'tool_timeout' if name.startswith('timeout') else 'tool_interrupted' if name == 'interrupt' else 'tool_spawn_error' if name == 'spawn' else 'tool_nonzero' if name == 'nonzero' else None
                if expected_event:
                    self.assertIn(expected_event, events, 'tool outcome must be observed before kill/drain or cleanup can mask it')
                self.assertEqual(records[0]['event'], 'start')
                self.assertEqual(records[-1]['event'], 'end')
                self.assertEqual(records[-1]['outcome'], 'success' if name == 'success' else 'failure')
                if name.startswith('timeout'):
                    observed = next(record for record in records if record['event'] == 'tool_timeout')
                    self.assertEqual(observed['exception_class'], 'TimeoutExpired')
                self.assertEqual(stdout.getvalue(), '')
                for private in ['SYNTHETIC_PRIVATE_CANARY', 'bearer=', '/private', '--private-argv', str(self.base), 'TEST']:
                    self.assertNotIn(private, stderr.getvalue())
        # Exercise actual build -> actual run_tool with fake Popen, not a mocked driver.
        root = source_fixture(self.base)
        version = Mock(returncode=0, pid=4322)
        version.communicate.return_value = (b'3.23.1', payload.encode())
        compiler = Mock(returncode=-9, pid=4323)
        compiler.communicate.side_effect = [subprocess.TimeoutExpired(command, 600, stderr=payload.encode()), (b'', b'')]
        stderr = io.StringIO()
        with patch.object(self.builder.subprocess, 'Popen', side_effect=[version, compiler]), \
             patch.object(self.builder.os, 'killpg') as killpg, contextlib.redirect_stderr(stderr):
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.build(root, diagnostics=self.builder.Diagnostics())
        self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
        records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
        self.assertIn('tool_timeout', [record['event'] for record in records], 'build must forward opt-in to the tool seam')
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
        killpg.assert_called_once_with(4323, signal.SIGKILL)
    def test_diagnostics_are_closed_schema_bounded_and_never_stringify_errors(self):
        import contextlib
        import io
        import json
        self.require_builder()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            diagnostics = self.builder.Diagnostics()
            for _ in range(1000):
                diagnostics.emit('cli', 'start')
        lines = stderr.getvalue().splitlines()
        self.assertGreater(len(lines), 0)
        self.assertLessEqual(len(lines), 64, 'diagnostics must have a fixed record cap')
        self.assertLessEqual(len(stderr.getvalue().encode()), 16384, 'diagnostics must have a fixed byte cap')
        self.assertTrue(all(len(line.encode()) <= 256 for line in lines))
        payload = 'SYNTHETIC_PRIVATE_CANARY bearer=fake /private/content\nTC_TIMEOUT --private-argv'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            diagnostics = self.builder.Diagnostics()
            diagnostics.emit(payload, 'start')
            diagnostics.emit('cli', payload)
            diagnostics.emit('cli', 'end', outcome=payload)
        self.assertEqual(len(stderr.getvalue()), 0, 'unrecognized fields must be dropped, not reflected')
        known_codes = {'TC_PATH', 'TC_SIZE', 'TC_SOURCE', 'TC_PIN', 'TC_ARTIFACT', 'TC_SOURCE_CHANGED',
                       'TC_TOOLCHAIN', 'TC_TIMEOUT', 'TC_BUILD', 'TC_BUSY', 'TC_ARGS', 'TC_INTERRUPTED', 'TC_IO'}
        unknown = type('SYNTHETIC_PRIVATE_CANARY', (OSError,), {'__str__': lambda self: (_ for _ in ()).throw(AssertionError('must not stringify'))})
        cases = [(self.builder.BuildRefusal(code), 'BuildRefusal', None, code) for code in sorted(known_codes)]
        cases += [(self.builder.BuildRefusal(payload), 'BuildRefusal', None, 'none'),
                  (self.builder.BuildRefusal('TC_TIMEOUT', payload), 'BuildRefusal', None, 'none'),
                  (unknown(13, payload), 'other', None, 'none')]
        for klass in [FileExistsError, IsADirectoryError, NotADirectoryError, ProcessLookupError,
                      BrokenPipeError, TimeoutError, BlockingIOError, InterruptedError]:
            cases.append((klass(5, payload, '/private/content'), klass.__name__, 5, 'none'))
        cases += [(OSError(value, payload), 'PermissionError' if value is True else 'OSError', None, 'none') for value in [-1, 100000, True, 'SYNTHETIC_PRIVATE_CANARY']]
        for number, (error, klass, error_number, code) in enumerate(cases):
            with self.subTest(case=number):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.builder.Diagnostics().emit('cli', 'end', outcome='failure', error=error)
                record = json.loads(stderr.getvalue()[len('TC_DIAG '):])
                self.assertEqual(set(record), {'phase', 'event', 'outcome', 'exception_class', 'errno', 'tc_code'})
                self.assertEqual((record['exception_class'], record['errno'], record['tc_code']), (klass, error_number, code))
                for private in ['SYNTHETIC_PRIVATE_CANARY', 'bearer=', '/private', '--private-argv']:
                    self.assertNotIn(private, stderr.getvalue())
    def test_diagnostic_sink_failures_do_not_mask_primary_or_prevent_group_kill(self):
        import contextlib
        import io
        import signal
        import subprocess
        import sys
        from unittest.mock import Mock, patch
        self.require_builder()
        payload = 'SYNTHETIC_PRIVATE_CANARY password=fake /private/content'
        for fault in [OSError(5, payload), ValueError(payload), RuntimeError(payload)]:
            with self.subTest(fault=type(fault).__name__):
                class BrokenSink:
                    def write(self, text):
                        raise fault
                    def flush(self):
                        raise fault
                primary = self.builder.BuildRefusal('TC_TIMEOUT')
                seen = None
                with contextlib.redirect_stderr(BrokenSink()):
                    try:
                        with self.builder.diagnostic_phase(self.builder.Diagnostics(), 'cli'):
                            raise primary
                    except BaseException as error:
                        seen = error
                self.assertTrue(seen is primary, 'diagnostic sink errors must not replace the primary exception')
                process = Mock(returncode=-9, pid=4567)
                process.communicate.side_effect = [subprocess.TimeoutExpired(['/private/tool'], 600, stderr=payload.encode()), (b'', b'')]
                with patch.object(self.builder.subprocess, 'Popen', return_value=process), \
                     patch.object(self.builder.os, 'killpg') as killpg, contextlib.redirect_stderr(BrokenSink()):
                    with self.assertRaises(self.builder.BuildRefusal) as caught:
                        self.builder.run_tool(['/private/tool'], cwd=self.base, env={}, timeout=600,
                            code='TC_BUILD', diagnostics=self.builder.Diagnostics())
                self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
                killpg.assert_called_once_with(4567, signal.SIGKILL)
        stdout = io.StringIO()
        with patch.object(sys, 'stderr', None), contextlib.redirect_stdout(stdout):
            self.builder.Diagnostics().emit('cli', 'start')
        self.assertEqual(stdout.getvalue(), '', 'missing stderr must not redirect diagnostic records into JSON stdout')
    def test_publication_cleanup_observes_original_error_without_fixing_masking(self):
        import contextlib
        import inspect
        import io
        import json
        from unittest.mock import patch
        self.require_builder()
        self.assertIn('diagnostics', inspect.signature(self.builder.publish_js).parameters,
                      'publication must distinguish write failure from temporary cleanup failure')
        original_replace, original_unlink = os.replace, Path.unlink
        payload = 'SYNTHETIC_PRIVATE_CANARY password=fake /private/content'
        for number, (write_fails, cleanup_fails) in enumerate([(True, True), (True, False), (False, True), (False, False)]):
            for optin in [False, True]:
                with self.subTest(case=number, optin=optin):
                    case = self.base / (str(number) + '-' + str(optin))
                    case.mkdir()
                    root = source_fixture(case)
                    target = root / self.builder.TARGET
                    target.parent.mkdir(parents=True)
                    old = b'/* stale synthetic fixture */'
                    target.write_bytes(old)
                    primary, cleanup_error = OSError(5, payload), PermissionError(13, payload)
                    def replace(source, destination):
                        if write_fails:
                            raise primary
                        return original_replace(source, destination)
                    def unlink(path, *args, **kwargs):
                        if path.name.startswith('.hero-') and cleanup_fails:
                            raise cleanup_error
                        return original_unlink(path, *args, **kwargs)
                    stderr = io.StringIO()
                    with patch.object(self.builder, 'run_tool', side_effect=self.fake_successful_tool), \
                         patch.object(self.builder.os, 'replace', replace), patch.object(Path, 'unlink', unlink), \
                         contextlib.redirect_stderr(stderr):
                        if write_fails or cleanup_fails:
                            with self.assertRaises(OSError) as caught:
                                self.builder.build(root, diagnostics=self.builder.Diagnostics() if optin else None)
                            self.assertIs(caught.exception, cleanup_error if cleanup_fails else primary)
                            if write_fails and cleanup_fails:
                                self.assertIs(cleanup_error.__context__, primary)
                        else:
                            result = self.builder.build(root, diagnostics=self.builder.Diagnostics() if optin else None)
                            self.assertEqual(result['sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
                    self.assertEqual(target.read_bytes(), old if write_fails else b'/* synthetic tool fixture, not compiled JS */\n')
                    self.assertFalse((root / '_build/.theme-client-driver.lock').exists())
                    if not optin:
                        self.assertEqual(stderr.getvalue(), '')
                        continue
                    records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
                    ends = {record['phase']: record for record in records if record['event'] == 'end'}
                    self.assertIn('publication_write', ends)
                    self.assertIn('publication_cleanup', ends)
                    self.assertEqual(ends['publication_write']['outcome'], 'failure' if write_fails else 'success')
                    self.assertEqual(ends['publication_cleanup']['outcome'], 'failure' if cleanup_fails else 'success')
                    self.assertEqual(ends['publication_write']['errno'], 5 if write_fails else None)
                    self.assertEqual(ends['publication_cleanup']['errno'], 13 if cleanup_fails else None)
                    self.assertEqual(ends['workspace_cleanup']['outcome'], 'success')
                    self.assertEqual(ends['lock_cleanup']['outcome'], 'success')
                    for private in ['SYNTHETIC_PRIVATE_CANARY', 'password=', '/private', str(root), 'hero.bc.js']:
                        self.assertNotIn(private, stderr.getvalue())
    def test_diagnostics_optin_requires_exact_flag_without_changing_legacy_options(self):
        import contextlib
        import io
        import json
        import sys
        from unittest.mock import patch
        self.require_builder()
        result = {'sha256': 'a' * 64, 'sources': {}, 'dune': '3.23.1'}
        for abbreviated in ['--d', '--diag', '--diagnostic']:
            with self.subTest(option=abbreviated):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(sys, 'argv', ['builder', abbreviated, '--site-root', str(self.base)]), \
                     patch.object(self.builder, 'build', return_value=result) as build, \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = self.builder.main()
                self.assertEqual(code, 2, 'only the exact diagnostic option may enable or accept diagnostics')
                self.assertEqual((stdout.getvalue(), stderr.getvalue()), ('', 'TC_ARGS\n'))
                build.assert_not_called()
        for argv, generic in [(['--unknown', 'SYNTHETIC_PRIVATE_CANARY'], 'TC_ARGS'),
                              (['--site-root', '../SYNTHETIC_PRIVATE_CANARY'], 'TC_PATH')]:
            with self.subTest(generic=generic):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(sys, 'argv', ['builder', '--diagnostics', *argv]), \
                     patch.object(self.builder, 'build') as build, \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = self.builder.main()
                self.assertEqual((code, stdout.getvalue(), stderr.getvalue().splitlines()[-1]), (2, '', generic))
                records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()[:-1]]
                self.assertEqual(records[-1]['tc_code'], generic)
                self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
                build.assert_not_called()
        for optin in [False, True]:
            stdout, stderr = io.StringIO(), io.StringIO()
            # Preserve the old --site-root abbreviation; no inherited env opt-in.
            argv = ['builder', '--site', str(self.base)] + (['--diagnostics'] if optin else [])
            with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'TC_DIAGNOSTICS': '1'}), \
                 patch.object(self.builder, 'build', return_value=result), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = self.builder.main()
            self.assertEqual((code, stdout.getvalue()), (0, json.dumps(result, sort_keys=True) + '\n'))
            if optin:
                records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
                self.assertEqual([record['event'] for record in records], ['start', 'end'])
                self.assertEqual(records[-1]['outcome'], 'success')
            else:
                self.assertEqual(stderr.getvalue(), '')
    def test_end_of_options_keeps_literal_diagnostics_token_opted_out(self):
        import contextlib
        import io
        import sys
        from unittest.mock import patch
        self.require_builder()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['builder', '--', '--diagnostics']), \
             patch.object(self.builder, 'build') as build, \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.builder.main()
        self.assertEqual((code, stdout.getvalue(), stderr.getvalue()), (2, '', 'TC_ARGS\n'),
                         'a literal after the option delimiter must not activate diagnostics')
        build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
