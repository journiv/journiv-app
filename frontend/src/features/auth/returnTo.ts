export const DEFAULT_RETURN_TO = "/timeline";

/** Only same-origin path references may survive an authentication round trip. */
export function safeReturnTo(value: unknown): string {
  return typeof value === "string" &&
    value.startsWith("/") &&
    !value.startsWith("//") &&
    !value.startsWith("/\\")
    ? value
    : DEFAULT_RETURN_TO;
}
