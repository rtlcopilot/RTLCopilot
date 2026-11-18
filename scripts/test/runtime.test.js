const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  ensurePortAvailable,
  LogTail,
  selectPython,
  stopChild,
  waitForHealth,
} = require("../../frontend/electron/runtime");

test("waitForHealth accepts only the expected health JSON", async () => {
  await waitForHealth({
    url: "http://backend/health",
    attempts: 2,
    intervalMs: 1,
    requestJson: async () => ({ statusCode: 200, body: { status: "ok" } }),
  });

  await assert.rejects(waitForHealth({
    url: "http://backend/health",
    attempts: 2,
    intervalMs: 1,
    requestJson: async () => ({ statusCode: 200, body: { status: "starting" } }),
  }), /did not become ready/);
});

test("waitForHealth rejects when the backend exits before readiness", async () => {
  const child = new EventEmitter();
  child.exitCode = null;
  const waiting = waitForHealth({
    url: "http://127.0.0.1:1/health",
    child,
    attempts: 50,
    intervalMs: 5,
  });
  child.exitCode = 3;
  child.emit("exit", 3, null);
  await assert.rejects(waiting, /exited.*3/i);
});

test("waitForHealth cannot succeed when the backend exits during a health request", async () => {
  const child = new EventEmitter();
  child.exitCode = null;
  await assert.rejects(waitForHealth({
    url: "http://backend/health",
    child,
    attempts: 1,
    requestJson: async () => {
      child.exitCode = 1;
      child.emit("exit", 1, null);
      return { statusCode: 200, body: { status: "ok" } };
    },
  }), /exited.*1/i);
});

test("ensurePortAvailable rejects an occupied backend port without touching its owner", async () => {
  const server = new EventEmitter();
  server.unref = () => {};
  server.listen = () => queueMicrotask(() => server.emit("error", Object.assign(new Error("busy"), { code: "EADDRINUSE" })));
  let closeCalled = false;
  server.close = () => { closeCalled = true; };

  await assert.rejects(
    ensurePortAvailable({ port: 8080, createServer: () => server }),
    /port 8080.*already in use/i,
  );
  assert.equal(closeCalled, false);
});

test("waitForHealth reports a bounded timeout", async () => {
  await assert.rejects(
    waitForHealth({ url: "http://127.0.0.1:1/health", attempts: 2, intervalMs: 1 }),
    /did not become ready after 2 attempts/,
  );
});

test("development Python prefers the repository virtual environment", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rtl runtime "));
  const executable = path.join(root, ".venv", "bin", "python");
  fs.mkdirSync(path.dirname(executable), { recursive: true });
  fs.writeFileSync(executable, "");

  const selected = selectPython({
    projectRoot: root,
    platform: "linux",
    probe: (command) => command === executable,
    fallback: () => ({ command: "python3", args: [] }),
  });

  assert.deepEqual(selected, { command: executable, args: [] });
});

test("a persistent valid override is validated but runtime still uses installed .venv dependencies", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rtl runtime "));
  const executable = path.join(root, ".venv", "bin", "python");
  fs.mkdirSync(path.dirname(executable), { recursive: true });
  fs.writeFileSync(executable, "");
  const probed = [];

  const selected = selectPython({
    projectRoot: root,
    platform: "linux",
    env: { RTLCOPILOT_PYTHON: "/system/python3" },
    probe: (command) => {
      probed.push(command);
      return true;
    },
  });

  assert.deepEqual(probed, ["/system/python3", executable]);
  assert.deepEqual(selected, { command: executable, args: [] });
});

test("an invalid runtime override fails explicitly", () => {
  assert.throws(() => selectPython({
    projectRoot: "/repo",
    env: { RTLCOPILOT_PYTHON: "/missing/python" },
    probe: () => false,
  }), /RTLCOPILOT_PYTHON.*not usable/i);
});

test("LogTail keeps only the configured number of complete lines", () => {
  const tail = new LogTail(3);
  tail.append("one\ntwo\n");
  tail.append("three\nfour\n");
  assert.equal(tail.toString(), "two\nthree\nfour");
});

test("LogTail joins a line split across stream chunks", () => {
  const tail = new LogTail(3);
  tail.append("partial");
  tail.append(" line\nnext\n");
  assert.equal(tail.toString(), "partial line\nnext");
});

test("stopChild sends SIGTERM and waits for exit", async () => {
  const child = new EventEmitter();
  child.exitCode = null;
  child.killed = false;
  child.kill = (signal) => {
    child.killed = true;
    child.signal = signal;
    child.exitCode = 0;
    queueMicrotask(() => child.emit("exit", 0, signal));
    return true;
  };

  await stopChild(child, { timeoutMs: 50 });

  assert.equal(child.signal, "SIGTERM");
});
