#!/usr/bin/env python3
"""Build the plugin upload ZIP, excluding local captures and development files."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
plugin = root / 'plugins/showandtell'
manifest = json.loads((plugin / '.codex-plugin/plugin.json').read_text())
output = root / 'dist' / ('showandtell-' + manifest['version'] + '.zip')
output.parent.mkdir(exist_ok=True)
files = [plugin / '.codex-plugin/plugin.json']
for folder in ('hooks', 'scripts', 'skills', 'assets'):
    files.extend(p for p in (plugin / folder).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
assert any(p.name == 'SKILL.md' for p in files), 'Missing skill'
assert all(not p.is_symlink() and p.resolve().is_relative_to(plugin.resolve()) for p in files)
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, path.relative_to(plugin))
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    assert '.codex-plugin/plugin.json' in archive.namelist()
digest = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n')
print(output)
print(f'{len(files)} files; SHA-256 {digest}')
