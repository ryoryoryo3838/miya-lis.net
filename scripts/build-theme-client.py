#!/usr/bin/env python3
"""Compile only trusted root configs/locks and theme/client; no content discovery."""
import hashlib
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile

ROOT_FILES = ('dune', 'dune-project', 'dune-workspace', 'flake.nix', 'flake.lock')
CLIENT_FILES = ('theme/client/dune', 'theme/client/hero.ml')
MAX_FILE = 4 * 1024 * 1024
MAX_SOURCES = 16 * 1024 * 1024
NIXPKGS_REV = '70ce234312134a463ba7728e94da2486a1d237ac'
FLAKE_HASHES = {
    'flake.nix': '5a13392018972f11aa1852efaf205199c70de43f6a19a601c51e6255193149f6',
    'flake.lock': '11032b8b75b1a1670fabe40fe1ca0ac3c96d03cc1e79116f55363a6a42fabb85',
}
TARGET = '_build/default/theme/client/hero.bc.js'
BUILD_TIMEOUT = 600


class BuildRefusal(Exception):
    """Diagnostics expose only constant codes, never source/tool payloads."""


class Diagnostics:
    """Opt-in stderr records use closed classifications, never exception text."""
    MAX_RECORDS = 64
    MAX_BYTES = 16384
    MAX_LINE_BYTES = 256
    PHASES = frozenset({'cli', 'tool', 'source_validation', 'output_validation',
                       'lock_acquire', 'workspace_create', 'workspace_enter', 'workspace_setup',
                       'source_copy', 'environment_setup', 'shell_setup', 'dune_version',
                       'client_build', 'ocaml_version', 'jsoo_version', 'source_recheck',
                       'publication', 'publication_write', 'publication_cleanup',
                       'build_work', 'workspace_cleanup', 'lock_cleanup'})
    EVENTS = frozenset({'start', 'end', 'tool_timeout', 'tool_nonzero',
                       'tool_spawn_error', 'tool_interrupted'})
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


class ObservedWorkspace:
    """Forward the original context manager; cleanup still masks as before."""
    def __init__(self, workspace, diagnostics):
        self.workspace = workspace
        self.diagnostics = diagnostics

    def __enter__(self):
        with diagnostic_phase(self.diagnostics, 'workspace_enter'):
            return self.workspace.__enter__()

    def __exit__(self, kind, value, traceback):
        with diagnostic_phase(self.diagnostics, 'workspace_cleanup'):
            return self.workspace.__exit__(kind, value, traceback)


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


def compile_environment(work):
    """No inherited HOME, OCaml settings, tokens, Git config or Nix credentials."""
    work = Path(work)
    nix = shutil.which('nix')
    if not nix:
        raise BuildRefusal('TC_TOOLCHAIN')
    home = work / 'owned-home'
    return {'PATH': str(Path(nix).resolve().parent) + ':/usr/bin:/bin',
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


def run_tool(command, *, cwd, env, timeout, code, diagnostics=None):
    with diagnostic_phase(diagnostics, 'tool'):
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
        except OSError as error:
            if diagnostics is not None:
                diagnostics.emit('tool', 'tool_spawn_error', outcome='failure', error=error)
            raise BuildRefusal(code) from None
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            if diagnostics is not None:
                diagnostics.emit('tool', 'tool_interrupted' if isinstance(error, KeyboardInterrupt) else 'tool_timeout',
                                 outcome='failure', error=error)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            if isinstance(error, KeyboardInterrupt):
                raise
            raise BuildRefusal('TC_TIMEOUT') from None
        if process.returncode:
            if diagnostics is not None:
                diagnostics.emit('tool', 'tool_nonzero', outcome='failure')
            raise BuildRefusal(code)
        return stdout.strip()


def publish_js(root, fresh, *, diagnostics=None):
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
    try:
        with diagnostic_phase(diagnostics, 'publication_write'):
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            output_namespace(root)
            os.replace(temporary, target)
            return hashlib.sha256(data).hexdigest()
    finally:
        with diagnostic_phase(diagnostics, 'publication_cleanup'):
            temporary.unlink(missing_ok=True)


def build(root, *, diagnostics=None):
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
    try:
        with diagnostic_phase(diagnostics, 'workspace_create'):
            workspace = tempfile.TemporaryDirectory(prefix='theme-client-source-', dir=base)
        with (workspace if diagnostics is None else ObservedWorkspace(workspace, diagnostics)) as directory:
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
                with diagnostic_phase(diagnostics, 'shell_setup'):
                    shell = work / 'shell'
                    shell.mkdir()
                    for name in FLAKE_HASHES:
                        (shell / name).write_bytes(read_source(fresh / name))
                    nix = shutil.which('nix')
                    prefix = [nix, 'develop', '--no-write-lock-file', 'path:' + str(shell), '--command']
                with diagnostic_phase(diagnostics, 'dune_version'):
                    version = run_tool(prefix + ['dune', '--version'], cwd=fresh, env=env,
                                       timeout=120, code='TC_TOOLCHAIN', diagnostics=diagnostics)
                    if version != b'3.23.1':
                        raise BuildRefusal('TC_TOOLCHAIN')
                with diagnostic_phase(diagnostics, 'client_build'):
                    run_tool(prefix + ['dune', 'build', 'theme/client/hero.bc.js'], cwd=fresh, env=env,
                             timeout=BUILD_TIMEOUT, code='TC_BUILD', diagnostics=diagnostics)
                versions = {}
                for program, expected, label in [('ocamlc', b'5.5.1', 'ocaml'), ('js_of_ocaml', b'6.4.1', 'js_of_ocaml')]:
                    with diagnostic_phase(diagnostics, 'ocaml_version' if program == 'ocamlc' else 'jsoo_version'):
                        actual = run_tool(prefix + ['dune', 'exec', '--', program, '-version' if program == 'ocamlc' else '--version'],
                                          cwd=fresh, env=env, timeout=120, code='TC_TOOLCHAIN', diagnostics=diagnostics)
                        if actual != expected:
                            raise BuildRefusal('TC_TOOLCHAIN')
                        versions[label] = actual.decode('ascii')
                with diagnostic_phase(diagnostics, 'source_recheck'):
                    if source_manifest(root) != before or source_manifest(fresh) != before:
                        raise BuildRefusal('TC_SOURCE_CHANGED')
                with diagnostic_phase(diagnostics, 'publication'):
                    digest = publish_js(root, fresh, diagnostics=diagnostics)
                return {'sha256': digest, 'sources': before, 'dune': '3.23.1', **versions}
    finally:
        with diagnostic_phase(diagnostics, 'lock_cleanup'):
            lock.unlink()


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
