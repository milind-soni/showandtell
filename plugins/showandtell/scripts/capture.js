// Showandtell recorder. Injected after CUA's required first discovery call; the
// REPL keeps state across calls, so one registry guards against reinjection.
// Only app/tab handles are instrumented. cua.computer and nodeRepl are the
// engine's read-only objects and are only ever called, never modified.
var __showandtell = globalThis.__showandtellCaptureV7 ||= (() => {
    const actions = {
      click: "click", drag: "drag", scroll: "scroll", typeText: "type", paste: "type",
      pressKey: "key", setValue: "setValue", selectText: "select", performSecondaryAction: "secondary",
      goto: "navigate", back: "navigate", forward: "navigate", reload: "navigate",
    };
    const observations = ["getScreenshot", "getAXState", "getAXStateAndScreenshot"];
    const wrappers = new WeakSet();
    const handles = new WeakMap();
    const photographed = new Set();
    const needsFullAX = new Set();
    const warnedOnce = new Set();
    let surfaceCount = 0;
    let sequence = 0;
    let lastTime = 0;
    let output = Promise.resolve();
    let destination = null;
    let turnFolder = null;
    let mode = "actions";
    const timestamp = () => (lastTime = Math.max(Date.now() / 1000, lastTime + 0.000001));
    const nextId = () => `std-${Date.now()}-${++sequence}`;
    const finite = (n) => typeof n === "number" && Number.isFinite(n);
    const point = (value) => Array.isArray(value) && value.length === 2 && value.every(finite) ? value : null;
    const isMac = () => { try { return cua?.computer?.target === "mac"; } catch (_) { return false; } };
    const warn = async (reason, error) => {
      if (warnedOnce.has(reason)) return;
      warnedOnce.add(reason);
      const code = typeof error?.code === "string" ? { code: error.code } : {};
      try { await nodeRepl.write(JSON.stringify({ showandtell: 1, kind: "warning", reason, ...code }) + "\n"); } catch (_) {}
    };
    const close = async () => {
      await output;
      const open = destination;
      destination = null;
      try { await open?.file?.close(); } catch (_) {}
    };
    const saveTo = async (directory, captureMode = "actions") => {
      await close();
      const folder = directory.slice(0, directory.lastIndexOf("/"));
      if (turnFolder !== folder) photographed.clear();
      turnFolder = folder;
      mode = ["reuse", "actions", "full"].includes(captureMode) ? captureMode : "actions";
      try {
        const fs = await import("node:fs/promises");
        const { fileURLToPath } = await import("node:url");
        const file = await fs.open(directory + "/events.jsonl",
          fs.constants.O_WRONLY | fs.constants.O_APPEND | fs.constants.O_CREAT | fs.constants.O_NOFOLLOW, 0o600);
        destination = { directory, fs, fileURLToPath, file };
      } catch (error) {
        await warn("capture-storage-unavailable", error);
      }
    };
    const emit = (event, image) => {
      const sink = destination;
      const entry = { showandtell: 1, ...event, t: timestamp() };
      if (!sink) return output;
      output = output.then(async () => {
        try {
          if (image) {
            entry.image = entry.id + "-" + entry.phase + ".img";
            await sink.fs.writeFile(sink.directory + "/" + entry.image, image, { flag: "wx", mode: 0o600 });
          }
          await sink.file.write(JSON.stringify(entry) + "\n");
        } catch (error) {
          await warn("capture-storage-write-failed", error);
        }
      }).catch(() => {});
      return output;
    };
    const bytesOf = (value) => ArrayBuffer.isView(value) && value.BYTES_PER_ELEMENT === 1 && value.byteLength
      ? new Uint8Array(new Uint8Array(value.buffer, value.byteOffset, value.byteLength)) : null;
    // The Mac engine returns each screenshot as a short-lived file URL.
    const readShot = async (url) => {
      const sink = destination;
      if (!sink || typeof url !== "string" || !url.startsWith("file:")) return null;
      try { return bytesOf(await sink.fs.readFile(sink.fileURLToPath(url))); } catch (_) { return null; }
    };
    const saveFrame = async (event, phase, image) => {
      if (!image?.length) return false;
      await emit({ ...event, kind: "frame", phase }, image);
      photographed.add(event.surface);
      return true;
    };
    const frame = async (target, info, event, phase) => {
      try {
        const method = target.getScreenshot;
        const original = wrappers.has(method) ? method.original : method;
        if (info.mac) needsFullAX.add(info.surface); // Its screenshot advances the engine's AX diff.
        if (await saveFrame(event, phase, bytesOf(await Reflect.apply(original, target, [{ emit: false }])))) return;
      } catch (_) { /* Capture must never prevent the requested action. */ }
      await emit({ ...event, kind: "warning", phase, reason: "screenshot-unavailable" });
    };
    // A Mac getAXState already makes the engine take a screenshot and discard
    // it. Making the same public call ourselves keeps that image as a frame.
    const observeAX = async (info, options) => {
      const request = options?.disableDiffing === undefined ? { app: info.app } : { app: info.app, disableDiff: options.disableDiffing };
      const state = await cua.computer.get_app_state(request);
      if (typeof state?.text !== "string") return null;
      if (options?.emit !== false) await nodeRepl.write(state.text, "cua.state");
      return { text: state.text, image: await readShot(state.screenshot?.url) };
    };
    const observe = async (target, info, name, original, args) => {
      let options = args[0];
      if (info.mac && name === "getScreenshot") needsFullAX.add(info.surface);
      if (info.mac && name !== "getScreenshot" && needsFullAX.has(info.surface)) {
        // A private screenshot advanced the diff; a diff now would claim "no change".
        options = { ...options, disableDiffing: true };
        args = [options, ...args.slice(1)];
      }
      let result, image = null;
      const free = info.mac && name === "getAXState" && info.app && destination ? await observeAX(info, options) : null;
      if (free) {
        result = free.text;
        image = free.image;
      } else {
        result = await Reflect.apply(original, target, args);
        image = bytesOf(name === "getScreenshot" ? result : result?.screenshot);
      }
      if (info.mac && name !== "getScreenshot" && options?.disableDiffing) needsFullAX.delete(info.surface);
      if (destination) await saveFrame({ id: nextId(), surface: info.surface }, "observed", image);
      return result;
    };
    const run = async (target, info, type, original, args) => {
      if (!destination) return Reflect.apply(original, target, args);
      const event = { id: nextId(), surface: info.surface };
      if (mode === "full" || (mode === "actions" && !photographed.has(info.surface))) await frame(target, info, event, "before");
      const from = point(args[0]);
      const details = { x: from?.[0] ?? null, y: from?.[1] ?? null };
      if (type === "drag") details.to = point(args[1]);
      await emit({ ...event, kind: "action", type, ...details });
      let status = "failed";
      try {
        const result = await Reflect.apply(original, target, args);
        status = "ok";
        return result;
      } finally {
        if (mode !== "reuse") await frame(target, info, event, "after");
        await emit({ ...event, kind: "status", status });
      }
    };
    const replace = (target, name, make) => {
      const original = target[name];
      if (typeof original !== "function" || wrappers.has(original)) return true;
      const wrapper = make(original);
      wrapper.original = original;
      wrappers.add(wrapper);
      try { return Reflect.set(target, name, wrapper) && target[name] === wrapper; } catch (_) { return false; }
    };
    const instrument = (target, kind = "app", app) => {
      if (!target || typeof target !== "object") return target;
      if (handles.has(target)) {
        if (typeof app === "string" && app) handles.get(target).app = app;
        return target;
      }
      const info = { kind, surface: `${kind === "browser" ? "browser" : "app"}:${++surfaceCount}`,
        mac: kind !== "browser" && isMac(), app: typeof app === "string" && app ? app : undefined };
      handles.set(target, info);
      let ok = true;
      for (const [name, type] of Object.entries(actions)) {
        ok = replace(target, name, (original) => (...args) => run(target, info, type, original, args)) && ok;
      }
      for (const name of observations) {
        ok = replace(target, name, (original) => (...args) => observe(target, info, name, original, args)) && ok;
      }
      if (!ok) void warn("immutable-target");
      return target;
    };
    const install = (api) => {
      if (!api || typeof api !== "object") return;
      for (const name of ["getApp", "getTab", "createBrowserTab"]) {
        const kind = name === "getApp" ? "app" : "browser";
        if (!replace(api, name, (original) => async function (...args) {
          return instrument(await Reflect.apply(original, this, args), kind, kind === "app" ? args[0] : undefined);
        })) void warn("immutable-creator");
      }
    };
    return { install, instrument, saveTo, close };
  })();
try { __showandtell.install(cua); } catch (_) {}
