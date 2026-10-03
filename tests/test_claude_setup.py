"""Claude setup uses temporary homes and a stub CLI; real accounts are untouched."""
import importlib.util
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/showandtell/scripts/claude_setup.py'
spec = importlib.util.spec_from_file_location('claude_setup', SCRIPT)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class ClaudeSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="showandtell Claude's test ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.plugin = self.home / 'plugin'
        for name, contents in {'scripts/run.sh': '#!/bin/sh\n', 'scripts/showandtell.py': '# runtime\n',
                               'skills/showandtell/SKILL.md': '# Showandtell\n'}.items():
            file = self.plugin / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(contents)
        hook = {'type': 'command', 'command': 'SHOWANDTELL_CLIENT=claude sh "$SHOWANDTELL_ROOT/scripts/run.sh" hook'}
        self.hooks = {'hooks': {'PreToolUse': [{'matcher': '^mcp__codex-cu__js$', 'hooks': [hook]}],
                               'Stop': [{'hooks': [{**hook, 'async': True}]}]}}
        (self.plugin / 'hooks').mkdir()
        (self.plugin / 'hooks/claude.json').write_text(json.dumps(self.hooks))
        self.codex = self.home / '.codex'
        script = self.home / 'native entry.mjs'
        script.write_text('// native runtime fixture\n')
        self.server = {'command': sys.executable, 'args': [str(script), '--literal=$(never-run)'],
                       'env': {'PRIVATE_TEST_VALUE': 'not printed'}, 'env_vars': [], 'enabled': True}
        self.native('1.9.0', {**self.server, 'env': {'VERSION': 'old'}})
        self.native('1.10.0', self.server)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        cli = self.bin / 'claude'
        cli.write_text(f'#!{sys.executable}\n' + '''import json, os, pathlib, sys
home = pathlib.Path(os.environ['HOME'])
with (home/'calls.jsonl').open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
if (home/'cli-fail').exists():
    print('PRIVATE_TEST_VALUE=not printed', file=sys.stderr)
    sys.exit(1)
file=home/'.claude.json'
config=json.loads(file.read_text()) if file.exists() else {}
if sys.argv[2] == 'remove':
    assert sys.argv[1:] == ['mcp','remove','--scope','user','codex-cu']
    del config['mcpServers']['codex-cu']
else:
    assert sys.argv[1:6] == ['mcp','add-json','--scope','user','codex-cu']
    server = json.loads(sys.argv[6])
    if (home/'fail-new').exists() and server['env'].get('VERSION') == 'new': sys.exit(1)
    config.setdefault('mcpServers',{})['codex-cu']=server
file.write_text(json.dumps(config))
''')
        cli.chmod(0o755)
        self.environment = patch.dict(os.environ, {'PATH': str(self.bin), 'CLAUDE_CONFIG_DIR': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def native(self, version, server):
        path = self.codex / 'plugins/cache/openai-bundled/unified-computer-use' / version / '.mcp.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'mcpServers': {'cua_repl': server}}))
        return path

    def configure(self, **kwargs):
        return setup.configure(plugin=self.plugin, home=self.home, codex_home=self.codex, **kwargs)

    def test_private_output_uses_newest_runtime_and_changes_no_user_settings(self):
        output = self.home / 'private output'
        for _ in range(2):
            self.configure(output=output)
        server = json.loads((output / 'mcp.json').read_text())['mcpServers']['codex-cu']
        self.assertEqual(server, {**{k: self.server[k] for k in ('command', 'args', 'env')}, 'type': 'stdio'})
        command = json.loads((output / 'settings.json').read_text())['hooks']['Stop'][0]['hooks'][0]['command']
        self.assertEqual(shlex.split(command), ['SHOWANDTELL_CLIENT=claude', 'sh', str(self.plugin.resolve() / 'scripts/run.sh'), 'hook'])
        for name in ('mcp.json', 'settings.json'):
            self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.home / '.claude').exists())
        self.assertFalse((self.home / 'calls.jsonl').exists())
        (output / 'settings.json').write_text('{"keep": true}')
        with self.assertRaisesRegex(ValueError, 'different configuration'):
            self.configure(output=output)

    def test_install_preserves_settings_copies_runtime_and_is_idempotent(self):
        settings = self.home / '.claude/settings.json'
        settings.parent.mkdir()
        original = {'permissions': {'deny': ['Bash(rm *)']}, 'env': {'USER_VALUE': 'keep'},
                    'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo unrelated'}]}]}}
        settings.write_text(json.dumps(original))
        config = self.home / '.claude.json'
        config.write_text(json.dumps({'theme': 'keep', 'mcpServers': {'other': {'command': '/other'}}}))
        runtime = self.configure(install=True)
        first = settings.read_bytes()
        self.configure(install=True)
        self.assertEqual(settings.read_bytes(), first)
        merged = json.loads(first)
        self.assertEqual(merged['permissions'], original['permissions'])
        self.assertEqual(merged['env'], original['env'])
        self.assertEqual(merged['hooks']['Stop'][0], original['hooks']['Stop'][0])
        self.assertEqual(len(merged['hooks']['Stop']), 2)
        backups = list(settings.parent.glob('settings.json.showandtell-backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), original)
        self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(config.read_text())['mcpServers']['other'], {'command': '/other'})
        self.assertEqual(len((self.home / 'calls.jsonl').read_text().splitlines()), 1)
        shutil.rmtree(self.plugin)
        self.assertEqual((runtime / 'scripts/showandtell.py').read_text(), '# runtime\n')
        self.assertEqual((self.home / '.claude/skills/showandtell/SKILL.md').read_text(), '# Showandtell\n')
        self.assertEqual(shlex.split(merged['hooks']['Stop'][1]['hooks'][0]['command'])[2], str(runtime / 'scripts/run.sh'))

    def test_conflicts_fail_before_registration_or_setting_changes(self):
        config = self.home / '.claude.json'
        original = {'mcpServers': {'codex-cu': {'command': '/different'}}}
        config.write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, 'different codex-cu'):
            self.configure(install=True)
        self.assertEqual(json.loads(config.read_text()), original)
        config.unlink()
        skill = self.home / '.claude/skills/showandtell'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('user skill')
        with self.assertRaisesRegex(ValueError, 'not owned'):
            self.configure(install=True)
        self.assertFalse((self.home / 'calls.jsonl').exists())
        self.assertFalse((self.home / '.showandtell').exists())

    def test_invalid_latest_runtime_is_not_silently_downgraded(self):
        for invalid in ({**self.server, 'command': '/missing'}, {**self.server, 'args': ['/missing.mjs']},
                        {**self.server, 'env': {'INVALID': 1}}):
            self.native('2.0.0', invalid)
            with self.assertRaises(ValueError):
                self.configure(output=self.home / 'output')
        self.assertFalse((self.home / 'output').exists())

    def test_owned_server_refresh_rolls_back_failure_then_updates(self):
        runtime = self.configure(install=True)
        old = json.loads((self.home / '.claude.json').read_text())['mcpServers']['codex-cu']
        self.native('2.0.0', {**self.server, 'env': {'VERSION': 'new'}})
        (self.home / 'fail-new').touch()
        with self.assertRaisesRegex(ValueError, 'was restored'):
            self.configure(install=True)
        self.assertEqual(json.loads((self.home / '.claude.json').read_text())['mcpServers']['codex-cu'], old)
        self.assertEqual(json.loads((runtime / '.codex-cu.json').read_text()), old)
        (self.home / 'fail-new').unlink()
        self.configure(install=True)
        new = json.loads((runtime / '.codex-cu.json').read_text())
        self.assertEqual(new['env'], {'VERSION': 'new'})
        self.assertEqual(new, json.loads((self.home / '.claude.json').read_text())['mcpServers']['codex-cu'])
        self.assertEqual((runtime / '.codex-cu.json').stat().st_mode & 0o777, 0o600)

    def test_cli_failure_does_not_install_hooks_or_expose_configuration(self):
        (self.home / 'cli-fail').touch()
        with self.assertRaisesRegex(ValueError, 'could not register') as error:
            self.configure(install=True)
        self.assertNotIn('PRIVATE_TEST_VALUE', str(error.exception))
        self.assertFalse((self.home / '.claude/settings.json').exists())
        self.assertFalse((self.home / '.showandtell').exists())
        stderr = io.StringIO()
        with redirect_stderr(stderr), patch.object(setup, 'configure', side_effect=subprocess.TimeoutExpired(['claude', 'secret-value'], 60)):
            with self.assertRaises(SystemExit) as result:
                setup.main(['--install'])
        self.assertEqual(result.exception.code, 1)
        self.assertNotIn('secret-value', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
