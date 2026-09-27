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
  const screenshots = [];
  const target = {
    value: 7,
    async getScreenshot(options) {
      assert.equal(this, target);
      screenshots.push(options);
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
  return { events, writes, calls, screenshots, target, context, cua };
}

test("default action preserves receiver/options/result and takes zero extra screenshots", async () => {
  const f = fixture();
  const app = await f.cua.getApp("Example");
  const options = { clickCount: 2 };
  assert.equal(await app.click([10, 20], options), 7);
  assert.equal(f.calls[0][1], options);
  assert.equal(await app.getState(), "state");
  assert.equal(app.value, 7);
  assert.deepEqual(f.events.map((e) => e.kind), ["action", "status"]);
  assert.equal(f.events[0].x, 10);
  assert.equal(f.events[0].y, 20);
  assert.equal(f.events[0].surface, "app:1");
  assert.equal(f.events[1].status, "ok");
  assert.equal(typeof f.events[0].t, "number");
  assert.deepEqual(f.screenshots, []);
  assert.ok(f.writes.every((value) => value.endsWith("\n")));
  assert.equal(f.writes.join("").trim().split("\n").length, 2);
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
  assert.equal(f.events.filter((e) => e.kind === "image").length, 0);
});

test("older recorder registry cannot suppress the direct capture API", async () => {
  const old = { wrap(value) { return value; } };
  const context = vm.createContext({ __showandtellCaptureV1: old, __showandtellCaptureV2: old, cua: {}, nodeRepl: { write() {} } });
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
  assert.equal(f.events.filter((e) => e.reason === "screenshot-unavailable").length, 0);
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

test("existing screenshot is sampled once with unchanged bytes/options and no duplicate image", async () => {
  const foreign = vm.runInNewContext("new Uint8Array([137, 80, 78, 71])");
  const options = { emit: true };
  let shots = 0;
  const f = fixture({ async getScreenshot(value) {
    assert.equal(this, f.target);
    assert.equal(value, options);
    shots++;
    f.context.nodeRepl.emitImage(foreign); // Normal CUA emission must remain the only image.
    return foreign;
  } });
  const app = await f.cua.getApp("Example");
  assert.equal(await app.getScreenshot(options), foreign);
  assert.equal(shots, 1);
  assert.equal(f.events.filter((e) => e.kind === "image").length, 1);
  assert.equal(f.events.filter((e) => e.kind === "frame").length, 1);
  assert.equal(f.events.find((e) => e.kind === "frame").phase, "observed");
});

test("state plus screenshot preserves result identity without retaining AX text", async () => {
  const result = { state: "private AX text", screenshot: new Uint8Array([1, 2, 3]) };
  const options = { emit: false, disableDiffing: true };
  const f = fixture({ async getAXStateAndScreenshot(value) {
    assert.equal(this, f.target);
    assert.equal(value, options);
    return result;
  } });
  const app = await f.cua.getApp("Example");
  assert.equal(await app.getAXStateAndScreenshot(options), result);
  assert.deepEqual(f.events.map((e) => e.kind), ["frame"]);
  assert.equal(f.writes.join("").includes(result.state), false);
  assert.deepEqual(f.screenshots, []);
});

test("text-only observations are not images and observation errors remain unchanged", async () => {
  const expected = new Error("private screenshot failure");
  const f = fixture({ async getAXStateAndScreenshot() { return { state: "AX text" }; } });
  const app = await f.cua.getApp("Example");
  await app.getAXStateAndScreenshot();
  f.target.getAXStateAndScreenshot = async () => "AX text";
  await app.getAXStateAndScreenshot();
  f.target.getScreenshot = async () => "AX text";
  await app.getScreenshot();
  assert.deepEqual(f.events, []);
  f.target.getScreenshot = async () => { throw expected; };
  await assert.rejects(app.getScreenshot(), (error) => error === expected);
});

test("nested public observation wrapping never calls or emits an extra screenshot", async () => {
  const f = fixture({ async getAXStateAndScreenshot(options) {
    return { state: "AX text", screenshot: await this.getScreenshot(options) };
  } });
  f.context.__showandtell.instrument(f.target);
  f.context.__showandtell.instrument(f.target);
  const app = f.context.__showandtell.wrap(f.context.__showandtell.wrap(f.target));
  await app.getAXStateAndScreenshot({ emit: false });
  assert.equal(f.screenshots.length, 1);
  assert.equal(f.events.filter((e) => e.kind === "frame").length, 2);
  assert.equal(f.events.filter((e) => e.kind === "image").length, 0);
});

test("concurrent public observations retain both returned images", async () => {
  const resolve = [];
  const f = fixture({ getScreenshot() { return new Promise((done) => resolve.push(done)); } });
  const app = await f.cua.getApp("Example");
  const first = app.getScreenshot({ emit: false });
  const second = app.getScreenshot({ emit: false });
  const a = new Uint8Array([1, 2, 3]);
  const b = new Uint8Array([4, 5, 6]);
  resolve[1](b);
  assert.equal(await second, b);
  resolve[0](a);
  assert.equal(await first, a);
  assert.equal(f.events.filter((e) => e.kind === "frame").length, 2);
  assert.equal(new Set(f.events.map((e) => e.id)).size, 2);
  assert.equal(f.events.filter((e) => e.kind === "image").length, 0);
});

test("observations and actions sharing the clock remain strictly ordered", async () => {
  const f = fixture();
  vm.runInContext("Date.now = () => 2000000000000", f.context);
  const app = await f.cua.getApp("Example");
  await app.getScreenshot({ emit: false });
  await app.click([1, 2]);
  await app.getScreenshot({ emit: false });
  assert.deepEqual(f.events.map((e) => e.kind), ["frame", "action", "status", "frame"]);
  assert.ok(f.events.every((e, i) => i === 0 || e.t > f.events[i - 1].t));
});

test("direct capture saves large bytes privately without tool-result images and switches calls", async () => {
  const directory = await mkdtemp(join(tmpdir(), "showandtell-capture-"));
  const bytes = vm.runInNewContext("new Uint8Array(1100000).fill(37)");
  const writes = [];
  let clicks = 0;
  let screenshots = 0;
  const app = { async getScreenshot() { screenshots++; return bytes; }, async click() { clicks++; return 42; } };
  const api = { async getApp() { return app; } };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  try {
    // Native CUA supports Node imports; exercise the same import outside vm contexts.
    const recorder = await new AsyncFunction("cua", "nodeRepl", source + "\nreturn __showandtell;")(
      api, { write(value) { writes.push(value); }, emitImage() { assert.fail("Images must stay on disk"); } });
    recorder.instrument(app);
    recorder.instrument(app);
    for (const call of ["full", "reuse"]) {
      const folder = join(directory, call);
      await mkdir(folder);
      await recorder.saveTo(folder, call === "full" ? "full" : undefined);
      const handle = await api.getApp();
      if (call === "reuse") assert.equal(await handle.getScreenshot({ emit: false }), bytes);
      assert.equal(await handle.click([10, 20]), 42);
      if (call === "reuse") assert.equal(await handle.getScreenshot({ emit: false }), bytes);
      const entries = (await readFile(join(folder, "events.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
      assert.deepEqual(entries.map((entry) => entry.kind), call === "full"
        ? ["frame", "action", "frame", "status"] : ["frame", "action", "status", "frame"]);
      assert.deepEqual(entries.filter((entry) => entry.image).map((entry) => entry.phase),
        call === "full" ? ["before", "after"] : ["observed", "observed"]);
      assert.equal(entries[1].x, 10);
      assert.equal(entries.find((entry) => entry.kind === "status").status, "ok");
      assert.equal((await readdir(folder)).length, 3);
      for (const entry of entries.filter((entry) => entry.image)) {
        assert.deepEqual(new Uint8Array(await readFile(join(folder, entry.image))), new Uint8Array(bytes));
        assert.equal((await stat(join(folder, entry.image))).mode & 0o777, 0o600);
      }
    }
    assert.equal(clicks, 2);
    assert.equal(screenshots, 4);
    assert.deepEqual(writes, []);
    const failedFolder = join(directory, "failed");
    await mkdir(failedFolder);
    await recorder.saveTo(failedFolder, "full");
    const expected = new Error("private action failure");
    app.getScreenshot = async () => { throw new Error("private screenshot failure"); };
    app.click = async () => { throw expected; };
    await assert.rejects((await api.getApp()).click([1, 2]), (error) => error === expected);
    const failures = (await readFile(join(failedFolder, "events.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
    assert.equal(failures.filter((event) => event.reason === "screenshot-unavailable").length, 2);
    assert.equal(failures.at(-1).status, "failed");
    assert.equal(JSON.stringify(failures).includes("private"), false);
    // Storage failure must preserve the requested computer action, even if output also fails.
    await recorder.saveTo(join(directory, "missing"));
    app.click = async () => 42;
    assert.equal(await (await api.getApp()).click([1, 2]), 42);
    assert.ok(writes.some((value) => value.includes("capture-storage-unavailable")));
  } finally {
    delete globalThis.__showandtellCaptureV3;
    await rm(directory, { recursive: true, force: true });
  }
});
