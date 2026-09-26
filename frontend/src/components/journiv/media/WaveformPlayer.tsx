import { Pause, Play } from "lucide-react";
import {
  type KeyboardEvent,
  type PointerEvent,
  type Ref,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { cx } from "../../../lib/cx";
import { IconButton } from "../../ui/icon-button";
import "./waveformPlayer.css";
import {
  DISPLAY_BARS,
  formatClock,
  reducePeaks,
  usablePeaks,
} from "./waveformPeaks";
import { WaveformBars } from "./WaveformBars";

/**
 * Playback for a Moment's recorded audio, drawn as its waveform.
 *
 * This is the presentation of an attached recording — the editor tray and the
 * reader gallery. React owns all of its DOM. It deliberately does not reach into
 * inline embeds: `AudioBlot` keeps a native `<audio>` for media a writer places
 * in the prose by hand, and Quill's DOM is never touched from here
 * (docs/features/editor.md, Voice notes).
 *
 * A missing waveform must never mean missing playback: with no peaks (still
 * processing, or audio that predates them) it renders the plain `<audio>`
 * element it replaces.
 *
 * The handle exists for a later phase that drives this player from the prose
 * (click a sentence, hear that moment). It is cheap to expose now and costly to
 * retrofit into every call site.
 */
export type WaveformPlayerHandle = {
  play(): Promise<void>;
  pause(): void;
  toggle(): Promise<void>;
  /** Moves the playhead; optionally starts playing from there. */
  seek(seconds: number, options?: { play?: boolean }): Promise<void>;
  getCurrentTime(): number;
};

type WaveformPlayerProps = {
  src: string;
  /** 0..100 amplitude buckets, or null while they have not been computed. */
  peaks?: readonly number[] | null;
  /** Server-reported length. Recorder output has none in its container. */
  durationHint?: number | null;
  /** Names the control, e.g. "Recording, 1:05". */
  label: string;
  onLoadError?: () => void;
  className?: string;
  ref?: Ref<WaveformPlayerHandle>;
};

const KEY_STEP_SECONDS = 5;
const KEY_PAGE_SECONDS = 15;

/** Only one recording plays at a time, as a writer expects from a list of them. */
let playing: HTMLAudioElement | null = null;

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function WaveformPlayer(props: WaveformPlayerProps) {
  const { src, peaks, durationHint, label, onLoadError, className, ref } =
    props;
  if (!usablePeaks(peaks)) {
    return (
      // biome-ignore lint/a11y/useMediaCaption: Journiv has no caption field on media.
      <audio
        className={cx("jv-waveform__native", className)}
        src={src}
        controls
        preload="metadata"
        aria-label={label}
        onError={onLoadError}
      />
    );
  }
  return (
    <WaveformControls
      src={src}
      peaks={peaks}
      durationHint={durationHint}
      label={label}
      onLoadError={onLoadError}
      className={className}
      ref={ref}
    />
  );
}

function WaveformControls({
  src,
  peaks,
  durationHint,
  label,
  onLoadError,
  className,
  ref,
}: Omit<WaveformPlayerProps, "peaks"> & { peaks: readonly number[] }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [metadataDuration, setMetadataDuration] = useState<number | null>(null);
  const dragging = useRef(false);

  const bars = useMemo(() => reducePeaks(peaks, DISPLAY_BARS), [peaks]);

  // Browser recordings report `Infinity` for a while (no container duration),
  // so the server's own figure is the fallback rather than a number to hide.
  const duration =
    metadataDuration ??
    (typeof durationHint === "number" && durationHint > 0 ? durationHint : 0);
  const fraction = duration > 0 ? Math.min(1, time / duration) : 0;

  const readDuration = useCallback(() => {
    const audio = audioRef.current;
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) {
      setMetadataDuration(audio.duration);
    }
  }, []);

  const seekTo = useCallback(
    (seconds: number) => {
      const audio = audioRef.current;
      if (!audio) return;
      const limit = duration > 0 ? duration : Number.POSITIVE_INFINITY;
      const next = Math.min(limit, Math.max(0, seconds));
      audio.currentTime = next;
      setTime(next);
    },
    [duration],
  );

  const play = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing && playing !== audio) playing.pause();
    playing = audio;
    try {
      await audio.play();
    } catch (caught) {
      if (playing === audio) playing = null;
      throw caught;
    }
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      play,
      pause: () => audioRef.current?.pause(),
      toggle: async () => {
        const audio = audioRef.current;
        if (!audio) return;
        if (audio.paused) await play();
        else audio.pause();
      },
      seek: async (seconds, options) => {
        seekTo(seconds);
        if (options?.play) await play();
      },
      getCurrentTime: () => audioRef.current?.currentTime ?? 0,
    }),
    [play, seekTo],
  );

  // Progress. `timeupdate` alone steps about four times a second; a frame loop
  // makes the playhead glide, and is skipped entirely under reduced motion.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !isPlaying || prefersReducedMotion()) return;
    let frame = 0;
    let lastUpdate = 0;
    const tick = (now: number) => {
      // The path contains hundreds of bars. Updating at 20 Hz is smooth for a
      // playhead without asking React to redraw it on every display frame.
      if (now - lastUpdate >= 50 && !dragging.current) {
        setTime(audio.currentTime);
        lastUpdate = now;
      }
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [isPlaying]);

  useEffect(() => {
    // An element whose metadata is already available never fires the event.
    readDuration();
    // Captured now: React detaches the ref before this cleanup runs.
    const audio = audioRef.current;
    return () => {
      // Leaving the page must not leave a recording talking.
      if (audio && playing === audio) playing = null;
      if (audio && !audio.paused) audio.pause();
    };
  }, [readDuration]);

  const seekFromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const track = trackRef.current;
    if (!track || duration <= 0) return;
    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = (event.clientX - rect.left) / rect.width;
    seekTo(Math.min(1, Math.max(0, ratio)) * duration);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const audio = audioRef.current;
    if (!audio) return;
    const at = audio.currentTime;
    const handled = (() => {
      switch (event.key) {
        case "ArrowRight":
        case "ArrowUp":
          seekTo(at + KEY_STEP_SECONDS);
          return true;
        case "ArrowLeft":
        case "ArrowDown":
          seekTo(at - KEY_STEP_SECONDS);
          return true;
        case "PageUp":
          seekTo(at + KEY_PAGE_SECONDS);
          return true;
        case "PageDown":
          seekTo(at - KEY_PAGE_SECONDS);
          return true;
        case "Home":
          seekTo(0);
          return true;
        case "End":
          if (duration > 0) seekTo(duration);
          return true;
        default:
          return false;
      }
    })();
    if (handled) event.preventDefault();
  };

  const clock = `${formatClock(time)} of ${duration > 0 ? formatClock(duration) : "unknown length"}`;

  return (
    // biome-ignore lint/a11y/useSemanticElements: role="group" names a cluster of controls; <fieldset> is a form construct and wrong here.
    <div
      className={cx("jv-waveform", className)}
      role="group"
      aria-label={label}
    >
      {/* biome-ignore lint/a11y/useMediaCaption: Journiv has no caption field on media. */}
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={readDuration}
        onDurationChange={readDuration}
        onTimeUpdate={(event) => {
          if (!dragging.current) setTime(event.currentTarget.currentTime);
        }}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => {
          setIsPlaying(false);
          setTime(0);
          if (playing === audioRef.current) playing = null;
        }}
        onError={onLoadError}
      />
      <IconButton
        label={isPlaying ? `Pause ${label}` : `Play ${label}`}
        variant="secondary"
        aria-pressed={isPlaying}
        onClick={() => {
          const audio = audioRef.current;
          if (!audio) return;
          if (audio.paused) {
            // Only an undecodable source is a load error. AbortError (paused
            // mid-start) and NotAllowedError (autoplay policy) are not.
            void play().catch((caught) => {
              if (
                caught instanceof DOMException &&
                caught.name === "NotSupportedError"
              ) {
                onLoadError?.();
              }
            });
          } else audio.pause();
        }}
      >
        {isPlaying ? (
          <Pause aria-hidden="true" size={16} />
        ) : (
          <Play aria-hidden="true" size={16} />
        )}
      </IconButton>
      {/* The waveform is decorative; this slider is the control. */}
      <div
        ref={trackRef}
        className="jv-waveform__track"
        role="slider"
        tabIndex={0}
        aria-label={`Seek ${label}`}
        aria-valuemin={0}
        aria-valuemax={Math.max(0, Math.floor(duration))}
        aria-valuenow={Math.floor(time)}
        aria-valuetext={clock}
        aria-disabled={duration <= 0}
        onKeyDown={onKeyDown}
        onPointerDown={(event) => {
          if (duration <= 0) return;
          dragging.current = true;
          event.currentTarget.setPointerCapture?.(event.pointerId);
          seekFromPointer(event);
        }}
        onPointerMove={(event) => {
          if (dragging.current) seekFromPointer(event);
        }}
        onPointerUp={(event) => {
          dragging.current = false;
          event.currentTarget.releasePointerCapture?.(event.pointerId);
        }}
        onPointerCancel={() => {
          dragging.current = false;
        }}
      >
        <WaveformBars bars={bars} className="jv-waveform__bars" />
        <div
          className="jv-waveform__played"
          style={{ clipPath: `inset(0 ${(1 - fraction) * 100}% 0 0)` }}
        >
          <WaveformBars bars={bars} className="jv-waveform__bars" />
        </div>
      </div>
      <span className="jv-waveform__time" aria-hidden="true">
        {formatClock(time)}
        {duration > 0 ? ` / ${formatClock(duration)}` : ""}
      </span>
    </div>
  );
}
