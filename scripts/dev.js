#!/usr/bin/env node

const http = require("node:http");
const path = require("node:path");
const {
  desktopSpecs,
  installShutdownHandlers,
  spawnSpec,
} = require("./lib/dev-runner");

function viteReady() {
  return new Promise((resolve, reject) => {
    const request = http.get("http://127.0.0.1:5173", (response) => {
      response.resume();
      response.statusCode && response.statusCode < 500 ? resolve() : reject(new Error(`Vite returned ${response.statusCode}`));
    });
    request.once("error", reject);
    request.setTimeout(500, () => request.destroy(new Error("Vite readiness timed out")));
  });
}

async function waitForVite(attempts = 40) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await viteReady();
      return;
    } catch (_error) {
      if (attempt === attempts) throw new Error("Vite did not become ready. Run npm run doctor.");
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
}

async function main() {
  const root = path.resolve(__dirname, "..");
  const [vite, electron] = desktopSpecs(root);
  const children = [spawnSpec(vite)];
  const shutdown = installShutdownHandlers(children);
  children[0].once("error", (error) => {
    console.error(`[vite] failed to start: ${error.message}`);
    shutdown(1);
  });
  try {
    await waitForVite();
    const electronChild = spawnSpec(electron);
    children.push(electronChild);
    electronChild.once("error", (error) => {
      console.error(`[electron] failed to start: ${error.message}`);
      shutdown(1);
    });
    electronChild.once("exit", (code) => shutdown(code || 0));
  } catch (error) {
    console.error(error.message);
    await shutdown(1);
  }
}

main();
