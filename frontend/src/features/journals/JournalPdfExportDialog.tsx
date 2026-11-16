import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { tagsQuery } from "../../api/query/options";
import { AppAdaptiveDialog } from "../../components/journiv/AppAdaptiveDialog";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Field, FieldDescription, FieldLabel } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";

export type JournalPdfFilters = {
  start_date?: string;
  end_date?: string;
  tag_id?: string;
};

export function JournalPdfExportDialog({
  open,
  onOpenChange,
  journalTitle,
  downloading,
  failed,
  onExport,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  journalTitle: string;
  downloading: boolean;
  failed: boolean;
  onExport: (filters: JournalPdfFilters) => void;
}) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [tagId, setTagId] = useState("");
  const tags = useQuery({ ...tagsQuery(), enabled: open });
  const invalidRange = Boolean(startDate && endDate && startDate > endDate);

  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={onOpenChange}
      dismissible={!downloading}
      title={`Export ${journalTitle} as PDF`}
      description="Include every entry, or narrow the export by date and tag."
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={downloading}
          >
            Cancel
          </Button>
          <Button
            onClick={() =>
              onExport({
                ...(startDate ? { start_date: startDate } : {}),
                ...(endDate ? { end_date: endDate } : {}),
                ...(tagId ? { tag_id: tagId } : {}),
              })
            }
            disabled={downloading || invalidRange}
          >
            {downloading ? "Preparing…" : "Download PDF"}
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field>
          <FieldLabel htmlFor="journal-pdf-start-date">From date</FieldLabel>
          <Input
            id="journal-pdf-start-date"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.currentTarget.value)}
          />
          <FieldDescription>Uses the Moment’s local date.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="journal-pdf-end-date">To date</FieldLabel>
          <Input
            id="journal-pdf-end-date"
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.currentTarget.value)}
          />
        </Field>
        {invalidRange && (
          <p role="alert" className="text-sm text-destructive">
            The start date must be on or before the end date.
          </p>
        )}
        <Field>
          <FieldLabel htmlFor="journal-pdf-tag">Tag</FieldLabel>
          <NativeSelect
            id="journal-pdf-tag"
            value={tagId}
            onChange={(event) => setTagId(event.currentTarget.value)}
            disabled={tags.isLoading || tags.isError}
          >
            <option value="">All tags</option>
            {(tags.data ?? []).map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {tags.isError && (
          <Alert variant="destructive">
            <AlertDescription className="flex items-center justify-between gap-3">
              Tags couldn’t be loaded.
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => void tags.refetch()}
              >
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}
        {failed && (
          <Alert variant="destructive">
            <AlertDescription>
              The PDF couldn’t be downloaded. Check your connection and try
              again.
            </AlertDescription>
          </Alert>
        )}
      </div>
    </AppAdaptiveDialog>
  );
}
