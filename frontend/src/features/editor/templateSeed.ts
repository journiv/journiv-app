import type {
  JournalResponse,
  QuillDelta,
} from "../../api/generated/types.gen";

/**
 * Journal entry templates (docs/features/journals.md, docs/features/editor.md).
 *
 * A journal may carry `entry_template`: plain text — typically a few fixed
 * questions — that pre-fills the body of every NEW entry written in it. Like
 * Quick Log's seeded note it is plain paragraphs, never headings, so it reads
 * as the start of the writer's own page. Each template line becomes one line
 * of the document; blank lines are kept so the writer controls the spacing.
 *
 * The template is a starting point, not a stored link: once seeded it is
 * ordinary prose, and editing the journal's template later never touches
 * entries already written.
 */

/** The journal's template as a document, or `null` when it has none. */
export function buildTemplateDelta(
  template: string | null | undefined,
): QuillDelta | null {
  const text = (template ?? "").replace(/\r\n?/g, "\n").trimEnd();
  if (!text.trim()) return null;
  // A document delta always ends in a newline; one insert carrying the
  // template's own line breaks is a valid plain-paragraph document.
  return { ops: [{ insert: `${text}\n` }] };
}

/** The template document for `journalId` among `journals`, if any. */
export function templateDeltaFor(
  journals: readonly JournalResponse[],
  journalId: string | undefined,
): QuillDelta | null {
  if (!journalId) return null;
  const journal = journals.find((candidate) => candidate.id === journalId);
  return buildTemplateDelta(journal?.entry_template);
}
