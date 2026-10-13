#!/usr/bin/env python3
"""Fail closed on pending synthetic anchors before any hosted content access."""
import argparse
import importlib.util
import os
import re
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location('safe_web', Path(__file__).absolute().with_name('safe-web.py'))
safe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safe)


def main():
    try:
        parser = safe.SafeParser(description=__doc__)
        parser.add_argument('--inputs', required=True)
        parser.add_argument('--pins', required=True)
        parser.add_argument('--github-output', required=True)
        args = parser.parse_args()
        if (os.environ.get('GITHUB_EVENT_NAME') != 'push' or
                os.environ.get('GITHUB_REPOSITORY') != 'ryoryoryo3838/miya-lis.net' or
                not re.fullmatch(r'refs/heads/ci/synthetic-dry-run-[A-Za-z0-9][A-Za-z0-9._-]*', os.environ.get('GITHUB_REF', ''))):
            raise safe.GateError('SW_SYNTHETIC_SCOPE')
        try:
            inputs = safe.strict_json(safe.read_bounded(safe.checked_path(args.inputs), safe.MAX_MANIFEST))
            safe.object_keys(inputs, {'schema', 'dataset', 'content_revision', 'manifest_sha256', 'home_id'})
            if inputs['schema'] != 'safe-web-synthetic-inputs-v1' or inputs['dataset'] != 'synthetic-only':
                raise safe.GateError('SW_SYNTHETIC_INPUT')
            safe.revision(inputs['content_revision'])
            if type(inputs['manifest_sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', inputs['manifest_sha256']):
                raise safe.GateError('SW_SYNTHETIC_INPUT')
            safe.identifier(inputs['home_id'])
        except (safe.GateError, OSError, ValueError, KeyError, TypeError, RecursionError):
            raise safe.GateError('SW_SYNTHETIC_INPUT') from None
        pins = safe.validate_pins(safe.strict_json(safe.read_bounded(safe.checked_path(args.pins), safe.MAX_MANIFEST)))
        if (pins['converter_revision'] != 'a98f2800a88748381fcf9821d64e713925a0a027' or
                pins['converter_build_argv'] != ['nix', 'develop', '--no-write-lock-file', '--command', 'python3', 'scripts/build-public-cli.py'] or
                pins['converter_executable'] != '_build/public-cli/tree_of_md'):
            raise safe.GateError('SW_PIN')
        payload = ('content_revision=' + inputs['content_revision'] + '\n' +
                   'manifest_sha256=' + inputs['manifest_sha256'] + '\n' +
                   'home_id=' + inputs['home_id'] + '\n' +
                   'converter_revision=' + pins['converter_revision'] + '\n')
        with safe.checked_path(args.github_output).open('a') as output:
            output.write(payload)
        return 0
    except safe.GateError as error:
        print(error.code, file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print('SW_IO', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
