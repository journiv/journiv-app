import { useEffect, useState } from "react";

/**
 * Keeps a server-supplied rate limit visible and prevents accidental repeated
 * version checks locally; the backend remains authoritative when this screen is
 * reopened.
 *
 * `begin()` re-seeds `now` with the current time so the first render after a
 * rate-limited response measures the countdown against the moment the limit was
 * received, never against a stale mount-time value.
 */
export function useCheckCooldown() {
  const [until, setUntil] = useState<number>();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!until) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [until]);

  const seconds = until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0;

  useEffect(() => {
    if (until && seconds === 0) setUntil(undefined);
  }, [seconds, until]);

  return {
    seconds,
    begin: (retryAfterSeconds: number) => {
      const start = Date.now();
      setNow(start);
      setUntil(start + retryAfterSeconds * 1000);
    },
    clear: () => setUntil(undefined),
  };
}
