const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const { findPython, venvPython, versionAtLeast } = require("./platform");

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const values = {};
  for (const rawLine of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const separator = line.indexOf("=");
    if (separator === -1) continue;
    let value = line.slice(separator + 1).trim();
    if (value.length >= 2 && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))) {
      value = value.slice(1, -1);
    }
    values[line.slice(0, separator).trim()] = value;
  }
  return values;
}

function defaultCheckCommand(command, args = []) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    timeout: 8000,
  });
  return !result.error && result.status === 0;
}

function defaultCheckBackendImports(python) {
  return defaultCheckCommand(python, [
    "-c",
    "import fastapi, uvicorn, slowapi, dotenv, openai, httpx, pytest",
  ]);
}

function defaultIsPortAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen({ host: "127.0.0.1", port, exclusive: true }, () => {
      server.close(() => resolve(true));
    });
  });
}

async function collectDiagnostics({
  root = path.resolve(__dirname, "..", ".."),
  nodeVersion = process.versions.node,
  platform = process.platform,
  findPythonImpl = findPython,
  checkBackendImports = defaultCheckBackendImports,
  checkCommand = defaultCheckCommand,
  isPortAvailable = defaultIsPortAvailable,
} = {}) {
  const report = { ready: [], requiredAction: [], optionalUnavailable: [] };

  if (versionAtLeast(nodeVersion, "18.0.0")) {
    report.ready.push(`Node.js ${nodeVersion}`);
  } else {
    report.requiredAction.push(`Node.js 18+ is required; found ${nodeVersion}.`);
  }

  try {
    const python = findPythonImpl();
    if (versionAtLeast(python.version, "3.10.0")) {
      report.ready.push(`System Python ${python.version}`);
    } else {
      report.requiredAction.push(`Python 3.10+ is required; found ${python.version}.`);
    }
  } catch (error) {
    report.requiredAction.push(error.message);
  }

  const projectPython = venvPython(root, platform);
  if (!fs.existsSync(projectPython)) {
    report.requiredAction.push("Project .venv is missing. Run npm run setup.");
  } else if (!checkBackendImports(projectPython)) {
    report.requiredAction.push("Backend dependencies are incomplete. Run npm run setup.");
  } else {
    report.ready.push("Backend virtual environment and imports");
  }

  const executableSuffix = platform === "win32" ? ".cmd" : "";
  const vite = path.join(root, "frontend", "node_modules", ".bin", `vite${executableSuffix}`);
  const electron = path.join(root, "frontend", "node_modules", "electron");
  if (fs.existsSync(vite) && fs.existsSync(electron)) {
    report.ready.push("Frontend Vite and Electron dependencies");
  } else {
    report.requiredAction.push("Frontend dependencies are incomplete. Run npm run setup.");
  }

  const backendEnv = parseEnvFile(path.join(root, "backend", ".env"));
  const frontendEnv = parseEnvFile(path.join(root, "frontend", ".env"));
  const backendOffline = String(backendEnv.OFFLINE_MODE || "").toLowerCase() === "true";
  const frontendOffline = String(frontendEnv.VITE_OFFLINE_MODE || "").toLowerCase() === "true";
  if (backendOffline !== frontendOffline) {
    report.requiredAction.push("Backend/frontend offline mode mismatch; set both OFFLINE_MODE and VITE_OFFLINE_MODE consistently.");
  } else if (backendOffline) {
    report.ready.push("Backend and frontend offline mode agree");
  } else {
    const missingOnlineValues = [
      [backendEnv.SUPABASE_URL, "backend SUPABASE_URL"],
      [backendEnv.SUPABASE_SERVICE_KEY, "backend SUPABASE_SERVICE_KEY"],
      [frontendEnv.VITE_SUPABASE_URL, "frontend VITE_SUPABASE_URL"],
      [frontendEnv.VITE_SUPABASE_ANON_KEY, "frontend VITE_SUPABASE_ANON_KEY"],
    ].filter(([value]) => !value).map(([, label]) => label);
    if (missingOnlineValues.length) {
      report.requiredAction.push(`Online mode is missing: ${missingOnlineValues.join(", ")}.`);
    } else {
      report.ready.push("Backend and frontend online Supabase configuration");
    }
  }

  for (const port of [5173, 8080]) {
    if (await isPortAvailable(port)) {
      report.ready.push(`Port ${port} is available`);
    } else {
      report.requiredAction.push(`Port ${port} is already in use; stop its owner or choose a different development port.`);
    }
  }

  if (checkCommand("iverilog", ["-V"])) {
    report.ready.push("Icarus Verilog simulation");
  } else {
    report.optionalUnavailable.push("Icarus Verilog is unavailable; simulation is disabled.");
  }

  if (checkCommand("docker", ["version"])) {
    report.ready.push("Docker daemon for physical design");
  } else {
    report.optionalUnavailable.push("Docker daemon is unavailable; physical design is disabled.");
  }
  report.optionalUnavailable.push("LLM capability is not configured by setup; enter a provider key in the application to enable AI features.");

  report.ok = report.requiredAction.length === 0;
  return report;
}

function formatSection(title, values) {
  return `${title}\n${values.length ? values.map((value) => `  - ${value}`).join("\n") : "  - None"}`;
}

function formatDiagnostics(report) {
  return [
    "RTLCopilot development doctor",
    formatSection("READY", report.ready),
    formatSection("REQUIRED ACTION", report.requiredAction),
    formatSection("OPTIONAL CAPABILITY UNAVAILABLE", report.optionalUnavailable),
  ].join("\n\n");
}

module.exports = {
  collectDiagnostics,
  defaultIsPortAvailable,
  formatDiagnostics,
  parseEnvFile,
};
