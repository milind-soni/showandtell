// Inject only after CUA's first discovery call. This uses public CUA methods only.
// CUA evaluates calls in fresh scopes, so a local var cannot guard reinjection.
var __showandtell = globalThis.__showandtellCaptureV3 ||= (() => {
    const actions = new Set([
      "click", "drag", "scroll", "typeText", "paste", "pressKey", "setValue",
      "selectText", "performSecondaryAction", "goto", "back", "forward", "reload",
    ]);
    const types = {
      typeText: "type", paste: "type", pressKey: "key", selectText: "select",
      performSecondaryAction: "secondary", goto: "navigate", back: "navigate",
      forward: "navigate", reload: "navigate",
    };
    const observations = new Set(["getScreenshot", "getAXStateAndScreenshot"]);
    const proxies = new WeakMap();
    const surfaces = new WeakMap();
    const wrappedMethods = new WeakSet();
    const wrappedCreators = new WeakSet();
    const creatorWarnings = new Set();
    const warned = new WeakSet();
    const originals = new WeakMap();
    let sequence = 0;
    let surfaceSequence = 0;
    let output = Promise.resolve();
    let destination = null;
    let mode = "reuse";
    let lastTime = 0;
    const timestamp = () => (lastTime = Math.max(Date.now() / 1000, lastTime + 0.000001));
    const saveTo = async (directory, captureMode = "reuse") => {
      await output;
      try { await destination?.file?.close(); } catch (_) {}
      mode = captureMode === "full" ? "full" : "reuse";
      destination = { directory };
      try {
        const fs = await import("node:fs/promises");
        destination = { directory, fs, file: await fs.open(directory + "/events.jsonl", "wx", 0o600) };
      } catch (_) {
        try { await nodeRepl.write(JSON.stringify({ showandtell: 1, kind: "warning",
          reason: "capture-storage-unavailable" }) + "\n"); } catch (_) {}
      }
    };
    const surfaceFor = (target, kind) => {
      if (!surfaces.has(target)) {
        surfaces.set(target, `${kind === "browser" ? "browser" : "app"}:${++surfaceSequence}`);
      }
      return surfaces.get(target);
    };
    const point = (value) => Array.isArray(value) && value.length === 2 &&
      value.every((n) => typeof n === "number" && Number.isFinite(n)) ? value : null;
    const imageBytes = (value) => ArrayBuffer.isView(value) && value.BYTES_PER_ELEMENT === 1 && value.byteLength
      ? new Uint8Array(new Uint8Array(value.buffer, value.byteOffset, value.byteLength)) : null;
    const emit = (event, image, emitImage = true) => {
      const sink = destination;
      event = { ...event, t: timestamp() };
      output = output.then(async () => {
        if (sink) {
          try {
            if (!sink.file) return;
            const entry = { showandtell: 1, ...event };
            if (image !== undefined) {
              entry.image = event.id + "-" + event.phase + ".img";
              await sink.fs.writeFile(sink.directory + "/" + entry.image, image,
                { flag: "wx", mode: 0o600 });
            }
            await sink.file.write(JSON.stringify(entry) + "\n");
          } catch (_) {
            await nodeRepl.write(JSON.stringify({ showandtell: 1, kind: "warning",
              reason: "capture-storage-write-failed" }) + "\n");
          }
          return;
        }
        await nodeRepl.write(JSON.stringify({ showandtell: 1, ...event }) + "\n");
        if (image !== undefined && emitImage) {
          try { await nodeRepl.emitImage(image); }
          catch (_) {
            await nodeRepl.write(JSON.stringify({ showandtell: 1, kind: "warning",
              id: event.id, surface: event.surface, phase: event.phase,
              t: timestamp(), reason: "image-emission-failed" }) + "\n");
          }
        }
      }).catch(() => {});
      return output;
    };
    const frame = async (target, event, phase) => {
      try {
        const method = target.getScreenshot;
        const screenshot = await Reflect.apply(originals.get(method) ?? method, target, [{ emit: false }]);
        const image = imageBytes(screenshot);
        if (image?.length) {
          await emit({ ...event, kind: "frame", phase }, image);
          return;
        }
      } catch (_) { /* Capture must never prevent the requested action. */ }
      await emit({ ...event, kind: "warning", phase,
        reason: "screenshot-unavailable" });
    };
    const observe = async (target, method, type, args, surface) => {
      const result = await Reflect.apply(method, target, args);
      const image = imageBytes(type === "getScreenshot" ? result : result?.screenshot);
      // Nested public observations may repeat a frame; the collector deduplicates its bytes.
      if (image) await emit({ id: `std-${Date.now()}-${++sequence}`, surface,
        kind: "frame", phase: "observed" }, image, false);
      return result;
    };
    const run = async (target, method, type, args, surface) => {
      const event = { id: `std-${Date.now()}-${++sequence}`, surface };
      const full = mode === "full";
      if (full) await frame(target, event, "before");
      const from = point(args[0]);
      const details = { x: from?.[0] ?? null, y: from?.[1] ?? null };
      if (type === "drag") details.to = point(args[1]);
      await emit({ ...event, kind: "action",
        type: types[type] ?? type, ...details });
      let status = "failed";
      try {
        const result = await Reflect.apply(method, target, args);
        status = "ok";
        return result;
      } finally {
        if (full) await frame(target, event, "after");
        await emit({ ...event, kind: "status", status });
      }
    };
    const makeMethod = (target, method, type, surface) => {
      const wrapped = (...args) => (observations.has(type) ? observe : run)(target, method, type, args, surface);
      wrappedMethods.add(wrapped);
      originals.set(wrapped, method);
      return wrapped;
    };
    const instrument = (target, kind = "app") => {
      if (!target || typeof target !== "object") return target;
      const surface = surfaceFor(target, kind);
      let failed = false;
      for (const type of [...actions, ...observations]) {
        try {
          const method = target[type];
          if (typeof method !== "function" || wrappedMethods.has(method)) continue;
          const wrapped = makeMethod(target, method, type, surface);
          if (!Reflect.set(target, type, wrapped) || target[type] !== wrapped) failed = true;
        } catch (_) { failed = true; }
      }
      if (failed && !warned.has(target)) {
        warned.add(target);
        void emit({ kind: "warning", surface, reason: "immutable-target" });
      }
      return target;
    };
    const wrap = (target, kind = "app") => {
      if (!target || typeof target !== "object") return target;
      if (proxies.has(target)) return proxies.get(target);
      const surface = surfaceFor(target, kind);
      const methods = new Map();
      // A separate facade permits wrapping immutable handles without Proxy invariants.
      const proxy = new Proxy({}, {
        get(_, property) {
          const value = Reflect.get(target, property, target);
          if (typeof value !== "function") return value;
          const cached = methods.get(property);
          if (cached?.original === value) return cached.wrapped;
          const wrapped = (actions.has(property) || observations.has(property)) && !wrappedMethods.has(value)
            ? makeMethod(target, value, property, surface) : value.bind(target);
          methods.set(property, { original: value, wrapped });
          return wrapped;
        },
        set(_, property, value) { return Reflect.set(target, property, value, target); },
        has(_, property) { return property in target; },
      });
      proxies.set(target, proxy);
      proxies.set(proxy, proxy);
      surfaces.set(proxy, surface);
      return proxy;
    };
    const install = (api) => {
      const warn = (method) => {
        if (creatorWarnings.has(method)) return;
        creatorWarnings.add(method);
        void emit({ kind: "warning", reason: "immutable-creator", method });
      };
      for (const name of ["getApp", "getTab", "createBrowserTab"]) {
        try {
          const original = api[name];
          if (typeof original !== "function" || wrappedCreators.has(original)) continue;
          const creator = async function (...args) {
            const target = await Reflect.apply(original, this, args);
            return wrap(target, name === "getApp" ? "app" : "browser");
          };
          wrappedCreators.add(creator);
          if (!Reflect.set(api, name, creator) || api[name] !== creator) warn(name);
        } catch (_) { warn(name); }
      }
    };
    return { instrument, wrap, install, saveTo };
  })();
try { __showandtell.install(cua); } catch (_) {}
