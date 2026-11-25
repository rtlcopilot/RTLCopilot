const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const { createPDHandlers, PDService } = require("./pd-runtime");
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
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");

let mainWindow = null;
let backendProcess = null;
let backendLogTail = new LogTail();
let shutdownInProgress = false;
const pdService = new PDService({
  projectRoot: IS_DEV ? PROJECT_ROOT : process.resourcesPath,
});
const pdHandlers = createPDHandlers({ service: pdService });

function startBackend() {
  const projectRoot = PROJECT_ROOT;
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


ipcMain.handle("pd-check-docker", pdHandlers.check);
ipcMain.handle("pd-start", pdHandlers.start);
ipcMain.handle("pd-stop", pdHandlers.stop);

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
  if (shutdownInProgress || (!backendProcess && !pdService.isActive())) return;
  event.preventDefault();
  shutdownInProgress = true;
  Promise.resolve()
    .then(stopBackend)
    .then(() => pdService.stop())
    .catch((error) => {
      process.exitCode = 1;
      console.error(`[shutdown] ${error.message}`);
    })
    .finally(() => app.exit(process.exitCode || 0));
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => app.quit());
}
