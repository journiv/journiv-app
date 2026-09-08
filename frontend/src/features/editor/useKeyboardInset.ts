import { type RefObject, useLayoutEffect } from "react";

/**
 * Track the on-screen keyboard and expose its height to CSS.
 *
 * At the compact width the editor's formatting bar docks at the bottom, and it
 * must sit *above* the on-screen keyboard. Only `window.visualViewport` reports
 * where the keyboard is: on iOS Safari the layout viewport never shrinks, and on
 * Android Chrome it only shrinks with a viewport opt-in this app does not set, so
 * in both cases the visual viewport is the single source of truth.
 *
 * DESIGN.md's "no JS layout state" rule stands for layout: this hook drives no
 * reflow. It writes two things straight onto the editor root and nothing else —
 *
 *   --jv-keyboard-inset   the keyboard's height in CSS pixels (0 when closed)
 *   data-kbd="open"       present only while a keyboard-sized inset is showing
 *
 * — so `editor.css` can translate a fixed-height bar and pad the scroll owner.
 * The writes are imperative on purpose: `visualViewport` fires `resize`/`scroll`
 * continuously during a keyboard animation or a pinch, and routing that through
 * React state would re-render the editor page on every frame, which the editor's
 * typing-cost invariants forbid (docs/features/editor.md).
 *
 * `active` is the compact-width flag. Above it the hook attaches nothing and
 * clears anything it left behind, so a desktop resize cannot strand an offset.
 */

/** Minimum inset (px) that counts as "a keyboard is open", not a browser bar. */
const KEYBOARD_OPEN_MIN = 120;

export function useKeyboardInset(
  rootRef: RefObject<HTMLElement | null>,
  active: boolean,
): void {
  useLayoutEffect(() => {
    const node = rootRef.current;
    const viewport =
      typeof window !== "undefined" ? window.visualViewport : null;

    const clear = () => {
      node?.style.removeProperty("--jv-keyboard-inset");
      if (node) delete node.dataset.kbd;
    };

    if (!node || !active || !viewport) {
      clear();
      return;
    }

    const update = () => {
      // How far the visual viewport's bottom sits above the layout viewport's
      // bottom — the keyboard, plus any browser bottom UI that overlays content.
      const inset = Math.max(
        0,
        window.innerHeight - viewport.height - viewport.offsetTop,
      );
      node.style.setProperty("--jv-keyboard-inset", `${inset}px`);
      if (inset >= KEYBOARD_OPEN_MIN) node.dataset.kbd = "open";
      else delete node.dataset.kbd;
    };

    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
      clear();
    };
  }, [rootRef, active]);
}
