import type { CSSProperties } from "react";
import { useEffect, useId, useState } from "react";
import type {
  JournalColor,
  JournalResponse,
} from "../../api/generated/types.gen";
import { AppAdaptiveDialog } from "../../components/journiv/AppAdaptiveDialog";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { JOURNAL_COLORS } from "../../lib/journalColors";
import { JOURNAL_ICONS } from "../../lib/journalIcons";

export type JournalFormValues = {
  title: string;
  description: string | null;
  color: JournalColor | null;
  icon: string | null;
};

/**
 * Create or edit a journal. `journal` undefined ⇒ create. The parent owns the
 * mutation and passes `onSubmit`; this dialog only collects and validates.
 */
export function JournalFormDialog({
  open,
  onOpenChange,
  journal,
  onSubmit,
  submitting,
  failed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  journal?: JournalResponse;
  onSubmit: (values: JournalFormValues) => Promise<unknown>;
  submitting: boolean;
  failed: boolean;
}) {
  const editing = Boolean(journal);
  const formId = useId();
  const titleId = useId();
  const descId = useId();
  const colorName = useId();
  const iconName = useId();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState<JournalColor | "">("");
  const [icon, setIcon] = useState("");
  const [touched, setTouched] = useState(false);

  // Seed from the journal each time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setTitle(journal?.title ?? "");
    setDescription(journal?.description ?? "");
    setColor((journal?.color as JournalColor | undefined) ?? "");
    setIcon(journal?.icon ?? "");
    setTouched(false);
  }, [open, journal]);

  const trimmed = title.trim();
  const invalid = trimmed.length === 0;
  const swatchTint = (value: string): CSSProperties =>
    ({ "--journal-accent": value }) as CSSProperties;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (invalid || submitting) return;
    await onSubmit({
      title: trimmed,
      description: description.trim() || null,
      color: color || null,
      icon: icon || null,
    });
  }

  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title={editing ? "Edit journal" : "New journal"}
      description={
        editing
          ? "Change the name, description or appearance."
          : "Journals group the moments you write."
      }
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="default"
            disabled={submitting}
          >
            {submitting
              ? "Saving…"
              : editing
                ? "Save changes"
                : "Create journal"}
          </Button>
        </>
      }
    >
      <form id={formId} className="jv-jform" onSubmit={submit}>
        <Label htmlFor={titleId}>Title</Label>
        <Input
          id={titleId}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          autoFocus
          aria-invalid={touched && invalid}
          aria-describedby={touched && invalid ? `${titleId}-error` : undefined}
        />
        {touched && invalid && (
          <p
            className="text-sm text-destructive"
            id={`${titleId}-error`}
            role="alert"
          >
            Give the journal a title.
          </p>
        )}

        <Label htmlFor={descId}>Description</Label>
        <Textarea
          id={descId}
          className="jv-jform__textarea"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={1000}
          rows={2}
        />

        <fieldset className="jv-jform__group">
          <legend>Colour</legend>
          <div className="jv-jform__swatches">
            <label className="jv-jform__swatch jv-jform__swatch--none">
              <input
                type="radio"
                name={colorName}
                className="sr-only"
                checked={color === ""}
                onChange={() => setColor("")}
              />
              <span className="sr-only">No colour</span>
            </label>
            {JOURNAL_COLORS.map((option) => (
              <label
                key={option.value}
                className="jv-jform__swatch"
                style={swatchTint(option.value)}
              >
                <input
                  type="radio"
                  name={colorName}
                  className="sr-only"
                  checked={color === option.value}
                  onChange={() => setColor(option.value)}
                />
                <span className="sr-only">{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="jv-jform__group">
          <legend>Icon</legend>
          <div className="jv-jform__icons">
            <label className="jv-jform__icon jv-jform__icon--none">
              <input
                type="radio"
                name={iconName}
                className="sr-only"
                checked={icon === ""}
                onChange={() => setIcon("")}
              />
              None
            </label>
            {JOURNAL_ICONS.map(({ key, label, Icon }) => (
              <label
                key={key}
                className="jv-jform__icon"
                style={color ? swatchTint(color) : undefined}
              >
                <input
                  type="radio"
                  name={iconName}
                  className="sr-only"
                  checked={icon === key}
                  onChange={() => setIcon(key)}
                />
                <span className="sr-only">{label}</span>
                <Icon size={17} aria-hidden="true" />
              </label>
            ))}
          </div>
        </fieldset>

        {failed && (
          <p className="text-sm text-destructive" role="alert">
            {editing
              ? "The change couldn’t be saved. Try again."
              : "The journal couldn’t be created. Try again."}
          </p>
        )}
      </form>
    </AppAdaptiveDialog>
  );
}
