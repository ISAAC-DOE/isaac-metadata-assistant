/*
 * WHICH MODIFIER KEY THIS READER'S KEYBOARD CALLS THE SHORTCUT KEY (B-A17).
 *
 * The search trigger printed `⌘K` on every platform. The handler has always accepted both
 * `metaKey` and `ctrlKey` (`SearchDialog`), so the shortcut WORKED on Windows and Linux —
 * but the one hint a reader could see named a key their keyboard does not have, which reads
 * as a shortcut that does not exist for them.
 *
 * Decided at CALL time, never at module load, so a test (or a browser that changes its
 * reported platform) is always read fresh. It prefers the structured `userAgentData`
 * Chromium exposes, then the legacy `navigator.platform`, then the user-agent string; any
 * of them may be absent (jsdom, privacy modes), and the safe default when NONE says "Apple"
 * is the Control key — the answer that is right on the platforms with no `⌘` at all.
 */
export function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  const reported = nav.userAgentData?.platform || nav.platform || nav.userAgent || '';
  return /mac|iphone|ipad|ipod/i.test(reported);
}

/** The search shortcut as it should be printed for this keyboard: `⌘K` or `Ctrl K`. */
export function searchShortcutHint(): string {
  return isApplePlatform() ? '⌘K' : 'Ctrl K';
}
