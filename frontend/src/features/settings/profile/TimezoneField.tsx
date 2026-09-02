import { useMemo } from "react";
import { Button } from "../../../components/ui/button";
import { FieldDescription } from "../../../components/ui/field";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "../../../components/ui/combobox";

/** The device's current IANA zone, or null if the platform won't say. */
function detectedTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/** Every IANA zone the runtime knows, plus whatever the account already has
 *  stored (so an unusual saved value is never silently dropped). */
function useZoneOptions(current: string): string[] {
  return useMemo(() => {
    const withValues = Intl as typeof Intl & {
      supportedValuesOf?: (key: string) => string[];
    };
    const base = withValues.supportedValuesOf?.("timeZone") ?? [];
    const set = new Set<string>(base);
    set.add("UTC");
    if (current) set.add(current);
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [current]);
}

/**
 * IANA timezone picker — a shadcn `Combobox` (Base UI, type-to-filter). Canonical
 * IANA values are stored; the id itself is the readable form, as elsewhere in
 * the product.
 */
export function TimezoneField({
  id,
  value,
  onChange,
  disabled,
}: {
  id: string;
  value: string;
  onChange: (timezone: string) => void;
  disabled?: boolean;
}) {
  const options = useZoneOptions(value);
  const detected = detectedTimezone();
  const canUseDetected = detected != null && detected !== value;

  return (
    <>
      <Combobox
        items={options}
        value={value}
        onValueChange={(next) => {
          if (typeof next === "string" && next) onChange(next);
        }}
        disabled={disabled}
      >
        <ComboboxInput id={id} placeholder="Search time zones…" />
        <ComboboxContent>
          <ComboboxEmpty>No matching time zone</ComboboxEmpty>
          <ComboboxList>
            {(zone: string) => (
              <ComboboxItem key={zone} value={zone}>
                {zone}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
      {detected != null && (
        <FieldDescription>Detected on this device: {detected}</FieldDescription>
      )}
      {canUseDetected && (
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          onClick={() => onChange(detected)}
        >
          Use detected timezone
        </Button>
      )}
    </>
  );
}
