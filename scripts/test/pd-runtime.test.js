const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");

const {
  OWNER_LABEL,
  PDService,
  buildPDRunArgs,
  createPDHandlers,
  inspectPDContainer,
  resolvePDPaths,
} = require("../../frontend/electron/pd-runtime");

function completedChild({ stdout = "", stderr = "", code = 0 } = {}) {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => true;
  queueMicrotask(() => {
    if (stdout) child.stdout.emit("data", Buffer.from(stdout));
    if (stderr) child.stderr.emit("data", Buffer.from(stderr));
    child.emit("exit", code, null);
    child.emit("close", code, null);
  });
  return child;
}

function dockerInspect(id, ownerId) {
  return JSON.stringify([{
    Id: id,
    Config: { Labels: { [OWNER_LABEL]: ownerId } },
  }]);
}

test("portable PD paths and run arguments preserve spaces and Windows drive letters", () => {
  const linux = resolvePDPaths("/repo with spaces", { platform: "linux" });
  assert.equal(linux.workDir, "/repo with spaces/pdtools/work");

  const windows = resolvePDPaths("C:\\repo with spaces", { platform: "win32" });
  assert.equal(windows.workDir, "C:\\repo with spaces\\pdtools\\work");

  const args = buildPDRunArgs({
    projectRoot: "C:\\repo with spaces",
    platform: "win32",
    ownerId: "session-1",
  });
  assert.deepEqual(args.slice(0, 12), [
    "run", "--rm", "-d",
    "--name", "rtlcopilot-pd",
    "--label", `${OWNER_LABEL}=session-1`,
    "-p", "127.0.0.1:7070:7070",
    "-v", "C:\\repo with spaces\\pdtools\\work:/work",
    "-v",
  ]);
  assert.ok(args.includes("C:\\repo with spaces\\pdtools\\api.py:/app/api.py"));
  assert.ok(args.includes("C:\\repo with spaces\\pdtools\\export_preview.py:/app/export_preview.py"));
  assert.equal(args.at(-1), "rtlcopilot/pd-tools");
});

test("container inspection distinguishes absence from Docker failures", () => {
  const absent = inspectPDContainer({
    reference: "missing",
    spawnSyncImpl: () => ({ status: 1, stdout: "", stderr: "Error: No such container: missing" }),
  });
  assert.equal(absent, null);

  assert.throws(() => inspectPDContainer({
    reference: "unknown",
    spawnSyncImpl: () => ({ status: 1, stdout: "", stderr: "permission denied" }),
  }), /inspect.*permission denied/i);
});

test("PD service starts and stops only its exact owned container without a shell", async () => {
  const syncCalls = [];
  const asyncCalls = [];
  const ownerId = "session-owned";
  const spawnSyncImpl = (command, args, options) => {
    syncCalls.push({ command, args, options });
    if (args[0] === "version") return { status: 0, stdout: "27.0", stderr: "" };
    if (args[0] === "image") return { status: 0, stdout: "[]", stderr: "" };
    if (args[0] === "container" && args[2] === "rtlcopilot-pd") {
      return { status: 1, stdout: "", stderr: "No such container" };
    }
    if (args[0] === "container" && args[2] === "container-123") {
      return { status: 0, stdout: dockerInspect("container-123", ownerId), stderr: "" };
    }
    if (args[0] === "stop") return { status: 0, stdout: "container-123", stderr: "" };
    throw new Error(`unexpected sync command: ${args.join(" ")}`);
  };
  const spawnImpl = (command, args, options) => {
    asyncCalls.push({ command, args, options });
    return completedChild({ stdout: "container-123\n" });
  };
  const made = [];
  const service = new PDService({
    projectRoot: "/repo with spaces",
    ownerId,
    spawnImpl,
    spawnSyncImpl,
    mkdirSync: (directory, options) => made.push({ directory, options }),
    ensurePort: async () => {},
    waitForReady: async () => {},
  });

  assert.equal(await service.start(), "container-123");
  await service.stop();

  assert.deepEqual(made, [{ directory: "/repo with spaces/pdtools/work", options: { recursive: true } }]);
  assert.equal(asyncCalls.length, 1);
  assert.equal(asyncCalls[0].command, "docker");
  assert.equal(asyncCalls[0].options.shell, false);
  assert.ok(asyncCalls[0].args.includes("127.0.0.1:7070:7070"));
  assert.ok(syncCalls.every((call) => call.options.shell === false));
  assert.ok(syncCalls.some((call) => call.args[0] === "stop" && call.args[1] === "container-123"));
});

test("PD service refuses a same-named container from any other session", async () => {
  const mutations = [];
  const service = new PDService({
    projectRoot: "/repo",
    ownerId: "this-session",
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container") {
        return { status: 0, stdout: dockerInspect("other-id", "other-session"), stderr: "" };
      }
      mutations.push(args);
      return { status: 0, stdout: "", stderr: "" };
    },
    spawnImpl: () => { throw new Error("must not run"); },
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => {},
  });

  await assert.rejects(service.start(), /already exists.*another session/i);
  assert.deepEqual(mutations, []);
});

test("failed PD readiness removes the exact newly created owned ID", async () => {
  const ownerId = "failed-session";
  const removed = [];
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container" && args[2] === "rtlcopilot-pd") return { status: 1, stdout: "", stderr: "No such container" };
      if (args[0] === "container" && args[2] === "failed-id") return { status: 0, stdout: dockerInspect("failed-id", ownerId), stderr: "" };
      if (args[0] === "rm") { removed.push(args); return { status: 0, stdout: "failed-id", stderr: "" }; }
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => completedChild({ stdout: "failed-id\n" }),
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => { throw new Error("PD service did not become ready"); },
  });

  await assert.rejects(service.start(), /did not become ready/);
  assert.deepEqual(removed, [["rm", "-f", "failed-id"]]);
});

test("stop during readiness aborts startup and cleans up without orphaning", async () => {
  const ownerId = "cancel-session";
  const removed = [];
  let readinessStarted;
  const readiness = new Promise((resolve) => { readinessStarted = resolve; });
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container" && args[2] === "rtlcopilot-pd") return { status: 1, stdout: "", stderr: "No such container" };
      if (args[0] === "container" && args[2] === "cancel-id") return { status: 0, stdout: dockerInspect("cancel-id", ownerId), stderr: "" };
      if (args[0] === "rm") { removed.push(args); return { status: 0, stdout: "cancel-id", stderr: "" }; }
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => completedChild({ stdout: "cancel-id\n" }),
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: ({ signal }) => new Promise((_resolve, reject) => {
      readinessStarted();
      signal.addEventListener("abort", () => reject(Object.assign(new Error("cancelled"), { name: "AbortError" })), { once: true });
    }),
  });

  const starting = service.start();
  await readiness;
  await service.stop();
  await assert.rejects(starting, /cancelled/i);
  assert.deepEqual(removed, [["rm", "-f", "cancel-id"]]);
});

test("a start requested during stop waits and launches a fresh container", async () => {
  const ownerId = "restart-session";
  let runNumber = 0;
  let readinessNumber = 0;
  const removed = [];
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container" && args[2] === "rtlcopilot-pd") return { status: 1, stdout: "", stderr: "No such container" };
      if (args[0] === "container" && args[2] === "restart-1") return { status: 0, stdout: dockerInspect("restart-1", ownerId), stderr: "" };
      if (args[0] === "rm") { removed.push(args); return { status: 0, stdout: "restart-1", stderr: "" }; }
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => {
      runNumber += 1;
      return completedChild({ stdout: `restart-${runNumber}\n` });
    },
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: ({ signal }) => {
      readinessNumber += 1;
      if (readinessNumber === 2) return Promise.resolve();
      return new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(Object.assign(new Error("cancelled"), { name: "AbortError" })), { once: true });
      });
    },
  });

  const firstStart = service.start();
  await new Promise((resolve) => setImmediate(resolve));
  const stopping = service.stop();
  const restarted = service.start();
  await stopping;
  await assert.rejects(firstStart, /cancelled/i);
  assert.equal(await restarted, "restart-2");
  assert.deepEqual(removed, [["rm", "-f", "restart-1"]]);
});

test("the latest stop cancels a restart queued behind an earlier stop", async () => {
  const ownerId = "latest-stop-session";
  let runs = 0;
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container" && args[2] === "rtlcopilot-pd") return { status: 1, stdout: "", stderr: "No such container" };
      if (args[0] === "container" && args[2] === "latest-1") return { status: 0, stdout: dockerInspect("latest-1", ownerId), stderr: "" };
      if (args[0] === "rm") return { status: 0, stdout: "latest-1", stderr: "" };
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => {
      runs += 1;
      return completedChild({ stdout: `latest-${runs}\n` });
    },
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: ({ signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(Object.assign(new Error("cancelled"), { name: "AbortError" })), { once: true });
    }),
  });

  const firstStart = service.start();
  await new Promise((resolve) => setImmediate(resolve));
  const firstStop = service.stop();
  const queuedRestart = service.start();
  const latestStop = service.stop();

  await Promise.all([firstStop, latestStop]);
  await assert.rejects(firstStart, /cancelled/i);
  await assert.rejects(queuedRestart, /cancelled/i);
  assert.equal(runs, 1);
  assert.equal(service.isActive(), false);
});

test("repeated starts share one Docker run", async () => {
  let runs = 0;
  const service = new PDService({
    projectRoot: "/repo",
    ownerId: "repeat-session",
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container") return { status: 1, stdout: "", stderr: "No such container" };
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => { runs += 1; return completedChild({ stdout: "repeat-id\n" }); },
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => {},
  });

  const [first, second] = await Promise.all([service.start(), service.start()]);
  assert.equal(first, "repeat-id");
  assert.equal(second, "repeat-id");
  assert.equal(runs, 1);
});

test("image pulls and Docker runs both avoid a shell", async () => {
  const calls = [];
  const progress = [];
  const service = new PDService({
    projectRoot: "/repo",
    ownerId: "pull-session",
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "image") return { status: 1, stdout: "", stderr: "No such image" };
      if (args[0] === "container") return { status: 1, stdout: "", stderr: "No such container" };
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: (_command, args, options) => {
      calls.push({ args, options });
      return args[0] === "pull"
        ? completedChild({ stderr: "pulling layer\n" })
        : completedChild({ stdout: "pull-id\n" });
    },
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => {},
  });

  await service.start((line) => progress.push(line));
  assert.deepEqual(calls.map((call) => call.args[0]), ["pull", "run"]);
  assert.ok(calls.every((call) => call.options.shell === false));
  assert.match(progress.join(""), /pulling layer/);
});

test("Docker child spawn errors are surfaced", async () => {
  const ownerId = "error-session";
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => true;
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container") return { status: 1, stdout: "", stderr: "No such container" };
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => {
      queueMicrotask(() => child.emit("error", Object.assign(new Error("spawn docker ENOENT"), { code: "ENOENT" })));
      return child;
    },
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => {},
  });

  await assert.rejects(service.start(), /spawn docker ENOENT/);
});

test("Docker run waits for stdout to close before reading the container ID", async () => {
  const ownerId = "delayed-output-session";
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => true;
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container") return { status: 1, stdout: "", stderr: "No such container" };
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => {
      queueMicrotask(() => {
        child.emit("exit", 0, null);
        child.stdout.emit("data", Buffer.from("delayed-id\n"));
        child.emit("close", 0, null);
      });
      return child;
    },
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => {},
  });

  assert.equal(await service.start(), "delayed-id");
});

test("cleanup failures are surfaced with the original startup failure", async () => {
  const ownerId = "cleanup-session";
  let cleanupAttempts = 0;
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container" && args[2] === "rtlcopilot-pd") return { status: 1, stdout: "", stderr: "No such container" };
      if (args[0] === "container" && args[2] === "cleanup-id") return { status: 0, stdout: dockerInspect("cleanup-id", ownerId), stderr: "" };
      if (args[0] === "rm") return { status: 1, stdout: "", stderr: "daemon refused cleanup" };
      if (args[0] === "stop") { cleanupAttempts += 1; return { status: 0, stdout: "cleanup-id", stderr: "" }; }
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => completedChild({ stdout: "cleanup-id\n" }),
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => { throw new Error("health timeout"); },
  });

  await assert.rejects(service.start(), /health timeout.*cleanup failed.*daemon refused cleanup/i);
  await service.stop();
  assert.equal(cleanupAttempts, 1);
  assert.equal(service.isActive(), false);
});

test("a failed normal stop retains the ID so shutdown can retry", async () => {
  const ownerId = "retry-stop-session";
  let stopAttempts = 0;
  const service = new PDService({
    projectRoot: "/repo",
    ownerId,
    spawnSyncImpl: (_command, args) => {
      if (args[0] === "version" || args[0] === "image") return { status: 0, stdout: "", stderr: "" };
      if (args[0] === "container" && args[2] === "rtlcopilot-pd") return { status: 1, stdout: "", stderr: "No such container" };
      if (args[0] === "container" && args[2] === "retry-id") return { status: 0, stdout: dockerInspect("retry-id", ownerId), stderr: "" };
      if (args[0] === "stop") {
        stopAttempts += 1;
        return stopAttempts === 1
          ? { status: 1, stdout: "", stderr: "temporary daemon failure" }
          : { status: 0, stdout: "retry-id", stderr: "" };
      }
      throw new Error(`unexpected: ${args.join(" ")}`);
    },
    spawnImpl: () => completedChild({ stdout: "retry-id\n" }),
    mkdirSync: () => {},
    ensurePort: async () => {},
    waitForReady: async () => {},
  });

  await service.start();
  await assert.rejects(service.stop(), /temporary daemon failure/);
  assert.equal(service.isActive(), true);
  await service.stop();
  assert.equal(stopAttempts, 2);
  assert.equal(service.isActive(), false);
});

test("PD IPC handlers report real start progress and stop results", async () => {
  const sent = [];
  const service = {
    checkDockerStatus: () => ({ installed: true, running: true }),
    start: async (onData) => {
      onData("pulling\n");
      return "ipc-id";
    },
    stop: async () => {},
  };
  const handlers = createPDHandlers({ service });
  const event = { sender: { send: (channel, line) => sent.push({ channel, line }) } };

  assert.deepEqual(handlers.check(), { installed: true, running: true });
  assert.deepEqual(await handlers.start(event), { ok: true, containerId: "ipc-id" });
  assert.deepEqual(await handlers.stop(), { ok: true });
  assert.deepEqual(sent, [
    { channel: "pd-pull-progress", line: "[INFO] Starting PD container...\n" },
    { channel: "pd-pull-progress", line: "pulling\n" },
    { channel: "pd-pull-progress", line: "[INFO] PD container ready on port 7070.\n" },
  ]);
});

test("PD IPC handlers never turn lifecycle failures into success", async () => {
  const handlers = createPDHandlers({
    service: {
      checkDockerStatus: () => ({ installed: true, running: true }),
      start: async () => { throw new Error("readiness failed"); },
      stop: async () => { throw new Error("cleanup failed"); },
    },
  });

  assert.deepEqual(await handlers.start({ sender: { send: () => {} } }), { ok: false, error: "readiness failed" });
  assert.deepEqual(await handlers.stop(), { ok: false, error: "cleanup failed" });
});
