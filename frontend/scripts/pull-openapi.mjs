import { mkdir, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const url =
  process.env.OPENAPI_URL ?? "http://localhost:8000/api/v1/openapi.json";
const output = resolve(import.meta.dirname, "..", "openapi", "openapi.json");

try {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(`OpenAPI request failed: ${response.status}`);
  const body = await response.json();
  if (
    typeof body?.openapi !== "string" ||
    !body.paths ||
    typeof body.paths !== "object"
  ) {
    throw new Error("Response is not an OpenAPI document with paths");
  }
  await mkdir(dirname(output), { recursive: true });
  const temporary = `${output}.tmp`;
  await writeFile(temporary, `${JSON.stringify(body, null, 2)}\n`);
  await rename(temporary, output);
} catch (error) {
  console.error(`OpenAPI snapshot was not changed: ${error.message}`);
  process.exitCode = 1;
}
