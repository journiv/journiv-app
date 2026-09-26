import { vi } from "vitest";

/**
 * Test-only stand-ins for the browser's recorder and microphone, shared by the
 * dictation tests. Never imported by product code.
 */

/** A controllable stand-in for the browser's recorder. */
export class FakeRecorder extends EventTarget {
  static instances: FakeRecorder[] = [];
  static supported = new Set<string>([
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/aac",
  ]);
  static reportedMime: string | null = null;
  static isTypeSupported = (type: string) => FakeRecorder.supported.has(type);

  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  audioBitsPerSecond: number;
  timeslice: number | undefined;
  constructor(
    public stream: MediaStream,
    options: { mimeType: string; audioBitsPerSecond: number },
  ) {
    super();
    this.mimeType = FakeRecorder.reportedMime ?? options.mimeType;
    this.audioBitsPerSecond = options.audioBitsPerSecond;
    FakeRecorder.instances.push(this);
  }
  start(timeslice?: number) {
    this.state = "recording";
    this.timeslice = timeslice;
  }
  stop() {
    this.state = "inactive";
    queueMicrotask(() => this.dispatchEvent(new Event("stop")));
  }
  emit(bytes: number) {
    const event = new Event("dataavailable") as Event & { data: Blob };
    event.data = new Blob([new Uint8Array(bytes)]);
    this.dispatchEvent(event);
  }
}

export function fakeStream() {
  const track = Object.assign(new EventTarget(), { stop: vi.fn() });
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  return { stream, track };
}

export const DEFAULT_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/aac",
];
