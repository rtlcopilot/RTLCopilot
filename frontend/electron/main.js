const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const {
  LogTail,
  ensurePortAvailable,
  selectPython,
  stopChild,
  waitForHealth,
} = require("./runtime");
const IS_DEV = !app.isPackaged || process.argv.includes("--dev");
const BACKEND_PORT = 8080;
const FRONTEND_PORT = 5173;
const PD_PORT = 7070;
const PD_IMAGE = "rtlcopilot/pd-tools";
const PD_CONTAINER_NAME = "rtlcopilot-pd";
const PD_WORK_DIR = path.join("D:\\RTLCopilot", "pd_work");

let mainWindow = null;
let backendProcess = null;
let backendLogTail = new LogTail();
let pdContainerRunning = false;
let shutdownInProgress = false;

function startBackend() {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const backendDir = IS_DEV
    ? path.join(projectRoot, "backend")
    : path.join(process.resourcesPath, "backend");

  console.log("[backend] projectRoot:", projectRoot);
  console.log("[backend] backendDir:", backendDir);

  const python = selectPython({
    projectRoot,
    fallback: () => {
      const candidates = app.isPackaged
        ? [path.join(process.resourcesPath, "python", "python.exe"), "python", "python3"]
        : ["python3", "python"];
      for (const command of candidates) {
        const result = spawnSync(command, ["--version"], {
          encoding: "utf8",
          shell: false,
          timeout: 3000,
          windowsHide: true,
        });
        if (result.status === 0) return { command, args: [] };
      }
      throw new Error("Python not found. Run npm run doctor.");
    },
  });

  console.log(`Starting backend with ${python.command} in ${backendDir}`);
  backendLogTail = new LogTail(40);

  backendProcess = spawn(
    python.command,
    [...python.args, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    {
      cwd: backendDir,
      shell: false,
      windowsHide: true,
      env: { ...process.env, PYTHONPATH: backendDir, DESKTOP_MODE: "1", PYTHONUNBUFFERED: "1", PYTHONUTF8: "1" },
    }
  );

  const ownedProcess = backendProcess;
  backendProcess.stdout.on("data", (d) => {
    backendLogTail.append(d);
    console.log("[backend]", d.toString().trim());
  });
  backendProcess.stderr.on("data", (d) => {
    backendLogTail.append(d);
    console.log("[backend err]", d.toString().trim());
  });
  backendProcess.on("exit", (code) => {
    console.log(`[backend] exited with code ${code}`);
    if (backendProcess === ownedProcess) backendProcess = null;
  });
  return ownedProcess;
}

async function stopBackend() {
  const ownedProcess = backendProcess;
  backendProcess = null;
  await stopChild(ownedProcess);
}

function checkDockerStatus() {
  const which = spawnSync(
    process.platform === "win32" ? "where" : "which",
    ["docker"],
    { timeout: 3000, windowsHide: true, shell: true }
  );
  if (which.status !== 0) {
    return { installed: false, running: false };
  }


  const version = spawnSync("docker", ["version", "--format", "{{.Server.Version}}"], {
    timeout: 8000, windowsHide: true, shell: true,
  });
  return { installed: true, running: version.status === 0 };
}

function imageExistsLocally() {
  const result = spawnSync("docker", ["image", "inspect", PD_IMAGE], {
    timeout: 5000, windowsHide: true, shell: true,
  });
  return result.status === 0;
}

function pullImage(onData) {
  return new Promise((resolve, reject) => {
    const proc = spawn("docker", ["pull", PD_IMAGE], { windowsHide: true, shell: true });
    proc.stdout.on("data", (d) => onData(d.toString()));
    proc.stderr.on("data", (d) => onData(d.toString()));
    proc.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`docker pull exited with code ${code}`));
    });
  });
}

function startPDContainer() {
  return new Promise((resolve, reject) => {
    spawnSync("docker", ["rm", "-f", PD_CONTAINER_NAME], {
      timeout: 5000, windowsHide: true, shell: true,
    });

    const fs = require("fs");
    if (!fs.existsSync(PD_WORK_DIR)) fs.mkdirSync(PD_WORK_DIR, { recursive: true });

    const proc = spawn("docker", [
      "run", "--rm", "-d",
      "--name", PD_CONTAINER_NAME,
      "-p", `${PD_PORT}:7070`,
      "-v", `${PD_WORK_DIR}:/work`,
      "-v", `D:\\RTLCopilot\\pdtools\\api.py:/app/api.py`,
      "-v", `D:\\RTLCopilot\\pdtools\\pd_verification.py:/app/pd_verification.py`,
      "-v", `D:\\RTLCopilot\\pdtools\\verification_policy.json:/app/verification_policy.json`,
      "-v", `D:\\RTLCopilot\\pdtools\\export_preview.py:/app/export_preview.py`,
      PD_IMAGE,
    ], { windowsHide: true, shell: true });

    let out = "";
    proc.stdout.on("data", (d) => { out += d.toString(); });
    proc.stderr.on("data", (d) => { out += d.toString(); });
    proc.on("exit", (code) => {
      if (code === 0) {
        pdContainerRunning = true;
        resolve();
      } else {
        reject(new Error(`docker run failed: ${out}`));
      }
    });
  });
}

function stopPDContainer() {
  if (!pdContainerRunning) return;
  spawnSync("docker", ["stop", PD_CONTAINER_NAME], {
    timeout: 10000, windowsHide: true, shell: true,
  });
  pdContainerRunning = false;
  console.log("[pd] container stopped");
}

function waitForPDContainer(retries = 30) {
  return new Promise((resolve) => {
    const http = require("http");
    let attempts = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${PD_PORT}/health`, (res) => {
        if (res.statusCode === 200) resolve();
        else retry();
      });
      req.on("error", retry);
      req.setTimeout(500, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      attempts++;
      if (attempts >= retries) resolve(); // don't block forever
      else setTimeout(check, 1000);
    };
    check();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 600,
    backgroundColor: "#0a0a0f",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    title: "RTL Copilot",
    icon: path.join(__dirname, "assets", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: !IS_DEV,
    },
  });

  if (IS_DEV) {
    mainWindow.loadURL(`http://localhost:${FRONTEND_PORT}`);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  mainWindow.on("closed", () => { mainWindow = null; });
}

ipcMain.handle("get-app-version", () => app.getVersion());
ipcMain.handle("get-backend-port", () => BACKEND_PORT);
ipcMain.handle("is-desktop", () => true);
ipcMain.handle("open-external", (_, url) => shell.openExternal(url));


ipcMain.handle("pd-check-docker", () => {
  return checkDockerStatus();
});


ipcMain.handle("pd-start", async (event) => {
  try {
    const { installed, running } = checkDockerStatus();
    if (!installed) return { ok: false, error: "Docker not installed" };
    if (!running)   return { ok: false, error: "Docker daemon not running" };


    if (!imageExistsLocally()) {
      event.sender.send("pd-pull-progress", "[INFO] Pulling rtlcopilot/pd-tools image (first time only, ~2GB)...\n");
      await pullImage((line) => event.sender.send("pd-pull-progress", line));
      event.sender.send("pd-pull-progress", "[INFO] Pull complete.\n");
    }

    event.sender.send("pd-pull-progress", "[INFO] Starting PD container...\n");
    await startPDContainer();
    await waitForPDContainer();
    event.sender.send("pd-pull-progress", "[INFO] PD container ready on port 7070.\n");

    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});


ipcMain.handle("pd-stop", () => {
  stopPDContainer();
  return { ok: true };
});

app.whenReady().then(async () => {
  try {
    await ensurePortAvailable({ port: BACKEND_PORT });
    const child = startBackend();
    await waitForHealth({
      url: `http://127.0.0.1:${BACKEND_PORT}/health`,
      child,
      attempts: 40,
      intervalMs: 250,
    });
    console.log("Backend ready");
    createWindow();
    if (process.env.RTLCOPILOT_SMOKE_TEST === "1") {
      mainWindow.webContents.once("did-finish-load", () => setTimeout(async () => {
        try {
          const rendered = await mainWindow.webContents.executeJavaScript(`
            Boolean(
              document.querySelector("#root > *") &&
              document.body.innerText.trim().length > 0
            )
          `);
          if (!rendered) throw new Error("Renderer loaded without application content.");
        } catch (error) {
          process.exitCode = 1;
          console.error(`[smoke] ${error.message}`);
        } finally {
          app.quit();
        }
      }, 500));
    }
  } catch (error) {
    const logTail = backendLogTail.toString();
    const message = `${error.message}\n\n${logTail ? `Backend log:\n${logTail}\n\n` : ""}Run npm run doctor for recovery steps.`;
    console.error(message);
    dialog.showErrorBox("RTLCopilot could not start", message);
    await stopBackend();
    app.quit();
    return;
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", (event) => {
  if (shutdownInProgress || (!backendProcess && !pdContainerRunning)) return;
  event.preventDefault();
  shutdownInProgress = true;
  Promise.resolve()
    .then(stopBackend)
    .then(stopPDContainer)
    .finally(() => app.exit(process.exitCode || 0));
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => app.quit());
}
