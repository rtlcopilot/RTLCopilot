#!/usr/bin/env node

const { setup } = require("./lib/setup");

try {
  setup();
} catch (error) {
  console.error(`\nSetup failed:\n${error.message}`);
  console.error("Fix the reported command and rerun npm run setup; reruns are safe.");
  process.exitCode = 1;
}
