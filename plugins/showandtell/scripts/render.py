#!/usr/bin/env python3
"""Render saved screenshots and action coordinates; never captures a display."""
import argparse
from bisect import bisect_right
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

WIDTH, HEIGHT, PADDING = 1280, 800, 32


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def ease(t):
    """Minimum jerk: zero velocity and acceleration at both endpoints."""
    t = min(1.0, max(0.0, t))
    return t * t * t * (10 + t * (-15 + 6 * t))


def placement(frame):
    scale = min((WIDTH - PADDING * 2) / frame["width"], (HEIGHT - PADDING * 2) / frame["height"])
    w, h = max(1, round(frame["width"] * scale)), max(1, round(frame["height"] * scale))
    return (WIDTH - w) // 2, (HEIGHT - h) // 2, w, h


def position(frame, x, y):
    number(x, "x")
    number(y, "y")
    if not (0 <= x < frame["width"] and 0 <= y < frame["height"]):
        raise ValueError("cursor position falls outside its screenshot")
    left, top, w, h = placement(frame)
    return left + x * w / frame["width"], top + y * h / frame["height"]


def load_session(directory):
    directory = Path(directory).resolve()
    data = json.loads((directory / "session.json").read_text())
    if data.get("version") != 1 or not isinstance(data.get("frames"), list) or not isinstance(data.get("actions", []), list):
        raise ValueError("expected a version 1 session with frames and actions arrays")
    frames = []
    for frame in data["frames"]:
        frame = dict(frame)
        number(frame.get("t"), "frame timestamp")
        for key in ("width", "height"):
            value = number(frame.get(key), key)
            if value != int(value) or not 1 <= value <= 32768:
                raise ValueError(f"invalid screenshot {key}")
        path = (directory / frame["file"]).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise ValueError("screenshot must be an existing file inside the session directory")
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ppm"):
            raise ValueError("unsupported screenshot format")
        frame["path"] = path
        frame["surface"] = str(frame.get("surface", ""))
        frames.append(frame)
    if not frames:
        raise ValueError("session contains no screenshots")
    actions = []
    for action in data.get("actions", []):
        action = dict(action)
        number(action.get("t"), "action timestamp")
        action["surface"] = str(action.get("surface", ""))
        actions.append(action)
    warnings = [str(warning) for warning in data.get("warnings", [])]
    return frames, actions, warnings


def timeline(frames, actions, warnings):
    """Keep state changes after their actions and remove long thinking pauses."""
    # Millisecond clocks can tie; a marked before image is valid for that action.
    events = sorted([(f["t"], 0 if f.get("phase") == "before" else 2, i, f) for i, f in enumerate(frames)] +
                    [(a["t"], 1, i, a) for i, a in enumerate(actions)])
    scenes, motions, clicks = [], [], []
    known, current, previous = {}, None, None
    clock, last_time = 0.0, events[0][0]
    for original, kind, _, item in events:
        if current is not None:
            clock += min(1.5, max(0, original - last_time))
        last_time = original
        surface = item["surface"]
        if kind != 1:
            known[surface] = item
            if current is None or (current["surface"], current["width"], current["height"]) != (surface, item["width"], item["height"]):
                motions.append((clock, clock, None, None))
                previous = None
            scenes.append((clock, item))
            current = item
            continue
        frame = known.get(surface) if surface else None
        try:
            if frame is None:
                raise ValueError("no preceding screenshot for this surface")
            target = position(frame, item.get("x"), item.get("y"))
            end = item.get("to")
            if item.get("type") == "drag":
                if not isinstance(end, (list, tuple)) or len(end) != 2:
                    raise ValueError("drag has no endpoint")
                end = position(frame, *end)
        except (ValueError, TypeError) as error:
            warnings.append(f"{item.get('type', 'action')} at {original}: cursor hidden ({error})")
            motions.append((clock, clock, None, None))
            previous = None
            continue
        if current is not frame:
            scenes.append((clock, frame))
            if current is None or current["surface"] != surface:
                previous = None
            current = frame
        start = previous if previous is not None else target
        distance = math.dist(start, target)
        travel = max(0.25, min(0.85, 0.35 + distance / 1600)) if previous is not None else 0.3
        motions.append((clock, clock + travel, start, target))
        clock += travel
        if item.get("type") in ("click", "double_click", "drag") and item.get("status") != "failed":
            clicks.append((clock, target, surface))
        if item.get("type") == "drag":
            duration = max(0.5, min(1.1, math.dist(target, end) / 750))
            motions.append((clock, clock + duration, target, end))
            clock += duration
            target = end
        previous = target
    return scenes, motions, clicks, clock + 1.0


def cursor_at(motions, starts, time):
    index = bisect_right(starts, time) - 1
    if index < 0 or motions[index][2] is None:
        return None
    start, end, p, q = motions[index]
    t = ease((time - start) / (end - start)) if end > start else 1.0
    return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t


def sprite():
    """Original arrow artwork, supersampled for a clean outline and soft shadow."""
    polygon = [(0, 0), (0, 31), (7.5, 24), (13, 37), (19, 34.5), (13.5, 22), (24, 22)]

    def inside(x, y):
        yes = False
        for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                yes = not yes
        return yes

    def edge(x, y):
        result = 100
        for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
            result = min(result, math.hypot(x - ax - t * dx, y - ay - t * dy))
        return result

    pixels = []
    for py in range(-3, 43):
        for px in range(-3, 30):
            alpha, shade = 0.0, 0.0
            for sy in range(4):
                for sx in range(4):
                    x, y = px + (sx + 0.5) / 4, py + (sy + 0.5) / 4
                    if inside(x, y):
                        a, c = 1, 24 if edge(x, y) < 1.2 else 252
                    else:
                        distance = 0 if inside(x - 1.5, y - 2) else edge(x - 1.5, y - 2)
                        a, c = max(0, 1 - distance / 2.5) * 0.22, 0
                    alpha += a / 16
                    shade += a * c / 16
            if alpha:
                pixels.append((px, py, alpha, round(shade / alpha)))
    return pixels


def blend(buffer, x, y, alpha, color):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        i = (y * WIDTH + x) * 3
        inverse = 1 - alpha
        for channel in range(3):
            buffer[i + channel] = round(buffer[i + channel] * inverse + color[channel] * alpha)


def draw_cursor(buffer, position_, pixels):
    x, y = (round(value) for value in position_)
    for dx, dy, alpha, shade in pixels:
        blend(buffer, x + dx, y + dy, alpha, (shade, shade, shade))


def draw_click(buffer, position_, age):
    progress = age / 0.45
    radius = 5 + 22 * ease(progress)
    x, y = position_
    extent = math.ceil(radius + 2)
    for py in range(round(y) - extent, round(y) + extent + 1):
        for px in range(round(x) - extent, round(x) + extent + 1):
            coverage = max(0, 1 - abs(math.hypot(px - x, py - y) - radius) / 1.5)
            if coverage:
                blend(buffer, px, py, coverage * (1 - progress) * 0.5, (164, 197, 255))


def decode(frame, ffmpeg):
    left, top, width, height = placement(frame)
    filters = (f"scale={width}:{height}:flags=lanczos,pad={WIDTH}:{HEIGHT}:{left}:{top}:color=0x15171c,"
               f"drawbox=x={left-1}:y={top-1}:w={width+2}:h={height+2}:color=0x454851:t=1")
    result = subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe",
                             "-f", "image2", "-pattern_type", "none", "-i", str(frame["path"]), "-vf", filters,
                             "-frames:v", "1", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, timeout=60)
    if result.returncode or len(result.stdout) != WIDTH * HEIGHT * 3:
        raise RuntimeError(f"Cannot decode screenshot {frame['path'].name}: {result.stderr.decode(errors='replace')[-2000:]}")
    return result.stdout


def render_session(session_dir, output, fps=60):
    number(fps, "fps")
    if fps != int(fps) or not 1 <= fps <= 120:
        raise ValueError("fps must be an integer from 1 to 120")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required. Install it, then run the export again.")
    frames, actions, warnings = load_session(session_dir)
    scenes, motions, clicks, duration = timeline(frames, actions, warnings)
    output = Path(output).resolve()
    if output.suffix.lower() != ".mp4" or any(output == f["path"] for f in frames):
        raise ValueError("output must be a separate .mp4 file")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.stem}-", suffix=".mp4", dir=output.parent)
    os.close(fd)
    process = None
    count = math.ceil(duration * fps)
    scene_starts, motion_starts = [s[0] for s in scenes], [m[0] for m in motions]
    normal = sprite()
    current, background = None, None
    try:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                                        "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(fps),
                                        "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "veryfast",
                                        "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", temporary],
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            for index in range(count):
                time = index / fps
                frame = scenes[max(0, bisect_right(scene_starts, time) - 1)][1]
                if current is not frame:
                    background = decode(frame, ffmpeg)
                    current = frame
                buffer = bytearray(background)
                active_clicks = [(at, point) for at, point, surface in clicks
                                 if surface == frame["surface"] and 0 <= time - at < 0.45]
                for at, point in active_clicks:
                    draw_click(buffer, point, time - at)
                pointer = cursor_at(motions, motion_starts, time)
                if pointer is not None:
                    draw_cursor(buffer, pointer, normal)
                process.stdin.write(buffer)
            process.stdin.close()
            if process.wait(timeout=60):
                errors.seek(0)
                raise RuntimeError(f"FFmpeg export failed: {errors.read().decode(errors='replace')[-2000:]}")
        os.replace(temporary, output)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        Path(temporary).unlink(missing_ok=True)
    return {"output": str(output), "duration": count / fps, "frames": count,
            "screenshots": len(frames), "warnings": list(dict.fromkeys(warnings))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--fps", type=int, default=60)
    args = parser.parse_args()
    try:
        print(json.dumps(render_session(args.session, args.output, args.fps), indent=2))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"showandtell: {error}\n")
