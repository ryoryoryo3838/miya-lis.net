"""Code-only synthetic CI contract; no hosted requests or real content."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/synthetic-dry-run.yml'
INPUTS = ROOT / 'config/synthetic-inputs.json'
PINS = ROOT / 'config/pins.json'
GATE = ROOT / 'scripts/synthetic-ci-config.py'
CONVERTER_REV = 'a98f2800a88748381fcf9821d64e713925a0a027'
BUILD_ARGV = ['nix', 'develop', '--no-write-lock-file', '--command',
              'python3', 'scripts/build-public-cli.py']
EXECUTABLE = '_build/public-cli/tree_of_md'


class SyntheticWorkflowTests(unittest.TestCase):
    def gate(self, inputs=INPUTS, pins=PINS, *, event='push', ref='refs/heads/ci/synthetic-dry-run-syntax-fixture', repository='ryoryoryo3838/miya-lis.net'):
        self.assertTrue(GATE.is_file(), 'null-gated synthetic preflight must exist')
        with tempfile.TemporaryDirectory(prefix='synthetic-config-') as directory:
            output = Path(directory) / 'github-output'
            result = subprocess.run([sys.executable, '-B', str(GATE), '--inputs', str(inputs),
                         '--pins', str(pins), '--github-output', str(output)],
                         env={'PATH': os.environ['PATH'], 'GITHUB_EVENT_NAME': event, 'GITHUB_REF': ref,
                              'GITHUB_REPOSITORY': repository},
                         capture_output=True, text=True, timeout=10)
            return result, output.read_text() if output.exists() else None

    def test_null_fixture_stops_before_creating_runner_outputs(self):
        self.assertTrue(GATE.is_file(), 'null-gated synthetic preflight must exist')
        self.assertTrue(INPUTS.is_file(), 'fixed synthetic input configuration must exist')
        current = json.loads(INPUTS.read_bytes())
        self.assertEqual(set(current), {'schema', 'dataset', 'content_revision', 'manifest_sha256', 'home_id'})
        self.assertEqual(current['schema'], 'safe-web-synthetic-inputs-v1')
        self.assertEqual(current['dataset'], 'synthetic-only')
        with tempfile.TemporaryDirectory(prefix='synthetic-null-fixture-') as directory:
            inputs = Path(directory) / 'inputs.json'
            inputs.write_text(json.dumps(dict(schema='safe-web-synthetic-inputs-v1', dataset='synthetic-only',
                                             content_revision=None, manifest_sha256=None, home_id=None)))
            result, output = self.gate(inputs)
        self.assertEqual((result.returncode, result.stdout, result.stderr, output),
                         (2, '', 'SW_SYNTHETIC_INPUT\n', None))

    def test_syntax_ready_fixture_emits_exact_anchors_without_a_content_lookup(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-syntax-ready-') as directory:
            inputs = Path(directory) / 'inputs.json'
            inputs.write_text(json.dumps(dict(schema='safe-web-synthetic-inputs-v1', dataset='synthetic-only',
                content_revision='a' * 40, manifest_sha256='b' * 64, home_id='MiXeD-Home')))
            result, output = self.gate(inputs)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertEqual(output, f'content_revision={"a" * 40}\nmanifest_sha256={"b" * 64}\nhome_id=MiXeD-Home\nconverter_revision={CONVERTER_REV}\n')

    def test_gate_rejects_nonapproved_event_branch_or_repository_before_output(self):
        valid = dict(event='push', ref='refs/heads/ci/synthetic-dry-run-syntax-fixture', repository='ryoryoryo3838/miya-lis.net')
        cases = [dict(event='workflow_dispatch'), dict(event='pull_request'), dict(event=''),
                 dict(ref='refs/heads/miya'), dict(ref='refs/tags/ci/synthetic-dry-run-fixture'),
                 dict(ref='refs/heads/ci/synthetic-dry-run-'),
                 dict(ref='refs/heads/ci/synthetic-dry-run-fixture/nested'),
                 dict(repository='unapproved/site')]
        with tempfile.TemporaryDirectory(prefix='synthetic-scope-') as directory:
            inputs = Path(directory) / 'inputs.json'
            inputs.write_text(json.dumps(dict(schema='safe-web-synthetic-inputs-v1', dataset='synthetic-only',
                content_revision='a' * 40, manifest_sha256='b' * 64, home_id='MiXeD-Home')))
            for case in cases:
                with self.subTest(scope=case):
                    result, output = self.gate(inputs, **(valid | case))
                    self.assertEqual((result.returncode, result.stdout, result.stderr, output),
                                     (2, '', 'SW_SYNTHETIC_SCOPE\n', None))

    def test_preflight_refuses_syntax_valid_but_unapproved_converter_pins(self):
        cases = [dict(converter_revision='c' * 40),
                 dict(converter_build_argv=['dune', 'build', 'bin/public_main.exe']),
                 dict(converter_executable='_build/other/tree_of_md')]
        with tempfile.TemporaryDirectory(prefix='synthetic-pin-tamper-') as directory:
            inputs, pins = Path(directory) / 'inputs.json', Path(directory) / 'pins.json'
            inputs.write_text(json.dumps(dict(schema='safe-web-synthetic-inputs-v1', dataset='synthetic-only',
                content_revision='a' * 40, manifest_sha256='b' * 64, home_id='MiXeD-Home')))
            for case in cases:
                with self.subTest(pin=tuple(case)):
                    pins.write_text(json.dumps(json.loads(PINS.read_bytes()) | case))
                    result, output = self.gate(inputs, pins)
                    self.assertEqual((result.returncode, result.stdout, result.stderr, output),
                                     (2, '', 'SW_PIN\n', None))

    def test_malformed_or_partial_inputs_refuse_without_echoing_or_outputs(self):
        ready = dict(schema='safe-web-synthetic-inputs-v1', dataset='synthetic-only',
                     content_revision='a' * 40, manifest_sha256='b' * 64, home_id='MiXeD-Home')
        cases = [ready | {field: None} for field in ['content_revision', 'manifest_sha256', 'home_id']]
        cases += [ready | dict(content_revision='main'), ready | dict(content_revision='A' * 40),
                  ready | dict(content_revision='a' * 39), ready | dict(content_revision=' a' + 'a' * 39),
                  ready | dict(manifest_sha256='B' * 64), ready | dict(manifest_sha256='b' * 63),
                  ready | dict(manifest_sha256=True), ready | dict(home_id='PUBLICA\nattack=value'),
                  ready | dict(home_id='../private'), ready | dict(home_id='home_id=other'),
                  ready | dict(dataset='real-notes'), ready | dict(schema='unapproved'),
                  ready | dict(unapproved='SYNTHETIC_PRIVATE_CANARY'),
                  {key: value for key, value in ready.items() if key != 'home_id'}, [], None]
        encoded = [json.dumps(value) for value in cases]
        encoded += [json.dumps(ready)[:-1] + ',"home_id":"duplicate"}', '{"schema":NaN}', 'invalid json']
        with tempfile.TemporaryDirectory(prefix='synthetic-invalid-input-') as directory:
            inputs = Path(directory) / 'inputs.json'
            for number, text in enumerate(encoded):
                with self.subTest(case=number):
                    inputs.write_text(text)
                    result, output = self.gate(inputs)
                    self.assertEqual((result.returncode, result.stdout, result.stderr, output),
                                     (2, '', 'SW_SYNTHETIC_INPUT\n', None))

    def test_unknown_cli_arguments_have_only_generic_diagnostics(self):
        result = subprocess.run([sys.executable, '-B', str(GATE), '--unknown', 'SYNTHETIC_PRIVATE_CANARY'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (2, '', 'SW_ARGS\n'))

    def test_candidate_uses_the_observed_converter_source_only_driver(self):
        from test_safe_web import load_module
        pins = json.loads(PINS.read_bytes())
        self.assertEqual(pins['converter_revision'], CONVERTER_REV)
        self.assertEqual(pins['converter_build_argv'], BUILD_ARGV)
        self.assertEqual(pins['converter_executable'], EXECUTABLE)
        self.assertEqual(load_module().validate_pins(pins), pins)

    def test_workflow_preflight_and_unit_child_cli_do_not_write_bytecode(self):
        # Read the job's environment, not the test runner's inherited -B/env.
        header = WORKFLOW.read_text(encoding='utf-8').split('\n  synthetic-html:\n', 1)[1]
        header = header.split('\n    steps:\n', 1)[0]
        env = {'PATH': os.environ['PATH'], 'GITHUB_EVENT_NAME': 'push',
               'GITHUB_REF': 'refs/heads/ci/synthetic-dry-run-bytecode-fixture',
               'GITHUB_REPOSITORY': 'ryoryoryo3838/miya-lis.net'}
        if '\n    env:\n' in header:
            for line in header.split('\n    env:\n', 1)[1].splitlines():
                if not line.startswith('      '):
                    break
                key, value = line.strip().split(':', 1)
                env[key] = value.strip().strip("'\"")
        with tempfile.TemporaryDirectory(prefix='synthetic-bytecode-', dir=os.environ.get('TMPDIR')) as directory:
            base = Path(directory)
            env['TMPDIR'] = directory
            preflight_site, child_site = base / 'preflight-site', base / 'child-site'
            # A cold child copy makes inherited suppression observable without
            # reusing or deleting the cache generated by the preflight.
            for site in [preflight_site, child_site]:
                for name in ['scripts/synthetic-ci-config.py', 'scripts/safe-web.py',
                             'config/synthetic-inputs.json', 'config/pins.json']:
                    target = site / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((ROOT / name).read_bytes())
            output = base / 'github-output'
            preflight = [sys.executable, 'scripts/synthetic-ci-config.py',
                         '--inputs', 'config/synthetic-inputs.json', '--pins', 'config/pins.json',
                         '--github-output', str(output)]
            # -B on the unit-style parent does not propagate to its raw CLI child.
            driver = ('import subprocess, sys; sys.exit(subprocess.run([sys.executable, '
                      '"scripts/synthetic-ci-config.py", "--unknown", '
                      '"SYNTHETIC_PRIVATE_CANARY"]).returncode)')
            steps = [('preflight', preflight_site, preflight, (0, '', '')),
                     ('unit child CLI', child_site, [sys.executable, '-B', '-c', driver],
                      (2, '', 'SW_ARGS\n'))]
            caches = {}
            for stage, site, command, expected in steps:
                result = subprocess.run(command, cwd=site, env=env, capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual((result.returncode, result.stdout, result.stderr), expected)
                caches[stage] = sorted(p.relative_to(site).as_posix() for p in site.rglob('*')
                                       if p.suffix in {'.pyc', '.pyo'} or p.name == '__pycache__')
            inputs = json.loads(INPUTS.read_bytes())
            expected_output = ''.join(key + '=' + inputs[key] + '\n'
                                      for key in ['content_revision', 'manifest_sha256', 'home_id'])
            self.assertEqual(output.read_text(), expected_output + 'converter_revision=' + CONVERTER_REV + '\n')
            self.assertEqual(caches, {'preflight': [], 'unit child CLI': []},
                             'generated bytecode after preflight or generated bytecode after unit child CLI')
            self.assertEqual(env.get('PYTHONDONTWRITEBYTECODE'), '1')

    def test_only_synthetic_branch_push_can_start_the_build_only_workflow(self):
        self.assertTrue(WORKFLOW.is_file(), 'new synthetic push-only workflow must exist')
        text = WORKFLOW.read_text(encoding='utf-8')
        trigger = text.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual(trigger.strip(), "push:\n    branches:\n      - 'ci/synthetic-dry-run-*'")
        self.assertEqual(sorted(p.name for p in WORKFLOW.parent.glob('*.yml')), ['synthetic-dry-run.yml'])
        self.assertIn('contents: read', text)
        self.assertIn("github.event_name == 'push'", text)
        self.assertIn("github.repository == 'ryoryoryo3838/miya-lis.net'", text)
        self.assertEqual(text.count('${{ secrets.PUBLIC_CONTENT_TOKEN }}'), 1)
        self.assertEqual(text.count('persist-credentials: false'), 3)
        self.assertEqual(text.count('fetch-depth: 1'), 3)
        self.assertEqual(text.count('submodules: false'), 3)
        self.assertEqual(text.count('lfs: false'), 3)
        for forbidden in ['workflow_dispatch:', 'pull_request:', 'schedule:', '${{ inputs.',
                          'contents: write', 'id-token: write', 'actions/cache@',
                          'deploy-pages@', 'wrangler', 'cloudflare', 'vault', 'wiki.miya-lis.net']:
            self.assertNotIn(forbidden, text.lower())
        self.assertIn('scripts/synthetic-ci-config.py', text)
        self.assertLess(text.index('scripts/synthetic-ci-config.py'), text.index('Install Nix'))
        self.assertLess(text.index('scripts/build-theme-client.py'),
                        text.index('repository: ryoryoryo3838/miya-lis-public'))
        self.assertIn('ref: ${{ steps.pins.outputs.content_revision }}', text)
        self.assertIn('ref: ${{ steps.pins.outputs.converter_revision }}', text)
        self.assertIn('f8fb5f5d88923db36643cf9c20c662adff969c98#legacyPackages.x86_64-linux.forester', text)
        self.assertIn('scripts/safe-web.py ci-run', text)
        self.assertIn('--theme-config config/theme.json', text)
        self.assertIn('--site-root .', text)
        self.assertIn('test_owned_css_leak.py', text)
        self.assertIn('test_synthetic_workflow.py', text)
        self.assertEqual(text.count('uses: actions/upload-artifact@'), 1)
        upload = text.split('uses: actions/upload-artifact@', 1)[1]
        self.assertIn('path: ${{ runner.temp }}/synthetic-public-html/', upload)
        self.assertIn('retention-days: 1', upload)
        self.assertIn('include-hidden-files: false', upload)
        self.assertIn('if-no-files-found: error', upload)


if __name__ == '__main__':
    unittest.main()
