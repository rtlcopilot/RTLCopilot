const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

class LogTail {
  constructor(maxLines = 40) {
    this.maxLines = maxLines;
    this.lines = [];
    this.pending = "";
  }

  append(chunk) {
    const parts = `${this.pending}${String(chunk)}`.split(/\r?\n/);
    this.pending = parts.pop();
    this.lines.push(...parts.filter((line) => line.length > 0));
    this.lines = this.lines.slice(-this.maxLines);
  }

  toString() {
    return [...this.lines, ...(this.pending ? [this.pending] : [])]
      .slice(-this.maxLines)
      .join("\n");
  }
}

function defaultProbe(command, args = []) {
  const result = spawnSync(command, [...args, "--version"], {
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    timeout: 5000,
  });
  return result.status === 0;
}

function defaultFallback(platform = process.platform) {
  const candidates = platform === "win32"
    ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }, { command: "python3", args: [] }]
    : [{ command: "python3", args: [] }, { command: "python", args: [] }];
  for (const candidate of candidates) {
    if (defaultProbe(candidate.command, candidate.args)) return candidate;
  }
  throw new Error("Python 3.10+ was not found. Run npm run doctor.");
}

function selectPython({
  projectRoot,
  platform = process.platform,
  env = process.env,
  probe = defaultProbe,
  fallback = () => defaultFallback(platform),
} = {}) {
  const override = env.RTLCOPILOT_PYTHON;
  if (override) {
    if (!probe(override, [])) throw new Error(`RTLCOPILOT_PYTHON is not usable: ${override}`);
  }
  const projectPython = platform === "win32"
    ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
    : path.join(projectRoot, ".venv", "bin", "python");
  if (fs.existsSync(projectPython) && probe(projectPython, [])) {
    return { command: projectPython, args: [] };
  }
  if (override) return { command: override, args: [] };
  return fallback();
}

function getJson(url, timeoutMs = 750) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => {
        try {
          resolve({ statusCode: response.statusCode, body: JSON.parse(body) });
        } catch (error) {
          reject(new Error(`Invalid JSON from ${url}: ${error.message}`));
        }
      });
    });
    request.once("error", reject);
    request.setTimeout(timeoutMs, () => request.destroy(new Error(`Timed out requesting ${url}`)));
  });
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForHealth({
  url,
  child = null,
  attempts = 30,
  intervalMs = 500,
  requestJson = getJson,
  serviceName = "Backend",
  signal = null,
} = {}) {
  let earlyExit = null;
  const onExit = (code, signal) => {
    earlyExit = new Error(`Backend exited before readiness (code ${code}, signal ${signal || "none"}).`);
  };
  if (child) child.once("exit", onExit);
  try {
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      if (signal && signal.aborted) throw Object.assign(new Error(`${serviceName} startup cancelled.`), { name: "AbortError" });
      if (earlyExit || (child && child.exitCode != null)) {
        throw earlyExit || new Error(`${serviceName} exited before readiness (code ${child.exitCode}).`);
      }
      let response = null;
      try {
        response = await requestJson(url);
      } catch (_error) {
        // A refused connection or incomplete response is expected while starting.
      }
      if (earlyExit || (child && child.exitCode != null)) {
        throw earlyExit || new Error(`Backend exited before readiness (code ${child.exitCode}).`);
      }
      if (response && response.statusCode === 200 && response.body && response.body.status === "ok") return;
      if (attempt < attempts) await delay(intervalMs);
    }
    throw new Error(`${serviceName} did not become ready after ${attempts} attempts.`);
  } finally {
    if (child) child.removeListener("exit", onExit);
  }
}

function ensurePortAvailable({
  port,
  host = "127.0.0.1",
  createServer = () => net.createServer(),
  serviceName = "Backend",
} = {}) {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.unref();
    server.once("error", (error) => {
      const detail = error && error.code === "EADDRINUSE" ? "already in use" : (error.message || "unavailable");
      reject(new Error(`${serviceName} port ${port} is ${detail}. Run npm run doctor.`));
    });
    server.listen({ host, port, exclusive: true }, () => {
      server.close(resolve);
    });
  });
}

function stopChild(child, { timeoutMs = 5000 } = {}) {
  if (!child || child.exitCode != null) return Promise.resolve();
  return new Promise((resolve) => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolve();
    };
    child.once("exit", finish);
    const timer = setTimeout(() => {
      if (child.exitCode == null) child.kill("SIGKILL");
      finish();
    }, timeoutMs);
    child.kill("SIGTERM");
  });
}

module.exports = {
  LogTail,
  ensurePortAvailable,
  getJson,
  selectPython,
  stopChild,
  waitForHealth,
};
