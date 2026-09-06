import type { JobStatus } from "../../../api/generated/types.gen";

type ResultData = { [key: string]: unknown } | undefined;

const CREATED_FIELDS: Array<[key: string, one: string, many: string]> = [
  ["entries_created", "entry", "entries"],
  ["journals_created", "journal", "journals"],
  ["moments_created", "moment", "moments"],
  ["media_files_imported", "media file", "media files"],
  ["tags_created", "tag", "tags"],
  ["people_created", "person", "people"],
  ["moods_created", "mood", "moods"],
  ["activities_created", "activity", "activities"],
  ["goals_created", "goal", "goals"],
];

const SKIPPED_FIELDS: Array<[key: string, one: string, many: string]> = [
  ["entries_skipped", "entry skipped", "entries skipped"],
  ["media_files_skipped", "media file skipped", "media files skipped"],
];

function num(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function line(data: ResultData, fields: typeof CREATED_FIELDS): string[] {
  return fields
    .map(([key, one, many]) => {
      const n = num(data?.[key]);
      if (n <= 0) return null;
      return `${n.toLocaleString()} ${n === 1 ? one : many}`;
    })
    .filter((v): v is string => v !== null);
}

/**
 * The settled state of an import job: the created/skipped breakdown from
 * `result_data` and, behind a disclosure, every non-fatal warning the run
 * produced (grouped counts first, then the individual messages).
 */
export function ImportResultSummary({
  status,
  resultData,
  warnings,
  processed,
  total,
}: {
  status: JobStatus;
  resultData: ResultData;
  warnings: string[] | undefined;
  processed: number;
  total: number;
}) {
  const created = line(resultData, CREATED_FIELDS);
  const skipped = line(resultData, SKIPPED_FIELDS);
  const categories = (resultData?.warning_categories ?? {}) as Record<
    string,
    unknown
  >;
  const categoryEntries = Object.entries(categories).filter(
    ([, count]) => num(count) > 0,
  );
  const uniqueMessages = [...new Set(warnings ?? [])];
  const warningCount =
    uniqueMessages.length ||
    categoryEntries.reduce((sum, [, count]) => sum + num(count), 0);

  return (
    <div className="jv-backup-result" role="status">
      <p className="jv-backup-result__headline">
        {status === "partial"
          ? "Import finished — some items were skipped."
          : "Import complete."}
      </p>

      {created.length > 0 ? (
        <ul className="jv-backup-result__stats">
          {created.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      ) : (
        <p className="jv-caption">
          {processed.toLocaleString()} of {total.toLocaleString()} items
          processed.
        </p>
      )}

      {skipped.length > 0 ? (
        <p className="jv-backup-result__warn">{skipped.join(" · ")}</p>
      ) : null}

      {warningCount > 0 ? (
        <details className="jv-backup-warnings">
          <summary>
            View {warningCount.toLocaleString()}{" "}
            {warningCount === 1 ? "warning" : "warnings"}
          </summary>
          {categoryEntries.length > 0 ? (
            <ul className="jv-backup-warnings__categories">
              {categoryEntries.map(([label, count]) => (
                <li key={label}>
                  {label} — {num(count).toLocaleString()}
                </li>
              ))}
            </ul>
          ) : null}
          {uniqueMessages.length > 0 ? (
            <ul className="jv-backup-warnings__messages">
              {uniqueMessages.slice(0, 100).map((message) => (
                <li key={message}>{message}</li>
              ))}
              {uniqueMessages.length > 100 ? (
                <li className="jv-caption">
                  … and {(uniqueMessages.length - 100).toLocaleString()} more.
                </li>
              ) : null}
            </ul>
          ) : null}
        </details>
      ) : null}
    </div>
  );
}
