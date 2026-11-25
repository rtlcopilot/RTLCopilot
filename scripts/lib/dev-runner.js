const path = require("node:path");
const { spawn } = require("node:child_process");

const { stopChild } = require("../../frontend/electron/runtime");
const { validatePythonOverride, venvPython } = require("./platform");

function commonOptions(cwd) {
  return {
    cwd,
    env: { ...process.env },
    shell: false,
    windowsHide: true,
    stdio: "inherit",
  };
}

function backendSpec(root, platform = process.platform, {
  reload = true,
  env = process.env,
  validateOverride = ({ env: selectedEnv }) => validatePythonOverride({ env: selectedEnv }),
} = {}) {
  validateOverride({ env });
  const args = ["-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8080"];
  if (reload) args.push("--reload");
  return {
    name: "backend",
    command: venvPython(root, platform),
    args,
    options: {
      ...commonOptions(path.join(root, "backend")),
      env: {
        ...env,
        PYTHONPATH: path.join(root, "backend"),
        PYTHONUNBUFFERED: "1",
        PYTHONUTF8: "1",
      },
    },
  };
}

function viteSpec(root, platform = process.platform, {
  nodeExecutable = process.execPath,
} = {}) {
  const pathImpl = platform === "win32" ? path.win32 : path;
  return {
    name: "vite",
    command: nodeExecutable,
    args: [pathImpl.join(root, "frontend", "node_modules", "vite", "bin", "vite.js")],
    options: commonOptions(pathImpl.join(root, "frontend")),
  };
}

function electronSpec(root, _platform = process.platform, {
  nodeExecutable = process.execPath,
} = {}) {
  return {
    name: "electron",
    command: nodeExecutable,
    args: [path.join(root, "frontend", "node_modules", "electron", "cli.js"), ".", "--dev"],
    options: commonOptions(path.join(root, "frontend")),
  };
}

function webSpecs(root, platform = process.platform, runtime = {}) {
  return [backendSpec(root, platform, { reload: true, ...runtime }), viteSpec(root, platform, runtime)];
}

function desktopSpecs(root, platform = process.platform, runtime = {}) {
  return [viteSpec(root, platform, runtime), electronSpec(root, platform, runtime)];
}

function spawnSpec(spec, spawnImpl = spawn) {
  const child = spawnImpl(spec.command, spec.args, spec.options);
  child.name = spec.name;
  return child;
}

async function stopChildren(children, stop = stopChild) {
  await Promise.all(children.map((child) => stop(child)));
}

function installShutdownHandlers(children, { exit = (code) => process.exit(code) } = {}) {
  let stopping = false;
  const shutdown = async (code = 0) => {
    if (stopping) return;
    stopping = true;
    await stopChildren(children);
    exit(code);
  };
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.once(signal, () => shutdown(0));
  }
  return shutdown;
}

module.exports = {
  backendSpec,
  desktopSpecs,
  electronSpec,
  installShutdownHandlers,
  spawnSpec,
  stopChildren,
  viteSpec,
  webSpecs,
};
