/**
 * `beforeinstallprompt` (Chromium/Android) and the iOS Safari fallback for
 * Settings → Install & offline (docs/features/pwa.md). Captured at module
 * load so the event is never missed while the settings page isn't mounted.
 */

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{
    outcome: "accepted" | "dismissed";
    platform: string;
  }>;
};

let deferredPrompt: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event as BeforeInstallPromptEvent;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    notify();
  });
}

export function hasDeferredInstallPrompt(): boolean {
  return deferredPrompt !== null;
}

export function subscribeToInstallPrompt(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Shows the captured native install prompt. Resolves "unavailable" if none
 *  was captured (already installed, unsupported browser, or not yet fired). */
export async function promptInstall(): Promise<
  "accepted" | "dismissed" | "unavailable"
> {
  if (!deferredPrompt) return "unavailable";
  const prompt = deferredPrompt;
  // The prompt is single-use regardless of outcome; clear it before awaiting
  // so a second click during the native dialog can't reuse a spent event.
  deferredPrompt = null;
  notify();
  await prompt.prompt();
  const choice = await prompt.userChoice;
  return choice.outcome;
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const navigatorStandalone = (
    navigator as Navigator & { standalone?: boolean }
  ).standalone;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    navigatorStandalone === true
  );
}

/** iOS never fires beforeinstallprompt; the only install route is Share →
 *  Add to Home Screen, so the settings page needs to detect this platform to
 *  show instructions instead of a button. */
export function isIosSafari(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const isIos = /iphone|ipad|ipod/i.test(ua);
  const isSafari = /safari/i.test(ua) && !/crios|fxios|edgios/i.test(ua);
  return isIos && isSafari;
}

export function resetInstallPromptForTests() {
  deferredPrompt = null;
  listeners.clear();
}
