const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  // App info
  getVersion:     () => ipcRenderer.invoke("get-app-version"),
  getBackendPort: () => ipcRenderer.invoke("get-backend-port"),
  isDesktop:      () => ipcRenderer.invoke("is-desktop"),

  // Open external links in browser
  openExternal:   (url) => ipcRenderer.invoke("open-external", url),

  // ── PD Docker management ──────────────────────────────────────────────────
  // Check if Docker is installed and running
  // Returns { installed: bool, running: bool }
  pdCheckDocker:  () => ipcRenderer.invoke("pd-check-docker"),

  // Start the PD container (pull if needed)
  // Returns { ok: bool, error?: string }
  pdStart:        () => ipcRenderer.invoke("pd-start"),

  // Stop the PD container
  pdStop:         () => ipcRenderer.invoke("pd-stop"),

  // Listen for pull/start progress lines streamed from main process
  onPdPullProgress: (callback) => {
    ipcRenderer.on("pd-pull-progress", (_, line) => callback(line));
  },

  // Remove pull progress listener
  offPdPullProgress: () => {
    ipcRenderer.removeAllListeners("pd-pull-progress");
  },
});