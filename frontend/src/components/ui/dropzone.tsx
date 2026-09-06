import { UploadIcon, XIcon } from "lucide-react";
import type * as React from "react";
import { useRef, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { formatBytes } from "@/lib/formatBytes";
import { cn } from "@/lib/utils";

/**
 * A single-file drop target: a labelled, keyboard-reachable area that opens the
 * native picker, accepts a drag-and-drop, and shows the chosen file as a
 * removable chip. Controlled — the caller owns the `File` and every validation
 * decision (type, size); this component only reports what the user picked.
 *
 * The native `<input type="file">` carries the accessible name and stays in the
 * tab order; the surrounding `<label>` is the drop surface and shows a
 * focus ring via `:focus-within`.
 */
export interface DropzoneProps {
  /** The currently selected file, or `null`. */
  value: File | null;
  onValueChange: (file: File | null) => void;
  /** Accessible name for the underlying file input. */
  label: string;
  /** Forwarded to `<input accept>` (e.g. `".zip,application/zip"`). */
  accept?: string;
  disabled?: boolean;
  /** One short line under the prompt — e.g. the accepted format and size cap. */
  hint?: React.ReactNode;
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
  className?: string;
}

export function Dropzone({
  value,
  onValueChange,
  label,
  accept,
  disabled = false,
  hint,
  id,
  "aria-describedby": describedBy,
  "aria-invalid": invalid,
  className,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);

  function handleDrop(event: React.DragEvent) {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (disabled) return;
    // Report whatever was dropped; the caller is the single validator for
    // type and size (a drop bypasses the native `accept` filter anyway).
    const file = event.dataTransfer.files?.[0];
    if (file) onValueChange(file);
  }

  if (value) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm",
          className,
        )}
        data-slot="dropzone-file"
      >
        <UploadIcon
          aria-hidden="true"
          className="size-4 text-muted-foreground"
        />
        <span className="min-w-0 flex-1 truncate">{value.name}</span>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {formatBytes(value.size)}
        </span>
        <IconButton
          label="Remove file"
          size="sm"
          disabled={disabled}
          onClick={() => {
            onValueChange(null);
            if (inputRef.current) inputRef.current.value = "";
          }}
        >
          <XIcon aria-hidden="true" className="size-4" />
        </IconButton>
      </div>
    );
  }

  return (
    <label
      data-slot="dropzone"
      data-dragging={dragging || undefined}
      data-disabled={disabled || undefined}
      className={cn(
        "flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed border-input px-4 py-6 text-center transition-colors",
        "hover:bg-muted/40 has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-ring",
        "data-[dragging]:border-ring data-[dragging]:bg-muted/60",
        "data-[disabled]:cursor-not-allowed data-[disabled]:opacity-55",
        className,
      )}
      onDragEnter={(event) => {
        event.preventDefault();
        dragDepth.current += 1;
        if (!disabled) setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        event.preventDefault();
        dragDepth.current -= 1;
        if (dragDepth.current <= 0) setDragging(false);
      }}
      onDrop={handleDrop}
    >
      <UploadIcon aria-hidden="true" className="size-5 text-muted-foreground" />
      <span className="text-sm">
        Drop a file here or <span className="text-brand underline">browse</span>
      </span>
      {hint ? (
        <span className="text-xs text-muted-foreground">{hint}</span>
      ) : null}
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        aria-label={label}
        aria-describedby={describedBy}
        aria-invalid={invalid}
        className="sr-only"
        onChange={(event) => {
          onValueChange(event.target.files?.[0] ?? null);
          // A file input fires no `change` event when the same path is picked
          // again, so clear it here — otherwise a file the caller rejects
          // (without adopting it as `value`) can't be re-selected.
          event.target.value = "";
        }}
      />
    </label>
  );
}
