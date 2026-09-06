import type { ImportSourceType } from "../../../api/generated/types.gen";

/**
 * The import sources the backend's `/import/upload` endpoint actually accepts
 * (`journiv`, `dayone`, `daylio`). `markdown` and `immich` are in the generated
 * enum but rejected by the endpoint, so they are deliberately not offered here.
 * Each entry carries the one line of guidance shown under the Source row —
 * enough to produce the right archive without leaving the screen.
 */
export type ImportSourceOption = {
  value: Extract<ImportSourceType, "journiv" | "dayone" | "daylio">;
  label: string;
  hint: string;
};

export const IMPORT_SOURCES: ImportSourceOption[] = [
  {
    value: "journiv",
    label: "Journiv",
    hint: "A .zip created by Journiv’s own export, containing data.json.",
  },
  {
    value: "dayone",
    label: "Day One",
    hint: "Day One → Settings → Import/Export → Export JSON, then upload that .zip.",
  },
  {
    value: "daylio",
    label: "Daylio",
    hint: "Daylio → More → Backup & restore → Export. Upload the .daylio file inside a .zip.",
  },
];
