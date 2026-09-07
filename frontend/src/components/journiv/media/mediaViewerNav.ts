/**
 * Whether a `?media=<id>` search param should be stripped from the URL.
 *
 * The rule is deliberately conservative: only remove the param once the moment
 * media list is *definitively* known and does not contain the id. While the
 * media query is still loading or refetching — or has not been enabled yet —
 * an unknown id is left alone, so a valid deep link is never dropped during the
 * brief window when the list is temporarily empty.
 */
export function shouldClearMediaParam(input: {
  /** The current `?media=` value, if any. */
  mediaParam: string | undefined;
  /** The moment media list has resolved (success, or known-empty). */
  settled: boolean;
  /** The list currently contains an item with `mediaParam` as its id. */
  hasItem: boolean;
}): boolean {
  return Boolean(input.mediaParam) && input.settled && !input.hasItem;
}
