const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { ensureEnvFile, setup } = require("../lib/setup");

function tempRepository() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rtlcopilot setup "));
  fs.mkdirSync(path.join(root, "backend"), { recursive: true });
  fs.mkdirSync(path.join(root, "frontend"), { recursive: true });
  return root;
}

function fakeOptions(root, calls = []) {
  return {
    root,
    nodeVersion: "20.12.0",
    platform: "linux",
    npmExecPath: null,
    findPythonImpl: () => ({ command: "/Python With Spaces/python3", args: [], version: "3.12.1" }),
    runImpl: (command, args) => {
      calls.push({ command, args });
      return { status: 0 };
    },
    log: () => {},
  };
}

test("ensureEnvFile creates a missing file once and preserves existing bytes", () => {
  const root = tempRepository();
  const envPath = path.join(root, "backend", ".env");

  assert.equal(ensureEnvFile(envPath, "OFFLINE_MODE=true\n"), true);
  assert.equal(fs.readFileSync(envPath, "utf8"), "OFFLINE_MODE=true\n");

  fs.writeFileSync(envPath, "CUSTOM=value\r\n", "utf8");
  assert.equal(ensureEnvFile(envPath, "OFFLINE_MODE=true\n"), false);
  assert.deepEqual(fs.readFileSync(envPath), Buffer.from("CUSTOM=value\r\n"));
});

test("Windows setup invokes npm through Node instead of relying on cmd shell execution", () => {
  const root = tempRepository();
  const calls = [];
  setup({
    ...fakeOptions(root, calls),
    platform: "win32",
    nodeExecutable: "C:\\Program Files\\nodejs\\node.exe",
    npmExecPath: "C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js",
  });

  assert.deepEqual(calls.at(-1), {
    command: "C:\\Program Files\\nodejs\\node.exe",
    args: [
      "C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js",
      "ci",
      "--prefix",
      path.join(root, "frontend"),
    ],
  });
});

test("setup creates offline defaults and invokes the reproducible install sequence", () => {
  const root = tempRepository();
  const calls = [];

  const result = setup(fakeOptions(root, calls));

  assert.equal(result.created.backendEnv, true);
  assert.equal(result.created.frontendEnv, true);
  assert.match(fs.readFileSync(path.join(root, "backend", ".env"), "utf8"), /OFFLINE_MODE=true/);
  assert.equal(
    fs.readFileSync(path.join(root, "frontend", ".env"), "utf8"),
    "VITE_OFFLINE_MODE=true\nVITE_API_URL=http://localhost:8080\n",
  );
  assert.deepEqual(calls, [
    { command: "/Python With Spaces/python3", args: ["-m", "venv", path.join(root, ".venv")] },
    { command: path.join(root, ".venv", "bin", "python"), args: ["-m", "pip", "install", "-r", path.join(root, "backend", "requirements-dev.txt")] },
    { command: "npm", args: ["ci", "--prefix", path.join(root, "frontend")] },
  ]);
});

test("rerunning setup does not alter existing environment files", () => {
  const root = tempRepository();
  const options = fakeOptions(root);
  setup(options);
  fs.writeFileSync(path.join(root, "backend", ".env"), "OFFLINE_MODE=false\nSECRET=keep\n");
  const before = fs.readFileSync(path.join(root, "backend", ".env"));

  const result = setup(options);

  assert.equal(result.created.backendEnv, false);
  assert.deepEqual(fs.readFileSync(path.join(root, "backend", ".env")), before);
});

test("setup rejects unsupported runtimes before installing anything", () => {
  const root = tempRepository();
  const calls = [];
  assert.throws(() => setup({ ...fakeOptions(root, calls), nodeVersion: "17.9.0" }), /Node\.js 18\+/);
  assert.equal(calls.length, 0);

  assert.throws(() => setup({
    ...fakeOptions(root, calls),
    findPythonImpl: () => ({ command: "python3", args: [], version: "3.9.18" }),
  }), /Python 3\.10\+/);
  assert.equal(calls.length, 0);
});

test("a failed install names the failed command and does not claim success", () => {
  const root = tempRepository();
  assert.throws(() => setup({
    ...fakeOptions(root),
    runImpl: (command, args) => {
      if (args.includes("pip")) throw new Error(`Command failed: ${command} ${args.join(" ")}\nnetwork unavailable`);
      return { status: 0 };
    },
  }), /pip install.*network unavailable/is);
});
