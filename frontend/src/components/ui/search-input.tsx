import { SearchIcon, XIcon } from "lucide-react";
import type { InputHTMLAttributes } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Journiv search field: a stock Input with a leading search glyph and a
 * trailing clear control. A small product composite (two call sites), not a
 * generic primitive.
 */
type SearchInputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  onClear?: () => void;
};

export function SearchInput({
  label,
  onClear,
  value,
  className,
  ...props
}: SearchInputProps) {
  const hasValue = typeof value === "string" && value.length > 0;
  return (
    <div className={cn("relative flex items-center", className)}>
      <SearchIcon
        aria-hidden="true"
        className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground"
      />
      <Input
        aria-label={label}
        value={value}
        className="pr-9 pl-8"
        {...props}
      />
      {hasValue && onClear && (
        <IconButton
          label="Clear search"
          size="sm"
          onClick={onClear}
          className="absolute right-1"
        >
          <XIcon aria-hidden="true" className="size-4" />
        </IconButton>
      )}
    </div>
  );
}
