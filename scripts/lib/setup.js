const fs = require("node:fs");
const path = require("node:path");

const {
  findPython,
  run,
  venvPython,
  versionAtLeast,
} = require("./platform");

const BACKEND_ENV = "OFFLINE_MODE=true\nALLOWED_ORIGINS=http://localhost:5173\n";
const FRONTEND_ENV = "VITE_OFFLINE_MODE=true\nVITE_API_URL=http://localhost:8080\n";

function ensureEnvFile(filePath, content) {
  if (fs.existsSync(filePath)) return false;
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, { encoding: "utf8", flag: "wx" });
  return true;
}

function setup({
  root = path.resolve(__dirname, "..", ".."),
  nodeVersion = process.versions.node,
  nodeExecutable = process.execPath,
  npmExecPath = process.env.npm_execpath || null,
  platform = process.platform,
  findPythonImpl = findPython,
  runImpl = run,
  log = console.log,
} = {}) {
  if (!versionAtLeast(nodeVersion, "18.0.0")) {
    throw new Error(`Node.js 18+ is required; found ${nodeVersion}.`);
  }

  const python = findPythonImpl();
  if (!versionAtLeast(python.version, "3.10.0")) {
    throw new Error(`Python 3.10+ is required; found ${python.version}.`);
  }

  const venvDir = path.join(root, ".venv");
  const venvExecutable = venvPython(root, platform);
  const npmCommand = npmExecPath ? nodeExecutable : (platform === "win32" ? "npm.cmd" : "npm");
  const npmArgs = npmExecPath ? [npmExecPath] : [];

  log(`Using Python ${python.version}: ${python.command}`);
  if (!fs.existsSync(venvExecutable)) {
    log("Creating .venv...");
    runImpl(python.command, [...python.args, "-m", "venv", venvDir], { cwd: root, stdio: "inherit" });
  } else {
    log("Reusing .venv...");
  }

  log("Installing backend development dependencies...");
  runImpl(venvExecutable, [
    "-m", "pip", "install", "-r", path.join(root, "backend", "requirements-dev.txt"),
  ], { cwd: root, stdio: "inherit" });

  log("Installing frontend dependencies from package-lock.json...");
  runImpl(npmCommand, [...npmArgs, "ci", "--prefix", path.join(root, "frontend")], {
    cwd: root,
    stdio: "inherit",
  });

  const created = {
    backendEnv: ensureEnvFile(path.join(root, "backend", ".env"), BACKEND_ENV),
    frontendEnv: ensureEnvFile(path.join(root, "frontend", ".env"), FRONTEND_ENV),
  };

  log(created.backendEnv ? "Created backend/.env for offline mode." : "Kept existing backend/.env.");
  log(created.frontendEnv ? "Created frontend/.env for offline mode." : "Kept existing frontend/.env.");
  log("Setup complete. Run npm run doctor, then npm run dev.");
  return { created, python, venvExecutable };
}

module.exports = {
  BACKEND_ENV,
  FRONTEND_ENV,
  ensureEnvFile,
  setup,
};
