"""Locked source-only client builds. Real compiler evidence is opt-in below."""
from contextlib import contextmanager
import hashlib
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from test_safe_web import ROOT, TMP

SCRIPT = ROOT / 'scripts/build-theme-client.py'
OWNED_WORKER_AUDIT = []


def fixture_identity(pid):
    """Independent harness identity; never calls or patches the builder reader."""
    path = Path('/proc') / str(pid)
    try:
        owner = path.stat().st_uid
        fields = (path / 'stat').read_bytes().rsplit(b') ', 1)[1].split()
    except FileNotFoundError:
        return None
    return (pid, int(fields[19]), int(fields[3]), owner, fields[0].decode('ascii'), int(fields[2]))


@contextmanager
def actual_owned_worker(base):
    """Pin, kill and reap only these two synthetic processes, even on RED."""
    import ctypes
    import json
    import signal
    import subprocess
    import sys
    import time
    libc = ctypes.CDLL(None)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    ready, release = base / 'owned-worker-ready.json', base / 'owned-worker-release'
    worker = ('import json,os,time; from pathlib import Path; os.setpgid(0,0); '
              'f=Path("/proc/self/stat").read_bytes().rsplit(b") ",1)[1].split(); '
              'Path(' + repr(str(ready)) + ').write_text(json.dumps([os.getpid(),int(f[19]),'
              'int(f[3]),os.getuid(),f[0].decode("ascii"),int(f[2])])); time.sleep(30)')
    launcher = ('import subprocess,sys,time; from pathlib import Path; '
                'subprocess.Popen([sys.executable,"-B","-c",' + repr(worker) + '],'
                'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
                'release=Path(' + repr(str(release)) + '); '
                '\nwhile not release.exists(): time.sleep(.01)\nprint("synthetic-ok")')
    owned = []
    process = None
    real_send = signal.pidfd_send_signal
    def pin(pid, role):
        before = fixture_identity(pid)
        assert before is not None and before[3] == os.getuid()
        fd = os.pidfd_open(pid)
        owned.append((before, fd, role))
        after = fixture_identity(pid)
        assert after is not None and after[:4] == before[:4]
        return before
    try:
        process = subprocess.Popen([sys.executable, '-B', '-c', launcher], start_new_session=True,
                                   env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        leader = pin(process.pid, 'leader')
        assert leader[2] == process.pid
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists(), 'actual synthetic worker must complete its identity handshake'
        recorded = tuple(json.loads(ready.read_text()))
        member = pin(recorded[0], 'worker')
        assert member[:4] == recorded[:4] and member[2] == process.pid
        assert member[5] == member[0] != member[2], 'fixture must exercise a separate process group'
        yield process, member, release
    finally:
        try:
            for old, fd, role in reversed(owned):
                now = fixture_identity(old[0])
                if now and now[:4] == old[:4] and now[4] not in {'Z', 'X'}:
                    try:
                        real_send(fd, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if process is not None:
                if any(stream is not None and stream.closed for stream in (process.stdout, process.stderr)):
                    process.wait(timeout=2)
                    for stream in (process.stdout, process.stderr):
                        if stream is not None:
                            stream.close()
                else:
                    process.communicate(timeout=2)
            for old, fd, role in owned:
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    now = fixture_identity(old[0])
                    if now is None or now[:4] != old[:4]:
                        break
                    try:
                        os.waitpid(old[0], os.WNOHANG)
                    except ChildProcessError:
                        pass
                    time.sleep(.01)
                now = fixture_identity(old[0])
                reaped = now is None or now[:4] != old[:4]
                OWNED_WORKER_AUDIT.append(dict(role=role, pid=old[0], start=old[1], sid=old[2],
                                              uid=old[3], reaped=reaped))
                assert reaped, 'independent harness must reap every exact owned fixture process'
        finally:
            for _, fd, _ in owned:
                os.close(fd)
            assert libc.prctl(36, previous.value, 0, 0, 0) == 0


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
    for name in ['dune', 'dune-project', 'dune-workspace', 'flake.nix', 'flake.lock', 'devbox.json']:
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
        self.synthetic_dune = self.base / 'fixture-dune'
        self.synthetic_dune.write_text('#!/bin/sh\nexit 0\n')
        self.synthetic_dune.chmod(0o755)
        from unittest.mock import patch
        import sys
        if os.environ.get('TC_REAL_BUILD') != '1':
            self.tools = patch.object(self.builder.shutil, 'which', return_value=sys.executable)
            self.tools.start()
            self.addCleanup(self.tools.stop)

    def require_builder(self):
        self.assertIsNotNone(self.builder, 'locked source-only site client builder must exist')

    def test_devbox_bootstraps_in_owned_directory_then_hands_off_direct_dune(self):
        import json
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        (root / 'devbox.json').write_bytes((ROOT / 'devbox.json').read_bytes())
        (root / '.devbox').mkdir()
        (root / '.devbox/poison').write_text('SYNTHETIC_PRIVATE_CANARY')
        dune = self.base / 'dune'
        dune.write_text('#!/bin/sh\nexit 0\n')
        dune.chmod(0o755)
        calls = []
        def tool(command, *, cwd, env, timeout, code, **kwargs):
            calls.append((command, cwd, env))
            self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', str(env))
            self.assertNotIn('develop', command)
            if command[-1] == 'version':
                return b'0.18.4'
            if 'install' in command:
                bootstrap = Path(command[command.index('--config') + 1])
                self.assertNotEqual(bootstrap, root)
                self.assertEqual(bootstrap, Path(cwd))
                self.assertEqual(set(p.name for p in bootstrap.iterdir()), {'devbox.json'})
                self.assertEqual(json.loads((bootstrap / 'devbox.json').read_text())['packages'],
                                 ['github:NixOS/nixpkgs/' + self.builder.NIXPKGS_REV + '#dune'])
                self.assertLessEqual(timeout, 600)
                return b''
            if command[-2:] == ['/usr/bin/which', 'dune']:
                self.assertIn('run', command)
                return os.fsencode(dune)
            self.assertEqual(command[0], str(dune.resolve()), 'no Devbox or Nix wrapper after handoff')
            if command[1:] == ['--version']:
                return b'3.23.1'
            if command[1:] == ['build', 'theme/client/hero.bc.js']:
                self.assertLessEqual(timeout, 1800)
                self.assertGreater(timeout, 600)
                self.assertEqual(env['PATH'], str(dune.parent) + ':/usr/bin:/bin')
                self.assertEqual(env['DUNE_ROOT'], str(cwd))
                target = Path(cwd) / self.builder.TARGET
                self.assertFalse((Path(cwd) / '_build').exists())
                target.parent.mkdir(parents=True)
                target.write_bytes(b'/* synthetic fixture, never compiler evidence */\n')
                return b''
            if command[-2:] == ['ocamlc', '-version']:
                return b'5.5.1'
            if command[-2:] == ['js_of_ocaml', '--version']:
                return b'6.4.1'
            self.fail('unexpected handoff boundary')
        with patch.object(self.builder, 'run_tool', side_effect=tool), \
             patch.object(self.builder.shutil, 'which', side_effect=lambda name: '/usr/local/bin/devbox' if name == 'devbox' else '/usr/bin/nix'), \
             patch.dict(os.environ, {'GITHUB_TOKEN': 'SYNTHETIC_PRIVATE_CANARY'}):
            result = self.builder.build(root)
        self.assertTrue(any('install' in command for command, _, _ in calls),
                        'driver must install Dune itself, not depend on repository .devbox')
        self.assertEqual(result['devbox'], '0.18.4')
        self.assertEqual(result['dune'], '3.23.1')
        self.assertEqual(result['sources']['devbox.json'], hashlib.sha256((root / 'devbox.json').read_bytes()).hexdigest())
        self.assertEqual((root / '.devbox/poison').read_text(), 'SYNTHETIC_PRIVATE_CANARY')

    def test_copy_includes_only_explicit_root_lock_and_client_sources(self):
        self.require_builder()
        root = source_fixture(self.base)
        fresh = self.base / 'fresh'
        fresh.mkdir()
        before = self.builder.source_manifest(root)
        self.assertEqual(self.builder.copy_sources(root, fresh), before)
        expected = {'dune', 'dune-project', 'dune-workspace', 'flake.nix', 'flake.lock', 'devbox.json',
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
                        'client must actually compile with Devbox-provided Dune, not reuse legacy JS')
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
    @unittest.skipUnless(os.name == 'posix' and Path('/proc/self/stat').exists(), 'Linux owned-session cancellation')
    def test_timeout_terminates_separate_group_redirected_pipe_worker(self):
        import json
        import signal
        import sys
        import time
        self.require_builder()
        import ctypes
        libc = ctypes.CDLL(None)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        identity_file = self.base / 'worker-identity.json'
        marker = self.base / 'worker-survived'
        worker = ('import json,os,time; from pathlib import Path; os.setpgid(0,0); '
                  'f=Path("/proc/self/stat").read_text().split(") ",1)[1].split(); '
                  'Path(' + repr(str(identity_file)) + ').write_text(json.dumps(dict(pid=os.getpid(),'
                  'start=int(f[19]),sid=int(f[3]),pgid=int(f[2])))); '
                  'time.sleep(3); Path(' + repr(str(marker)) + ').write_text("synthetic"); time.sleep(2)')
        launcher = ('import subprocess,time; from pathlib import Path; '
                    'subprocess.Popen([' + repr(sys.executable) + ',"-B","-c",' + repr(worker) + '],'
                    'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
                    'time.sleep(4)')
        try:
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.run_tool([sys.executable, '-B', '-c', launcher], cwd=self.base,
                                      env={'PATH': '/usr/bin:/bin'}, timeout=.6, code='TC_BUILD')
            self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
            self.assertTrue(identity_file.exists(), 'worker must have entered its separate group before timeout')
            info = json.loads(identity_file.read_text())
            self.assertEqual(info['pgid'], info['pid'])
            self.assertNotEqual(info['sid'], info['pgid'])
            path = Path('/proc') / str(info['pid']) / 'stat'
            state = path.read_text().split(') ', 1)[1].split()[0] if path.exists() else None
            self.assertIn(state, [None, 'Z', 'X'], 'all owned workers must terminate before run_tool returns')
            self.assertFalse(marker.exists(), 'owned workers must not race workspace cleanup')
        finally:
            # The RED run must not leak its deliberately surviving worker.
            if identity_file.exists():
                info = json.loads(identity_file.read_text())
                path = Path('/proc') / str(info['pid']) / 'stat'
                if path.exists():
                    fields = path.read_text().split(') ', 1)[1].split()
                    if int(fields[19]) == info['start'] and int(fields[3]) == info['sid'] and fields[0] != 'Z':
                        os.kill(info['pid'], signal.SIGKILL)
                deadline = time.monotonic() + 1
                while path.exists() and time.monotonic() < deadline:
                    try:
                        os.waitpid(info['pid'], os.WNOHANG)
                    except ChildProcessError:
                        pass
                    time.sleep(.01)
                self.assertFalse(path.exists(), 'owned fixture worker must be reaped')
            self.assertEqual(libc.prctl(36, previous.value, 0, 0, 0), 0)

    def test_missing_initial_leader_identity_retains_workspace_with_actual_worker(self):
        from unittest.mock import patch
        self.require_builder()
        assert self.builder is not None
        root = source_fixture(self.base)
        target = root / self.builder.TARGET
        target.parent.mkdir(parents=True)
        old = b'/* previous synthetic JS */'
        target.write_bytes(old)
        run_tool, identity_reader = self.builder.run_tool, self.builder.process_identity
        with actual_owned_worker(self.base) as (process, worker, release):
            def tool(command, **kwargs):
                if command[1:] != ['build', 'theme/client/hero.bc.js']:
                    return self.fake_successful_tool(command, **kwargs)
                assert self.builder is not None
                fresh_target = Path(kwargs['cwd']) / self.builder.TARGET
                fresh_target.parent.mkdir(parents=True)
                fresh_target.write_bytes(b'/* new synthetic JS, not compiler evidence */')
                release.touch()
                with patch.object(self.builder.subprocess, 'Popen', return_value=process), \
                     patch.object(self.builder, 'process_identity',
                                  side_effect=lambda pid: None if pid == process.pid else identity_reader(pid)):
                    return run_tool(command, **kwargs)
            with patch.object(self.builder, 'run_tool', side_effect=tool), \
                 patch.object(self.builder.signal, 'pidfd_send_signal') as signalled:
                with self.assertRaises(self.builder.BuildRefusal) as caught:
                    self.builder.build(root)
            self.assertEqual(str(caught.exception), 'TC_TOOLCHAIN')
            self.assertTrue(getattr(caught.exception, 'unsafe_workspace_cleanup', False))
            signalled.assert_not_called()
            self.assertEqual(target.read_bytes(), old)
            self.assertTrue((root / '_build/.theme-client-driver.lock').is_file())
            self.assertTrue(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()))
            current = fixture_identity(worker[0])
            self.assertIsNotNone(current, 'unverified worker must not be signalled or hidden by cleanup')
            assert current is not None
            self.assertEqual(current[:4], worker[:4])
            self.assertNotIn(current[4], {'Z', 'X'})

    def test_unreadable_tracked_worker_retains_workspace_after_leader_exit(self):
        from unittest.mock import patch
        self.require_builder()
        assert self.builder is not None
        root = source_fixture(self.base)
        target = root / self.builder.TARGET
        target.parent.mkdir(parents=True)
        old = b'/* previous synthetic JS */'
        target.write_bytes(old)
        run_tool, identity_reader = self.builder.run_tool, self.builder.process_identity
        session_type, original_iterdir = self.builder.OwnedSession, Path.iterdir
        hidden = [False]
        sessions = []
        with actual_owned_worker(self.base) as (process, worker, release):
            def session_factory(child):
                session = session_type(child)
                self.assertTrue(any(member[:4] == worker[:4] for member in session.live_members()))
                self.assertIn(worker[:2], session.members, 'identity must be tracked before its read fails')
                sessions.append(session)
                hidden[0] = True
                release.touch()
                return session
            def iterdir(path):
                entries = original_iterdir(path)
                if path == Path('/proc') and hidden[0]:
                    # Force the tracked-identity check, independently of rediscovery.
                    return (entry for entry in entries if entry.name != str(worker[0]))
                return entries
            def tool(command, **kwargs):
                if command[1:] != ['build', 'theme/client/hero.bc.js']:
                    return self.fake_successful_tool(command, **kwargs)
                assert self.builder is not None
                fresh_target = Path(kwargs['cwd']) / self.builder.TARGET
                fresh_target.parent.mkdir(parents=True)
                fresh_target.write_bytes(b'/* new synthetic JS, not compiler evidence */')
                with patch.object(self.builder.subprocess, 'Popen', return_value=process), \
                     patch.object(self.builder, 'OwnedSession', side_effect=session_factory), \
                     patch.object(self.builder, 'process_identity', side_effect=lambda pid:
                                  None if hidden[0] and pid == worker[0] else identity_reader(pid)), \
                     patch.object(Path, 'iterdir', iterdir):
                    return run_tool(command, **kwargs)
            with patch.object(self.builder, 'run_tool', side_effect=tool), \
                 patch.object(self.builder.signal, 'pidfd_send_signal') as signalled:
                with self.assertRaises(self.builder.BuildRefusal) as caught:
                    self.builder.build(root)
            self.assertEqual(str(caught.exception), 'TC_TOOLCHAIN')
            self.assertTrue(getattr(caught.exception, 'unsafe_workspace_cleanup', False))
            self.assertEqual(len(sessions), 1)
            self.assertEqual(process.returncode, 0, 'leader has exited; its worker still needs proof')
            signalled.assert_not_called()
            self.assertEqual(target.read_bytes(), old)
            self.assertTrue((root / '_build/.theme-client-driver.lock').is_file())
            self.assertTrue(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()))
            current = fixture_identity(worker[0])
            assert current is not None
            self.assertEqual(current[:4], worker[:4])
            self.assertNotIn(current[4], {'Z', 'X'})

    def test_missing_identity_safe_cancellation_refuses_before_spawning(self):
        from unittest.mock import Mock, patch
        self.require_builder()
        process = Mock(pid=4321, returncode=0)
        process.communicate.return_value = (b'fixture', b'')
        with patch.object(self.builder.os, 'pidfd_open', None), \
             patch.object(self.builder.subprocess, 'Popen', return_value=process) as popen:
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.run_tool(['fixture'], cwd=self.base, env={}, timeout=1, code='TC_BUILD')
        self.assertEqual(str(caught.exception), 'TC_TOOLCHAIN')
        popen.assert_not_called()

    def test_nonzero_worker_cancel_error_preserves_build_code_and_retains_ownership(self):
        from unittest.mock import Mock, patch
        self.require_builder()
        process = Mock(pid=12345, returncode=7)
        process.communicate.return_value = (b'SYNTHETIC_PRIVATE_CANARY', b'SYNTHETIC_PRIVATE_CANARY')
        session = Mock()
        session.live_members.return_value = [object()]
        session.cancel.side_effect = PermissionError(13, 'SYNTHETIC_PRIVATE_CANARY')
        with patch.object(self.builder.subprocess, 'Popen', return_value=process), \
             patch.object(self.builder, 'OwnedSession', return_value=session):
            try:
                self.builder.run_tool(['fixture'], cwd=self.base, env={}, timeout=1, code='TC_BUILD')
            except self.builder.BuildRefusal as error:
                self.assertEqual(str(error), 'TC_BUILD')
                self.assertTrue(getattr(error, 'unsafe_workspace_cleanup', False))
            except OSError:
                self.fail('cancellation cleanup must not replace the nonzero build code')
            else:
                self.fail('nonzero build must refuse')
        session.cancel.assert_called_once_with()

    def test_pipe_io_failure_cancels_owned_session_before_propagating_primary(self):
        import contextlib
        import io
        from unittest.mock import Mock, patch
        self.require_builder()
        primary = OSError(5, 'SYNTHETIC_PRIVATE_CANARY')
        process = Mock(pid=12345, returncode=-9)
        process.communicate.side_effect = primary
        session = Mock()
        session.live_members.return_value = []
        stderr = io.StringIO()
        with patch.object(self.builder.subprocess, 'Popen', return_value=process), \
             patch.object(self.builder, 'OwnedSession', return_value=session), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(OSError) as caught:
                self.builder.run_tool(['fixture'], cwd=self.base, env={}, timeout=1, code='TC_BUILD',
                                      diagnostics=self.builder.Diagnostics())
        self.assertIs(caught.exception, primary)
        session.cancel.assert_called_once_with()
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())

    def test_unverified_cancellation_keeps_owned_workspace_and_lock_without_masking_timeout(self):
        import contextlib
        import io
        import json
        import subprocess
        from unittest.mock import Mock, patch
        self.require_builder()
        root = source_fixture(self.base)
        original = self.builder.run_tool
        process = Mock(pid=12345, returncode=-9)
        process.communicate.side_effect = subprocess.TimeoutExpired(['fixture'], 1)
        session = Mock()
        session.cancel.side_effect = PermissionError(13, 'SYNTHETIC_PRIVATE_CANARY')
        session.live_members.return_value = []
        def tool(command, **kwargs):
            if command[1:] == ['build', 'theme/client/hero.bc.js']:
                return original(command, **kwargs)
            return self.fake_successful_tool(command, **kwargs)
        stderr = io.StringIO()
        try:
            with patch.object(self.builder, 'run_tool', side_effect=tool), \
                 patch.object(self.builder.subprocess, 'Popen', return_value=process), \
                 patch.object(self.builder, 'OwnedSession', return_value=session), \
                 contextlib.redirect_stderr(stderr):
                with self.assertRaises(self.builder.BuildRefusal) as caught:
                    self.builder.build(root, diagnostics=self.builder.Diagnostics())
            self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
            self.assertTrue((root / '_build/.theme-client-driver.lock').is_file(), 'unverified cancellation must retain ownership')
            self.assertTrue(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()),
                            'unsafe workspace removal must be skipped, not raced')
            self.assertFalse((root / self.builder.TARGET).exists())
            records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
            skipped = {record['phase'] for record in records if record['event'] == 'cleanup_skipped'}
            self.assertEqual(skipped, {'workspace_cleanup', 'lock_cleanup'})
            self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
        finally:
            # No real worker was spawned by this explicit tool-boundary fixture.
            shutil.rmtree(root / '_build', ignore_errors=True)

    def test_graceful_signal_error_still_attempts_verified_hard_cancellation(self):
        import signal
        from unittest.mock import Mock, patch
        self.require_builder()
        process = Mock(pid=12345)
        process.communicate.return_value = (b'', b'')
        identity = (12345, 10, 12345, os.getuid(), 'S', 12345)
        with patch.object(self.builder, 'process_identity', return_value=identity):
            session = self.builder.OwnedSession(process)
        live = [True]
        def send(member, number):
            if number == signal.SIGINT:
                raise PermissionError(13, 'SYNTHETIC_PRIVATE_CANARY')
            self.assertEqual(number, signal.SIGKILL)
            live[0] = False
        with patch.object(session, 'live_members', side_effect=lambda: [identity] if live[0] else []), \
             patch.object(session, 'send', side_effect=send) as signalled, \
             patch.object(session, 'GRACE_SECONDS', .01):
            try:
                session.cancel()
            except PermissionError:
                self.fail('graceful signal failure must not bypass hard cancellation')
        self.assertEqual([call.args[1] for call in signalled.call_args_list], [signal.SIGINT, signal.SIGKILL])
        process.communicate.assert_called_once_with(timeout=2)

    def test_unreadable_identity_at_signal_boundary_refuses_without_signalling(self):
        import signal
        from unittest.mock import patch
        self.require_builder()
        assert self.builder is not None
        with actual_owned_worker(self.base) as (_, worker, _release):
            with patch.object(self.builder, 'process_identity', return_value=None), \
                 patch.object(self.builder.signal, 'pidfd_send_signal') as send:
                with self.assertRaises(self.builder.BuildRefusal) as caught:
                    self.builder.OwnedSession.send(worker, signal.SIGKILL)
            self.assertEqual(str(caught.exception), 'TC_TOOLCHAIN')
            send.assert_not_called()
            current = fixture_identity(worker[0])
            assert current is not None
            self.assertEqual(current[:4], worker[:4])
            self.assertNotIn(current[4], {'Z', 'X'})

    def test_pidfd_signal_rechecks_start_identity_and_never_hits_reused_pid(self):
        import signal
        from unittest.mock import patch
        self.require_builder()
        old = (12345, 10, 12345, os.getuid(), 'S', 12345)
        reused = (12345, 11, 12345, os.getuid(), 'S', 12345)
        with patch.object(self.builder.os, 'pidfd_open', return_value=99), \
             patch.object(self.builder, 'process_identity', return_value=reused), \
             patch.object(self.builder.signal, 'pidfd_send_signal') as send, \
             patch.object(self.builder.os, 'close') as close:
            self.builder.OwnedSession.send(old, signal.SIGKILL)
        send.assert_not_called()
        close.assert_called_once_with(99)

    def test_cancellation_allows_scheduler_shutdown_and_leaves_other_sessions_alone(self):
        import subprocess
        import sys
        import textwrap
        self.require_builder()
        shutdown = self.base / 'scheduler-shutdown'
        launcher = self.base / 'scheduler-fixture.py'
        launcher.write_text(textwrap.dedent('''
            import os, signal, subprocess, sys, time
            from pathlib import Path
            worker = subprocess.Popen([sys.executable, '-B', '-c',
                'import os,time; os.setpgid(0,0); time.sleep(5)'],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            def stop(number, frame):
                worker.terminate()
                worker.wait(timeout=1)
                Path(sys.argv[1]).write_text('synthetic graceful shutdown')
                raise SystemExit(0)
            signal.signal(signal.SIGINT, stop)
            time.sleep(5)
        '''))
        outsider = subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(5)'],
                                    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.run_tool([sys.executable, '-B', str(launcher), str(shutdown)], cwd=self.base,
                                      env={'PATH': '/usr/bin:/bin'}, timeout=.4, code='TC_BUILD')
            self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
            self.assertTrue(shutdown.exists(), 'scheduler must receive SIGINT and reap its separate-group worker')
            self.assertIsNone(outsider.poll(), 'unrelated sessions must never be signalled')
        finally:
            outsider.kill()
            outsider.wait(timeout=2)

    def test_source_readback_refuses_late_client_change_without_replacing_previous_js(self):
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        target = root / self.builder.TARGET
        target.parent.mkdir(parents=True)
        target.write_bytes(b'/* stale synthetic */')
        def tool(command, **kwargs):
            result = self.fake_successful_tool(command, **kwargs)
            if command[1:] == ['build', 'theme/client/hero.bc.js']:
                (root / 'theme/client/hero.ml').write_text('let () = ()\n')
            return result
        with patch.object(self.builder, 'run_tool', side_effect=tool):
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.build(root)
        self.assertEqual(str(caught.exception), 'TC_SOURCE_CHANGED')
        self.assertEqual(target.read_bytes(), b'/* stale synthetic */')

    def test_bootstrap_refuses_unpinned_devbox_before_installation(self):
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        with patch.object(self.builder, 'run_tool', return_value=b'0.18.5') as tool:
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.build(root)
        self.assertEqual(str(caught.exception), 'TC_TOOLCHAIN')
        self.assertEqual(tool.call_count, 1)
        self.assertFalse((root / self.builder.TARGET).exists())

    def test_enotempty_is_secondary_cleanup_classification_not_worker_evidence(self):
        import contextlib
        import io
        import json
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        original = self.builder.tempfile.TemporaryDirectory.cleanup
        def cleanup(workspace):
            original(workspace)
            raise OSError(39, 'SYNTHETIC_PRIVATE_CANARY')
        stderr = io.StringIO()
        with patch.object(self.builder, 'run_tool', side_effect=self.builder.BuildRefusal('TC_TIMEOUT')), \
             patch.object(self.builder.tempfile.TemporaryDirectory, 'cleanup', cleanup), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.build(root, diagnostics=self.builder.Diagnostics())
        self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
        records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
        cleanup_end = next(record for record in records if record['phase'] == 'workspace_cleanup' and record['event'] == 'end')
        self.assertEqual((cleanup_end['exception_class'], cleanup_end['errno']), ('OSError', 39))
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
        self.assertNotIn('worker', stderr.getvalue(), 'ENOTEMPTY alone says nothing about worker survival')

    def test_identity_reader_accepts_non_ascii_worker_name_without_reading_payloads(self):
        import subprocess
        import sys
        import time
        self.require_builder()
        worker = subprocess.Popen([sys.executable, '-B', '-c',
            'import ctypes,time; ctypes.CDLL(None).prctl(15,ctypes.c_char_p(bytes([255,254,65])),0,0,0); time.sleep(4)'])
        try:
            time.sleep(.1)
            identity = self.builder.process_identity(worker.pid)
            self.assertIsNotNone(identity, 'process name bytes must not hide an owned worker')
            self.assertEqual(identity[0], worker.pid)
            self.assertEqual(identity[3], os.getuid())
        finally:
            worker.kill()
            worker.wait(timeout=2)

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
        if command[-1] == 'version':
            return b'0.18.4'
        if 'install' in command:
            self.assertLessEqual(timeout, 600)
            bootstrap = Path(command[command.index('--config') + 1])
            self.assertEqual({p.name for p in bootstrap.iterdir()}, {'devbox.json'})
            return b''
        if command[-2:] == ['/usr/bin/which', 'dune']:
            return os.fsencode(self.synthetic_dune)
        self.assertEqual(command[0], str(self.synthetic_dune))
        if command[1:] == ['--version']:
            self.assertLessEqual(timeout, 120)
            return b'3.23.1'
        if command[1:] == ['build', 'theme/client/hero.bc.js']:
            self.assertLessEqual(timeout, 1800)
            self.assertGreater(timeout, 600)
            self.assertEqual(code, 'TC_BUILD')
            target = Path(cwd) / self.builder.TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(b'/* synthetic tool fixture, not compiled JS */\n')
            return b''
        self.assertLessEqual(timeout, 120)
        if command[-2:] == ['ocamlc', '-version']:
            return b'5.5.1'
        if command[-2:] == ['js_of_ocaml', '--version']:
            return b'6.4.1'
        self.fail('unexpected synthetic tool boundary')

    def test_total_deadline_stops_after_exhausted_bootstrap_before_compile_or_publication(self):
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        now = [100.]
        seen = []
        def tool(command, **kwargs):
            seen.append(command)
            if 'install' in command:
                now[0] = 2000.
            return self.fake_successful_tool(command, **kwargs)
        with patch.object(self.builder, 'run_tool', side_effect=tool), \
             patch.object(self.builder.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.build(root)
        self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
        self.assertFalse(any('build' in command for command in seen), 'shared total budget must stop the compiler')
        self.assertFalse((root / self.builder.TARGET).exists(), 'deadline refusal must not publish fresh JS')

    def test_expired_publication_fsync_never_replaces_old_or_absent_target(self):
        from unittest.mock import patch
        self.require_builder()
        assert self.builder is not None
        real_fsync, real_replace = os.fsync, os.replace
        for existing in (False, True):
            with self.subTest(existing=existing):
                case = self.base / str(existing)
                case.mkdir()
                root = source_fixture(case)
                target = root / self.builder.TARGET
                old = b'/* previous synthetic JS */'
                if existing:
                    target.parent.mkdir(parents=True)
                    target.write_bytes(old)
                now = [0.]
                synced = []
                def tool(command, **kwargs):
                    value = self.fake_successful_tool(command, **kwargs)
                    if command[-2:] == ['js_of_ocaml', '--version']:
                        now[0] = 1798.
                    return value
                def fsync(fd):
                    real_fsync(fd)
                    synced.append(fd)
                    now[0] = 1801.  # Actual staging boundary exhausted the shared deadline.
                with patch.object(self.builder, 'run_tool', side_effect=tool), \
                     patch.object(self.builder.time, 'monotonic', side_effect=lambda: now[0]), \
                     patch.object(self.builder.os, 'fsync', side_effect=fsync), \
                     patch.object(self.builder.os, 'replace', wraps=real_replace) as replace:
                    with self.assertRaises(self.builder.BuildRefusal) as caught:
                        self.builder.build(root)
                self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
                self.assertEqual(len(synced), 1, 'real staging fsync must be exercised')
                replace.assert_not_called()
                if existing:
                    self.assertEqual(target.read_bytes(), old)
                else:
                    self.assertFalse(target.exists(), 'expired staging cannot create a new JS target')
                self.assertEqual(list(target.parent.glob('.hero-*.js')), [])
                self.assertFalse((root / '_build/.theme-client-driver.lock').exists())
                self.assertFalse(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()))

    def test_authorized_atomic_commit_does_not_time_out_during_postcommit_cleanup(self):
        from unittest.mock import patch
        self.require_builder()
        assert self.builder is not None
        root = source_fixture(self.base)
        target = root / self.builder.TARGET
        target.parent.mkdir(parents=True)
        target.write_bytes(b'/* previous synthetic JS */')
        now = [0.]
        committed = []
        real_replace = os.replace
        real_cleanup = self.builder.tempfile.TemporaryDirectory.cleanup
        def tool(command, **kwargs):
            value = self.fake_successful_tool(command, **kwargs)
            if command[-2:] == ['js_of_ocaml', '--version']:
                now[0] = 1798.
            return value
        def replace(source, destination):
            self.assertEqual(now[0], 1798., 'real replace must start with an authorized deadline')
            value = real_replace(source, destination)
            committed.append(target.read_bytes())
            now[0] = 1801.  # The real atomic commit completed; it cannot be uncommitted.
            return value
        def cleanup(workspace):
            real_cleanup(workspace)
            now[0] = 1810.  # Synchronous filesystem cleanup is outside the commit budget.
        with patch.object(self.builder, 'run_tool', side_effect=tool), \
             patch.object(self.builder.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(self.builder.os, 'replace', side_effect=replace), \
             patch.object(self.builder.tempfile.TemporaryDirectory, 'cleanup', cleanup):
            try:
                result = self.builder.build(root)
            except self.builder.BuildRefusal as error:
                self.fail('authorized atomic commit must not become ' + str(error) + ' from a postcommit clock')
        expected = b'/* synthetic tool fixture, not compiled JS */\n'
        self.assertEqual(committed, [expected])
        self.assertEqual(target.read_bytes(), expected)
        self.assertEqual(result['sha256'], hashlib.sha256(expected).hexdigest())
        self.assertEqual(result['timings']['total_seconds'], 1810.)
        self.assertFalse((root / '_build/.theme-client-driver.lock').exists())
        self.assertFalse(any(p.name.startswith('theme-client-source-') for p in (root / '_build').iterdir()))

    def test_success_timings_use_monotonic_and_only_closed_finite_numeric_fields(self):
        import json
        import math
        from unittest.mock import patch
        self.require_builder()
        root = source_fixture(self.base)
        now = [10.]
        def tool(command, **kwargs):
            if command[1:] == ['--version']:
                now[0] = 13.
            elif command[1:] == ['build', 'theme/client/hero.bc.js']:
                now[0] = 21.
            elif command[-2:] == ['ocamlc', '-version']:
                now[0] = 22.
            elif command[-2:] == ['js_of_ocaml', '--version']:
                now[0] = 23.
            return self.fake_successful_tool(command, **kwargs)
        with patch.object(self.builder, 'run_tool', side_effect=tool), \
             patch.object(self.builder.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(self.builder.time, 'time', side_effect=AssertionError('wall clock is not elapsed time')):
            result = self.builder.build(root)
        self.assertIn('timings', result, 'successful builds must report bootstrap, compile and total separately')
        self.assertEqual(result['timings'], dict(bootstrap_seconds=3., compile_seconds=8., total_seconds=13.))
        self.assertTrue(all(type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1800
                            for value in result['timings'].values()))
        self.assertNotIn(str(self.base), json.dumps(result))

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
                    'workspace_setup', 'source_copy', 'environment_setup', 'bootstrap',
                    'devbox_version', 'devbox_install', 'dune_resolve',
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
    def test_recovery_api_propagates_fresh_cleanup_failures_inside_handled_caller_error(self):
        import contextlib
        import io
        import json
        import sys
        from unittest.mock import patch
        self.require_builder()
        assert self.builder is not None
        original_cleanup = self.builder.tempfile.TemporaryDirectory.cleanup
        original_unlink = Path.unlink
        for phase in ('workspace_cleanup', 'publication_cleanup', 'lock_cleanup'):
            for optin in (False, True):
                with self.subTest(phase=phase, diagnostics=optin):
                    case = self.base / (phase + '-' + str(optin))
                    case.mkdir()
                    root = source_fixture(case)
                    fault = PermissionError(13, 'SYNTHETIC_PRIVATE_CANARY')
                    calls = []
                    def cleanup(workspace):
                        original_cleanup(workspace)
                        if phase == 'workspace_cleanup':
                            calls.append(phase)
                            raise fault
                    def unlink(path, *args, **kwargs):
                        value = original_unlink(path, *args, **kwargs)
                        if ((phase == 'publication_cleanup' and path.name.startswith('.hero-')) or
                            (phase == 'lock_cleanup' and path == root / '_build/.theme-client-driver.lock')):
                            calls.append(phase)
                            raise fault
                        return value
                    stderr, stdout = io.StringIO(), io.StringIO()
                    caller = ValueError('handled caller recovery error')
                    try:
                        raise caller
                    except ValueError:
                        with patch.object(self.builder, 'run_tool', side_effect=self.fake_successful_tool), \
                             patch.object(self.builder.tempfile.TemporaryDirectory, 'cleanup', cleanup), \
                             patch.object(Path, 'unlink', unlink), \
                             contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
                            with self.assertRaises(PermissionError) as caught:
                                self.builder.build(root, diagnostics=self.builder.Diagnostics() if optin else None)
                        self.assertIs(sys.exc_info()[1], caller, 'recovery caller retains its own handled exception')
                    self.assertIs(caught.exception, fault, 'only the fresh build cleanup error must propagate')
                    self.assertEqual(calls, [phase], 'cleanup fault must be exercised exactly once')
                    self.assertEqual(stdout.getvalue(), '')
                    self.assertTrue((root / self.builder.TARGET).is_file(), 'postcommit cleanup failure does not roll back JS')
                    self.assertFalse((root / '_build/.theme-client-driver.lock').exists())
                    self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
                    self.assertNotIn(str(root), stderr.getvalue())
                    if optin:
                        records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
                        end = next(record for record in records if record['phase'] == phase and record['event'] == 'end')
                        self.assertEqual((end['outcome'], end['exception_class'], end['errno']),
                                         ('failure', 'PermissionError', 13))
                    else:
                        self.assertEqual(stderr.getvalue(), '')

    def test_workspace_and_lock_cleanup_preserve_primary_and_classify_secondary(self):
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
                    winning = primary if primary_fails else workspace_error if workspace_fails else lock_error
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
                    self.assertIs(seen[0], winning, 'cleanup failures must not replace the first primary error')
                    if not optin:
                        self.assertEqual(stderr.getvalue(), 'TC_TIMEOUT\n' if primary_fails else 'TC_IO\n')
                        continue
                    lines = stderr.getvalue().splitlines()
                    self.assertEqual(lines[-1], 'TC_TIMEOUT' if primary_fails else 'TC_IO')
                    records = [json.loads(line[len('TC_DIAG '):]) for line in lines[:-1]]
                    ends = {record['phase']: record for record in records if record['event'] == 'end'}
                    self.assertIn('workspace_cleanup', ends, 'workspace cleanup needs its own outcome')
                    self.assertIn('lock_cleanup', ends, 'lock cleanup needs a separate outcome')
                    self.assertEqual(ends['build_work']['tc_code'], 'TC_TIMEOUT' if primary_fails else 'none')
                    self.assertEqual(ends['workspace_cleanup']['outcome'], 'failure' if workspace_fails else 'success')
                    self.assertEqual(ends['lock_cleanup']['outcome'], 'failure' if lock_fails else 'success')
                    self.assertEqual(ends['workspace_cleanup']['errno'], 13 if workspace_fails else None)
                    self.assertEqual(ends['lock_cleanup']['errno'], 5 if lock_fails else None)
                    self.assertEqual(ends['cli']['exception_class'], 'BuildRefusal' if primary_fails else 'PermissionError' if workspace_fails else 'OSError')
                    self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
                    self.assertNotIn('password=', stderr.getvalue())
                    self.assertNotIn('/private', stderr.getvalue())
                    self.assertNotIn(str(root), stderr.getvalue())
    def test_tool_outcomes_distinguish_timeout_nonzero_spawn_and_interrupt_safely(self):
        import contextlib
        import inspect
        import io
        import json
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
                session = Mock()
                session.live_members.return_value = []
                session.cancel.side_effect = kill_error if kill_error else lambda: process.communicate(timeout=2)
                stderr, stdout = io.StringIO(), io.StringIO()
                with patch.object(self.builder.subprocess, 'Popen', side_effect=spawn_error if name == 'spawn' else None,
                                  return_value=process) as popen, \
                     patch.object(self.builder, 'OwnedSession', return_value=session), \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    if name == 'success':
                        result = self.builder.run_tool(command, cwd=self.base, env={'TEST': payload},
                            timeout=120, code='TC_BUILD', diagnostics=self.builder.Diagnostics())
                        self.assertEqual(result, payload.encode())
                    else:
                        expected_type = KeyboardInterrupt if name == 'interrupt' else self.builder.BuildRefusal
                        with self.assertRaises(expected_type) as caught:
                            self.builder.run_tool(command, cwd=self.base, env={'TEST': payload},
                                timeout=120, code='TC_BUILD', diagnostics=self.builder.Diagnostics())
                        if name == 'interrupt':
                            self.assertIs(caught.exception, interrupt)
                        elif expected_type is self.builder.BuildRefusal:
                            self.assertEqual(str(caught.exception), 'TC_TIMEOUT' if name.startswith('timeout') else 'TC_BUILD')
                    self.assertTrue(popen.call_args.kwargs['start_new_session'])
                    self.assertIs(popen.call_args.kwargs['stdout'], subprocess.PIPE)
                    self.assertIs(popen.call_args.kwargs['stderr'], subprocess.PIPE)
                    if name.startswith('timeout') or name == 'interrupt':
                        session.cancel.assert_called_once_with()
                        self.assertEqual(process.communicate.call_count, 1 if name == 'timeout-kill-error' else 2)
                    else:
                        session.cancel.assert_not_called()
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
        def version_process(value, pid):
            process = Mock(returncode=0, pid=pid)
            process.communicate.return_value = (value, payload.encode())
            return process
        preparation = [version_process(b'0.18.4', 4324), version_process(b'', 4325),
                       version_process(os.fsencode(self.synthetic_dune), 4326), version_process(b'3.23.1', 4322)]
        compiler = Mock(returncode=-9, pid=4323)
        compiler.communicate.side_effect = [subprocess.TimeoutExpired(command, 1800, stderr=payload.encode()), (b'', b'')]
        stderr = io.StringIO()
        session = Mock()
        session.live_members.return_value = []
        session.cancel.side_effect = lambda: compiler.communicate(timeout=2)
        with patch.object(self.builder.subprocess, 'Popen', side_effect=[*preparation, compiler]), \
             patch.object(self.builder, 'OwnedSession', return_value=session), contextlib.redirect_stderr(stderr):
            with self.assertRaises(self.builder.BuildRefusal) as caught:
                self.builder.build(root, diagnostics=self.builder.Diagnostics())
        self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
        records = [json.loads(line[len('TC_DIAG '):]) for line in stderr.getvalue().splitlines()]
        self.assertIn('tool_timeout', [record['event'] for record in records], 'build must forward opt-in to the tool seam')
        self.assertNotIn('SYNTHETIC_PRIVATE_CANARY', stderr.getvalue())
        session.cancel.assert_called_once_with()
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
                session = Mock()
                session.live_members.return_value = []
                with patch.object(self.builder.subprocess, 'Popen', return_value=process), \
                     patch.object(self.builder, 'OwnedSession', return_value=session), contextlib.redirect_stderr(BrokenSink()):
                    with self.assertRaises(self.builder.BuildRefusal) as caught:
                        self.builder.run_tool(['/private/tool'], cwd=self.base, env={}, timeout=600,
                            code='TC_BUILD', diagnostics=self.builder.Diagnostics())
                self.assertEqual(str(caught.exception), 'TC_TIMEOUT')
                session.cancel.assert_called_once_with()
        stdout = io.StringIO()
        with patch.object(sys, 'stderr', None), contextlib.redirect_stdout(stdout):
            self.builder.Diagnostics().emit('cli', 'start')
        self.assertEqual(stdout.getvalue(), '', 'missing stderr must not redirect diagnostic records into JSON stdout')
    def test_publication_cleanup_preserves_primary_write_error(self):
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
                            self.assertIs(caught.exception, primary if write_fails else cleanup_error)
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
