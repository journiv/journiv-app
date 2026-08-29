/** Tiny class joiner. Falsy values are dropped. */
export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}
