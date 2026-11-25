const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {
  backendSpec,
  desktopSpecs,
  stopChildren,
  webSpecs,
} = require("../lib/dev-runner");

test("browser backend keeps reload and uses the project virtual environment", () => {
  const root = path.join("/tmp", "repo with spaces");
  const spec = backendSpec(root, "linux", { reload: true });
  assert.equal(spec.command, path.join(root, ".venv", "bin", "python"));
  assert.deepEqual(spec.args, [
    "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8080", "--reload",
  ]);
  assert.equal(spec.options.shell, false);
  assert.equal(spec.options.cwd, path.join(root, "backend"));
});

test("browser backend rejects an invalid configured Python override", () => {
  assert.throws(() => backendSpec("/repo", "linux", {
    reload: true,
    env: { RTLCOPILOT_PYTHON: "/missing/python" },
    validateOverride: () => { throw new Error("RTLCOPILOT_PYTHON is not usable: /missing/python"); },
  }), /RTLCOPILOT_PYTHON.*not usable/i);
});

test("web and desktop specs use direct commands without a shell", () => {
  const root = "/repo";
  assert.deepEqual(webSpecs(root, "linux").map((spec) => spec.name), ["backend", "vite"]);
  assert.deepEqual(desktopSpecs(root, "linux").map((spec) => spec.name), ["vite", "electron"]);
  for (const spec of [...webSpecs(root, "linux"), ...desktopSpecs(root, "linux")]) {
    assert.equal(spec.options.shell, false);
  }
});

test("Vite is a direct child so shutdown cannot orphan an npm grandchild", () => {
  const root = "/repo with spaces";
  const nodeExecutable = "/opt/node/bin/node";
  const spec = desktopSpecs(root, "linux", { nodeExecutable })[0];

  assert.equal(spec.command, nodeExecutable);
  assert.deepEqual(spec.args, [path.join(root, "frontend", "node_modules", "vite", "bin", "vite.js")]);
  assert.equal(spec.options.cwd, path.join(root, "frontend"));
});

test("Windows runners invoke Vite and Electron JavaScript entrypoints through Node", () => {
  const root = "C:\\repo with spaces";
  const runtime = {
    nodeExecutable: "C:\\Program Files\\nodejs\\node.exe",
    npmExecPath: "C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js",
  };
  const web = webSpecs(root, "win32", runtime);
  const desktop = desktopSpecs(root, "win32", runtime);

  assert.equal(web[1].command, runtime.nodeExecutable);
  assert.equal(web[1].args[0], path.win32.join(root, "frontend", "node_modules", "vite", "bin", "vite.js"));
  assert.equal(desktop[1].command, runtime.nodeExecutable);
  assert.equal(desktop[1].args[0], path.join(root, "frontend", "node_modules", "electron", "cli.js"));
  assert.equal(desktop[1].options.shell, false);
});

test("stopChildren waits for every owned child", async () => {
  const stopped = [];
  const children = ["backend", "vite"].map((name) => ({ name }));
  await stopChildren(children, async (child) => stopped.push(child.name));
  assert.deepEqual(stopped.sort(), ["backend", "vite"]);
});
