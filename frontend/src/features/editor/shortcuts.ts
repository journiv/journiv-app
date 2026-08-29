type SaveShortcutEvent = Pick<
  KeyboardEvent,
  "altKey" | "ctrlKey" | "isComposing" | "key" | "metaKey"
>;

export function isExplicitSaveShortcut(event: SaveShortcutEvent): boolean {
  return (
    !event.isComposing &&
    !event.altKey &&
    (event.metaKey || event.ctrlKey) &&
    event.key.toLowerCase() === "s"
  );
}
