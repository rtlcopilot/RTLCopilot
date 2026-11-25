export function createDesktopPDSession(electronAPI, { onProgress = () => {} } = {}) {
  let active = true;
  let subscribed = false;
  const removeProgressListener = () => {
    if (!subscribed) return;
    electronAPI.offPdPullProgress();
    subscribed = false;
  };

  return {
    async start() {
      const status = await electronAPI.pdCheckDocker();
      if (!active) return { ok: false, cancelled: true };
      if (!status.installed) return { ok: false, error: "Docker Desktop is not installed. It is required to run the Physical Design tools." };
      if (!status.running) return { ok: false, error: "Docker Desktop is not running. Please start it and try again." };

      electronAPI.onPdPullProgress(onProgress);
      subscribed = true;
      if (!active) {
        removeProgressListener();
        return { ok: false, cancelled: true };
      }

      const result = await electronAPI.pdStart();
      removeProgressListener();
      if (!active) {
        await electronAPI.pdStop?.();
        return { ok: false, cancelled: true };
      }
      return result;
    },

    async stop() {
      active = false;
      removeProgressListener();
      return electronAPI.pdStop?.();
    },
  };
}
