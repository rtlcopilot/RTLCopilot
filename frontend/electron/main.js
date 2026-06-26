const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

// ─── Config ───────────────────────────────────────────────────────────────────
const IS_DEV = !app.isPackaged || process.argv.includes("--dev");
const BACKEND_PORT = 8080;
const FRONTEND_PORT = 5173;
const PD_PORT = 7070;
const PD_IMAGE = "rtlcopilot/pd-tools";
const PD_CONTAINER_NAME = "rtlcopilot-pd";
const PD_WORK_DIR = path.join("D:\\RTLCopilot", "pd_work");

let mainWindow = null;
let backendProcess = null;
let pdContainerRunning = false;

// ─── RTL Backend launcher ─────────────────────────────────────────────────────
function startBackend() {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const backendDir = IS_DEV
    ? path.join(projectRoot, "backend")
    : path.join(process.resourcesPath, "backend");

  console.log("[backend] projectRoot:", projectRoot);
  console.log("[backend] backendDir:", backendDir);

  const pythonCandidates = IS_DEV
    ? ["python", "python3"]
    : [
        path.join(process.resourcesPath, "python", "python.exe"),
        "python",
        "python3",
      ];

  let pythonExe = null;
  for (const candidate of pythonCandidates) {
    try {
      const result = spawnSync(candidate, ["--version"], {
        timeout: 3000,
        windowsHide: true,
      });
      if (result.status === 0 || (result.stdout && result.stdout.toString().includes("Python"))) {
        pythonExe = candidate;
        break;
      }
    } catch {
      // try next
    }
  }

  if (!pythonExe) {
    console.error("Python not found — backend will not start");
    return;
  }

  console.log(`Starting backend with ${pythonExe} in ${backendDir}`);

  backendProcess = spawn(
    pythonExe,
    ["-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT), "--reload"],
    {
      cwd: backendDir,
      env: { ...process.env, PYTHONPATH: backendDir, DESKTOP_MODE: "1", PYTHONUNBUFFERED: "1", PYTHONUTF8: "1" },
    }
  );

  backendProcess.stdout.on("data", (d) => console.log("[backend]", d.toString().trim()));
  backendProcess.stderr.on("data", (d) => console.log("[backend err]", d.toString().trim()));
  backendProcess.on("exit", (code) => {
    console.log(`[backend] exited with code ${code}`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill("SIGTERM");
    backendProcess = null;
  }
}

// ─── Docker / PD helpers ──────────────────────────────────────────────────────

// Returns { installed: bool, running: bool }
function checkDockerStatus() {
  // Check if docker binary exists — shell:true ensures Windows PATH is resolved correctly
  const which = spawnSync(
    process.platform === "win32" ? "where" : "which",
    ["docker"],
    { timeout: 3000, windowsHide: true, shell: true }
  );
  if (which.status !== 0) {
    return { installed: false, running: false };
  }

  // docker version is more reliable than docker info on Windows named pipe
  // shell:true ensures Docker Desktop PATH additions are picked up
  const version = spawnSync("docker", ["version", "--format", "{{.Server.Version}}"], {
    timeout: 8000, windowsHide: true, shell: true,
  });
  return { installed: true, running: version.status === 0 };
}

// Check if image exists locally
function imageExistsLocally() {
  const result = spawnSync("docker", ["image", "inspect", PD_IMAGE], {
    timeout: 5000, windowsHide: true, shell: true,
  });
  return result.status === 0;
}

// Pull image — streams progress lines back via callback
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

// Start the PD container
function startPDContainer() {
  return new Promise((resolve, reject) => {
    // Stop any existing container with the same name first
    spawnSync("docker", ["rm", "-f", PD_CONTAINER_NAME], {
      timeout: 5000, windowsHide: true, shell: true,
    });

    // Ensure work directory exists
    const fs = require("fs");
    if (!fs.existsSync(PD_WORK_DIR)) fs.mkdirSync(PD_WORK_DIR, { recursive: true });

    const proc = spawn("docker", [
      "run", "--rm", "-d",
      "--name", PD_CONTAINER_NAME,
      "-p", `${PD_PORT}:7070`,
      "-v", `${PD_WORK_DIR}:/work`,
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

// Stop the PD container
function stopPDContainer() {
  if (!pdContainerRunning) return;
  spawnSync("docker", ["stop", PD_CONTAINER_NAME], {
    timeout: 10000, windowsHide: true, shell: true,
  });
  pdContainerRunning = false;
  console.log("[pd] container stopped");
}

// Wait for PD container /health to respond
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

// ─── Window creator ───────────────────────────────────────────────────────────
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

// ─── Wait for RTL backend ─────────────────────────────────────────────────────
function waitForBackend(retries = 20) {
  return new Promise((resolve) => {
    const http = require("http");
    let attempts = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/health`, (res) => {
        if (res.statusCode === 200) { console.log("Backend ready"); resolve(); }
        else retry();
      });
      req.on("error", retry);
      req.setTimeout(500, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      attempts++;
      if (attempts >= retries) { console.warn("Backend did not start in time"); resolve(); }
      else setTimeout(check, 500);
    };
    check();
  });
}

// ─── IPC handlers ─────────────────────────────────────────────────────────────
ipcMain.handle("get-app-version", () => app.getVersion());
ipcMain.handle("get-backend-port", () => BACKEND_PORT);
ipcMain.handle("is-desktop", () => true);
ipcMain.handle("open-external", (_, url) => shell.openExternal(url));

// Check if Docker is installed and daemon is running
ipcMain.handle("pd-check-docker", () => {
  return checkDockerStatus();
});

// Start PD container — pull if needed, then run
// Streams pull progress back to renderer via event
ipcMain.handle("pd-start", async (event) => {
  try {
    const { installed, running } = checkDockerStatus();
    if (!installed) return { ok: false, error: "Docker not installed" };
    if (!running)   return { ok: false, error: "Docker daemon not running" };

    // Pull if image not local
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

// Stop PD container
ipcMain.handle("pd-stop", () => {
  stopPDContainer();
  return { ok: true };
});

// ─── App lifecycle ────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  startBackend();
  await new Promise((r) => setTimeout(r, 1500));
  await waitForBackend();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  stopBackend();
  stopPDContainer();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopBackend();
  stopPDContainer();
});