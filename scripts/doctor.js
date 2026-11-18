#!/usr/bin/env node

const { collectDiagnostics, formatDiagnostics } = require("./lib/doctor");

collectDiagnostics()
  .then((report) => {
    console.log(formatDiagnostics(report));
    if (!report.ok) process.exitCode = 1;
  })
  .catch((error) => {
    console.error(`Doctor failed: ${error.message}`);
    process.exitCode = 1;
  });
