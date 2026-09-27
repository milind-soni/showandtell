"""Run directly: python3 tests/test_render.py (requires FFmpeg and ffprobe)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render", ROOT / "plugins/showandtell/scripts/render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


def run():
    assert render.ease(0) == 0 and render.ease(1) == 1
    assert abs(render.ease(0.5) - 0.5) < 1e-10
    assert render.ease(0.001) < 1e-7
    points = [(0, 1, (20, 30), (600, 200))]
    assert render.cursor_at(points, [0], 0) == (20, 30)
    assert render.cursor_at(points, [0], 1) == (600, 200)
    assert render.cursor_at(points, [0], 0.5) == (310, 115)
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        for name, color in [("before", (240, 244, 250)), ("after", (185, 225, 199))]:
            (folder / f"{name}.ppm").write_bytes(b"P6\n128 80\n255\n" + bytes(color) * (128 * 80))
        data = {"version": 1, "frames": [
            {"t": 100, "file": "before.ppm", "width": 128, "height": 80, "surface": "a"},
            {"t": 101.01, "file": "after.ppm", "width": 128, "height": 80, "surface": "a"},
            {"t": 110, "file": "before.ppm", "width": 128, "height": 80, "surface": "b"}],
            "actions": [{"t": 101, "type": "click", "x": 20, "y": 30, "surface": "a"},
                        {"t": 102, "type": "drag", "x": 20, "y": 30, "to": [95, 60], "surface": "a"},
                        {"t": 111, "type": "click", "x": 50, "y": 50, "surface": "b"},
                        {"t": 112, "type": "click", "surface": "b"}]}
        (folder / "session.json").write_text(json.dumps(data))
        frames, actions, warnings = render.load_session(folder)
        scenes, motions, clicks, duration = render.timeline(frames, actions, warnings)
        assert scenes[1][0] > clicks[0][0], "after screenshot must follow its click"
        assert duration < 12, "idle gaps must be removed"
        assert len(warnings) == 1 and "cursor hidden" in warnings[0]
        assert motions[-2][2] == motions[-2][3], "no pointer glide between surfaces"
        assert motions[-1][2] is None, "missing coordinates must hide cursor"
        assert render.position(frames[0], 0, 0) == (51, 32)
        tied_before = dict(frames[0], t=101, phase="before")
        tied_after = dict(frames[1], t=101, phase="after")
        tied_warnings = []
        tied_scenes, _, tied_clicks, _ = render.timeline([tied_after, tied_before], actions[:1], tied_warnings)
        assert not tied_warnings and len(tied_clicks) == 1, "tied before image must precede the first action"
        assert tied_scenes[0][1] is tied_before and tied_scenes[1][1] is tied_after
        assert tied_scenes[1][0] >= tied_clicks[0][0], "tied after image must not precede its action"
        _, failed_motions, failed_clicks, _ = render.timeline([tied_before], [dict(actions[0], status="failed")], [])
        assert not failed_clicks and failed_motions[-1][3] is not None, "failed click may move but must not show success feedback"
        output = folder / "movie.mp4"
        result = render.render_session(folder, output)
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration",
            "-of", "json", str(output)]))
        stream = probe["streams"][0]
        assert (stream["width"], stream["height"], stream["r_frame_rate"]) == (1280, 800, "60/1")
        assert int(stream["nb_frames"]) == result["frames"]
        assert abs(float(probe["format"]["duration"]) - result["duration"]) < 0.02
        # Check the actual arrow pixels, not only the interpolation math.
        blank = bytearray([127]) * (render.WIDTH * render.HEIGHT * 3)
        render.draw_cursor(blank, (200, 100), render.sprite())
        assert blank[((100 + 9) * render.WIDTH + 203) * 3] > 220
        assert blank[(100 * render.WIDTH + 190) * 3] == 127
        # A failed export must preserve an existing destination.
        before = output.read_bytes()
        (folder / "before.ppm").write_text("broken image")
        try:
            render.render_session(folder, output)
            raise AssertionError("corrupt input accepted")
        except RuntimeError:
            assert output.read_bytes() == before
        data["frames"][0]["file"] = "../outside.png"
        (folder / "session.json").write_text(json.dumps(data))
        try:
            render.load_session(folder)
            raise AssertionError("path escape accepted")
        except ValueError:
            pass
    print("render: interpolation, chronology, surface isolation, cursor pixels, 60fps MP4, atomic failure and path validation passed")


if __name__ == "__main__":
    run()
