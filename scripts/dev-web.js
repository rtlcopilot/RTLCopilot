#!/usr/bin/env node

const path = require("node:path");
const {
  installShutdownHandlers,
  spawnSpec,
  webSpecs,
} = require("./lib/dev-runner");

const root = path.resolve(__dirname, "..");
const children = webSpecs(root).map((spec) => spawnSpec(spec));
const shutdown = installShutdownHandlers(children);

for (const child of children) {
  child.once("error", (error) => {
    console.error(`[${child.name}] failed to start: ${error.message}`);
    shutdown(1);
  });
  child.once("exit", (code, signal) => {
    if (code !== 0) {
      console.error(`[${child.name}] exited (code ${code}, signal ${signal || "none"}).`);
      shutdown(code || 1);
    }
  });
}
