#!/usr/bin/env python3
"""Compile only trusted root configs/locks and theme/client; no content discovery."""
import hashlib
import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

ROOT_FILES = ('dune', 'dune-project', 'dune-workspace', 'flake.nix', 'flake.lock', 'devbox.json')
CLIENT_FILES = ('theme/client/dune', 'theme/client/hero.ml')
MAX_FILE = 4 * 1024 * 1024
MAX_SOURCES = 16 * 1024 * 1024
NIXPKGS_REV = '70ce234312134a463ba7728e94da2486a1d237ac'
FLAKE_HASHES = {
    'flake.nix': '5a13392018972f11aa1852efaf205199c70de43f6a19a601c51e6255193149f6',
    'flake.lock': '11032b8b75b1a1670fabe40fe1ca0ac3c96d03cc1e79116f55363a6a42fabb85',
}
TARGET = '_build/default/theme/client/hero.bc.js'
BUILD_TIMEOUT = 1800
BOOTSTRAP_TIMEOUT = 600
DEVBOX_VERSION = b'0.18.4'
DEVBOX_SHA256 = '2e04f455818f532cda55d1847545f422799e70194d75493a6dc5db8459a53817'


class BuildRefusal(Exception):
    """Diagnostics expose only constant codes, never source/tool payloads."""


class Diagnostics:
    """Opt-in stderr records use closed classifications, never exception text."""
    MAX_RECORDS = 64
    MAX_BYTES = 16384
    MAX_LINE_BYTES = 256
    PHASES = frozenset({'cli', 'tool', 'source_validation', 'output_validation',
                       'lock_acquire', 'workspace_create', 'workspace_enter', 'workspace_setup',
                       'source_copy', 'environment_setup', 'shell_setup', 'bootstrap', 'devbox_version',
                       'devbox_install', 'dune_resolve', 'dune_version',
                       'client_build', 'ocaml_version', 'jsoo_version', 'source_recheck',
                       'publication', 'publication_write', 'publication_cleanup',
                       'build_work', 'workspace_cleanup', 'lock_cleanup', 'session_cancel'})
    EVENTS = frozenset({'start', 'end', 'tool_timeout', 'tool_nonzero',
                       'tool_spawn_error', 'tool_interrupted', 'cleanup_skipped'})
    CODES = frozenset({'TC_PATH', 'TC_SIZE', 'TC_SOURCE', 'TC_PIN', 'TC_ARTIFACT',
                       'TC_SOURCE_CHANGED', 'TC_TOOLCHAIN', 'TC_TIMEOUT', 'TC_BUILD',
                       'TC_BUSY', 'TC_ARGS', 'TC_INTERRUPTED', 'TC_IO'})
    CLASSES = {BuildRefusal: 'BuildRefusal', OSError: 'OSError',
               PermissionError: 'PermissionError', FileNotFoundError: 'FileNotFoundError',
               FileExistsError: 'FileExistsError', IsADirectoryError: 'IsADirectoryError',
               NotADirectoryError: 'NotADirectoryError', ProcessLookupError: 'ProcessLookupError',
               BrokenPipeError: 'BrokenPipeError', TimeoutError: 'TimeoutError',
               BlockingIOError: 'BlockingIOError', InterruptedError: 'InterruptedError',
               ValueError: 'ValueError', KeyError: 'KeyError', TypeError: 'TypeError',
               KeyboardInterrupt: 'KeyboardInterrupt', subprocess.TimeoutExpired: 'TimeoutExpired'}

    def __init__(self):
        self.records = 0
        self.bytes = 0

    def emit(self, phase, event, *, outcome='none', error=None):
        if (self.records >= self.MAX_RECORDS or
                type(phase) is not str or phase not in self.PHASES or
                type(event) is not str or event not in self.EVENTS or
                type(outcome) is not str or outcome not in {'none', 'success', 'failure'}):
            return
        kind = type(error)
        name = 'none' if error is None else self.CLASSES.get(kind, 'other')
        number = error.errno if kind in self.CLASSES and issubclass(kind, OSError) else None
        if type(number) is not int or not 0 <= number <= 255:
            number = None
        code = 'none'
        if kind is BuildRefusal and len(error.args) == 1:
            value = error.args[0]
            if type(value) is str and value in self.CODES:
                code = value
        record = dict(phase=phase, event=event, outcome=outcome,
                      exception_class=name, errno=number, tc_code=code)
        line = 'TC_DIAG ' + json.dumps(record, sort_keys=True) + '\n'
        size = len(line.encode('ascii'))
        if size > self.MAX_LINE_BYTES or self.bytes + size > self.MAX_BYTES:
            return
        self.records += 1
        self.bytes += size
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
        except Exception:
            # Observation must not create a failure or prevent process-group kill.
            pass


@contextmanager
def diagnostic_phase(diagnostics, phase):
    if diagnostics is None:
        yield
        return
    diagnostics.emit(phase, 'start')
    try:
        yield
    except BaseException as error:
        diagnostics.emit(phase, 'end', outcome='failure', error=error)
        raise
    else:
        diagnostics.emit(phase, 'end', outcome='success')


@contextmanager
def preserving_cleanup(diagnostics, phase, primary):
    """Preserve only this operation's explicit primary; None means success."""
    try:
        with diagnostic_phase(diagnostics, phase):
            yield
    except BaseException:
        if primary is None:
            raise


class ObservedWorkspace:
    """Always preserve the primary failure, even with diagnostics disabled."""
    def __init__(self, workspace, diagnostics):
        self.workspace = workspace
        self.diagnostics = diagnostics

    def __enter__(self):
        with diagnostic_phase(self.diagnostics, 'workspace_enter'):
            return self.workspace.__enter__()

    def __exit__(self, kind, value, traceback):
        if getattr(value, 'unsafe_workspace_cleanup', False):
            # Retain local-only state and ownership if termination could not be verified.
            self.workspace._finalizer.detach()
            if self.diagnostics is not None:
                self.diagnostics.emit('workspace_cleanup', 'cleanup_skipped', outcome='failure')
            return False
        with preserving_cleanup(self.diagnostics, 'workspace_cleanup', value):
            self.workspace.__exit__(kind, value, traceback)
        return False


def checked(path, *, directory=False):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise BuildRefusal('TC_PATH')
    for parent in reversed(path.parents):
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise BuildRefusal('TC_PATH')
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not valid:
        raise BuildRefusal('TC_PATH')
    return info


def read_source(path):
    info = checked(path)
    if info.st_size > MAX_FILE:
        raise BuildRefusal('TC_SIZE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise BuildRefusal('TC_PATH')
        data = stream.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise BuildRefusal('TC_SIZE')
    return data


def source_manifest(root):
    root = Path(root)
    checked(root, directory=True)
    names = [*ROOT_FILES, *CLIENT_FILES]
    lock = root / 'dune.lock'
    checked(lock, directory=True)
    for path in sorted(lock.iterdir()):
        if path.name != 'lock.dune' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+~-]*\.pkg', path.name):
            raise BuildRefusal('TC_SOURCE')
        names.append('dune.lock/' + path.name)
    if 'dune.lock/lock.dune' not in names:
        raise BuildRefusal('TC_SOURCE')
    checked(root / 'theme/client', directory=True)
    if {path.name for path in (root / 'theme/client').iterdir()} != {'dune', 'hero.ml'}:
        raise BuildRefusal('TC_SOURCE')
    result, total = {}, 0
    for name in names:
        data = read_source(root / name)
        total += len(data)
        if total > MAX_SOURCES:
            raise BuildRefusal('TC_SIZE')
        result[name] = hashlib.sha256(data).hexdigest()
    if result['devbox.json'] != DEVBOX_SHA256:
        raise BuildRefusal('TC_PIN')
    if any(result[name] != digest for name, digest in FLAKE_HASHES.items()):
        raise BuildRefusal('TC_PIN')
    for name, version in [('ocaml', '5.5.1'), ('js_of_ocaml', '6.4.1'), ('js_of_ocaml-ppx', '6.4.1')]:
        if ('dune.lock/' + name + '.' + version + '.pkg' not in result or
                not read_source(lock / (name + '.' + version + '.pkg')).startswith(('(version ' + version + ')\n').encode())):
            raise BuildRefusal('TC_PIN')
    return result


def copy_sources(root, fresh):
    root, fresh = Path(root), Path(fresh)
    manifest = source_manifest(root)
    checked(fresh, directory=True)
    if any(fresh.iterdir()):
        raise BuildRefusal('TC_ARTIFACT')
    for name, digest in manifest.items():
        data = read_source(root / name)
        if hashlib.sha256(data).hexdigest() != digest:
            raise BuildRefusal('TC_SOURCE_CHANGED')
        destination = fresh / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(data)
    return manifest


def compile_environment(work, dune=None):
    """No inherited HOME, OCaml settings, tokens, Git config or Nix credentials."""
    work = Path(work)
    nix = shutil.which('nix')
    if not nix:
        raise BuildRefusal('TC_TOOLCHAIN')
    home = work / 'owned-home'
    binary = Path(dune).resolve() if dune is not None else Path(nix).resolve()
    return {'PATH': str(binary.parent) + ':/usr/bin:/bin',
            'HOME': str(home), 'TMPDIR': str(work / 'tmp'),
            'XDG_CACHE_HOME': str(home / 'cache'), 'XDG_CONFIG_HOME': str(home / 'config'),
            'XDG_DATA_HOME': str(home / 'data'), 'DUNE_ROOT': str(work / 'sources'),
            'DUNE_CACHE': 'disabled', 'NIX_USER_CONF_FILES': '',
            'NIX_CONFIG': 'experimental-features = nix-command flakes\naccept-flake-config = false\n',
            'LC_ALL': 'C', 'TZ': 'UTC'}


def output_namespace(root):
    target = root / TARGET
    for parent in reversed(target.parents):
        if parent == root or root in parent.parents:
            if os.path.lexists(parent):
                checked(parent, directory=True)
    if os.path.lexists(target):
        checked(target)
    return target


def process_identity(pid):
    """Linux identity only; never read cmdline, environ or worker payloads."""
    try:
        path = Path('/proc') / str(pid)
        owner = path.stat().st_uid
        text = (path / 'stat').read_bytes()
        fields = text[text.rfind(b')') + 2:].split()
        return (pid, int(fields[19]), int(fields[3]), owner, fields[0].decode('ascii'), int(fields[2]))
    except (OSError, ValueError, IndexError, UnicodeError):
        return None


def verified_process_identity(pid):
    """None is proof of exit only when the /proc PID entry is also absent."""
    identity = process_identity(pid)
    if identity is None:
        try:
            (Path('/proc') / str(pid)).stat()
        except FileNotFoundError:
            return None
        except OSError:
            raise BuildRefusal('TC_TOOLCHAIN') from None
        raise BuildRefusal('TC_TOOLCHAIN')
    return identity


class OwnedSession:
    """Bounded scheduler grace, then pidfd-checked entire Linux session."""
    GRACE_SECONDS = 2
    KILL_SECONDS = 2

    def __init__(self, process):
        self.process = process
        leader = process_identity(process.pid)
        if (leader is None or leader[2] != process.pid or
                leader[3] != os.getuid()):
            raise BuildRefusal('TC_TOOLCHAIN')
        self.leader = leader
        self.members = {leader[:2]: leader}

    def live_members(self):
        current = verified_process_identity(self.process.pid)
        # Never discover a different session after leader PID reuse.
        if current is None or current[:4] == self.leader[:4]:
            for path in Path('/proc').iterdir():
                if path.name.isdecimal():
                    info = verified_process_identity(int(path.name))
                    if info and info[2] == self.process.pid and info[3] == os.getuid():
                        self.members[info[:2]] = info
        live = []
        for old in self.members.values():
            now = verified_process_identity(old[0])
            if now and now[:4] == old[:4] and now[4] not in {'Z', 'X'}:
                live.append(now)
        return live

    @staticmethod
    def send(identity, number):
        # pidfd pins identity across the recheck->signal boundary; no killpg
        # broadside can hit an unrelated reused group or PID.
        try:
            descriptor = os.pidfd_open(identity[0])
        except ProcessLookupError:
            return
        try:
            current = verified_process_identity(identity[0])
            if current and current[:4] == identity[:4] and current[4] not in {'Z', 'X'}:
                signal.pidfd_send_signal(descriptor, number)
        except ProcessLookupError:
            pass
        finally:
            os.close(descriptor)

    def cancel(self):
        live = self.live_members()  # Snapshot before Dune is permitted to exit/reap.
        for identity in live:
            if identity[5] == self.process.pid:
                try:
                    self.send(identity, signal.SIGINT)
                except OSError:
                    # Still attempt all identities in the hard-cancel phase.
                    pass
        deadline = time.monotonic() + self.GRACE_SECONDS
        while self.live_members() and time.monotonic() < deadline:
            self.process.poll()
            time.sleep(.02)
        deadline = time.monotonic() + self.KILL_SECONDS
        kill_error = None
        while True:
            live = self.live_members()
            if not live:
                break
            for identity in live:
                try:
                    self.send(identity, signal.SIGKILL)
                except OSError as error:
                    kill_error = error
            if time.monotonic() >= deadline:
                if kill_error is not None:
                    raise kill_error
                raise BuildRefusal('TC_TOOLCHAIN')
            time.sleep(.02)
        # Never perform an unbounded pipe drain after cancellation.
        self.process.communicate(timeout=self.KILL_SECONDS)


def run_tool(command, *, cwd, env, timeout, code, diagnostics=None):
    with diagnostic_phase(diagnostics, 'tool'):
        if (not sys.platform.startswith('linux') or not Path('/proc/self/stat').is_file() or
                not callable(getattr(os, 'pidfd_open', None)) or
                not callable(getattr(signal, 'pidfd_send_signal', None))):
            raise BuildRefusal('TC_TOOLCHAIN')
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
        except OSError as error:
            if diagnostics is not None:
                diagnostics.emit('tool', 'tool_spawn_error', outcome='failure', error=error)
            raise BuildRefusal(code) from None
        try:
            session = OwnedSession(process)
        except BaseException as error:
            # Without the initial identity we cannot safely signal or prove exit.
            setattr(error, 'unsafe_workspace_cleanup', True)
            with preserving_cleanup(diagnostics, 'session_cancel', error):
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
                process.poll()  # waitpid on our direct child only; never a PID signal.
            raise
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except BaseException as error:
            if diagnostics is not None and isinstance(error, (subprocess.TimeoutExpired, KeyboardInterrupt)):
                diagnostics.emit('tool', 'tool_interrupted' if isinstance(error, KeyboardInterrupt) else 'tool_timeout',
                                 outcome='failure', error=error)
            primary = BuildRefusal('TC_TIMEOUT') if isinstance(error, subprocess.TimeoutExpired) else error
            try:
                with diagnostic_phase(diagnostics, 'session_cancel'):
                    session.cancel()
            except BaseException:
                # Preserve the primary code, but forbid unsafe workspace removal.
                setattr(primary, 'unsafe_workspace_cleanup', True)
            raise primary from None
        primary = BuildRefusal(code) if process.returncode else None
        if primary is not None and diagnostics is not None:
            diagnostics.emit('tool', 'tool_nonzero', outcome='failure')
        try:
            if session.live_members():
                with diagnostic_phase(diagnostics, 'session_cancel'):
                    session.cancel()
        except BaseException as error:
            primary = primary if primary is not None else error
            setattr(primary, 'unsafe_workspace_cleanup', True)
        if primary is not None:
            raise primary from None
        return stdout.strip()


def publish_js(root, fresh, *, deadline, diagnostics=None):
    source = fresh / TARGET
    data = read_source(source)
    if not data.strip():
        raise BuildRefusal('TC_ARTIFACT')
    try:
        data.decode('utf-8', errors='strict')
    except UnicodeError:
        raise BuildRefusal('TC_ARTIFACT') from None
    target = output_namespace(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.hero-', suffix='.js', dir=target.parent)
    temporary = Path(name)
    primary = None
    try:
        with diagnostic_phase(diagnostics, 'publication_write'):
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            output_namespace(root)
            remaining_timeout(deadline, 120)  # Authorize the actual atomic commit, after fsync.
            os.replace(temporary, target)
            return hashlib.sha256(data).hexdigest()
    except BaseException as error:
        primary = error
        raise
    finally:
        with preserving_cleanup(diagnostics, 'publication_cleanup', primary):
            temporary.unlink(missing_ok=True)


def remaining_timeout(deadline, limit):
    remaining = deadline - time.monotonic()
    if not math.isfinite(remaining):
        raise BuildRefusal('TC_IO')
    if remaining <= 0:
        raise BuildRefusal('TC_TIMEOUT')
    return min(limit, remaining)


def build(root, *, diagnostics=None):
    started = time.monotonic()
    deadline = started + BUILD_TIMEOUT
    root = Path(root)
    with diagnostic_phase(diagnostics, 'source_validation'):
        before = source_manifest(root)
    with diagnostic_phase(diagnostics, 'output_validation'):
        output_namespace(root)
    with diagnostic_phase(diagnostics, 'lock_acquire'):
        base = root / '_build'
        base.mkdir(exist_ok=True)
        lock = base / '.theme-client-driver.lock'
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise BuildRefusal('TC_BUSY') from None
        os.close(descriptor)
    primary = None
    try:
        with diagnostic_phase(diagnostics, 'workspace_create'):
            workspace = tempfile.TemporaryDirectory(prefix='theme-client-source-', dir=base)
        with ObservedWorkspace(workspace, diagnostics) as directory:
            with diagnostic_phase(diagnostics, 'build_work'):
                with diagnostic_phase(diagnostics, 'workspace_setup'):
                    work = Path(directory)
                    fresh = work / 'sources'
                    fresh.mkdir()
                with diagnostic_phase(diagnostics, 'source_copy'):
                    if copy_sources(root, fresh) != before:
                        raise BuildRefusal('TC_SOURCE_CHANGED')
                with diagnostic_phase(diagnostics, 'environment_setup'):
                    env = compile_environment(work)
                    for key in ['HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME']:
                        Path(env[key]).mkdir(parents=True, exist_ok=True)
                bootstrap_started = time.monotonic()
                bootstrap_deadline = min(deadline, bootstrap_started + BOOTSTRAP_TIMEOUT)
                with diagnostic_phase(diagnostics, 'bootstrap'):
                    devbox = shutil.which('devbox')
                    if not devbox:
                        raise BuildRefusal('TC_TOOLCHAIN')
                    bootstrap = work / 'bootstrap'
                    bootstrap.mkdir()
                    (bootstrap / 'devbox.json').write_bytes(read_source(fresh / 'devbox.json'))
                    with diagnostic_phase(diagnostics, 'devbox_version'):
                        if run_tool([devbox, 'version'], cwd=bootstrap, env=env,
                                    timeout=remaining_timeout(bootstrap_deadline, 120), code='TC_TOOLCHAIN', diagnostics=diagnostics) != DEVBOX_VERSION:
                            raise BuildRefusal('TC_TOOLCHAIN')
                    with diagnostic_phase(diagnostics, 'devbox_install'):
                        run_tool([devbox, 'install', '--config', str(bootstrap)], cwd=bootstrap, env=env,
                                 timeout=remaining_timeout(bootstrap_deadline, BOOTSTRAP_TIMEOUT), code='TC_TOOLCHAIN', diagnostics=diagnostics)
                    with diagnostic_phase(diagnostics, 'dune_resolve'):
                        raw = run_tool([devbox, 'run', '--config', str(bootstrap), '--', '/usr/bin/which', 'dune'],
                                       cwd=bootstrap, env=env, timeout=remaining_timeout(bootstrap_deadline, 120), code='TC_TOOLCHAIN', diagnostics=diagnostics)
                        try:
                            candidate = Path(raw.decode('utf-8', errors='strict'))
                            if not candidate.is_absolute() or '..' in candidate.parts or b'\n' in raw:
                                raise BuildRefusal('TC_TOOLCHAIN')
                            dune = candidate.resolve(strict=True)
                            checked(dune)
                            if not os.access(dune, os.X_OK):
                                raise BuildRefusal('TC_TOOLCHAIN')
                        except (OSError, UnicodeError, ValueError):
                            raise BuildRefusal('TC_TOOLCHAIN') from None
                        prefix = [str(dune)]
                    with diagnostic_phase(diagnostics, 'dune_version'):
                        env = compile_environment(work, dune)
                        if run_tool(prefix + ['--version'], cwd=fresh, env=env,
                                    timeout=remaining_timeout(bootstrap_deadline, 120), code='TC_TOOLCHAIN', diagnostics=diagnostics) != b'3.23.1':
                            raise BuildRefusal('TC_TOOLCHAIN')
                bootstrap_elapsed = time.monotonic() - bootstrap_started
                compile_started = time.monotonic()
                with diagnostic_phase(diagnostics, 'client_build'):
                    run_tool(prefix + ['build', 'theme/client/hero.bc.js'], cwd=fresh, env=env,
                             timeout=remaining_timeout(deadline, BUILD_TIMEOUT), code='TC_BUILD', diagnostics=diagnostics)
                compile_elapsed = time.monotonic() - compile_started
                versions = {}
                for program, expected, label in [('ocamlc', b'5.5.1', 'ocaml'), ('js_of_ocaml', b'6.4.1', 'js_of_ocaml')]:
                    with diagnostic_phase(diagnostics, 'ocaml_version' if program == 'ocamlc' else 'jsoo_version'):
                        actual = run_tool(prefix + ['exec', '--', program, '-version' if program == 'ocamlc' else '--version'],
                                          cwd=fresh, env=env, timeout=remaining_timeout(deadline, 120), code='TC_TOOLCHAIN', diagnostics=diagnostics)
                        if actual != expected:
                            raise BuildRefusal('TC_TOOLCHAIN')
                        versions[label] = actual.decode('ascii')
                with diagnostic_phase(diagnostics, 'source_recheck'):
                    if source_manifest(root) != before or source_manifest(fresh) != before:
                        raise BuildRefusal('TC_SOURCE_CHANGED')
                with diagnostic_phase(diagnostics, 'publication'):
                    remaining_timeout(deadline, 120)
                    digest = publish_js(root, fresh, deadline=deadline, diagnostics=diagnostics)
                result = {'sha256': digest, 'sources': before, 'devbox': '0.18.4', 'dune': '3.23.1', **versions}
    except BaseException as error:
        primary = error
        raise
    finally:
        if getattr(primary, 'unsafe_workspace_cleanup', False):
            if diagnostics is not None:
                diagnostics.emit('lock_cleanup', 'cleanup_skipped', outcome='failure')
        else:
            with preserving_cleanup(diagnostics, 'lock_cleanup', primary):
                lock.unlink()
    timings = dict(bootstrap_seconds=bootstrap_elapsed, compile_seconds=compile_elapsed,
                   total_seconds=time.monotonic() - started)
    if any(type(value) not in {int, float} or not math.isfinite(value) or value < 0 for value in timings.values()):
        raise BuildRefusal('TC_IO')
    # The shared deadline authorizes commit; post-commit filesystem cleanup cannot
    # roll it back. Its elapsed time is observed, never a retroactive TC_TIMEOUT.
    result['timings'] = timings
    return result


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise BuildRefusal('TC_ARGS')


def main():
    options = sys.argv[1:]
    if '--' in options:
        options = options[:options.index('--')]
    diagnostics = Diagnostics() if '--diagnostics' in options else None
    try:
        with diagnostic_phase(diagnostics, 'cli'):
            parser = SafeParser(description=__doc__)
            parser.add_argument('--site-root', default=str(Path(__file__).absolute().parents[1]))
            parser.add_argument('--diagnostics', action='store_true')
            args = parser.parse_args()
            if args.diagnostics and diagnostics is None:
                raise BuildRefusal('TC_ARGS')
            if '..' in Path(args.site_root).parts:
                raise BuildRefusal('TC_PATH')
            root = Path(os.path.abspath(args.site_root))
            result = build(root) if diagnostics is None else build(root, diagnostics=diagnostics)
    except BuildRefusal as error:
        print(str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('TC_INTERRUPTED', file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError, TypeError):
        print('TC_IO', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
