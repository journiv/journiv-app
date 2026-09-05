import type { QuillDelta } from "../../api/generated/types.gen";

/**
 * Seeding the editor body with plain text that was captured elsewhere.
 *
 * Quick Log stores its short free text in `moment.note`. When the writer chooses
 * "Continue as full entry" the note has to land *inside* the entry so they can
 * keep writing from where they left off (docs/features/quicklog.md). This is the
 * reusable seam for that — the editor decides when to call it; callers never
 * touch Quill directly.
 *
 * Plain paragraphs only: unlike `prependPromptHeading`, seeded text carries no
 * heading attribute, so it reads as the writer's own opening sentence rather
 * than a title. Internal newlines are preserved as line breaks.
 */
export function prependPlainParagraph(
  doc: QuillDelta,
  text: string,
): QuillDelta {
  const trimmed = text.trim();
  if (!trimmed) return doc;
  return {
    ops: [{ insert: trimmed }, { insert: "\n\n" }, ...(doc.ops ?? [])],
  };
}
