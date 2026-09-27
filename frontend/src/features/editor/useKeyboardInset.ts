import { type RefObject, useLayoutEffect } from "react";

/**
 * Track the on-screen keyboard and pin the editor to the visible area.
 *
 * At the compact width the editor's formatting bar docks at the bottom, and it
 * must sit *above* the on-screen keyboard. Only `window.visualViewport` reports
 * where the keyboard is: on iOS Safari the layout viewport never shrinks, and on
 * Android Chrome it only shrinks with a viewport opt-in this app does not set, so
 * in both cases the visual viewport is the single source of truth.
 *
 * iOS also *pans* the page to reveal the caret, which scrolls the header off
 * the top and leaves an in-flow bottom bar behind the keyboard. So while the
 * keyboard is open the editor is pinned to the visual viewport instead of
 * translating a bar by a guessed inset.
 *
 * "Keyboard open" is judged by how much shorter the visual viewport is than
 * the layout viewport — never by where its bottom edge sits. iOS pans the
 * visual viewport all the way down when the caret is low in the page (writing
 * in the body), which puts its bottom edge on the layout viewport's bottom and
 * would read as "no keyboard" — the exact moment the pin is needed.
 *
 * DESIGN.md's "no JS layout state" rule stands for layout: this hook drives no
 * reflow through React. It writes these straight onto the editor root —
 *
 *   --jv-vv-top/-height   the visual viewport's offset and height in CSS pixels
 *   data-kbd="open"       present only while a keyboard-sized inset is showing
 *
 * — so `editor.css` can pin the editor to the visual viewport and pad the
 * scroll owner.
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
      node?.style.removeProperty("--jv-vv-top");
      node?.style.removeProperty("--jv-vv-height");
      if (node) delete node.dataset.kbd;
    };

    if (!node || !active || !viewport) {
      clear();
      return;
    }

    const update = () => {
      // How much of the layout viewport the visual viewport does not cover —
      // the keyboard, plus any browser bottom UI that overlays content. Scaled
      // back to unzoomed pixels so a pinch-zoom does not read as a keyboard,
      // and independent of `offsetTop` so iOS panning the page cannot hide it.
      const layoutHeight = Math.max(
        window.innerHeight,
        document.documentElement.clientHeight,
      );
      const inset = Math.max(
        0,
        layoutHeight - viewport.height * viewport.scale,
      );
      const wasOpen = node.dataset.kbd === "open";
      node.style.setProperty("--jv-vv-top", `${viewport.offsetTop}px`);
      node.style.setProperty("--jv-vv-height", `${viewport.height}px`);
      if (inset >= KEYBOARD_OPEN_MIN) {
        node.dataset.kbd = "open";
        // Pinning shrinks the scroll owner to the visible area, so a caret iOS
        // had revealed by panning the page may now sit below it. Bring it back
        // once, on the transition only — never per frame.
        if (!wasOpen) revealCaret(node);
      } else delete node.dataset.kbd;
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

/**
 * Scroll the editor's scroll owner (only — never the page, which would pan the
 * visual viewport again) so the caret sits inside its scroll-padding band.
 */
function revealCaret(root: HTMLElement): void {
  const scroller = root.querySelector<HTMLElement>(".jv-editor__scroll");
  const surface = root.querySelector(".jv-editor__surface");
  const selection = window.getSelection();
  if (!scroller || !surface || !selection || selection.rangeCount === 0) return;
  // Prose only: the title sits at the top, and a <textarea> exposes no range.
  const focusNode = selection.focusNode;
  if (!focusNode || !surface.contains(focusNode)) return;

  let rect = selection.getRangeAt(0).getBoundingClientRect();
  // A collapsed range on an empty line has no box; use its line instead.
  if (rect.height === 0) {
    const line =
      focusNode instanceof Element ? focusNode : focusNode.parentElement;
    if (!line) return;
    rect = line.getBoundingClientRect();
  }

  const style = getComputedStyle(scroller);
  const bounds = scroller.getBoundingClientRect();
  const top = bounds.top + (Number.parseFloat(style.scrollPaddingTop) || 0);
  const bottom =
    bounds.bottom - (Number.parseFloat(style.scrollPaddingBottom) || 0);
  if (rect.bottom > bottom) scroller.scrollTop += rect.bottom - bottom;
  else if (rect.top < top) scroller.scrollTop -= top - rect.top;
}
