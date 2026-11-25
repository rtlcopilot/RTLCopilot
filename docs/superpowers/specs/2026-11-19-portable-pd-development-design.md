# Portable PD Development Design

## Intent

Make the existing physical-design UI usable during development on Windows,
macOS, and Linux without hard-coded checkout paths or unsafe Docker cleanup.
Keep Docker optional for the base RTLCopilot application.

## Goals

- Electron derives PD source and work paths from the active project root.
- Docker commands use argument arrays with `shell: false`, including paths with
  spaces and Windows drive letters.
- Each Electron process uses a unique owner label, tracks the exact container
  ID it creates, and only removes or stops that ID after re-verifying ownership.
- Port 7070 is checked before startup without stopping an unknown owner.
- PD readiness requires HTTP 200 with JSON `{ "status": "ok" }`; timeouts fail
  visibly and clean up an owned failed container.
- The PD service binds to loopback for local development.
- `npm run dev:web` can call the manually started Compose PD service through
  explicit local-development CORS.
- README documents both supported flows and their lifecycle commands.

## Non-goals

- Authentication or authorization for PD endpoints.
- Reworking path validation inside PD download/run endpoints.
- Changing OpenROAD, Yosys, KLayout, the PDK, or the PD stage algorithms.
- Optimizing the Docker image or packaging it into desktop installers.
- Automatically installing or starting Docker Desktop/Engine.

## Approaches

### Chosen: small PD runtime module plus the existing Docker CLI

Extract path construction, Docker argument construction, and ownership checks
from Electron `main.js` into `pd-runtime.js`. Keep the current container model
but make ownership explicit with a label. This retains the existing UI and
preload contract while making the risky logic independently testable.

### Rejected: make Electron invoke Docker Compose

Compose is convenient for browser development, but Electron needs to own and
stop exactly the container it starts. Sharing the same Compose project with a
developer terminal blurs ownership and can stop a user's manually managed
service.

### Rejected: manual Compose only

This would be portable but would regress the desktop experience, where opening
PD is intended to start its optional dependency automatically.

## Runtime behavior

Electron uses `<project-root>/pdtools` and `<project-root>/pdtools/work` in
development. It inspects the fixed container name before startup. A missing
container is fine; any existing container with that name causes an actionable
error because a shared label cannot prove another Electron process is stale.
After the name check, port 7070 must be available.

The detached container is started with a loopback-only port mapping, the work
directory, four live source mounts, and the unique Electron-process ownership
label. A testable PD service object owns every Docker probe, pull, run, health,
and cleanup operation; all commands use `shell: false`. Its lifecycle coalesces
repeated starts, aborts an active pull/readiness wait when stop is requested,
cleans up a just-created owned ID, and serializes a new start behind any active
stop. A failed Docker run or health check returns an error to the PD page.
Shutdown re-inspects the exact ID and ownership before stopping it. Inspect,
remove, and stop errors fail closed.

For browser development, Compose starts the same API on loopback. The PD API
allows only the local Vite origins by default, with an optional
`PD_ALLOWED_ORIGINS` comma-separated extension passed through Compose. Wildcard
origins are rejected. Compose mounts the same four live files as Electron.

The PD module becomes importable as `pdtools.api` for tests while preserving
the Docker `api:app` entrypoint fallback. Jinja2 is declared explicitly rather
than relying on a transitive install.

## Acceptance

- Pure Node tests cover Linux, macOS, and Windows paths, including spaces.
- Tests cover conflicting containers, safe stop behavior, start/stop
  cancellation, repeated starts, every shell-free Docker operation, spawn/run
  failures, cleanup failures, loopback publishing, and strict health failures.
- A Python test proves a Vite-origin OPTIONS preflight to `/new_run` succeeds
  while an unrelated origin is rejected.
- `npm test`, `npm run doctor`, Docker Compose config validation, and an
  Electron smoke test remain green.
