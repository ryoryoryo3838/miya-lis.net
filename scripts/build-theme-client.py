#!/usr/bin/env python3
"""Compile only trusted root configs/locks and theme/client; no content discovery."""
import hashlib
import argparse
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


def run_tool(command, *, cwd, env, timeout, code):
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except OSError:
        raise BuildRefusal(code) from None
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        if isinstance(error, KeyboardInterrupt):
            raise
        raise BuildRefusal('TC_TIMEOUT') from None
    if process.returncode:
        raise BuildRefusal(code)
    return stdout.strip()


def publish_js(root, fresh):
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
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        output_namespace(root)
        os.replace(temporary, target)
        return hashlib.sha256(data).hexdigest()
    finally:
        temporary.unlink(missing_ok=True)


def build(root):
    root = Path(root)
    before = source_manifest(root)
    output_namespace(root)
    base = root / '_build'
    base.mkdir(exist_ok=True)
    lock = base / '.theme-client-driver.lock'
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise BuildRefusal('TC_BUSY') from None
    os.close(descriptor)
    try:
        with tempfile.TemporaryDirectory(prefix='theme-client-source-', dir=base) as directory:
            work = Path(directory)
            fresh = work / 'sources'
            fresh.mkdir()
            if copy_sources(root, fresh) != before:
                raise BuildRefusal('TC_SOURCE_CHANGED')
            env = compile_environment(work)
            for key in ['HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME']:
                Path(env[key]).mkdir(parents=True, exist_ok=True)
            shell = work / 'shell'
            shell.mkdir()
            for name in FLAKE_HASHES:
                (shell / name).write_bytes(read_source(fresh / name))
            nix = shutil.which('nix')
            prefix = [nix, 'develop', '--no-write-lock-file', 'path:' + str(shell), '--command']
            version = run_tool(prefix + ['dune', '--version'], cwd=fresh, env=env,
                               timeout=120, code='TC_TOOLCHAIN')
            if version != b'3.23.1':
                raise BuildRefusal('TC_TOOLCHAIN')
            run_tool(prefix + ['dune', 'build', 'theme/client/hero.bc.js'], cwd=fresh, env=env,
                     timeout=BUILD_TIMEOUT, code='TC_BUILD')
            versions = {}
            for program, expected, label in [('ocamlc', b'5.5.1', 'ocaml'), ('js_of_ocaml', b'6.4.1', 'js_of_ocaml')]:
                actual = run_tool(prefix + ['dune', 'exec', '--', program, '-version' if program == 'ocamlc' else '--version'],
                                  cwd=fresh, env=env, timeout=120, code='TC_TOOLCHAIN')
                if actual != expected:
                    raise BuildRefusal('TC_TOOLCHAIN')
                versions[label] = actual.decode('ascii')
            if source_manifest(root) != before or source_manifest(fresh) != before:
                raise BuildRefusal('TC_SOURCE_CHANGED')
            digest = publish_js(root, fresh)
            return {'sha256': digest, 'sources': before, 'dune': '3.23.1', **versions}
    finally:
        lock.unlink()


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise BuildRefusal('TC_ARGS')


def main():
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument('--site-root', default=str(Path(__file__).absolute().parents[1]))
        args = parser.parse_args()
        if '..' in Path(args.site_root).parts:
            raise BuildRefusal('TC_PATH')
        result = build(Path(os.path.abspath(args.site_root)))
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
