import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

const source = await readFile(new URL("../plugins/showandtell/scripts/capture.js", import.meta.url), "utf8");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const RESOLVED = "/Applications/Example.app";

// Models the bundled Mac engine as REPL code sees it: cua.computer is a
// read-only proxy over RPC stubs, nodeRepl is frozen, every observation returns
// AX text plus a short-lived screenshot file, actions return nothing, and AX
// text is a diff against the previous observation unless disableDiff is set.
async function engine(root, { target = "mac", tab } = {}) {
  const shots = join(root, "shots");
  await mkdir(shots, { recursive: true });
  const f = { calls: [], writes: [], state: 0, diffBase: null, failShots: false, failClick: null, shotCount: 0 };
  const skyshot = async (request) => {
    if (f.failShots) throw new Error("private screenshot failure");
    const file = join(shots, `shot-${++f.shotCount}.jpg`);
    await writeFile(file, Buffer.from([0xff, 0xd8, f.state]));
    const text = request.disableDiff || f.diffBase !== f.state ? `Display ${f.state}` : "no change";
    f.diffBase = f.state;
    return { app: RESOLVED, screenshot: { url: pathToFileURL(file).href }, text };
  };
  const stubs = {
    target,
    async get_app_state(request) { f.calls.push(["get_app_state", request]); return skyshot(request); },
    async click(request) { f.calls.push(["click", request]); if (f.failClick) throw f.failClick; f.state = request.x ?? f.state; },
    async drag(request) { f.calls.push(["drag", request]); },
    async type_text(request) { f.calls.push(["type_text", request]); },
    async press_key(request) { f.calls.push(["press_key", request]); },
    async scroll(request) { f.calls.push(["scroll", request]); },
  };
  const proxyTarget = {};
  const computer = new Proxy(proxyTarget, {
    get(_, name) { const value = Reflect.get(stubs, name); return typeof value === "function" ? value.bind(stubs) : value; },
    getOwnPropertyDescriptor(_, name) { return Object.getOwnPropertyDescriptor(stubs, name); },
    has: (_, name) => name in stubs,
    ownKeys: () => Object.keys(stubs),
  });
  // CUA's bound app handle, shaped like bind_mac_app: it calls the shared client.
  const handle = (app) => ({
    async getAXState(o) {
      const text = (await computer.get_app_state({ app, disableDiff: o?.disableDiffing })).text;
      if (o?.emit !== false) await nodeRepl.write(text, "cua.state");
      return text;
    },
    async getScreenshot(o) {
      const r = await computer.get_app_state({ app });
      const bytes = new Uint8Array(await readFile(new URL(r.screenshot.url)));
      if (o?.emit !== false) await nodeRepl.emitImage(bytes);
      return bytes;
    },
    async getAXStateAndScreenshot(o) {
      const r = await computer.get_app_state({ app, disableDiff: o?.disableDiffing });
      return { state: r.text, screenshot: new Uint8Array(await readFile(new URL(r.screenshot.url))) };
    },
    async click(p, o) { return computer.click(Array.isArray(p) ? { app, x: p[0], y: p[1], ...o } : { app, element_index: p }); },
    async typeText(text) { return computer.type_text({ app, text }); },
    async pressKey(key) { return computer.press_key({ app, key }); },
    async drag(a, b) { return computer.drag({ app, from_x: a[0], from_y: a[1], to_x: b[0], to_y: b[1] }); },
  });
  const cua = {
    computer,
    async getApp(name) { const r = await computer.get_app_state({ app: name, disableDiff: true }); return handle(r.app); },
    ...(tab ? { async getTab() { return tab; } } : {}),
  };
  const nodeRepl = Object.freeze({
    write(value, channel) { f.writes.push([value, channel]); },
    emitImage(value) { f.writes.push(["image", value.length]); },
    rpc() { throw new Error("not for REPL code"); },
  });
  const recorder = await new AsyncFunction("cua", "nodeRepl", source + "\nreturn __showandtell;")(cua, nodeRepl);
  const events = async (folder) => (await readFile(join(folder, "events.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
  const folder = async (...parts) => { const p = join(root, ...parts); await mkdir(p, { recursive: true }); return p; };
  return { ...f, f, cua, computer, proxyTarget, stubs, handle, nodeRepl, recorder, events, folder, source };
}

async function scenario(run, options) {
  const root = await mkdtemp(join(tmpdir(), "showandtell-recorder-"));
  let recorder;
  try {
    const e = await engine(root, options);
    recorder = e.recorder;
    await run(e, root);
    assert.deepEqual(Reflect.ownKeys(e.proxyTarget), []); // The engine's proxy is never written to.
    assert.equal(Object.isFrozen(e.nodeRepl), true);
  } finally {
    await recorder?.close();
    delete globalThis.__showandtellCaptureV7;
    await rm(root, { recursive: true, force: true });
  }
}

const kinds = (events) => events.map((e) => e.kind + (e.phase ? ":" + e.phase : ""));
const stateOf = async (folder, event) => (await readFile(join(folder, event.image)))[2];
const requests = (e) => e.f.calls.filter(([name]) => name === "get_app_state").map(([, r]) => r);

test("reuse mode keeps the screenshot behind every Mac observation, with no extra calls", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  await e.recorder.saveTo(folder, "reuse");
  const app = await e.cua.getApp("Example"); // Its own observation precedes the handle, so no frame yet.
  assert.equal(await app.getAXState(), "no change"); // The engine's own diff, untouched by capture.
  assert.deepEqual(e.f.writes.at(-1), ["no change", "cua.state"]); // Displayed exactly like the engine does.
  await app.click([10, 20], { clickCount: 2 });
  assert.equal(await app.getAXState({ emit: false }), "Display 10");
  assert.equal((await app.getScreenshot({ emit: false }))[2], 10);
  const events = await e.events(folder);
  assert.deepEqual(kinds(events), ["frame:observed", "action", "status", "frame:observed", "frame:observed"]);
  assert.deepEqual(requests(e), [{ app: "Example", disableDiff: true }, { app: "Example" }, { app: "Example" }, { app: RESOLVED }]);
  assert.equal(events[1].x, 10);
  assert.equal(events[1].y, 20);
  assert.equal(events[1].type, "click");
  assert.equal(events[2].status, "ok");
  assert.deepEqual([...new Set(events.map((x) => x.surface))], ["app:1"]);
  assert.deepEqual(await Promise.all(events.filter((x) => x.image).map((x) => stateOf(folder, x))), [0, 10, 10]);
  for (const secret of ["Example", "file:", RESOLVED, "Display", "clickCount"]) assert.equal(JSON.stringify(events).includes(secret), false, secret);
  assert.equal(e.f.writes.filter(([v]) => typeof v === "string" && v.includes("showandtell")).length, 0);
}));

test("a handle from the first call is instrumented by name and gets free AX frames", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  const app = e.handle(RESOLVED); // Created before the recorder existed, like the discovery call.
  const original = app.getAXState;
  assert.equal(e.recorder.instrument(app, "app", "Example"), app);
  assert.notEqual(app.getAXState, original);
  await e.recorder.saveTo(folder, "reuse");
  assert.equal(await app.getAXState({ emit: false, disableDiffing: true }), "Display 0");
  assert.deepEqual(requests(e), [{ app: "Example", disableDiff: true }]);
  assert.deepEqual(kinds(await e.events(folder)), ["frame:observed"]);
  // Without a known app name the engine's own method runs and only text is observed.
  const anonymous = e.recorder.instrument(e.handle(RESOLVED), "app");
  assert.equal(await anonymous.getAXState({ emit: false }), "no change");
  assert.deepEqual(requests(e).at(-1), { app: RESOLVED, disableDiff: undefined });
  assert.deepEqual(kinds(await e.events(folder)), ["frame:observed"]);
}));

test("actions mode records each state and keeps the caller's next AX diff truthful", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  await e.recorder.saveTo(folder);
  const app = await e.cua.getApp("Example");
  await app.click([1, 2]); // No frame of this app yet, so a baseline comes first.
  await app.click([2, 2]);
  assert.equal(await app.getAXState({ emit: false }), "Display 2"); // Not "no change" after our private screenshots.
  assert.equal(await app.getAXState({ emit: false }), "no change");
  assert.deepEqual(requests(e), [
    { app: "Example", disableDiff: true }, { app: RESOLVED }, { app: RESOLVED }, { app: RESOLVED },
    { app: "Example", disableDiff: true }, { app: "Example" },
  ]);
  const events = await e.events(folder);
  assert.deepEqual(kinds(events), ["frame:before", "action", "frame:after", "status", "action", "frame:after", "status",
    "frame:observed", "frame:observed"]);
  assert.deepEqual(await Promise.all(events.filter((x) => x.image).map((x) => stateOf(folder, x))), [0, 1, 2, 2, 2]);
  assert.ok(events.every((x, i) => i === 0 || x.t > events[i - 1].t));
  // A handle without any frame this turn gets one baseline before its first action.
  const other = e.recorder.instrument(e.handle("/Applications/Other.app"), "app", "Other");
  await other.click([5, 5]);
  await other.click([6, 6]);
  const later = (await e.events(folder)).slice(events.length);
  assert.deepEqual(kinds(later), ["frame:before", "action", "frame:after", "status", "action", "frame:after", "status"]);
  assert.equal(later[0].surface, "app:2");
}));

test("the caller's explicit diff request is overridden only after a private screenshot", () => scenario(async (e) => {
  await e.recorder.saveTo(await e.folder("turn", "call"));
  const app = await e.cua.getApp("Example");
  assert.equal(await app.getAXState({ emit: false, disableDiffing: false }), "no change");
  await app.click([3, 3]);
  assert.equal(await app.getAXState({ emit: false, disableDiffing: false }), "Display 3");
  assert.equal(requests(e).at(-1).disableDiff, true);
  assert.equal((await app.getAXStateAndScreenshot({ emit: false })).state, "no change");
  await app.getScreenshot({ emit: false }); // A public screenshot advances the diff as well.
  assert.equal((await app.getAXStateAndScreenshot({ emit: false })).state, "Display 3");
}));

test("private screenshot and storage failures never change the requested action", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  await e.recorder.saveTo(folder);
  const app = await e.cua.getApp("Example");
  e.f.failShots = true;
  await app.click([4, 4]);
  let events = await e.events(folder);
  assert.deepEqual(kinds(events.slice(1)), ["action", "warning:after", "status"]);
  assert.equal(events.at(-2).reason, "screenshot-unavailable");
  e.f.failShots = false;
  const expected = new Error("private click failure");
  e.f.failClick = expected;
  await assert.rejects(app.click([5, 5]), (error) => error === expected);
  events = await e.events(folder);
  assert.equal(events.at(-1).status, "failed");
  assert.equal(events.at(-2).phase, "after");
  assert.equal(JSON.stringify(events).includes("private"), false);
  e.f.failClick = null;
  await e.recorder.saveTo(join(folder, "missing", "call"));
  await app.click([6, 6]);
  await e.recorder.saveTo(join(folder, "missing", "again"));
  await app.click([7, 7]);
  assert.equal(e.f.state, 7);
  const warnings = e.f.writes.filter(([v]) => typeof v === "string" && v.includes("showandtell"));
  assert.equal(warnings.length, 1);
  assert.ok(warnings[0][0].includes("capture-storage-unavailable"));
  assert.equal(await e.events(folder).then((x) => x.length), events.length);
}));

test("typed text, keys, options, and app names stay out of the recording", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  await e.recorder.saveTo(folder, "reuse");
  const app = await e.cua.getApp("Example");
  await app.typeText("secret-password");
  await app.pressKey("secret-key");
  await app.drag([1, 2], [3, 4]);
  await app.click(12, { text: "secret-option" });
  const actions = (await e.events(folder)).filter((x) => x.kind === "action");
  assert.deepEqual(actions.map((x) => [x.type, x.x, x.y]), [["type", null, null], ["key", null, null], ["drag", 1, 2], ["click", null, null]]);
  assert.deepEqual(actions[2].to, [3, 4]);
  for (const secret of ["secret", "Example", RESOLVED]) assert.equal(JSON.stringify(await e.events(folder)).includes(secret), false, secret);
}));

test("reinjection reuses one recorder and never stacks wrappers", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  await e.recorder.saveTo(folder, "reuse");
  const getApp = e.cua.getApp;
  const again = await new AsyncFunction("cua", "nodeRepl", e.source + "\nreturn __showandtell;")(e.cua, e.nodeRepl);
  assert.equal(again, e.recorder);
  assert.equal(e.cua.getApp, getApp);
  const app = await e.cua.getApp("Example");
  const method = app.click;
  assert.equal(e.recorder.instrument(app, "app", "Example"), app);
  assert.equal(app.click, method);
  await app.click([1, 1]);
  assert.equal((await e.events(folder)).filter((x) => x.kind === "action").length, 1);
}));

test("browser tabs are instrumented in place with before/after frames", async () => {
  const bytes = () => new Uint8Array([137, 80, 78, 71, 1]);
  const tab = {
    id: "tab-1", calls: [],
    async getScreenshot(o) { this.calls.push(["screenshot", o]); return bytes(); },
    async getAXState() { return "AX text"; },
    async getAXStateAndScreenshot() { return { state: "AX text", screenshot: bytes() }; },
    async goto(url) { this.calls.push(["goto", url]); },
    async click(p) { this.calls.push(["click", p]); return 7; },
    async typeText(index, text) { this.calls.push(["type", index, text]); },
  };
  await scenario(async (e) => {
    const folder = await e.folder("turn", "call");
    await e.recorder.saveTo(folder);
    const bound = await e.cua.getTab("https://example.test/?token=secret");
    assert.equal(bound, tab);
    await bound.goto("https://another.test/?token=secret");
    assert.equal(await bound.click([30, 40]), 7);
    await bound.typeText(3, "secret");
    assert.equal(await bound.getAXState(), "AX text");
    assert.deepEqual(await bound.getAXStateAndScreenshot(), { state: "AX text", screenshot: bytes() });
    const events = await e.events(folder);
    assert.deepEqual(kinds(events), ["frame:before", "action", "frame:after", "status", "action", "frame:after", "status",
      "action", "frame:after", "status", "frame:observed"]);
    assert.deepEqual(events.filter((x) => x.kind === "action").map((x) => [x.type, x.x, x.y]), [["navigate", null, null], ["click", 30, 40], ["type", null, null]]);
    assert.deepEqual([...new Set(events.map((x) => x.surface))], ["browser:1"]);
    assert.deepEqual(tab.calls.filter(([k]) => k === "screenshot").map(([, o]) => o.emit), [false, false, false, false]);
    assert.deepEqual(requests(e), []);
    for (const secret of ["secret", "example.test", "AX text", "tab-1"]) assert.equal(JSON.stringify(events).includes(secret), false, secret);
  }, { tab });
});

test("frozen handles warn once and keep working", async () => {
  const tab = Object.freeze({ async click() { return 1; }, async getScreenshot() { return new Uint8Array([1]); } });
  await scenario(async (e) => {
    await e.recorder.saveTo(await e.folder("turn", "call"));
    assert.equal(await (await e.cua.getTab("x")).click([1, 1]), 1);
    assert.equal(await (await e.cua.getTab("x")).click([1, 1]), 1);
    assert.deepEqual(e.f.writes.map(([w]) => JSON.parse(w).reason), ["immutable-target"]);
  }, { tab });
});

test("non-Mac app handles get screenshots only through their own methods", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  await e.recorder.saveTo(folder);
  let shots = 0;
  const app = { async getScreenshot() { shots++; return new Uint8Array([137, 80, 78, 71]); }, async getAXState() { return "state"; }, async click() { return 3; } };
  e.cua.getApp = async () => app;
  e.recorder.install(e.cua);
  const bound = await e.cua.getApp({ windowId: 1 });
  assert.equal(await bound.click([2, 2]), 3);
  assert.equal(await bound.getAXState(), "state");
  assert.deepEqual(kinds(await e.events(folder)), ["frame:before", "action", "frame:after", "status"]);
  assert.equal(shots, 2);
  assert.deepEqual(requests(e), []);
}, { target: "linux" }));

test("a new turn takes a fresh baseline; a retried call appends to its own recording", () => scenario(async (e) => {
  const app = e.recorder.instrument(e.handle(RESOLVED), "app", "Example");
  const first = await e.folder("turn-1", "call-a");
  await e.recorder.saveTo(first);
  await app.click([1, 1]);
  assert.deepEqual(kinds(await e.events(first)), ["frame:before", "action", "frame:after", "status"]);
  const second = await e.folder("turn-1", "call-b");
  await e.recorder.saveTo(second);
  await app.click([2, 2]);
  assert.deepEqual(kinds(await e.events(second)), ["action", "frame:after", "status"]);
  await e.recorder.saveTo(second); // A permission retry repeats PreToolUse for the same call.
  await app.click([3, 3]);
  assert.equal((await e.events(second)).filter((x) => x.kind === "action").length, 2);
  const third = await e.folder("turn-2", "call-c");
  await e.recorder.saveTo(third);
  await app.click([4, 4]);
  assert.deepEqual(kinds(await e.events(third)), ["frame:before", "action", "frame:after", "status"]);
}));

test("timestamps stay strictly ordered within one millisecond", () => scenario(async (e) => {
  const folder = await e.folder("turn", "call");
  await e.recorder.saveTo(folder, "reuse");
  const now = Date.now;
  Date.now = () => 2000000000000;
  try {
    const app = await e.cua.getApp("Example");
    await app.getAXState({ emit: false });
    await app.click([1, 2]);
    await app.getAXState({ emit: false });
  } finally {
    Date.now = now;
  }
  const events = await e.events(folder);
  assert.equal(events.length, 4);
  assert.ok(events.every((x, i) => i === 0 || x.t > events[i - 1].t));
}));
