import assert from "node:assert/strict";
import { readFile, mkdtemp, mkdir, readdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import vm from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../plugins/showandtell/scripts/capture.js", import.meta.url), "utf8");
function fixture(overrides = {}) {
  const events = [];
  const writes = [];
  const calls = [];
  const target = {
    value: 7,
    async getScreenshot(options) {
      assert.equal(options.emit, false);
      return new Uint8Array([137, 80, 78, 71]);
    },
    async click(...args) { assert.equal(this, target); calls.push(args); return this.value; },
    async drag(...args) { calls.push(args); },
    async typeText(...args) { calls.push(args); },
    async getState() { assert.equal(this, target); return "state"; },
    ...overrides,
  };
  const cua = { async getApp() { assert.equal(this, cua); return target; } };
  const context = vm.createContext({ cua, nodeRepl: {
    write(value) { writes.push(value); events.push(JSON.parse(value)); },
    emitImage(value) { events.push({ kind: "image", value }); },
  } });
  vm.runInContext(source, context);
  return { events, writes, calls, target, context, cua };
}

test("creator wrapping preserves receivers, arguments, results, and capture order", async () => {
  const f = fixture();
  const app = await f.cua.getApp("Example");
  const options = { clickCount: 2 };
  assert.equal(await app.click([10, 20], options), 7);
  assert.equal(f.calls[0][1], options);
  assert.equal(await app.getState(), "state");
  assert.equal(app.value, 7);
  assert.deepEqual(f.events.map((e) => e.kind), ["frame", "image", "action", "frame", "image", "status"]);
  assert.equal(f.events[0].phase, "before");
  assert.equal(f.events[3].phase, "after");
  assert.equal(f.events[2].x, 10);
  assert.equal(f.events[2].y, 20);
  assert.equal(f.events[2].surface, "app:1");
  assert.equal(f.events[0].id, f.events[2].id);
  assert.equal(f.events[5].status, "ok");
  assert.equal(typeof f.events[2].t, "number");
  assert.ok(f.writes.every((value) => value.endsWith("\n")));
  assert.equal(f.writes.join("").trim().split("\n").length, 4);
});

test("repeated bootstrap and repeated wrapping do not double capture", async () => {
  const f = fixture();
  const app = await f.cua.getApp("Example");
  const helper = f.context.__showandtell;
  vm.runInContext(source, f.context);
  assert.equal(f.context.__showandtell, helper);
  assert.equal(await f.cua.getApp("Example"), app);
  assert.equal(helper.wrap(app), app);
  await app.click(5);
  assert.equal(f.events.filter((e) => e.kind === "action").length, 1);
  assert.equal(f.events.find((e) => e.kind === "action").x, null);
});

test("fresh call scopes reuse one recorder without nested capture", async () => {
  const f = fixture();
  f.context.existing = await f.cua.getApp("Example");
  const helper = f.context.__showandtell;
  for (let i = 0; i < 3; i++) {
    const reused = await vm.runInContext(`(async () => {
      ${source}
      existing = __showandtell.wrap(existing);
      await existing.click([1, 2]);
      return __showandtell;
    })()`, f.context);
    assert.equal(reused, helper);
  }
  assert.equal(f.calls.length, 3);
  const actions = f.events.filter((e) => e.kind === "action");
  assert.equal(actions.length, 3);
  assert.deepEqual(actions.map((e) => e.id.split("-").at(-1)), ["1", "2", "3"]);
  assert.equal(f.events.filter((e) => e.kind === "image").length, 6);
});

test("older recorder registry cannot suppress the direct capture API", async () => {
  const old = { wrap(value) { return value; } };
  const context = vm.createContext({ __showandtellCaptureV1: old, cua: {}, nodeRepl: { write() {} } });
  vm.runInContext(source, context);
  assert.equal(context.__showandtellCaptureV1, old);
  assert.notEqual(context.__showandtell, old);
  assert.equal(typeof context.__showandtell.saveTo, "function");
});

test("existing const handles can be instrumented in place", async () => {
  const f = fixture();
  f.context.existing = f.target;
  vm.runInContext("const app = existing; __showandtell.instrument(app, 'existing'); __showandtell.instrument(app, 'existing');", f.context);
  await vm.runInContext("app.click([1, 2])", f.context);
  assert.equal(f.events.filter((e) => e.kind === "action").length, 1);
  await f.context.__showandtell.wrap(f.target).click([1, 2]);
  assert.equal(f.events.filter((e) => e.kind === "action").length, 2);
});

test("capture/output failures do not prevent actions or replace their errors", async () => {
  const expected = new Error("private failure message");
  const f = fixture({ async getScreenshot() { throw new Error("capture failed"); } });
  const app = await f.cua.getApp("Example");
  assert.equal(await app.click([1, 2]), 7);
  f.target.click = async () => { throw expected; };
  await assert.rejects(app.click([1, 2]), (error) => error === expected);
  assert.equal(f.events.at(-1).status, "failed");
  assert.equal(f.events.filter((e) => e.reason === "screenshot-unavailable").length, 4);
  assert.equal(JSON.stringify(f.events).includes(expected.message), false);
  f.context.nodeRepl.write = () => { throw new Error("output failed"); };
  f.target.click = async () => 42;
  assert.equal(await app.click(3), 42);
});

test("text and action option values never appear in markers", async () => {
  const f = fixture();
  const app = await f.cua.getApp("Example");
  await app.typeText(12, "secret-password");
  await app.click(12, { text: "secret-option" });
  await app.drag([1, 2], [3, 4]);
  const actions = f.events.filter((e) => e.kind === "action");
  assert.equal(actions[0].x, null);
  assert.equal(actions[0].type, "type");
  assert.deepEqual(actions[2].to, [3, 4]);
  assert.equal(JSON.stringify(f.events).includes("secret"), false);
});

test("immutable handles still work through facade and warn for in-place instrumentation", async () => {
  const f = fixture();
  Object.freeze(f.target);
  f.context.__showandtell.instrument(f.target, "existing");
  const app = await f.cua.getApp("Example");
  assert.equal(await app.click([1, 2]), 7);
  assert.equal(f.events.filter((e) => e.kind === "warning").length, 1);
  assert.equal(f.events.filter((e) => e.kind === "action").length, 1);
});

test("surface identities reveal no creator arguments and action types are normalized", async () => {
  const f = fixture();
  f.target.goto = async () => {};
  f.target.pressKey = async () => {};
  f.target.selectText = async () => {};
  f.cua.getTab = async () => f.target;
  vm.runInContext(source, f.context);
  const tab = await f.cua.getTab("https://example.test/?token=secret");
  await tab.goto("https://another.test/?token=secret");
  await tab.pressKey("secret");
  await tab.selectText(1, "secret");
  assert.deepEqual(f.events.filter((e) => e.kind === "action").map((e) => e.type),
    ["navigate", "key", "select"]);
  assert.equal(f.events[0].surface, "browser:1");
  assert.equal(JSON.stringify(f.events).includes("secret"), false);
  assert.equal(JSON.stringify(f.events).includes("example.test"), false);
});

test("immutable creator methods emit one generic warning without breaking access", async () => {
  const f = fixture();
  f.cua.getTab = async () => f.target;
  Object.freeze(f.cua);
  vm.runInContext(source, f.context);
  vm.runInContext(source, f.context);
  assert.equal(await f.cua.getTab("secret"), f.target);
  await f.context.__showandtell.wrap(f.target).click([1, 2]);
  assert.equal(f.events.filter((e) => e.reason === "immutable-creator").length, 1);
  assert.equal(JSON.stringify(f.events).includes("secret"), false);
});

test("cross-realm screenshot bytes are normalized before emission", async () => {
  const foreign = vm.runInNewContext("new Uint8Array([137, 80, 78, 71])");
  assert.equal(foreign instanceof Uint8Array, false);
  const f = fixture({ async getScreenshot() { return foreign; } });
  const localBytes = vm.runInContext("Uint8Array", f.context);
  const images = [];
  f.context.nodeRepl.emitImage = (image) => {
    assert.ok(image instanceof localBytes);
    images.push(image);
  };
  await (await f.cua.getApp("Example")).click([1, 2]);
  assert.equal(images.length, 2);
  assert.deepEqual(Array.from(images[0]), [137, 80, 78, 71]);
  assert.equal(f.events.some((event) => event.kind === "warning"), false);
});

test("image emission failure warns with its frame identity and preserves actions", async () => {
  const f = fixture();
  f.context.nodeRepl.emitImage = () => { throw new Error("private image failure"); };
  assert.equal(await (await f.cua.getApp("Example")).click([1, 2]), 7);
  const warnings = f.events.filter((event) => event.reason === "image-emission-failed");
  assert.equal(warnings.length, 2);
  assert.equal(warnings[0].id, f.events[0].id);
  assert.equal(warnings[0].phase, "before");
  assert.equal(warnings[1].phase, "after");
  assert.equal(f.events.at(-1).status, "ok");
  assert.equal(JSON.stringify(f.events).includes("private image failure"), false);
});

test("direct capture saves large bytes privately without tool-result images and switches calls", async () => {
  const directory = await mkdtemp(join(tmpdir(), "showandtell-capture-"));
  const bytes = new Uint8Array(1_100_000).fill(37);
  const writes = [];
  let clicks = 0;
  const app = { async getScreenshot() { return bytes; }, async click() { clicks++; return 42; } };
  const api = { async getApp() { return app; } };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  try {
    // Native CUA supports Node imports; exercise the same import outside vm contexts.
    const recorder = await new AsyncFunction("cua", "nodeRepl", source + "\nreturn __showandtell;")(
      api, { write(value) { writes.push(value); }, emitImage() { assert.fail("Images must stay on disk"); } });
    for (const call of ["one", "two"]) {
      const folder = join(directory, call);
      await mkdir(folder);
      await recorder.saveTo(folder);
      assert.equal(await (await api.getApp()).click([10, 20]), 42);
      const entries = (await readFile(join(folder, "events.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
      assert.deepEqual(entries.map((entry) => entry.kind), ["frame", "action", "frame", "status"]);
      assert.equal(entries[1].x, 10);
      assert.equal(entries[3].status, "ok");
      assert.equal((await readdir(folder)).length, 3);
      for (const entry of entries.filter((entry) => entry.image)) {
        assert.deepEqual(new Uint8Array(await readFile(join(folder, entry.image))), bytes);
        assert.equal((await stat(join(folder, entry.image))).mode & 0o777, 0o600);
      }
    }
    assert.equal(clicks, 2);
    assert.deepEqual(writes, []);
    // Storage failure must preserve the requested computer action, even if output also fails.
    await recorder.saveTo(join(directory, "missing"));
    assert.equal(await (await api.getApp()).click([1, 2]), 42);
    assert.ok(writes.some((value) => value.includes("capture-storage-unavailable")));
  } finally {
    delete globalThis.__showandtellCaptureV2;
    await rm(directory, { recursive: true, force: true });
  }
});
