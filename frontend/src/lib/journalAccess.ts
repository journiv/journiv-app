import type { JournalResponse } from "../api/generated/types.gen";

export type JournalAccessLevel = "owner" | "readonly" | "edit";
export type AccessibleJournal = JournalResponse & {
  access_level?: JournalAccessLevel;
  owner_name?: string | null;
  owner_id?: string | null;
};

export function journalAccessLevel(
  journal: JournalResponse,
): JournalAccessLevel {
  // Older owned-journal payloads omit access_level, so missing still means owner.
  return (journal as AccessibleJournal).access_level ?? "owner";
}

export function canEditJournal(journal: JournalResponse): boolean {
  return journalAccessLevel(journal) !== "readonly";
}

export function canManageJournal(journal: JournalResponse): boolean {
  return journalAccessLevel(journal) === "owner";
}

export function isSharedJournal(journal: JournalResponse): boolean {
  return journalAccessLevel(journal) !== "owner";
}
