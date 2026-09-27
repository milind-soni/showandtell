"""Exercise hook boundaries with local fixtures; no CUA or renderer is run."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zlib


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/showandtell/scripts/showandtell.py"
SPEC = importlib.util.spec_from_file_location("showandtell_hooks_under_test", SCRIPT)
hooks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hooks)


def png(color=(255, 0, 0)):
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    pixels = b"".join(b"\x00" + bytes(color) * 2 for _ in range(2))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def image(color=(255, 0, 0)):
    return {"type": "image", "mimeType": "image/png",
            "data": base64.b64encode(png(color)).decode()}


def marker(kind, **values):
    return json.dumps({"showandtell": 1, "kind": kind, **values})


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            "SHOWANDTELL_HOME": str(self.home), "SHOWANDTELL_DISABLED": "0",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.turn = self.home / "session-1" / "turn-1"

    def event(self, kind, **values):
        return {"hook_event_name": kind, "session_id": "session-1",
                "turn_id": "turn-1", "tool_name": "mcp__cua_repl__js", **values}

    def pre(self, code, **arguments):
        return hooks.hook(self.event("PreToolUse", tool_input={"code": code, **arguments}))

    def collect(self, blocks, call="call-1", **values):
        return hooks.collect(self.event("PostToolUse", tool_use_id=call,
                                        tool_response={"content": blocks}, **values), self.turn)

    def test_first_discovery_is_unchanged_and_next_call_preserves_arguments(self):
        self.assertEqual(self.pre('let app = await cua.getApp("Example");'), {})
        code = "await app.click([12, 34]);"
        result = self.pre(code, timeout_ms=45000, title="Click a button")
        output = result["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "allow")
        self.assertEqual(output["updatedInput"]["timeout_ms"], 45000)
        self.assertEqual(output["updatedInput"]["title"], "Click a button")
        injected = output["updatedInput"]["code"]
        self.assertTrue(injected.endswith("\n" + code))
        self.assertIn("__showandtell", injected)
        self.assertIn('app = __showandtell.wrap(app, "app")', injected)

    def test_const_binding_is_instrumented_without_reassignment(self):
        self.pre('const tab = await cua.getTab("123", {browser: "chrome"});')
        injected = self.pre("await tab.click([5, 6]);")["hookSpecificOutput"]["updatedInput"]["code"]
        self.assertIn('__showandtell.instrument(tab, "browser")', injected)
        self.assertNotIn("tab = __showandtell.wrap", injected)

    def test_redeclared_binding_does_not_get_a_tdz_lookup(self):
        self.pre('let tab = await cua.getTab("123");')
        code = 'const tab = await cua.getTab("456"); await tab.click([5, 6]);'
        injected = self.pre(code)["hookSpecificOutput"]["updatedInput"]["code"]
        self.assertNotIn('typeof tab !== "undefined"', injected)
        self.assertTrue(injected.endswith("\n" + code))

    def test_reset_post_clears_state_and_preserves_next_discovery(self):
        self.pre('let oldApp = await cua.getApp("Example");')
        hooks.hook(self.event("PostToolUse", tool_name="mcp__cua_repl__js_reset",
                              tool_response={"content": []}))
        runtime = json.loads((self.home / "session-1/runtime.json").read_text())
        self.assertEqual(runtime, {"seen": False, "bindings": {}})
        self.assertEqual(self.pre('let app = await cua.getApp("Example");'), {})
        injected = self.pre("await app.click([1, 2]);")["hookSpecificOutput"]["updatedInput"]["code"]
        self.assertNotIn("typeof oldApp", injected)

    def test_repeated_standalone_discovery_never_gets_a_prefix(self):
        for code in ('await cua.getState();', 'let app = await cua.getApp("Example");',
                     'await cua.getBrowser({url: "https://example.com"});',
                     'await cua.rewriteDocumentation();',
                     'let tab = await cua.createBrowserTab("iab", "https://example.com", {visible: false});'):
            with self.subTest(code=code):
                self.assertEqual(self.pre(code), {})

    def test_wrong_tool_and_malformed_arguments_are_not_rewritten(self):
        self.pre("await cua.getState();")
        self.assertEqual(hooks.hook(self.event("PreToolUse", tool_name="mcp__other_cua_repl__js",
                                              tool_input={"code": "await app.click([1, 2]);"})), {})
        for args in (None, [], {}, {"code": 5}):
            with self.subTest(args=args):
                self.assertEqual(hooks.hook(self.event("PreToolUse", tool_input=args)), {})

    def test_content_containers_and_empty_responses(self):
        for response in ({}, {"error": "failed"}, None, [], "not JSON", {"result": {}}):
            with self.subTest(response=response):
                self.assertEqual(hooks.content_blocks(response), [])
        block = {"type": "text", "text": "hello"}
        for response in ({"content": [block]}, {"result": {"content": [block]}},
                         json.dumps({"content": [block]})):
            self.assertEqual(hooks.content_blocks(response), [block])

    def test_grouped_cua_text_and_images_pair_frame_markers_fifo(self):
        text = ("Accessibility output\n"
                + marker("frame", id="a", surface="app", phase="before", t=10)
                + marker("action", id="a", surface="app", type="drag", t=11,
                         x=1, y=2, to=[30, 40])
                + "\nUI state changed\n"
                + marker("frame", id="a", surface="app", phase="after", t=12)
                + marker("status", id="a", status="ok", t=13))
        session = self.collect([{"type": "text", "text": text}, image(), image((0, 255, 0))])
        self.assertEqual([(f["phase"], f["t"], f["surface"]) for f in session["frames"]],
                         [("before", 10, "app"), ("after", 12, "app")])
        self.assertEqual(session["actions"], [{"id": "a", "t": 11, "type": "drag", "surface": "app",
                                               "x": 1, "y": 2, "to": [30, 40], "status": "ok", "end": 13}])
        for frame, color in zip(session["frames"], [(255, 0, 0), (0, 255, 0)]):
            self.assertEqual((self.turn / frame["file"]).read_bytes(), png(color))
            self.assertEqual((frame["width"], frame["height"]), (2, 2))

    def test_import_unwraps_saved_cua_json_text_result(self):
        text = (marker("frame", id="a", surface="app", phase="before", t=10)
                + marker("action", id="a", surface="app", type="click", t=11, x=1, y=1)
                + marker("frame", id="a", surface="app", phase="after", t=12)
                + marker("status", id="a", status="ok", t=13))
        inner = {"content": [{"type": "text", "text": text}, image(), image((0, 255, 0))]}
        result = {"content": [{"type": "text", "text": json.dumps(inner)}]}
        transcript = self.home / "rollout.jsonl"
        transcript.write_text(json.dumps({"timestamp": "2026-09-27T12:00:00Z", "payload": {
            "type": "item_completed", "item": {"type": "McpToolCall", "server": "cua_repl",
            "id": "live-call", "result": result}}}) + "\n")
        hooks.import_transcript(transcript, self.turn)
        saved = json.loads((self.turn / "session.json").read_text())
        self.assertEqual([(f["phase"], f["t"]) for f in saved["frames"]], [("before", 10), ("after", 12)])
        self.assertEqual(saved["actions"][0]["status"], "ok")
        self.assertEqual(saved["warnings"], [])
        self.assertEqual((self.turn / saved["frames"][1]["file"]).read_bytes(), png((0, 255, 0)))
        ordinary = {"type": "text", "text": json.dumps({"showandtell": 1, "kind": "action"})}
        self.assertEqual(hooks.content_blocks({"content": [ordinary]}), [ordinary])

    def test_invalid_markers_and_images_warn_without_storing_actions(self):
        text = (marker("action", type="unsupported", t=1)
                + marker("action", type="click", t="invalid")
                + marker("frame", phase="before", t=2)
                + marker("frame", phase="after", t=3)
                + marker("warning", reason="capture failed"))
        session = self.collect([{"type": "text", "text": text},
                                {"type": "image", "data": "not base64"}])
        self.assertEqual(session["actions"], [])
        self.assertEqual(session["frames"], [])
        self.assertIn("Ignored an invalid action marker.", session["warnings"])
        self.assertIn("Skipped an invalid or unsupported screenshot.", session["warnings"])
        self.assertIn("Some screenshot markers had no image in the tool result.", session["warnings"])
        self.assertEqual(len(session["warnings"]), len(set(session["warnings"])))

    def test_ambiguous_extra_image_withholds_cursor_association(self):
        text = marker("frame", id="a", surface="app", phase="before", t=1)
        session = self.collect([{"type": "text", "text": text}, image(), image((0, 0, 255))])
        self.assertTrue(all(f["surface"] == "untracked" for f in session["frames"]))
        self.assertTrue(any("mismatch" in w for w in session["warnings"]))

    def test_failed_image_emission_does_not_shift_remaining_pairs(self):
        text = (marker("frame", id="a", surface="app", phase="before", t=1)
                + marker("warning", id="a", phase="before", reason="image-emission-failed")
                + marker("frame", id="a", surface="app", phase="after", t=3))
        session = self.collect([{"type": "text", "text": text}, image()])
        self.assertEqual([(f["phase"], f["t"]) for f in session["frames"]], [("after", 3)])

    def test_collection_does_not_retain_typed_text_or_raw_javascript(self):
        secret = "unique private text 78109"
        code = 'await app.typeText("' + secret + '");'
        text = ("AX field value: " + secret + "\n"
                + marker("action", id="a", type="type", t=1, surface="app",
                         text=secret, code=code, arguments=[secret])
                + marker("frame", phase="after", t=2, surface="app"))
        self.collect([{"type": "text", "text": text}, image()], tool_input={"code": code})
        saved = (self.turn / "session.json").read_text()
        self.assertNotIn(secret, saved)
        self.assertNotIn(code, saved)
        self.assertNotIn("tool_input", saved)
        self.assertEqual(json.loads(saved)["actions"][0]["type"], "type")

    def test_repeated_tool_id_is_deduplicated(self):
        blocks = [{"type": "text", "text": marker("frame", phase="after", t=2)}, image()]
        first = self.collect(blocks)
        second = self.collect(blocks)
        self.assertEqual(second, first)
        self.assertEqual(second["calls"], ["call-1"])
        self.assertEqual(len(second["frames"]), 1)

    def test_stop_renders_once_per_manifest_and_uses_the_turn_id(self):
        self.collect([image()], recorded_at=10)
        renderer = types.ModuleType("render")

        def render(directory, destination):
            self.assertEqual(directory, self.turn)
            destination.write_bytes(b"test video")
            return {"output": str(destination), "duration": 1}

        renderer.render_session = Mock(side_effect=render)
        with patch.dict(sys.modules, {"render": renderer}):
            first = hooks.hook(self.event("Stop"))
            self.assertIn(str(self.turn / "video.mp4"), first["systemMessage"])
            self.assertEqual(hooks.hook(self.event("Stop", stop_hook_active=True)), {})
            renderer.render_session.assert_called_once()
            self.collect([image((0, 255, 0))], call="call-2", recorded_at=20)
            hooks.hook(self.event("Stop"))
            self.assertEqual(renderer.render_session.call_count, 2)

    def test_malformed_hook_stdin_returns_warning_and_success(self):
        for stdin in ("not JSON", "[]"):
            with self.subTest(stdin=stdin):
                result = subprocess.run([sys.executable, str(SCRIPT), "hook"], input=stdin,
                                        text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, 0)
                self.assertTrue(json.loads(result.stdout)["systemMessage"].startswith("Showandtell:"))


if __name__ == "__main__":
    unittest.main()
