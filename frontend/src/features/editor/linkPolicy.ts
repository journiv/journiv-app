export function validateLinkUrl(value: string): string | null {
  const candidate = value.trim();
  if (!candidate) return null;

  try {
    const parsed = new URL(candidate);
    if (!["http:", "https:", "mailto:"].includes(parsed.protocol.toLowerCase()))
      return null;
    if (parsed.protocol === "mailto:" && !parsed.pathname) return null;
    return candidate;
  } catch {
    return null;
  }
}
