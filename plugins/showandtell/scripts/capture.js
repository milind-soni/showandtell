// Inject only after CUA's first discovery call. This uses public CUA methods only.
// CUA evaluates calls in fresh scopes, so a local var cannot guard reinjection.
var __showandtell = globalThis.__showandtellCaptureV2 ||= (() => {
    const actions = new Set([
      "click", "drag", "scroll", "typeText", "paste", "pressKey", "setValue",
      "selectText", "performSecondaryAction", "goto", "back", "forward", "reload",
    ]);
    const types = {
      typeText: "type", paste: "type", pressKey: "key", selectText: "select",
      performSecondaryAction: "secondary", goto: "navigate", back: "navigate",
      forward: "navigate", reload: "navigate",
    };
    const proxies = new WeakMap();
    const surfaces = new WeakMap();
    const wrappedMethods = new WeakSet();
    const wrappedCreators = new WeakSet();
    const creatorWarnings = new Set();
    const warned = new WeakSet();
    let sequence = 0;
    let surfaceSequence = 0;
    let output = Promise.resolve();
    let destination = null;
    const saveTo = async (directory) => {
      await output;
      try { await destination?.file?.close(); } catch (_) {}
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
    const emit = (event, image) => {
      const sink = destination;
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
        if (image !== undefined) {
          try { await nodeRepl.emitImage(image); }
          catch (_) {
            await nodeRepl.write(JSON.stringify({ showandtell: 1, kind: "warning",
              id: event.id, surface: event.surface, phase: event.phase,
              t: Date.now() / 1000, reason: "image-emission-failed" }) + "\n");
          }
        }
      }).catch(() => {});
      return output;
    };
    const frame = async (target, event, phase) => {
      try {
        const screenshot = await target.getScreenshot({ emit: false });
        // Native handles can return cross-realm bytes rejected by emitImage.
        const image = screenshot == null ? null : new Uint8Array(screenshot);
        if (image?.length) {
          await emit({ ...event, kind: "frame", t: Date.now() / 1000, phase }, image);
          return;
        }
      } catch (_) { /* Capture must never prevent the requested action. */ }
      await emit({ ...event, kind: "warning", t: Date.now() / 1000, phase,
        reason: "screenshot-unavailable" });
    };
    const run = async (target, method, type, args, surface) => {
      const event = { id: `std-${Date.now()}-${++sequence}`, surface };
      await frame(target, event, "before");
      const from = point(args[0]);
      const details = { x: from?.[0] ?? null, y: from?.[1] ?? null };
      if (type === "drag") details.to = point(args[1]);
      await emit({ ...event, kind: "action", t: Date.now() / 1000,
        type: types[type] ?? type, ...details });
      let status = "failed";
      try {
        const result = await Reflect.apply(method, target, args);
        status = "ok";
        return result;
      } finally {
        await frame(target, event, "after");
        await emit({ ...event, kind: "status", t: Date.now() / 1000, status });
      }
    };
    const makeMethod = (target, method, type, surface) => {
      const wrapped = (...args) => run(target, method, type, args, surface);
      wrappedMethods.add(wrapped);
      return wrapped;
    };
    const instrument = (target, kind = "app") => {
      if (!target || typeof target !== "object") return target;
      const surface = surfaceFor(target, kind);
      let failed = false;
      for (const type of actions) {
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
          const wrapped = actions.has(property) && !wrappedMethods.has(value)
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
