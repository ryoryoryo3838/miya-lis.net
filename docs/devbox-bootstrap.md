# Devbox installs Dune; the client driver builds directly

The client bootstrap uses Devbox **0.18.4** and exactly one package:
`github:NixOS/nixpkgs/70ce234312134a463ba7728e94da2486a1d237ac#dune`.
The installed Dune must report **3.23.1**. `devbox.json` has no init hooks,
project scripts, opam switch, dotfile sourcing or legacy binary PATH additions.
Devbox itself still uses Nix internally; a working Nix installation is a host
prerequisite, as are native C build tools and make.

```sh
python3 scripts/build-theme-client.py --site-root . --diagnostics
```

The caller supplies the pinned Devbox executable on PATH, not an already
initialized Devbox shell or repository `.devbox/` directory. The driver:

1. Validates the exact source projection: root Dune configuration, unchanged
   `flake.nix` / `flake.lock`, the reviewed Dune-only `devbox.json`, every existing
   `dune.lock` entry, and only `theme/client/dune` and `theme/client/hero.ml`.
   Symlinks, hardlinks, unknown client/lock files and changed bootstrap pins are
   refused. Content, vault files, old outputs and credential caches are not read.
2. Copies these sources into an empty, newly owned workspace, with a fresh
   internal `_build`. Existing root `_build` compiler output is never reused.
3. Creates a separate content-free bootstrap directory containing only the
   reviewed `devbox.json`. It checks Devbox's version and runs `devbox install`
   there. Generated Devbox state is local-only, never part of the projection.
4. Resolves Dune using the installed bootstrap, checks the executable and its
   exact version, then invokes that resolved binary **directly** for build and
   version checks. Neither `devbox run build` nor direct `nix develop` wraps the
   client compiler. No shellenv stream is printed or evaluated by this driver.
5. Gives Dune an allowlisted environment with owned HOME, XDG and temporary
   directories, explicit `DUNE_ROOT`, disabled Dune cache, no inherited OCaml,
   opam, Git or token settings, and no Nix user configuration. The existing full
   `dune.lock` manages OCaml 5.5.1 and js_of_ocaml 6.4.1; it is never re-solved.
6. Rechecks both original and copied source hashes. Only new, regular, nonempty
   strict UTF-8 JS is copied atomically to `_build/default/theme/client/hero.bc.js`
   with mode 0644. A failed build does not authorize stale JS as a fresh artifact.

## Deadlines and safe observations

`BUILD_TIMEOUT` is an 1800-second **pre-commit** budget. Tool calls share its
remaining time; the bootstrap shares a separate 600-second maximum, so installation
and resolution cannot silently extend it. Publication rechecks this same deadline
**after staging/fsync and final target validation, immediately before `os.replace`**.
Expiry there retains previous JS, or leaves a previously absent JS target absent.
An authorized atomic replace is the commit boundary; its syscall is not preempted
or rolled back merely because the monotonic clock advances during or after it.

Post-commit filesystem cleanup receives **no new tool/build budget**. It runs
synchronously outside the pre-commit deadline, with **no separately enforced
filesystem time cap**. Its time remains included in `total_seconds`, which can
therefore exceed 1800 without retroactively returning `TC_TIMEOUT`. A new cleanup
failure still propagates (`TC_IO` at the CLI); committed JS is not rolled back and
no success JSON is returned. Cancellation separately retains bounded grace,
hard-kill and pipe-drain deadlines. Cleanup is not a compiler retry. No dependency
versions or source revisions are lowered to pass.

Successful JSON retains source/artifact hashes and verified versions and adds
`timings` with exactly three finite, nonnegative numeric fields:

- `bootstrap_seconds`: fresh Devbox install, binary resolution and Dune check;
- `compile_seconds`: the Dune build, **including locked dependency preparation**,
  not merely compilation of hero.ml;
- `total_seconds`: validation through version checks, publication and cleanup.

Elapsed times use a monotonic clock. A fresh workspace is not necessarily a cold
machine: Devbox/Nix can reuse immutable public packages already in the Nix store.
Do not infer a cold/warm speedup from one measurement.

The default CLI has generic errors. Explicit `--diagnostics` emits only closed
phase/event/outcome/error-class/errno/code records, capped at 64 records, 16384
bytes and 256 bytes per line. Raw tool streams, argv, environment values, exception
messages and private paths are never emitted. Timing fields are not raw logs.

## Linux cancellation and cleanup

This driver requires Linux `/proc` and Python's pidfd APIs. It starts each tool in
an owned session, identifies members by PID, start identity, session and UID, gives
the initial group up to two seconds of SIGINT grace for Dune scheduler shutdown,
and then repeatedly checks and kills remaining owned-session workers, including
separate process groups with redirected pipes. pidfds and a second identity check
prevent signalling an unrelated reused PID. Hard cancellation and pipe draining
have bounded deadlines. Other sessions are not targeted. This is ownership-based
cleanup of trusted tools, not a sandbox against a tool deliberately escaping its
session.

A missing initial leader identity is a refusal, not an empty owned session. A
later unreadable tracked/scanned identity is accepted as absent **only** if its
`/proc` PID entry is also confirmed absent; unreadable existing entries fail
closed. Unknown identities are never signalled, and a changed start/session/UID
identity is never treated as the old process. These metadata failures retain the
local workspace and lock rather than claiming that termination was verified.

A workspace/lock/publication cleanup failure must not replace an existing primary
build error. Each operation passes its own exception explicitly; `None` means a
successful body, so an unrelated caller's already handled exception cannot suppress
a fresh cleanup failure. Secondary cleanup outcomes remain separately classified.
If tool termination cannot be verified, workspace removal is skipped and its local
lock and workspace are retained for explicit recovery; nothing is published. An
`ENOTEMPTY` cleanup result alone is **not** evidence of a surviving worker.

## Migration boundary

This migration is **client-only**. **Native Forester** realization and the
**converter** driver still use their existing pinned **Nix** paths for this CI
check. Their source revisions, content pins, full dependency lock and native
assets are unchanged. Migrating those remaining paths is separate future work.
Client compilation alone does not establish native HTML, browser acceptance,
hosted CI success or deployment. Hosted runs and publication require their own
review and authorization; local-only measurement evidence is not distributed.
