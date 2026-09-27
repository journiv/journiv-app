/**
 * Pure helpers for dictation: what the recorder negotiates, how long it may run,
 * and what identifies the place a recording started.
 *
 * Nothing here touches the browser, so every rule is unit-testable and the
 * recorder hook stays a thin shell around `MediaRecorder`.
 */

/**
 * Containers to try, best first. WebM/Opus is Chrome, Firefox, Android and
 * Safari 18.4+; MP4/AAC is older Safari and iOS. If none is supported the
 * feature is unavailable — the recorder never records into a container it did
 * not choose. AAC is not preferred where WebM exists: Chrome's AAC encoder
 * fails on ordinary mono microphone input. The server re-encodes Opus to AAC
 * so every browser can play the result (docs/features/editor.md, Voice notes).
 */
export const RECORDER_MIME_PREFERENCE = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/aac",
] as const;

/**
 * The bitrate asked of the recorder. Speech does not need more, and asking for
 * a known rate is what makes the duration cap below computable rather than a
 * guess. The recorder's own reported rate wins when it differs.
 */
export const REQUESTED_BITS_PER_SECOND = 32_000;

/**
 * How often `MediaRecorder` hands over data. Short enough that little is lost if
 * the page dies, long enough that IndexedDB is not written to constantly.
 */
export const TIMESLICE_MS = 4_000;

/** Fraction of the upload limit a recording may use; the rest is container and
 * encoder overhead, which the bitrate arithmetic cannot see. */
export const SIZE_SAFETY_MARGIN = 0.8;

/** Once this little time is left, the recorder says so. */
export const LOW_TIME_WARNING_MS = 60_000;

export function pickRecorderMime(
  isTypeSupported: (type: string) => boolean,
): string | null {
  for (const type of RECORDER_MIME_PREFERENCE) {
    if (isTypeSupported(type)) return type;
  }
  return null;
}

/** `audio/webm;codecs=opus` -> `audio/webm`. */
export function baseMimeType(mimeType: string): string {
  return mimeType.split(";")[0]?.trim().toLowerCase() ?? "";
}

/**
 * The extension the server sniff and `kindForFile` will agree with. Chosen from
 * the recorder's *actual* MIME, not the one that was asked for.
 */
export function extensionForMime(mimeType: string): string {
  switch (baseMimeType(mimeType)) {
    case "audio/webm":
      return "webm";
    case "audio/mp4":
      return "m4a";
    case "audio/aac":
      return "aac";
    case "audio/ogg":
      return "ogg";
    default:
      return "webm";
  }
}

/**
 * How long a recording may run before it would exceed the instance's upload
 * limit, or `null` when the limit is unknown.
 *
 * Derived from `max_file_size_mb` and the negotiated bitrate — never a number
 * invented here. Unknown means uncapped rather than a made-up ceiling: a
 * recording that turns out too large fails at upload and stays staged, which is
 * recoverable; a wrong cap silently truncates someone's speech.
 */
export function maxRecordingMs(
  maxFileSizeMb: number | null | undefined,
  bitsPerSecond: number,
): number | null {
  if (!maxFileSizeMb || maxFileSizeMb <= 0 || bitsPerSecond <= 0) return null;
  const bytesPerSecond = bitsPerSecond / 8;
  const seconds =
    (maxFileSizeMb * 1024 * 1024 * SIZE_SAFETY_MARGIN) / bytesPerSecond;
  return Math.floor(seconds * 1000);
}

/** `1:05`, `12:03`, `1:02:03`. */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${minutes}:${pad(seconds)}`;
}

/**
 * Where in the document a recording started.
 *
 * The index alone means nothing once the document has changed, so the text on
 * either side is kept with it, so a caller can tell whether the document still
 * looks the way it did (`anchorMatches`; docs/features/editor.md, Voice notes). An
 * index that no longer matches its context must never be trusted.
 */
export type DictationAnchor = {
  index: number;
  before: string;
  after: string;
};

/** Characters of context kept on each side of the caret. */
export const ANCHOR_CONTEXT_CHARS = 32;

export function anchorMatches(
  anchor: DictationAnchor,
  current: { before: string; after: string },
): boolean {
  return current.before === anchor.before && current.after === anchor.after;
}

/**
 * A rolling window of recent amplitude samples, resampled to a fixed number of
 * bars for the live display.
 *
 * The final length of a recording is unknown while it runs, so live audio cannot
 * be bucketed into the stored 400 buckets. This keeps the newest `capacity`
 * samples (memory is bounded however long the recording is) and reduces them to
 * `bars` by taking the peak of each group. The server's waveform replaces it
 * once the file has been processed.
 */
export class RollingPeaks {
  private readonly samples: number[] = [];

  constructor(private readonly capacity: number) {}

  push(level: number) {
    this.samples.push(Math.min(1, Math.max(0, level)));
    if (this.samples.length > this.capacity) this.samples.shift();
  }

  get length() {
    return this.samples.length;
  }

  /** The window reduced to at most `bars` values in 0..1, oldest first. */
  bars(bars: number): number[] {
    const count = this.samples.length;
    if (bars <= 0 || count === 0) return [];
    if (count <= bars) return [...this.samples];
    const out: number[] = [];
    for (let i = 0; i < bars; i += 1) {
      const start = Math.floor((i * count) / bars);
      const end = Math.max(Math.floor(((i + 1) * count) / bars), start + 1);
      let peak = 0;
      for (let j = start; j < end; j += 1) {
        peak = Math.max(peak, this.samples[j] ?? 0);
      }
      out.push(peak);
    }
    return out;
  }
}
