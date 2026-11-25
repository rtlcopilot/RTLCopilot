const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { spawn, spawnSync } = require("node:child_process");

const { ensurePortAvailable, waitForHealth } = require("./runtime");

const PD_PORT = 7070;
const PD_IMAGE = "rtlcopilot/pd-tools";
const PD_CONTAINER_NAME = "rtlcopilot-pd";
const OWNER_LABEL = "com.rtlcopilot.owner";

function abortError(message = "PD service startup cancelled.") {
  return Object.assign(new Error(message), { name: "AbortError" });
}

function resolvePDPaths(projectRoot, { platform = process.platform } = {}) {
  const pathImpl = platform === "win32" ? path.win32 : path.posix;
  const pdDir = pathImpl.join(projectRoot, "pdtools");
  return {
    pdDir,
    workDir: pathImpl.join(pdDir, "work"),
    api: pathImpl.join(pdDir, "api.py"),
    verification: pathImpl.join(pdDir, "pd_verification.py"),
    policy: pathImpl.join(pdDir, "verification_policy.json"),
    preview: pathImpl.join(pdDir, "export_preview.py"),
  };
}

function buildPDRunArgs({
  projectRoot,
  platform = process.platform,
  ownerId,
  port = PD_PORT,
  image = PD_IMAGE,
} = {}) {
  if (!ownerId) throw new Error("PD container ownerId is required.");
  const paths = resolvePDPaths(projectRoot, { platform });
  return [
    "run", "--rm", "-d",
    "--name", PD_CONTAINER_NAME,
    "--label", `${OWNER_LABEL}=${ownerId}`,
    "-p", `127.0.0.1:${port}:7070`,
    "-v", `${paths.workDir}:/work`,
    "-v", `${paths.api}:/app/api.py`,
    "-v", `${paths.verification}:/app/pd_verification.py`,
    "-v", `${paths.policy}:/app/verification_policy.json`,
    "-v", `${paths.preview}:/app/export_preview.py`,
    image,
  ];
}

function syncOptions(timeout = 8000) {
  return { encoding: "utf8", shell: false, windowsHide: true, timeout };
}

function resultDetail(result) {
  return String((result && (result.stderr || result.stdout)) || "unknown Docker error").trim();
}

function inspectPDContainer({ reference, spawnSyncImpl = spawnSync } = {}) {
  const result = spawnSyncImpl("docker", ["container", "inspect", reference], syncOptions());
  if (result.error) throw new Error(`Docker inspect could not start: ${result.error.message}`);
  if (result.status !== 0) {
    const detail = resultDetail(result);
    if (/no such (container|object)/i.test(detail)) return null;
    throw new Error(`Docker inspect failed: ${detail}`);
  }
  try {
    const value = JSON.parse(result.stdout);
    const container = Array.isArray(value) ? value[0] : value;
    if (!container || !container.Id) throw new Error("missing container ID");
    return {
      id: container.Id,
      ownerId: container.Config && container.Config.Labels
        ? container.Config.Labels[OWNER_LABEL] || null
        : null,
    };
  } catch (error) {
    throw new Error(`Docker inspect returned invalid JSON: ${error.message}`);
  }
}

function runChild({ spawnImpl, args, signal = null, onData = null } = {}) {
  if (signal && signal.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    let settled = false;
    let stdout = "";
    let stderr = "";
    const child = spawnImpl("docker", args, { shell: false, windowsHide: true });
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      if (signal) signal.removeEventListener("abort", onAbort);
      if (error) reject(error);
      else resolve(value);
    };
    const onAbort = () => {
      if (child && typeof child.kill === "function") child.kill("SIGTERM");
      finish(abortError());
    };
    if (signal) signal.addEventListener("abort", onAbort, { once: true });
    child.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      stdout += text;
      if (onData) onData(text);
    });
    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      if (onData) onData(text);
    });
    child.once("error", (error) => finish(error));
    child.once("close", (code, exitSignal) => {
      if (code === 0) finish(null, { stdout, stderr });
      else finish(new Error(`docker ${args[0]} exited with code ${code} (signal ${exitSignal || "none"}): ${stderr || stdout}`));
    });
  });
}

class PDService {
  constructor({
    projectRoot,
    platform = process.platform,
    ownerId = `electron-${process.pid}-${randomUUID()}`,
    spawnImpl = spawn,
    spawnSyncImpl = spawnSync,
    mkdirSync = fs.mkdirSync,
    ensurePort = ensurePortAvailable,
    waitForReady = waitForHealth,
    image = PD_IMAGE,
    port = PD_PORT,
  } = {}) {
    this.projectRoot = projectRoot;
    this.platform = platform;
    this.ownerId = ownerId;
    this.spawnImpl = spawnImpl;
    this.spawnSyncImpl = spawnSyncImpl;
    this.mkdirSync = mkdirSync;
    this.ensurePort = ensurePort;
    this.waitForReady = waitForReady;
    this.image = image;
    this.port = port;
    this.containerId = null;
    this.startPromise = null;
    this.stopPromise = null;
    this.startController = null;
    this.desiredRunning = false;
    this.queuedStartPromise = null;
  }

  checkDockerStatus() {
    const result = this.spawnSyncImpl("docker", ["version", "--format", "{{.Server.Version}}"], syncOptions());
    if (result.error && result.error.code === "ENOENT") return { installed: false, running: false };
    if (result.error) return { installed: true, running: false };
    return { installed: true, running: result.status === 0 };
  }

  imageExistsLocally() {
    const result = this.spawnSyncImpl("docker", ["image", "inspect", this.image], syncOptions(5000));
    if (result.error) throw new Error(`Docker image inspection could not start: ${result.error.message}`);
    if (result.status === 0) return true;
    const detail = resultDetail(result);
    if (/no such image/i.test(detail) || !detail) return false;
    throw new Error(`Docker image inspection failed: ${detail}`);
  }

  inspect(reference) {
    return inspectPDContainer({ reference, spawnSyncImpl: this.spawnSyncImpl });
  }

  verifyOwned(reference) {
    const container = this.inspect(reference);
    if (!container) return null;
    if (container.ownerId !== this.ownerId) {
      throw new Error(`Refusing to modify container ${container.id}; it belongs to another session.`);
    }
    return container;
  }

  removeOwned(reference) {
    const container = this.verifyOwned(reference);
    if (!container) return;
    const result = this.spawnSyncImpl("docker", ["rm", "-f", container.id], syncOptions(10000));
    if (result.error || result.status !== 0) {
      throw new Error(`Docker cleanup failed: ${result.error ? result.error.message : resultDetail(result)}`);
    }
  }

  stopOwned(reference) {
    const container = this.verifyOwned(reference);
    if (!container) return;
    const result = this.spawnSyncImpl("docker", ["stop", container.id], syncOptions(10000));
    if (result.error || result.status !== 0) {
      throw new Error(`Docker stop failed: ${result.error ? result.error.message : resultDetail(result)}`);
    }
  }

  start(onData = null) {
    this.desiredRunning = true;
    if (this.stopPromise) {
      if (this.queuedStartPromise) return this.queuedStartPromise;
      const queued = this.stopPromise
        .then(() => {
          if (!this.desiredRunning) throw abortError();
          return this.start(onData);
        })
        .finally(() => {
          if (this.queuedStartPromise === queued) this.queuedStartPromise = null;
        });
      this.queuedStartPromise = queued;
      return queued;
    }
    if (this.containerId) return Promise.resolve(this.containerId);
    if (this.startPromise) return this.startPromise;
    const controller = new AbortController();
    this.startController = controller;
    const promise = this.startInternal({ signal: controller.signal, onData })
      .then((containerId) => {
        this.containerId = containerId;
        return containerId;
      })
      .finally(() => {
        if (this.startPromise === promise) this.startPromise = null;
        if (this.startController === controller) this.startController = null;
      });
    this.startPromise = promise;
    return promise;
  }

  async startInternal({ signal, onData }) {
    const status = this.checkDockerStatus();
    if (!status.installed) throw new Error("Docker is not installed.");
    if (!status.running) throw new Error("Docker daemon is not running.");

    if (!this.imageExistsLocally()) {
      await runChild({
        spawnImpl: this.spawnImpl,
        args: ["pull", this.image],
        signal,
        onData,
      });
    }
    if (signal.aborted) throw abortError();

    const existing = this.inspect(PD_CONTAINER_NAME);
    if (existing) {
      throw new Error(`Container ${PD_CONTAINER_NAME} already exists and may belong to another session. Stop it explicitly before retrying.`);
    }

    await this.ensurePort({ port: this.port, serviceName: "PD service" });
    const paths = resolvePDPaths(this.projectRoot, { platform: this.platform });
    this.mkdirSync(paths.workDir, { recursive: true });

    let containerId = null;
    try {
      const runResult = await runChild({
        spawnImpl: this.spawnImpl,
        args: buildPDRunArgs({
          projectRoot: this.projectRoot,
          platform: this.platform,
          ownerId: this.ownerId,
          port: this.port,
          image: this.image,
        }),
      });
      containerId = runResult.stdout.trim();
      if (!containerId) throw new Error("Docker run did not return a container ID.");
      if (signal.aborted) throw abortError();
      await this.waitForReady({
        url: `http://127.0.0.1:${this.port}/health`,
        attempts: 30,
        intervalMs: 1000,
        serviceName: "PD service",
        signal,
      });
      if (signal.aborted) throw abortError();
      return containerId;
    } catch (error) {
      if (containerId) {
        try {
          this.removeOwned(containerId);
        } catch (cleanupError) {
          this.containerId = containerId;
          throw new Error(`${error.message}; cleanup failed: ${cleanupError.message}`, { cause: error });
        }
      }
      throw error;
    }
  }

  stop() {
    this.desiredRunning = false;
    if (this.stopPromise) return this.stopPromise;
    if (this.startController) this.startController.abort();
    const activeStart = this.startPromise;
    const promise = (async () => {
      if (activeStart) {
        try {
          await activeStart;
        } catch (_error) {
          // Startup owns cleanup and its caller receives the original error.
        }
      }
      const containerId = this.containerId;
      if (containerId) {
        this.stopOwned(containerId);
        if (this.containerId === containerId) this.containerId = null;
      }
    })().finally(() => {
      if (this.stopPromise === promise) this.stopPromise = null;
    });
    this.stopPromise = promise;
    return promise;
  }

  isActive() {
    return Boolean(this.containerId || this.startPromise || this.stopPromise || this.queuedStartPromise);
  }
}

function createPDHandlers({ service } = {}) {
  const send = (event, line) => event.sender.send("pd-pull-progress", line);
  return {
    check: () => service.checkDockerStatus(),
    start: async (event) => {
      try {
        send(event, "[INFO] Starting PD container...\n");
        const containerId = await service.start((line) => send(event, line));
        send(event, "[INFO] PD container ready on port 7070.\n");
        return { ok: true, containerId };
      } catch (error) {
        return { ok: false, error: error.message };
      }
    },
    stop: async () => {
      try {
        await service.stop();
        return { ok: true };
      } catch (error) {
        return { ok: false, error: error.message };
      }
    },
  };
}

module.exports = {
  OWNER_LABEL,
  PD_CONTAINER_NAME,
  PD_IMAGE,
  PD_PORT,
  PDService,
  buildPDRunArgs,
  createPDHandlers,
  inspectPDContainer,
  resolvePDPaths,
};
