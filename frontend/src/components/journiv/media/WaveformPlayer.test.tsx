import { act, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WaveformPlayer, type WaveformPlayerHandle } from "./WaveformPlayer";

const peaks = Array.from({ length: 400 }, (_, i) => (i * 7) % 101);

/** jsdom implements no media playback; give elements enough to be driven. */
function stubMedia(duration = 65) {
  const paused = new WeakMap<HTMLMediaElement, boolean>();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    paused.set(this, false);
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    paused.set(this, true);
    this.dispatchEvent(new Event("pause"));
  });
  Object.defineProperty(HTMLMediaElement.prototype, "paused", {
    configurable: true,
    get(this: HTMLMediaElement) {
      return paused.get(this) ?? true;
    },
  });
  Object.defineProperty(HTMLMediaElement.prototype, "duration", {
    configurable: true,
    get: () => duration,
  });
  const times = new WeakMap<HTMLMediaElement, number>();
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true,
    get(this: HTMLMediaElement) {
      return times.get(this) ?? 0;
    },
    set(this: HTMLMediaElement, value: number) {
      times.set(this, value);
    },
  });
}

const audioEl = (container: HTMLElement) =>
  container.querySelector("audio") as HTMLAudioElement;

beforeEach(() => stubMedia());
afterEach(() => {
  vi.restoreAllMocks();
  delete (HTMLMediaElement.prototype as unknown as Record<string, unknown>)
    .duration;
});

describe("WaveformPlayer", () => {
  it("draws the waveform with a named play control and a named slider", () => {
    const { container } = render(
      <WaveformPlayer
        src="/a.webm"
        peaks={peaks}
        durationHint={65}
        label="audio"
      />,
    );
    expect(screen.getByRole("button", { name: "Play audio" })).toBeTruthy();
    const slider = screen.getByRole("slider", { name: "Seek audio" });
    expect(slider.getAttribute("aria-valuetext")).toBe("0:00 of 1:05");
    // The waveform itself is decorative.
    expect(
      container.querySelectorAll("svg[aria-hidden='true']").length,
    ).toBeGreaterThan(0);
    // No native controls once the waveform is the presentation.
    expect(audioEl(container).hasAttribute("controls")).toBe(false);
  });

  it("falls back to the plain audio element when there are no peaks", () => {
    for (const missing of [null, undefined, []]) {
      const { container, unmount } = render(
        <WaveformPlayer src="/a.webm" peaks={missing} label="audio" />,
      );
      const audio = audioEl(container);
      expect(audio.hasAttribute("controls")).toBe(true);
      expect(audio.getAttribute("src")).toBe("/a.webm");
      expect(screen.queryByRole("slider")).toBeNull();
      unmount();
    }
  });

  it("plays and pauses, and says which state it is in", async () => {
    render(<WaveformPlayer src="/a.webm" peaks={peaks} label="audio" />);
    const play = screen.getByRole("button", { name: "Play audio" });
    expect(play.getAttribute("aria-pressed")).toBe("false");
    await act(async () => {
      fireEvent.click(play);
    });
    const pause = screen.getByRole("button", { name: "Pause audio" });
    expect(pause.getAttribute("aria-pressed")).toBe("true");
    await act(async () => {
      fireEvent.click(pause);
    });
    expect(screen.getByRole("button", { name: "Play audio" })).toBeTruthy();
  });

  it("seeks from the keyboard, clamped to the recording", () => {
    const { container } = render(
      <WaveformPlayer src="/a.webm" peaks={peaks} label="audio" />,
    );
    const slider = screen.getByRole("slider", { name: "Seek audio" });
    const audio = audioEl(container);

    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(audio.currentTime).toBe(5);
    fireEvent.keyDown(slider, { key: "PageUp" });
    expect(audio.currentTime).toBe(20);
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(audio.currentTime).toBe(15);
    fireEvent.keyDown(slider, { key: "End" });
    expect(audio.currentTime).toBe(65);
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(audio.currentTime).toBe(65); // clamped
    fireEvent.keyDown(slider, { key: "Home" });
    expect(audio.currentTime).toBe(0);
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(audio.currentTime).toBe(0); // clamped
    expect(slider.getAttribute("aria-valuenow")).toBe("0");
    expect(slider.getAttribute("aria-valuemax")).toBe("65");
  });

  it("does not swallow keys it does not use", () => {
    render(<WaveformPlayer src="/a.webm" peaks={peaks} label="audio" />);
    const slider = screen.getByRole("slider", { name: "Seek audio" });
    expect(fireEvent.keyDown(slider, { key: "Tab" })).toBe(true);
    expect(fireEvent.keyDown(slider, { key: "ArrowRight" })).toBe(false);
  });

  it("uses the server duration when the browser reports none", () => {
    Object.defineProperty(HTMLMediaElement.prototype, "duration", {
      configurable: true,
      get: () => Number.POSITIVE_INFINITY,
    });
    render(
      <WaveformPlayer
        src="/a.webm"
        peaks={peaks}
        durationHint={42}
        label="audio"
      />,
    );
    const slider = screen.getByRole("slider", { name: "Seek audio" });
    expect(slider.getAttribute("aria-valuemax")).toBe("42");
    expect(slider.getAttribute("aria-valuetext")).toBe("0:00 of 0:42");
  });

  it("seeks where the track is clicked", () => {
    const { container } = render(
      <WaveformPlayer src="/a.webm" peaks={peaks} label="audio" />,
    );
    const slider = screen.getByRole("slider", { name: "Seek audio" });
    slider.getBoundingClientRect = () =>
      ({
        left: 100,
        width: 200,
        top: 0,
        height: 44,
        right: 300,
        bottom: 44,
        x: 100,
        y: 0,
        toJSON: () => ({}),
      }) as DOMRect;
    fireEvent.pointerDown(slider, { clientX: 200, pointerId: 1 });
    expect(audioEl(container).currentTime).toBeCloseTo(32.5, 5);
  });

  it("exposes a handle to drive it from outside", async () => {
    const ref = createRef<WaveformPlayerHandle>();
    const { container } = render(
      <WaveformPlayer src="/a.webm" peaks={peaks} label="audio" ref={ref} />,
    );
    await act(async () => {
      await ref.current?.seek(30, { play: true });
    });
    expect(ref.current?.getCurrentTime()).toBe(30);
    expect(screen.getByRole("button", { name: "Pause audio" })).toBeTruthy();
    act(() => ref.current?.pause());
    expect(screen.getByRole("button", { name: "Play audio" })).toBeTruthy();
    await act(async () => {
      await ref.current?.toggle();
    });
    expect(audioEl(container).paused).toBe(false);
  });

  it("plays one recording at a time", async () => {
    render(
      <>
        <WaveformPlayer src="/a.webm" peaks={peaks} label="first" />
        <WaveformPlayer src="/b.webm" peaks={peaks} label="second" />
      </>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play first" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play second" }));
    });
    expect(screen.getByRole("button", { name: "Play first" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pause second" })).toBeTruthy();
  });

  it("stops playing when it goes away", async () => {
    const { unmount } = render(
      <WaveformPlayer src="/a.webm" peaks={peaks} label="audio" />,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play audio" }));
    });
    const pause = HTMLMediaElement.prototype.pause as unknown as ReturnType<
      typeof vi.fn
    >;
    pause.mockClear();
    unmount();
    expect(pause).toHaveBeenCalled();
  });

  it("does not run a frame loop under reduced motion", async () => {
    const raf = vi.spyOn(window, "requestAnimationFrame");
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      onchange: null,
      dispatchEvent: () => false,
    }));
    try {
      render(<WaveformPlayer src="/a.webm" peaks={peaks} label="audio" />);
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Play audio" }));
      });
      expect(raf).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("animates the playhead when motion is allowed", async () => {
    const raf = vi.spyOn(window, "requestAnimationFrame");
    render(<WaveformPlayer src="/a.webm" peaks={peaks} label="audio" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play audio" }));
    });
    expect(raf).toHaveBeenCalled();
  });

  it("reports a load error to its owner", () => {
    const onLoadError = vi.fn();
    const { container } = render(
      <WaveformPlayer
        src="/a.webm"
        peaks={peaks}
        label="audio"
        onLoadError={onLoadError}
      />,
    );
    fireEvent.error(audioEl(container));
    expect(onLoadError).toHaveBeenCalled();
  });
});
