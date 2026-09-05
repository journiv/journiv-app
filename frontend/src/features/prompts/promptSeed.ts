import type { QuillDelta, QuillOp } from "../../api/generated/types.gen";

/**
 * Turning a chosen prompt into editor content (docs/features/prompts.md).
 *
 * When a writer starts an entry from a prompt, the prompt text is dropped in as
 * a level-3 heading at the very top of the document and the writing goes
 * underneath it. `header` at value 3 is inside the editor's Gate-1 delta
 * profile (src/features/editor/deltaProfile.ts), so a seeded document still
 * saves.
 */

/** The heading ops for one prompt: the text, then a heading-3 line break. */
function promptHeadingOps(text: string): QuillOp[] {
  return [{ insert: text }, { insert: "\n", attributes: { header: 3 } }];
}

/**
 * A fresh document seeded with the prompt heading and one empty line beneath
 * it — used before the editor mounts, when arriving on `/timeline/new?prompt=`.
 */
export function buildPromptSeedDelta(text: string): QuillDelta {
  const trimmed = text.trim();
  return { ops: [...promptHeadingOps(trimmed), { insert: "\n" }] };
}

/**
 * `doc` with the prompt heading prepended. Existing content is kept and pushed
 * below the heading. A document delta always ends in "\n", so the result does
 * too.
 */
export function prependPromptHeading(
  doc: QuillDelta,
  text: string,
): QuillDelta {
  const trimmed = text.trim();
  if (!trimmed) return doc;
  return { ops: [...promptHeadingOps(trimmed), ...(doc.ops ?? [])] };
}
