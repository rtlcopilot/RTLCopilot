# Developer Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fresh clone start as an offline Electron development app with `npm run setup` and `npm run dev` on Windows, macOS, and Linux.

**Architecture:** Dependency-free CommonJS modules under `scripts/` own platform discovery, setup, diagnostics, and child orchestration. Electron consumes a focused runtime helper for Python selection, health readiness, log capture, and shutdown; FastAPI exposes a dependency-free readiness route.

**Tech Stack:** Node.js 18+, `node:test`, Python 3.10+, FastAPI, pytest, Vite, Electron, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-18-developer-setup-design.md`

## Global Constraints

- Existing `.env` files must never be edited or replaced.
- Base development requires only Node.js 18+ and Python 3.10+.
- Icarus, Docker, Supabase, and LLM credentials are optional.
- Child processes are spawned without shell-specific syntax and must be terminated by their owner.
- Preserve `docs/REPOSITORY_ARCHITECTURE.md` and `output/` unchanged.

## Review Focus

- Paths containing spaces must remain valid on every platform.
- A configured Python override that is invalid must fail explicitly, not silently fall back.
- Existing user configuration must survive successful and failed setup attempts byte-for-byte.
- A port occupied during doctor must be reported as required action without killing its owner.
- Early backend exit and malformed health responses must prevent Electron from opening a broken window.

---

### Task 1: Shared Setup Utilities and Root Command Surface

**Files:**
- Create: `package.json`
- Create: `scripts/lib/platform.js`
- Create: `scripts/test/platform.test.js`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `findPython(options)`, `venvPython(root, platform)`, `versionAtLeast(actual, minimum)`, `run(command, args, options)`.

- [ ] Write failing `node:test` cases for override precedence, invalid override failure, Windows/macOS/Linux candidates, paths with spaces, and version comparison.
- [ ] Run `node --test scripts/test/platform.test.js` and confirm failure because the module is absent.
- [ ] Add the dependency-free root package scripts and minimal shared implementation.
- [ ] Run `node --test scripts/test/platform.test.js` and confirm all cases pass.

### Task 2: Idempotent Bootstrap

**Files:**
- Create: `backend/requirements-dev.txt`
- Create: `scripts/setup.js`
- Create: `scripts/lib/setup.js`
- Create: `scripts/test/setup.test.js`

**Interfaces:**
- Consumes: Task 1 process and interpreter helpers.
- Produces: `ensureEnvFile(path, content)`, `setup(options)` and `npm run setup`.

- [ ] Write failing tests for fresh env creation, byte-for-byte preservation, reruns, and actionable failed-command output.
- [ ] Run `node --test scripts/test/setup.test.js` and confirm expected failures.
- [ ] Implement setup: validate versions, create `.venv`, install development requirements, run frontend `npm ci`, and create only missing offline env files.
- [ ] Run `node --test scripts/test/setup.test.js` and confirm all cases pass.

### Task 3: Read-only Capability Doctor

**Files:**
- Create: `scripts/doctor.js`
- Create: `scripts/lib/doctor.js`
- Create: `scripts/test/doctor.test.js`

**Interfaces:**
- Consumes: Task 1 version/interpreter utilities.
- Produces: `collectDiagnostics(options)`, `formatDiagnostics(report)`, and `npm run doctor`.

- [ ] Write failing tests for required failures, optional missing capabilities, mismatched offline env, occupied ports, and status grouping.
- [ ] Run `node --test scripts/test/doctor.test.js` and confirm expected failures.
- [ ] Implement read-only checks for versions, `.venv` imports, frontend tools, offline configuration, ports, Icarus, Docker, and LLM guidance.
- [ ] Run `node --test scripts/test/doctor.test.js` and confirm all cases pass.

### Task 4: Backend Health Contract

**Files:**
- Modify: `backend/api.py`
- Create: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `GET /health -> 200 {"status":"ok"}` with no external dependency access.

- [ ] Write a failing FastAPI test that disables external dependency entry points and calls `/health`.
- [ ] Run `python -m pytest backend/tests/test_health.py -q` and confirm 404.
- [ ] Add the minimal route.
- [ ] Run the health test and backend suite.

### Task 5: Reliable Electron and Web Runners

**Files:**
- Create: `frontend/electron/runtime.js`
- Modify: `frontend/electron/main.js`
- Create: `scripts/dev.js`
- Create: `scripts/dev-web.js`
- Create: `scripts/test/runtime.test.js`
- Create: `scripts/test/dev-runner.test.js`

**Interfaces:**
- Consumes: Task 1 Python selection and Task 4 health endpoint.
- Produces: health polling that rejects on timeout/early exit, bounded log tails, graceful child shutdown, `npm run dev`, and `npm run dev:web`.

- [ ] Write failing tests for genuine readiness, malformed responses, timeout, early exit, interpreter preference, and child shutdown.
- [ ] Run the focused Node tests and confirm expected failures.
- [ ] Extract the runtime helper, remove Electron backend reload, gate window creation on readiness, and add actionable errors with `npm run doctor`.
- [ ] Implement browser and desktop runners with forwarded signals and test-only smoke hooks.
- [ ] Run the focused Node tests and frontend build.

### Task 6: Canonical Documentation and CI

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Create: `.github/workflows/setup.yml`

**Interfaces:**
- Consumes: Tasks 1-5 public commands.
- Produces: one canonical quick start and cross-platform setup verification.

- [ ] Replace duplicated quick starts with the root workflow, capability table, environment override, non-overwrite guarantee, and manual fallback.
- [ ] Add a Windows/macOS/Linux workflow for Node tests, backend tests, doctor, and frontend build; add Linux Electron smoke under a virtual display.
- [ ] Run `npm test`, `npm run doctor`, and `npm run build --prefix frontend`.
