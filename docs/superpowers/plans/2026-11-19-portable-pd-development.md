# Portable PD Development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make Electron-managed and browser-managed physical-design development work safely across Windows, macOS, and Linux.

**Architecture:** Extract Docker path/argument/ownership logic into a small CommonJS PD runtime module consumed by Electron. Add narrowly scoped local CORS to the PD FastAPI service, keep manual Compose as the browser workflow, and retain Electron ownership of only its labeled container.

**Tech Stack:** Node.js CommonJS and `node:test`, Electron, Docker CLI/Compose, FastAPI/Starlette, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-portable-pd-development-design.md`

## Global Constraints

- Docker remains optional for base application startup.
- Never stop or remove a container whose exact ID and unique session owner label do not both match.
- Spawn Docker without a shell.
- Bind development PD port 7070 to loopback.
- CORS allows explicit local Vite origins, never `*`.
- Preserve existing untracked `docs/REPOSITORY_ARCHITECTURE.md` and `output/`.

## Review Focus

- Windows drive-letter and space-containing mount paths must remain single Docker arguments.
- A manual Compose container occupying port 7070 must produce an error, not be killed.
- An unrelated container named `rtlcopilot-pd` must never be removed or stopped.
- Stop during pull/readiness and repeated start/stop requests must not orphan or cross-stop containers.
- A health endpoint returning 200 with non-ready or invalid JSON must not count as ready.
- Browser preflight must allow localhost/127.0.0.1 Vite and reject unrelated origins.

---

### Task 1: Testable Electron PD runtime

**Files:**
- Create: `frontend/electron/pd-runtime.js`
- Create: `scripts/test/pd-runtime.test.js`
- Modify: `frontend/electron/runtime.js`
- Modify: `scripts/test/runtime.test.js`
- Modify: `package.json`

**Interfaces:**
- Produces `resolvePDPaths(projectRoot)`, `buildPDRunArgs(options)`, `inspectPDContainer(options)`, and `PDService` with injected process/health/port dependencies.
- Extends `waitForHealth` and `ensurePortAvailable` with a service label while preserving backend defaults.

- [x] Write failing tests for portable paths, shell-free status/image/pull/run/inspect/remove/stop operations, exact-ID ownership, failed-closed Docker errors, spawn/run failures, lifecycle cancellation/repetition, cleanup failures, port labels, and PD health labels.
- [x] Run the focused Node tests and confirm failures are caused by missing behavior.
- [x] Implement the minimal PD runtime and generic service-label options.
- [x] Run the focused Node tests and confirm they pass.

### Task 2: Integrate safe PD lifecycle into Electron

**Files:**
- Modify: `frontend/electron/main.js`
- Test: `scripts/test/pd-runtime.test.js`

**Interfaces:**
- Consumes Task 1 PD runtime functions and existing `waitForHealth`/`ensurePortAvailable`.
- Preserves preload IPC names `pd-check-docker`, `pd-start`, and `pd-stop`.

- [x] Add failing injected-service tests that cover Electron's start/stop contract, strict readiness, cancellation, and owned cleanup.
- [x] Replace hard-coded paths and unconditional removal with the tested runtime helpers.
- [x] Ensure readiness failure cleans up only an owned container and returns an actionable error.
- [x] Run all Node setup/runtime tests.

### Task 3: Enable browser PD requests safely

**Files:**
- Create: `pdtools/tests/test_cors.py`
- Modify: `pdtools/api.py`
- Create: `pdtools/__init__.py`
- Modify: `scripts/run-backend-tests.js`
- Modify: `pdtools/docker-compose.yml`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces local-origin CORS behavior and loopback-only Compose port publishing.
- Adds PD tests to the existing root backend-test command.

- [x] Write failing ASGI tests for allowed Vite preflight, actual GET/POST CORS responses, rejected unrelated origins, and rejected wildcard configuration.
- [x] Make PD imports deterministic and declare Jinja2 explicitly for clean-clone tests.
- [x] Add explicit localhost/127.0.0.1 Vite CORS origins plus non-wildcard `PD_ALLOWED_ORIGINS` values.
- [x] Bind Compose to `127.0.0.1:7070`, pass through `PD_ALLOWED_ORIGINS`, mount all four live files, and remove the obsolete Compose version field.
- [x] Run backend/PD tests and Compose config validation.

### Task 4: Align documentation and verify end to end

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `frontend/src/PDPage.jsx`

**Interfaces:**
- Documents Electron-managed desktop PD and Compose-managed browser PD without overlapping ownership.

- [x] Replace the temporary blocker text with two supported workflows, exact output locations, origin-restart guidance, and portable in-app wording.
- [x] Run `git diff --check`, `npm test`, `npm run doctor`, Compose config validation, and the Linux Electron smoke test.
- [x] Review the whole diff for unowned-container safety and platform portability.
