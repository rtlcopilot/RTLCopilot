const path = require("node:path");
const { spawnSync } = require("node:child_process");

function numericVersion(value) {
  const match = String(value).match(/(\d+)\.(\d+)(?:\.(\d+))?/);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3] || 0)] : null;
}

function versionAtLeast(actual, minimum) {
  const left = numericVersion(actual);
  const right = numericVersion(minimum);
  if (!left || !right) return false;
  for (let index = 0; index < 3; index += 1) {
    if (left[index] > right[index]) return true;
    if (left[index] < right[index]) return false;
  }
  return true;
}

function pythonCandidates(platform = process.platform) {
  if (platform === "win32") {
    return [
      { command: "py", args: ["-3"] },
      { command: "python", args: [] },
      { command: "python3", args: [] },
    ];
  }
  return [
    { command: "python3", args: [] },
    { command: "python", args: [] },
  ];
}

function inspectPython(candidate, spawnSyncImpl) {
  const result = spawnSyncImpl(candidate.command, [...candidate.args, "--version"], {
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    timeout: 5000,
  });
  if (result.status !== 0) return null;
  const version = numericVersion(`${result.stdout || ""}\n${result.stderr || ""}`);
  if (!version) return null;
  return { ...candidate, version: version.join(".") };
}

function findPython({
  env = process.env,
  platform = process.platform,
  spawnSyncImpl = spawnSync,
} = {}) {
  const override = validatePythonOverride({ env, spawnSyncImpl });
  if (override) return override;

  for (const candidate of pythonCandidates(platform)) {
    const resolved = inspectPython(candidate, spawnSyncImpl);
    if (resolved) return resolved;
  }
  throw new Error("Python was not found. Install Python 3.10+ or set RTLCOPILOT_PYTHON.");
}

function validatePythonOverride({
  env = process.env,
  spawnSyncImpl = spawnSync,
} = {}) {
  const override = env.RTLCOPILOT_PYTHON;
  if (!override) return null;
  const resolved = inspectPython({ command: override, args: [] }, spawnSyncImpl);
  if (!resolved) {
    throw new Error(`RTLCOPILOT_PYTHON is not usable: ${override}`);
  }
  return resolved;
}

function venvPython(root, platform = process.platform) {
  return platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
}

function formatCommand(command, args) {
  return [command, ...args].map((part) => {
    const text = String(part);
    return /\s/.test(text) ? JSON.stringify(text) : text;
  }).join(" ");
}

function run(command, args = [], {
  spawnSyncImpl = spawnSync,
  ...options
} = {}) {
  const result = spawnSyncImpl(command, args, {
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    ...options,
  });
  if (result.status !== 0) {
    const details = [result.stderr, result.stdout]
      .filter(Boolean)
      .map((value) => String(value).trim())
      .filter(Boolean)
      .join("\n");
    const status = result.status == null ? "could not start" : `exit code ${result.status}`;
    throw new Error(`Command failed (${status}): ${formatCommand(command, args)}${details ? `\n${details}` : ""}`);
  }
  return result;
}

module.exports = {
  findPython,
  formatCommand,
  pythonCandidates,
  run,
  validatePythonOverride,
  venvPython,
  versionAtLeast,
};
