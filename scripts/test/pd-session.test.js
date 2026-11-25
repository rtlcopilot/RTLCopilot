const test = require("node:test");
const assert = require("node:assert/strict");

test("unmount before Docker status resolves prevents a stale PD start", async () => {
  const { createDesktopPDSession } = await import("../../frontend/src/pdSession.mjs");
  let resolveCheck;
  let starts = 0;
  let stops = 0;
  const session = createDesktopPDSession({
    pdCheckDocker: () => new Promise((resolve) => { resolveCheck = resolve; }),
    pdStart: async () => { starts += 1; return { ok: true }; },
    pdStop: async () => { stops += 1; return { ok: true }; },
    onPdPullProgress: () => {},
    offPdPullProgress: () => {},
  });

  const starting = session.start();
  await session.stop();
  resolveCheck({ installed: true, running: true });

  assert.deepEqual(await starting, { ok: false, cancelled: true });
  assert.equal(starts, 0);
  assert.equal(stops, 1);
});

test("unmount during PD start requests cleanup after the stale start settles", async () => {
  const { createDesktopPDSession } = await import("../../frontend/src/pdSession.mjs");
  let resolveStart;
  let stops = 0;
  const session = createDesktopPDSession({
    pdCheckDocker: async () => ({ installed: true, running: true }),
    pdStart: () => new Promise((resolve) => { resolveStart = resolve; }),
    pdStop: async () => { stops += 1; return { ok: true }; },
    onPdPullProgress: () => {},
    offPdPullProgress: () => {},
  });

  const starting = session.start();
  await new Promise((resolve) => setImmediate(resolve));
  await session.stop();
  resolveStart({ ok: true });

  assert.deepEqual(await starting, { ok: false, cancelled: true });
  assert.equal(stops, 2);
});
