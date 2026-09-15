import { useEffect, useState } from "react";

/**
 * `navigator.onLine` plus `online`/`offline` events, so a *running* session
 * that loses the network gets the same hint the boot restore uses.
 *
 * The same rule as the boot restore applies here (docs/features/pwa.md):
 * this is a hint about when to check, never a verdict. A request that fails
 * with a network error is what actually puts the session into offline mode,
 * and a request that succeeds is what takes it out -- whatever this reports.
 * An `offline` event alone must never flip a working session into
 * offline-restricted mode while requests are still succeeding against a LAN
 * server.
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return online;
}
