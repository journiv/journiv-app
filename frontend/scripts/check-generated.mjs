import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { join, relative } from "node:path";

const generatedRoot = new URL("../src/api/generated/", import.meta.url);

async function snapshot(rootUrl) {
  const root = rootUrl.pathname;
  const files = new Map();
  async function visit(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await visit(path);
      else {
        const digest = createHash("sha256")
          .update(await readFile(path))
          .digest("hex");
        files.set(relative(root, path), digest);
      }
    }
  }
  await visit(root);
  return files;
}

const before = await snapshot(generatedRoot);
const generation = spawnSync("npm", ["run", "api:generate"], {
  encoding: "utf8",
  shell: process.platform === "win32",
  stdio: "inherit",
});
if (generation.status !== 0) process.exit(generation.status ?? 1);
const after = await snapshot(generatedRoot);

const changed = [...new Set([...before.keys(), ...after.keys()])].filter(
  (path) => before.get(path) !== after.get(path),
);
if (changed.length) {
  console.error(`Generated API output changed:\n${changed.join("\n")}`);
  process.exit(1);
}
console.log(`Generated API output is deterministic (${after.size} files).`);
