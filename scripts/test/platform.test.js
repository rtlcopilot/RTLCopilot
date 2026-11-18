const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {
  findPython,
  pythonCandidates,
  run,
  venvPython,
  versionAtLeast,
} = require("../lib/platform");

function fakeSpawn(results, calls) {
  return (command, args, options) => {
    calls.push({ command, args, options });
    return results[command] || { status: 1, stdout: "", stderr: "missing" };
  };
}

test("RTLCOPILOT_PYTHON takes precedence and paths with spaces are not shell split", () => {
  const calls = [];
  const override = path.join("C:\\Program Files", "Python", "python.exe");
  const result = findPython({
    env: { RTLCOPILOT_PYTHON: override },
    platform: "win32",
    spawnSyncImpl: fakeSpawn({
      [override]: { status: 0, stdout: "Python 3.12.2\n", stderr: "" },
    }, calls),
  });

  assert.equal(result.command, override);
  assert.deepEqual(result.args, []);
  assert.deepEqual(calls[0].args, ["--version"]);
  assert.equal(calls[0].options.shell, false);
});

test("an invalid configured override fails instead of silently falling back", () => {
  assert.throws(
    () => findPython({
      env: { RTLCOPILOT_PYTHON: "/missing/python" },
      spawnSyncImpl: () => ({ status: 1, stdout: "", stderr: "not found" }),
    }),
    /RTLCOPILOT_PYTHON.*not usable/i,
  );
});

test("platform candidates are deterministic", () => {
  assert.deepEqual(pythonCandidates("win32"), [
    { command: "py", args: ["-3"] },
    { command: "python", args: [] },
    { command: "python3", args: [] },
  ]);
  assert.deepEqual(pythonCandidates("darwin"), [
    { command: "python3", args: [] },
    { command: "python", args: [] },
  ]);
  assert.deepEqual(pythonCandidates("linux"), [
    { command: "python3", args: [] },
    { command: "python", args: [] },
  ]);
});

test("findPython returns the first usable platform candidate with its prefix args", () => {
  const calls = [];
  const result = findPython({
    env: {},
    platform: "win32",
    spawnSyncImpl: fakeSpawn({
      py: { status: 0, stdout: "Python 3.11.8\n", stderr: "" },
    }, calls),
  });

  assert.deepEqual(result, { command: "py", args: ["-3"], version: "3.11.8" });
  assert.deepEqual(calls[0].args, ["-3", "--version"]);
});

test("findPython accepts a successful version probe even when the host reports a spawn warning", () => {
  const result = findPython({
    env: {},
    platform: "linux",
    spawnSyncImpl: () => ({
      status: 0,
      stdout: "Python 3.12.3\n",
      stderr: "",
      error: Object.assign(new Error("spawn warning"), { code: "EPERM" }),
    }),
  });

  assert.equal(result.version, "3.12.3");
});

test("venvPython uses the native virtual environment layout", () => {
  assert.equal(venvPython("/repo", "linux"), path.join("/repo", ".venv", "bin", "python"));
  assert.equal(venvPython("C:\\repo", "win32"), path.join("C:\\repo", ".venv", "Scripts", "python.exe"));
});

test("versionAtLeast compares numeric version components", () => {
  assert.equal(versionAtLeast("18.0.0", "18.0.0"), true);
  assert.equal(versionAtLeast("20.1.0", "18.0.0"), true);
  assert.equal(versionAtLeast("17.9.9", "18.0.0"), false);
  assert.equal(versionAtLeast("3.10", "3.10.0"), true);
});

test("run reports the exact failed command", () => {
  assert.throws(
    () => run("tool with spaces", ["install", "pkg"], {
      spawnSyncImpl: () => ({ status: 7, stdout: "out", stderr: "network down" }),
    }),
    (error) => {
      assert.match(error.message, /"tool with spaces" install pkg/);
      assert.match(error.message, /exit code 7/);
      assert.match(error.message, /network down/);
      return true;
    },
  );
});
