# Developer Setup Design

## Intent

Make a fresh RTLCopilot clone usable for offline Electron development on Windows,
macOS, and Linux with `npm run setup` followed by `npm run dev`. Keep the setup
layer small and dependency-free: Node orchestrates the repository's existing
Python, npm, Vite, Electron, and FastAPI tools.

## Goals

- Provide root `setup`, `doctor`, `dev`, `dev:web`, and `test` commands.
- Create a repository `.venv`, install backend and frontend dependencies, and
  create missing offline `.env` files without changing existing ones.
- Make Electron use the project interpreter and wait for a real backend health
  response before opening the application.
- Treat Icarus, Docker, and LLM configuration as optional capabilities.
- Consolidate contributor setup documentation and verify setup on all three
  desktop operating systems.

## Non-goals

Installers, a bundled Python runtime, Supabase setup, automatic system-package
installation, PD portability/security, dependency optimization, UI redesign,
and broad frontend/backend refactors are deferred.

## Approach

Use cross-platform Node scripts and spawn commands without shell-specific
syntax. Platform-specific Bash/PowerShell scripts were rejected because they
would duplicate logic; a Docker-first environment was rejected because it
would make the base workflow much heavier and complicate Electron development.

Offline mode is the contributor default. Canvas, project persistence, and
Verilog generation form the base installation. Icarus enables simulation, an
in-app provider key enables AI, and Docker enables physical design.

## Constraints

- Node.js 18+ and Python 3.10+ are required.
- `RTLCOPILOT_PYTHON` overrides interpreter discovery.
- Setup never edits an existing `.env` file.
- Doctor is read-only and returns nonzero only when the base environment is
  unusable.
- Electron owns one non-reloading backend child; browser development retains
  backend reload.
- Existing untracked architecture documentation and `output/` remain untouched.
