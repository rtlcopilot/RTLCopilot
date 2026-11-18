const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { collectDiagnostics, formatDiagnostics } = require("../lib/doctor");

function readyRepository() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rtlcopilot-doctor-"));
  const directories = [
    path.join(root, ".venv", "bin"),
    path.join(root, "backend"),
    path.join(root, "frontend", "node_modules", ".bin"),
    path.join(root, "frontend", "node_modules", "electron"),
  ];
  directories.forEach((directory) => fs.mkdirSync(directory, { recursive: true }));
  fs.writeFileSync(path.join(root, ".venv", "bin", "python"), "");
  fs.writeFileSync(path.join(root, "frontend", "node_modules", ".bin", "vite"), "");
  fs.writeFileSync(path.join(root, "backend", ".env"), "OFFLINE_MODE=true\n");
  fs.writeFileSync(path.join(root, "frontend", ".env"), "VITE_OFFLINE_MODE=true\n");
  return root;
}

function options(root, overrides = {}) {
  return {
    root,
    nodeVersion: "20.12.0",
    platform: "linux",
    findPythonImpl: () => ({ command: "python3", args: [], version: "3.12.1" }),
    checkBackendImports: () => true,
    checkCommand: () => false,
    isPortAvailable: async () => true,
    ...overrides,
  };
}

test("a ready base environment stays successful when optional tools are missing", async () => {
  const report = await collectDiagnostics(options(readyRepository()));

  assert.equal(report.ok, true);
  assert.equal(report.requiredAction.length, 0);
  assert.match(report.ready.join("\n"), /Node\.js 20\.12\.0/);
  assert.match(report.optionalUnavailable.join("\n"), /Icarus Verilog/);
  assert.match(report.optionalUnavailable.join("\n"), /Docker/);
  assert.match(report.optionalUnavailable.join("\n"), /LLM.*in the application/i);
});

test("missing base dependencies are required actions", async () => {
  const root = readyRepository();
  fs.rmSync(path.join(root, ".venv", "bin", "python"));
  const report = await collectDiagnostics(options(root, { nodeVersion: "17.9.0" }));

  assert.equal(report.ok, false);
  assert.match(report.requiredAction.join("\n"), /Node\.js 18\+/);
  assert.match(report.requiredAction.join("\n"), /npm run setup/);
});

test("backend and frontend offline modes must agree", async () => {
  const root = readyRepository();
  fs.writeFileSync(path.join(root, "frontend", ".env"), "VITE_OFFLINE_MODE=false\n");

  const report = await collectDiagnostics(options(root));

  assert.equal(report.ok, false);
  assert.match(report.requiredAction.join("\n"), /offline mode.*mismatch/i);
});

test("quoted offline values follow dotenv semantics", async () => {
  const root = readyRepository();
  fs.writeFileSync(path.join(root, "backend", ".env"), 'OFFLINE_MODE="true"\n');
  fs.writeFileSync(path.join(root, "frontend", ".env"), "VITE_OFFLINE_MODE='true'\n");

  const report = await collectDiagnostics(options(root));

  assert.equal(report.ok, true);
  assert.match(report.ready.join("\n"), /offline mode agree/i);
});

test("a fully configured online environment remains usable", async () => {
  const root = readyRepository();
  fs.writeFileSync(path.join(root, "backend", ".env"), [
    "OFFLINE_MODE=false",
    "SUPABASE_URL=https://example.supabase.co",
    "SUPABASE_SERVICE_KEY=service-key",
  ].join("\n"));
  fs.writeFileSync(path.join(root, "frontend", ".env"), [
    "VITE_OFFLINE_MODE=false",
    "VITE_SUPABASE_URL=https://example.supabase.co",
    "VITE_SUPABASE_ANON_KEY=anon-key",
  ].join("\n"));

  const report = await collectDiagnostics(options(root));

  assert.equal(report.ok, true);
  assert.match(report.ready.join("\n"), /online Supabase configuration/i);
});

test("occupied development ports are reported without changing their owner", async () => {
  const checked = [];
  const report = await collectDiagnostics(options(readyRepository(), {
    isPortAvailable: async (port) => {
      checked.push(port);
      return port !== 8080;
    },
  }));

  assert.equal(report.ok, false);
  assert.deepEqual(checked, [5173, 8080]);
  assert.match(report.requiredAction.join("\n"), /port 8080.*already in use/i);
});

test("formatDiagnostics groups ready, required, and optional results", () => {
  const output = formatDiagnostics({
    ok: false,
    ready: ["Node ready"],
    requiredAction: ["Install Python"],
    optionalUnavailable: ["Docker unavailable"],
  });

  assert.match(output, /READY[\s\S]*Node ready/);
  assert.match(output, /REQUIRED ACTION[\s\S]*Install Python/);
  assert.match(output, /OPTIONAL CAPABILITY UNAVAILABLE[\s\S]*Docker unavailable/);
});
