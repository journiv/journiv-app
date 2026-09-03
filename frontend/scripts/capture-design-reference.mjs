#!/usr/bin/env node
/**
 * Capture the design reference screenshots used by DESIGN.md.
 *
 * Dependency-free: drives headless Chrome over the DevTools Protocol using
 * Node's built-in WebSocket. Regenerate the references whenever a redesign
 * lands so the documentation cannot drift from the product.
 *
 *   JOURNIV_EMAIL=... JOURNIV_PASSWORD=... \
 *     node scripts/capture-design-reference.mjs --base http://127.0.0.1:5199
 *
 * Credentials are read from the environment only. Never hard-code an account
 * in this file: it is committed.
 */
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";
import path from "node:path";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
}
const BASE = args.get("base") ?? "http://127.0.0.1:5199";
const OUT = path.resolve(args.get("out") ?? "docs/design/reference");
const CHROME =
  args.get("chrome") ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const EMAIL = process.env.JOURNIV_EMAIL;
const PASSWORD = process.env.JOURNIV_PASSWORD;

if (!EMAIL || !PASSWORD) {
  console.error(
    "Set JOURNIV_EMAIL and JOURNIV_PASSWORD for a disposable local account.",
  );
  process.exit(1);
}

/** Scenarios are named after what they demonstrate, not after test data. */
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, scale: 1 },
  // The 861–1100px band has its own layout (nav in a drawer, two panes) and
  // was previously never captured.
  { name: "tablet", width: 1024, height: 768, scale: 1 },
  { name: "mobile", width: 390, height: 844, scale: 1 },
];
const THEMES = ["light", "dark"];

const PORT = 9333;
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--no-first-run",
  "--no-default-browser-check",
  "--user-data-dir=/tmp/journiv-design-capture",
  "--hide-scrollbars",
  "--force-device-scale-factor=1",
  "about:blank",
]);
chrome.stderr.on("data", () => {});

async function cdpTarget() {
  for (let i = 0; i < 40; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const targets = await response.json();
      const page = targets.find((t) => t.type === "page");
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch {
      /* chrome not up yet */
    }
    await delay(250);
  }
  throw new Error("Chrome DevTools endpoint never became available");
}

function connect(url) {
  const socket = new WebSocket(url);
  const pending = new Map();
  let id = 0;
  const ready = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    const entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    if (message.error) entry.reject(new Error(JSON.stringify(message.error)));
    else entry.resolve(message.result);
  });
  return {
    ready,
    close: () => socket.close(),
    send(method, params = {}) {
      id += 1;
      const messageId = id;
      return new Promise((resolve, reject) => {
        pending.set(messageId, { resolve, reject });
        socket.send(JSON.stringify({ id: messageId, method, params }));
      });
    },
  };
}

async function main() {
  const cdp = connect(await cdpTarget());
  await cdp.ready;
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");

  const evaluate = async (expression) => {
    const result = await cdp.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(
        result.exceptionDetails.exception?.description ?? "eval failed",
      );
    }
    return result.result.value;
  };

  const goto = async (url) => {
    await cdp.send("Page.navigate", { url });
    await delay(900);
  };

  await goto(`${BASE}/login`);

  // Authenticate through the API and seed the session the app expects, so the
  // capture never types credentials into the UI.
  const signedIn = await evaluate(`(async () => {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: ${JSON.stringify(EMAIL)}, password: ${JSON.stringify(PASSWORD)} }),
    });
    if (!response.ok) return "login failed: " + response.status;
    const tokens = await response.json();
    sessionStorage.setItem("journiv.session.v1", JSON.stringify({
      version: 1,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    }));
    return "ok";
  })()`);
  if (signedIn !== "ok") throw new Error(String(signedIn));

  const moments = await evaluate(`(async () => {
    const token = JSON.parse(sessionStorage.getItem("journiv.session.v1")).accessToken;
    const auth = { Authorization: "Bearer " + token };
    const response = await fetch("/api/v1/moments?limit=50&include_empty=true", { headers: auth });
    const items = (await response.json()).items;
    const pick = (predicate) => items.find(predicate);

    // Inline media has to be found by inspecting entry content: the Moment list
    // does not carry content_delta.
    let inline = null;
    const candidates = items.filter((m) => m.entry && m.media_count > 0).slice(0, 8);
    for (const moment of candidates) {
      const entry = await fetch("/api/v1/entries/" + moment.entry.id, { headers: auth });
      if (!entry.ok) continue;
      const ops = (await entry.json())?.content_delta?.ops ?? [];
      if (ops.some((op) => op && typeof op.insert === "object")) {
        inline = moment.id;
        break;
      }
    }

    return {
      rich: pick((m) => m.entry && m.media_count === 1 && m.tags?.length && m.id !== inline)?.id ?? null,
      plain: pick((m) => m.entry && !m.media_count && !m.tags?.length)?.id ?? null,
      noteOnly: pick((m) => !m.entry && m.note)?.id ?? null,
      mediaOnly: pick((m) => !m.entry && !m.note && m.media_count > 0)?.id ?? null,
      mediaGallery: pick((m) => m.entry && m.media_count > 1 && m.id !== inline)?.id ?? null,
      inline,
    };
  })()`);

  // Named after the canonical Moment scenarios in docs/domain/moments.md, so the
  // reference set always covers both sparse and rich Moments.
  const scenes = [
    { name: "01-timeline", url: `${BASE}/timeline` },
    moments.rich && {
      name: "02-reader-rich",
      url: `${BASE}/timeline/${moments.rich}`,
    },
    moments.plain && {
      name: "03-reader-plain",
      url: `${BASE}/timeline/${moments.plain}`,
    },
    moments.noteOnly && {
      name: "04-reader-note-only",
      url: `${BASE}/timeline/${moments.noteOnly}`,
    },
    moments.mediaOnly && {
      name: "05-reader-media-only",
      url: `${BASE}/timeline/${moments.mediaOnly}`,
    },
    moments.mediaGallery && {
      name: "06-reader-media-gallery",
      url: `${BASE}/timeline/${moments.mediaGallery}`,
    },
    moments.inline && {
      name: "07-reader-inline-media",
      url: `${BASE}/timeline/${moments.inline}`,
    },
    moments.rich && {
      name: "08-editor",
      url: `${BASE}/timeline/${moments.rich}/edit`,
    },
    { name: "09-editor-new", url: `${BASE}/timeline/new` },
    { name: "10-empty-search", url: `${BASE}/timeline?q=zzzznothingmatches` },
    // Settings overlay (docs/features/settings.md): the desktop capture shows the two-column
    // modal, the mobile capture the full-screen routed page.
    { name: "12-settings-profile", url: `${BASE}/settings/profile` },
    { name: "13-settings-security", url: `${BASE}/settings/security` },
    // Appearance carries the densest set of stock controls in the product —
    // selects, a toggle group, swatches, a textarea — so it is the fastest
    // read on whether controls still look like base-vega.
    { name: "14-settings-appearance", url: `${BASE}/settings/appearance` },
    // Library rows and the Journals list are the product's two row treatments.
    { name: "15-library-people", url: `${BASE}/settings/journaling/people` },
    { name: "16-journals", url: `${BASE}/journals` },
  ].filter(Boolean);

  await mkdir(OUT, { recursive: true });
  for (const viewport of VIEWPORTS) {
    for (const theme of THEMES) {
      await cdp.send("Emulation.setDeviceMetricsOverride", {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor: viewport.scale,
        mobile: viewport.name === "mobile",
      });
      await cdp.send("Emulation.setEmulatedMedia", {
        features: [{ name: "prefers-color-scheme", value: theme }],
      });
      await evaluate(
        `localStorage.setItem("journiv.theme", ${JSON.stringify(theme)})`,
      );

      for (const scene of scenes) {
        await goto(scene.url);
        await delay(1500); // let queries settle and images decode
        const shot = await cdp.send("Page.captureScreenshot", {
          format: "png",
          captureBeyondViewport: false,
        });
        const file = path.join(
          OUT,
          `${scene.name}-${viewport.name}-${theme}.png`,
        );
        await writeFile(file, Buffer.from(shot.data, "base64"));
        console.log("captured", path.relative(process.cwd(), file));
      }
    }
  }

  cdp.close();
  chrome.kill();
}

main().catch((error) => {
  console.error(error);
  chrome.kill();
  process.exit(1);
});
