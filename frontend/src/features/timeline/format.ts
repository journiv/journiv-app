export function formatMomentDateTime(
  value: string,
  timezone: string,
  locale = "en-US",
) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}

export function excerpt(
  value: string | null | undefined,
  fallback = "No narrative yet",
) {
  const text = value?.trim() || fallback;
  return text.length > 140 ? `${text.slice(0, 137).trimEnd()}…` : text;
}
