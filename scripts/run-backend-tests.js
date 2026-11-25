#!/usr/bin/env node

const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { venvPython } = require("./lib/platform");

const root = path.resolve(__dirname, "..");
const result = spawnSync(venvPython(root), ["-m", "pytest", "backend/tests", "pdtools/tests", "-q"], {
  cwd: root,
  env: { ...process.env },
  shell: false,
  stdio: "inherit",
  windowsHide: true,
});

if (result.error && result.status == null) {
  console.error(`Could not run backend tests: ${result.error.message}`);
  process.exitCode = 1;
} else {
  process.exitCode = result.status || 0;
}
