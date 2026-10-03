"""Configure Claude Code to use this Mac's installed Codex computer-use runtime."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile


PLUGIN = Path(__file__).resolve().parents[1]
OWNER = 'Showandtell Claude setup v1\n'
MARKER = '.showandtell-owned'


def read_object(path):
    if not path.exists():
        return {}
    try:
        result = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise ValueError(f'Cannot read valid JSON from {path.name}; it was not changed.') from None
    if not isinstance(result, dict):
        raise ValueError(f'{path.name} must contain a JSON object.')
    return result


def native_server(codex_home):
    bundled = codex_home / 'plugins/cache/openai-bundled/unified-computer-use'
    candidates = [p for p in bundled.glob('*/.mcp.json')
                  if re.fullmatch(r'\d+(?:\.\d+)+', p.parent.name)]
    if not candidates:
        raise ValueError('Open Codex desktop with computer use installed, then run setup again.')
    source = max(candidates, key=lambda p: tuple(map(int, p.parent.name.split('.'))))
    servers = read_object(source).get('mcpServers', {})
    config = servers.get('cua_repl') if isinstance(servers, dict) else None
    if not isinstance(config, dict):
        raise ValueError('The installed computer-use configuration has no cua_repl server.')
    command, args, env = config.get('command'), config.get('args'), config.get('env', {})
    if (not isinstance(command, str) or '\x00' in command
            or not Path(command).is_absolute() or not Path(command).is_file()
            or not os.access(command, os.X_OK)):
        raise ValueError('The installed computer-use executable is unavailable; repair/update Codex first.')
    if (not isinstance(args, list) or not args
            or any(not isinstance(arg, str) or '\x00' in arg for arg in args)
            or not Path(args[0]).is_absolute() or not Path(args[0]).is_file()):
        raise ValueError('The installed computer-use script or arguments are unavailable; repair/update Codex first.')
    if (not isinstance(env, dict) or any(not isinstance(k, str) or not k or '=' in k or '\x00' in k
            or not isinstance(v, str) or '\x00' in v for k, v in env.items())):
        raise ValueError('The installed computer-use environment is invalid.')
    env = dict(env)
    inherited = config.get('env_vars', [])
    if not isinstance(inherited, list) or any(not isinstance(k, str) or not k or '=' in k or '\x00' in k for k in inherited):
        raise ValueError('The installed computer-use environment list is invalid.')
    for name in inherited:
        if name in os.environ and name not in env:
            env[name] = os.environ[name]
    return {'type': 'stdio', 'command': command, 'args': args, 'env': env}


def hook_settings(plugin, runtime):
    settings = read_object(plugin / 'hooks/claude.json')
    hooks = settings.get('hooks')
    if not isinstance(hooks, dict) or not hooks:
        raise ValueError('This Showandtell package is missing Claude hooks.')
    script = shlex.quote(str(runtime / 'scripts/run.sh'))
    for groups in hooks.values():
        for group in groups:
            for hook in group['hooks']:
                hook['command'] = hook['command'].replace('"$SHOWANDTELL_ROOT/scripts/run.sh"', script)
                if '$SHOWANDTELL_ROOT' in hook['command']:
                    raise ValueError('Cannot resolve the packaged Claude hook command.')
    return settings


def merge_settings(current, additions):
    merged = deepcopy(current)
    hooks = merged.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Existing Claude hooks are not an object; settings were not changed.')
    owned = {hook['command'] for groups in additions['hooks'].values()
             for group in groups for hook in group['hooks']}
    for event, groups in hooks.items():
        if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get('hooks'), list)
                or any(not isinstance(h, dict) for h in g['hooks']) for g in groups):
            raise ValueError('Existing Claude hooks are invalid; settings were not changed.')
        kept = []
        for group in groups:
            group['hooks'] = [hook for hook in group['hooks'] if hook.get('command') not in owned]
            if group['hooks']:
                kept.append(group)
        hooks[event] = kept
    for event, groups in additions['hooks'].items():
        hooks.setdefault(event, []).extend(deepcopy(groups))
    return merged


def check_owned(directory):
    if directory.is_symlink() or (directory.exists() and (not directory.is_dir()
            or not (directory / MARKER).is_file() or (directory / MARKER).read_text() != OWNER
            or any(p.is_symlink() for p in directory.rglob('*')))):
        raise ValueError(f'{directory} already exists and is not owned by this setup; it was not changed.')


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, data):
    private_write(path, (json.dumps(data, indent=2) + '\n').encode())


def copy_tree(source, destination):
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in source.rglob('*'):
        if '__pycache__' in item.parts or item.suffix == '.pyc':
            continue
        if item.is_symlink():
            raise ValueError('Showandtell runtime copies cannot contain symlinks.')
        if item.is_file():
            private_write(destination / item.relative_to(source), item.read_bytes())


def register_server(claude, home, server, previous=None):
    """Only replace our exact prior configuration; restore it if an upgrade fails."""
    def invoke(arguments):
        try:
            return subprocess.run([claude, 'mcp', *arguments], capture_output=True, text=True,
                                  timeout=60, cwd=home, env={**os.environ, 'HOME': str(home)}).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def saved():
        return read_object(home / '.claude.json').get('mcpServers', {}).get('codex-cu')

    if previous is not None:
        if saved() != previous or not invoke(['remove', '--scope', 'user', 'codex-cu']):
            raise ValueError('Claude could not remove the prior owned codex-cu server; inspect its configuration and retry.')
    invoke(['add-json', '--scope', 'user', 'codex-cu', json.dumps(server)])
    if saved() == server:
        return
    if previous is not None and saved() is None:
        invoke(['add-json', '--scope', 'user', 'codex-cu', json.dumps(previous)])
        if saved() == previous:
            raise ValueError('Claude could not register the updated server. The prior codex-cu server was restored; retry setup later.')
    raise ValueError('Claude could not register codex-cu; no Showandtell hooks were changed. Check claude mcp configuration and retry.')


def configure(*, output=None, install=False, plugin=PLUGIN, home=None, codex_home=None):
    home = Path.home() if home is None else Path(home)
    codex_home = Path(os.environ.get('CODEX_HOME', home / '.codex')) if codex_home is None else Path(codex_home)
    server = native_server(codex_home)
    if output is not None:
        output = Path(output).expanduser().resolve()
        documents = {'mcp.json': {'mcpServers': {'codex-cu': server}},
                     'settings.json': hook_settings(plugin, plugin.resolve())}
        for name, data in documents.items():
            target = output / name
            if target.is_symlink() or (target.exists() and read_object(target) != data):
                raise ValueError(f'{target.name} already contains different configuration; choose an empty output directory.')
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name, data in documents.items():
            write_json(output / name, data)
        return output
    if not install:
        raise ValueError('Choose --output DIRECTORY or --install.')
    if os.environ.get('CLAUDE_CONFIG_DIR') and Path(os.environ['CLAUDE_CONFIG_DIR']).expanduser().resolve() != (home / '.claude').resolve():
        raise ValueError('Custom CLAUDE_CONFIG_DIR profiles are not installed automatically; use --output DIRECTORY.')
    claude = shutil.which('claude')
    if not claude:
        raise ValueError('Install Claude Code and put claude on PATH before using --install.')
    config_path = home / '.claude.json'
    settings_path = home / '.claude/settings.json'
    if config_path.is_symlink() or settings_path.is_symlink():
        raise ValueError('Claude configuration files are symlinks; use --output instead of replacing them.')
    config = read_object(config_path)
    servers = config.get('mcpServers', {})
    if not isinstance(servers, dict):
        raise ValueError('Existing Claude MCP configuration is invalid; it was not changed.')
    runtime = home / '.showandtell/runtime'
    skill = home / '.claude/skills/showandtell'
    for path in (runtime, skill):
        check_owned(path)
    existing = servers.get('codex-cu')
    prior_owned = read_object(runtime / '.codex-cu.json')
    if existing is not None and existing != server and not (prior_owned and existing == prior_owned):
        raise ValueError('Claude already has a different codex-cu server. Review it with claude mcp get codex-cu; setup will not replace it.')
    current = read_object(settings_path)
    settings = merge_settings(current, hook_settings(plugin, runtime))
    # Validate all source files before registering or writing any persistent settings.
    for folder in ('scripts', 'hooks', 'skills'):
        if not (plugin / folder).is_dir() or any(p.is_symlink() for p in (plugin / folder).rglob('*')):
            raise ValueError('The Showandtell runtime source is missing or contains symlinks.')
    if not (plugin / 'skills/showandtell/SKILL.md').is_file():
        raise ValueError('The Showandtell skill is missing.')
    if existing != server:
        register_server(claude, home, server, existing)
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(runtime / MARKER, OWNER.encode())
    write_json(runtime / '.codex-cu.json', server)
    for folder in ('scripts', 'hooks', 'skills'):
        copy_tree(plugin / folder, runtime / folder)
    copy_tree(plugin / 'skills/showandtell', skill)
    private_write(skill / MARKER, OWNER.encode())
    if settings != current:
        if settings_path.exists():
            fd, backup = tempfile.mkstemp(prefix='settings.json.showandtell-backup-', dir=settings_path.parent)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(settings_path.read_bytes())
        write_json(settings_path, settings)
    return runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path, help='Write private mcp.json/settings.json for one Claude run; no user settings change')
    mode.add_argument('--install', action='store_true', help='Register user MCP access and copy stable hooks/skill into the home directory')
    args = parser.parse_args(argv)
    try:
        destination = configure(output=args.output, install=args.install)
    except subprocess.SubprocessError:
        parser.exit(1, 'Showandtell: Claude registration failed or timed out; inspect the MCP configuration and retry.\n')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Showandtell: {error}\n')
    if args.output:
        print(f'Private Claude configuration written to {destination}.')
        print('Use --strict-mcp-config --mcp-config <directory>/mcp.json --settings <directory>/settings.json.')
    else:
        print(f'Claude setup installed. Stable runtime: {destination}')
        print('Restart Claude Code and review the MCP server and hooks. Tool permissions were not auto-approved.')


if __name__ == '__main__':
    main()
