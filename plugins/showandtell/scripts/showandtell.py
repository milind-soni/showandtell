#!/usr/bin/env python3
"""Collect Codex hook results locally. Python standard library + FFmpeg only."""
import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
CUA = re.compile(r'^mcp__cua_repl(?:__|\.)js$')
BINDING = re.compile(r'\b(var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+cua\.(getApp|getTab|createBrowserTab)\s*\(')
DISCOVERY = re.compile(r'^\s*(?:(?:var|let|const)\s+[A-Za-z_$][\w$]*\s*=\s*)?await\s+cua\.(?:getState|getApp|getTab|getBrowser|createBrowserTab|rewriteDocumentation)\([^;]*\)\s*;?\s*$', re.S)
KINDS = {'click', 'drag', 'scroll', 'move', 'type', 'key', 'navigate', 'select', 'setValue', 'secondary'}


def data_root():
    return Path(os.environ.get('SHOWANDTELL_HOME', str(Path.home() / '.showandtell'))).expanduser()


def key(value):
    value = str(value or 'unknown')
    return value if re.fullmatch(r'[\w-]{1,128}', value, re.ASCII) else hashlib.sha256(value.encode()).hexdigest()[:24]


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.writing-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, indent=2, allow_nan=False)
            f.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / '.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def image_info(raw):
    """Read PNG/JPEG dimensions without trusting a mislabeled MIME type."""
    if raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw) >= 24:
        width, height = struct.unpack('>II', raw[16:24])
        extension = 'png'
    elif raw.startswith(b'\xff\xd8'):
        i, width, height = 2, 0, 0
        while i + 4 < len(raw):
            if raw[i] != 255:
                break
            while i < len(raw) and raw[i] == 255:
                i += 1
            if i + 3 >= len(raw):
                break
            marker = raw[i]
            i += 1
            length = int.from_bytes(raw[i:i+2], 'big')
            if length < 2 or i + length > len(raw):
                break
            if marker in (0xC0, 0xC1, 0xC2) and length >= 7:
                height, width = struct.unpack('>HH', raw[i+3:i+7])
                break
            i += length
        extension = 'jpg'
    else:
        raise ValueError('Only PNG and JPEG screenshots are supported')
    if not (0 < width <= 16384 and 0 < height <= 16384 and width * height <= 50_000_000):
        raise ValueError('Invalid or excessive screenshot dimensions')
    return extension, width, height


def content_blocks(response, depth=0):
    """Only inspect result containers; never open URLs or referenced local files."""
    if depth >= 8:
        return []
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return []
    if not isinstance(response, dict):
        return []
    if isinstance(response.get('content'), list):
        blocks = response['content']
        # Saved CUA calls can wrap their entire result in one JSON text block.
        if len(blocks) == 1 and isinstance(blocks[0], dict) and blocks[0].get('type') == 'text':
            try:
                nested = json.loads(blocks[0].get('text', ''))
            except (ValueError, TypeError):
                nested = None
            if isinstance(nested, dict) and isinstance(nested.get('content'), list):
                return content_blocks(nested, depth + 1)
        return blocks
    return content_blocks(response['result'], depth + 1) if 'result' in response else []


def markers(text):
    # CUA can concatenate writes with AX output; parse only our JSON prefix.
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{"showandtell"\s*:\s*1\s*[,}]', text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get('showandtell') == 1:
            yield obj


def capture_file(path, limit):
    """Read only a bounded regular file from our private capture spool."""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Invalid capture file')
        raw = handle.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('Oversized capture file')
        return raw


def capture_id(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:32]


def collect_pending(directory, call_id=None):
    """Collect direct CUA captures even when its tool result was truncated."""
    directory = Path(directory)
    if call_id and 'capture:' + capture_id(call_id) in read_json(directory / 'session.json', {}).get('calls', []):
        return True
    pending = directory / 'captures'
    if not pending.is_dir() or pending.is_symlink():
        return False
    captured = False
    folders = [pending / capture_id(call_id)] if call_id else sorted(pending.iterdir())
    for folder in folders:
        if not re.fullmatch(r'[0-9a-f]{32}', folder.name) or folder.is_symlink() or not folder.is_dir():
            continue
        blocks = []
        try:
            lines = capture_file(folder / 'events.jsonl', 8_000_000).splitlines()
        except (OSError, ValueError):
            continue
        for line in lines:
            try:
                marker = json.loads(line)
            except (ValueError, UnicodeError):
                continue  # An interrupted tool may leave its last write incomplete.
            if not isinstance(marker, dict) or marker.get('showandtell') != 1:
                continue
            if marker.get('kind') == 'frame':
                name = marker.get('image')
                try:
                    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}\.img', name):
                        raise ValueError('Invalid screenshot filename')
                    raw = capture_file(folder / name, 21_000_000)
                    image_info(raw)
                except (OSError, ValueError, struct.error):
                    marker = {'showandtell': 1, 'kind': 'warning', 'reason': 'capture-image-unavailable'}
                else:
                    blocks.append({'type': 'image', '_capture_bytes': raw})
            blocks.append({'type': 'text', 'text': json.dumps(marker)})
        if blocks:
            collect({'tool_use_id': 'capture:' + folder.name, 'tool_response': {'content': blocks}}, directory)
            captured = True
        shutil.rmtree(folder)
    return captured


def collect(event, directory):
    directory = Path(directory)
    with locked(directory):
        session = read_json(directory / 'session.json', {'version': 1, 'frames': [], 'actions': [], 'warnings': [], 'calls': []})
        call_id = str(event.get('tool_use_id') or '')
        if call_id and call_id in session['calls']:
            return session
        frame_markers, marked, got_image = [], False, False
        now = event.get('recorded_at', time.time())
        if not finite(now):
            now = time.time()
        blocks = content_blocks(event.get('tool_response', {}))
        # CUA groups text and image output independently. Pair marked images FIFO.
        blocks = [b for b in blocks if isinstance(b, dict)]
        blocks = [b for b in blocks if b.get('type') == 'text'] + [b for b in blocks if b.get('type') == 'image']
        events = [m for b in blocks if b.get('type') == 'text' for m in markers(str(b.get('text', '')))]
        failed_images = {(str(m.get('id')), str(m.get('phase'))) for m in events if m.get('kind') == 'warning' and m.get('reason') == 'image-emission-failed'}
        expected = sum(m.get('kind') == 'frame' and (str(m.get('id')), str(m.get('phase'))) not in failed_images for m in events)
        ambiguous = expected > 0 and expected != sum(b.get('type') == 'image' for b in blocks)
        if ambiguous:
            session['warnings'].append('Image/marker count mismatch: screenshots retained without cursor association.')
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'text':
                for marker in markers(str(block.get('text', ''))):
                    kind = marker.get('kind')
                    if kind == 'frame':
                        if (str(marker.get('id')), str(marker.get('phase'))) in failed_images:
                            continue
                        frame_markers.append(marker)
                        marked = True
                    elif kind == 'action':
                        marked = True
                        if marker.get('type') not in KINDS or not finite(marker.get('t')):
                            session['warnings'].append('Ignored an invalid action marker.')
                            continue
                        action = {k: marker[k] for k in ('id', 't', 'type', 'surface') if k in marker}
                        action['surface'] = str(action.get('surface', 'unknown'))[:256]
                        if finite(marker.get('x')) and finite(marker.get('y')):
                            action.update(x=marker['x'], y=marker['y'])
                        to = marker.get('to')
                        if isinstance(to, list) and len(to) == 2 and all(finite(n) for n in to):
                            action['to'] = to
                        session['actions'].append(action)
                    elif kind == 'status':
                        for action in reversed(session['actions']):
                            if action.get('id') == marker.get('id'):
                                action['status'] = 'ok' if marker.get('status') == 'ok' else 'failed'
                                if finite(marker.get('t')):
                                    action['end'] = marker['t']
                                break
                    elif kind == 'warning':
                        marked = True
                        session['warnings'].append('Capture could not instrument an action or obtain a screenshot.')
            elif block.get('type') == 'image':
                pending = frame_markers.pop(0) if frame_markers and not ambiguous else None
                try:
                    raw = block.get('_capture_bytes')
                    if not isinstance(raw, bytes):
                        encoded = block.get('data', '')
                        if not isinstance(encoded, str) or len(encoded) > 28_000_000:
                            session['warnings'].append('Skipped an oversized screenshot.')
                            continue
                        raw = base64.b64decode(encoded, validate=True)
                    extension, width, height = image_info(raw)
                except (ValueError, struct.error):
                    session['warnings'].append('Skipped an invalid or unsupported screenshot.')
                    pending = None
                    continue
                got_image = True
                name = hashlib.sha256(raw).hexdigest()[:24] + '.' + extension
                frames_dir = directory / 'frames'
                frames_dir.mkdir(exist_ok=True, mode=0o700)
                path = frames_dir / name
                if not path.exists():
                    with path.open('xb') as f:
                        f.write(raw)
                    path.chmod(0o600)
                meta = pending or {}
                stamp = meta.get('t', now)
                surface = str(meta.get('surface', 'untracked'))[:256]
                # The caller may emit the same after-frame again; retain marked pairs.
                if pending or not session['frames'] or session['frames'][-1]['file'] != 'frames/' + name:
                    session['frames'].append({'t': stamp if finite(stamp) else now, 'file': 'frames/' + name,
                                              'width': width, 'height': height, 'surface': surface,
                                              'phase': meta.get('phase') if meta.get('phase') in ('before', 'after') else 'observed'})
                pending = None
        if got_image and not marked:
            session['warnings'].append('Uninstrumented call: saved its screenshots; no cursor coordinates were inferred.')
        if not got_image and not marked:
            return session
        if frame_markers:
            session['warnings'].append('Some screenshot markers had no image in the tool result.')
        if call_id:
            session['calls'].append(call_id)
        session['warnings'] = list(dict.fromkeys(session['warnings']))
        atomic_json(directory / 'session.json', session)
        return session


def hook(event):
    if os.environ.get('SHOWANDTELL_DISABLED') == '1':
        return {}
    session_dir = data_root() / key(event.get('session_id'))
    turn_dir = session_dir / key(event.get('turn_id'))
    kind = event.get('hook_event_name')
    if kind == 'SessionStart' or (kind == 'PostToolUse' and re.fullmatch(r'mcp__cua_repl(?:__|\.)js_reset', str(event.get('tool_name', '')))):
        with locked(session_dir):
            atomic_json(session_dir / 'runtime.json', {'seen': False, 'bindings': {}})
        return {}
    if kind == 'PreToolUse' and CUA.search(str(event.get('tool_name', ''))):
        args = event.get('tool_input', {})
        if not isinstance(args, dict) or not isinstance(args.get('code'), str):
            return {}
        code = args['code']
        with locked(session_dir):
            runtime = read_json(session_dir / 'runtime.json', {'seen': False, 'bindings': {}})
            previous = dict(runtime['bindings'])
            declared = set()
            for match in BINDING.finditer(code):
                declared.add(match[2])
                runtime['bindings'][match[2]] = {'kind': 'app' if match[3] == 'getApp' else 'browser', 'mutable': match[1] != 'const'}
            first = not runtime['seen'] or DISCOVERY.fullmatch(code)
            runtime['seen'] = True
            atomic_json(session_dir / 'runtime.json', runtime)
        if first:
            return {}  # Preserve CUA's required first-call bootstrap verbatim.
        setup = (HERE / 'capture.js').read_text()
        turn_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        pending = turn_dir / 'captures'
        pending.mkdir(exist_ok=True, mode=0o700)
        call_id = event.get('tool_use_id')
        capture_dir = pending / (capture_id(call_id) if call_id else uuid.uuid4().hex)
        capture_dir.mkdir(mode=0o700)
        mode = 'full' if os.environ.get('SHOWANDTELL_CAPTURE') == 'full' else 'reuse'
        setup += '\nawait __showandtell.saveTo(' + json.dumps(str(capture_dir.resolve())) + ', ' + json.dumps(mode) + ');'
        for name, binding in previous.items():
            if name in declared:
                continue
            operation = name + ' = __showandtell.wrap' if binding['mutable'] else '__showandtell.instrument'
            setup += '\ntry { if (typeof ' + name + ' !== "undefined") ' + operation + '(' + name + ', ' + json.dumps(binding['kind']) + '); } catch (_) {}'
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow',
                                      'updatedInput': {**args, 'code': setup + '\n' + code}}}
    if kind == 'PostToolUse':
        if collect_pending(turn_dir, event.get('tool_use_id')):
            warnings = [marker for block in content_blocks(event.get('tool_response', {}))
                        if isinstance(block, dict) and block.get('type') == 'text'
                        for marker in markers(str(block.get('text', ''))) if marker.get('kind') == 'warning']
            if warnings:
                collect({**event, 'tool_response': {'content': [
                    {'type': 'text', 'text': json.dumps(marker)} for marker in warnings]}}, turn_dir)
        else:
            collect(event, turn_dir)
        return {}
    if kind == 'Stop':
        collect_pending(turn_dir)
    if kind == 'Stop' and (turn_dir / 'session.json').exists():
        from render import render_session
        with locked(turn_dir):
            digest = hashlib.sha256((turn_dir / 'session.json').read_bytes()).hexdigest()
            done = read_json(turn_dir / 'export.json', {})
            if done.get('digest') == digest and (turn_dir / 'video.mp4').exists():
                return {}
            manifest = read_json(turn_dir / 'session.json', {})
            if not manifest.get('frames'):
                return {'systemMessage': 'Showandtell saved action metadata but no screenshot frames, so no video was rendered. '
                        'Reuse mode needs normal getScreenshot or getAXStateAndScreenshot observations. '
                        'Text-only accessibility observations are not video frames.'}
            result = render_session(turn_dir, turn_dir / 'video.mp4')
            atomic_json(turn_dir / 'export.json', {**result, 'digest': digest})
        return {'systemMessage': 'Showandtell video: ' + str(turn_dir / 'video.mp4')}
    return {}


def import_transcript(source, directory):
    """Import supported saved MCP results without executing recorded code."""
    count = 0
    for line in Path(source).open():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        payload = record.get('payload', {})
        item = payload.get('item', {}) if payload.get('type') == 'item_completed' else {}
        if item.get('type') != 'McpToolCall' or not re.search(r'cua|browser|computer', item.get('server', '')):
            continue
        from datetime import datetime
        stamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00')).timestamp()
        collect({'tool_response': item.get('result', {}), 'tool_use_id': item.get('id'), 'recorded_at': stamp}, directory)
        count += 1
    return {'importedCalls': count, 'session': str(Path(directory).resolve())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('hook', help='Read one Codex lifecycle event from stdin')
    sub.add_parser('doctor', help='Check the two runtime requirements')
    imp = sub.add_parser('import', help='Recover available images/markers from a local task transcript')
    imp.add_argument('transcript', type=Path)
    imp.add_argument('-o', '--output', required=True, type=Path)
    ren = sub.add_parser('render', help='Re-render a captured session')
    ren.add_argument('session', type=Path)
    ren.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    if args.command == 'hook':
        try:
            event = json.load(sys.stdin)
            if not isinstance(event, dict):
                raise ValueError('Hook input must be an object')
            print(json.dumps(hook(event)))
        except Exception as error:
            # A video failure must not break the user's computer-use workflow.
            print(json.dumps({'systemMessage': 'Showandtell: ' + str(error)[:250]}))
    elif args.command == 'doctor':
        checks = {x: shutil.which(x) for x in ('python3', 'ffmpeg', 'ffprobe')}
        print(json.dumps(checks, indent=2))
        if not all(checks.values()):
            sys.exit('Install Python 3 and FFmpeg first (macOS: brew install python ffmpeg).')
    elif args.command == 'import':
        print(json.dumps(import_transcript(args.transcript, args.output)))
    else:
        from render import render_session
        print(json.dumps(render_session(args.session, args.output or args.session / 'video.mp4'), indent=2))


if __name__ == '__main__':
    main()
