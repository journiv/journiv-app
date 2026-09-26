/**
 * Bars drawn for a stored waveform. The server keeps 400 buckets per recording;
 * that is far more than a phone can draw legibly, so the player reduces them to
 * a fixed, coarser count by taking the loudest bucket in each group. The count
 * is fixed rather than measured so the player needs no layout state.
 */
export const DISPLAY_BARS = 96;

/** A usable waveform is a non-empty list of finite numbers. Anything else means
 * "not computed yet" and the player falls back to the plain audio element. */
export function usablePeaks(
  peaks: readonly number[] | null | undefined,
): peaks is readonly number[] {
  return (
    Array.isArray(peaks) &&
    peaks.length > 0 &&
    peaks.every((value) => Number.isFinite(value))
  );
}

/** `peaks` (0..100) reduced to `bars` values in 0..1, oldest first. */
export function reducePeaks(
  peaks: readonly number[],
  bars: number = DISPLAY_BARS,
): number[] {
  const count = peaks.length;
  if (count === 0 || bars <= 0) return [];
  const clamp = (value: number) => Math.min(1, Math.max(0, value / 100));
  if (count <= bars) return peaks.map(clamp);
  const out: number[] = [];
  for (let i = 0; i < bars; i += 1) {
    const start = Math.floor((i * count) / bars);
    const end = Math.max(Math.floor(((i + 1) * count) / bars), start + 1);
    let peak = 0;
    for (let j = start; j < end; j += 1) peak = Math.max(peak, peaks[j] ?? 0);
    out.push(clamp(peak));
  }
  return out;
}

/** `1:05`, `12:03`, `1:02:03`. */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(rest)}`
    : `${minutes}:${pad(rest)}`;
}
