/**
 * MOVE FOCUS TO A DESTINATION THAT MAY NOT EXIST YET — bounded, and cancellable.
 *
 * WHY THIS EXISTS (2026-09-22, PR #277 trusted-suite failure). "Review N Proposals"
 * leaves the Capture view for the Proposals view and hands focus to that view's
 * heading. The hand-off used to try ONCE, in an effect keyed on the view: if the
 * heading was not in the document on that exact commit it returned and never tried
 * again, so focus was dropped on `<body>` for good. The first visit to a workspace
 * MOUNTS it (workspaces are lazily mounted, then kept), and the navigation runs in a
 * React transition, so whether the destination exists on the first commit that sees
 * the new view is a matter of scheduling — which is exactly the kind of thing that
 * passes locally and fails on a slower CI runner.
 *
 * WHAT IT DOES. Looks for the target now, and then once per animation frame, until
 * it exists, is connected, and is not inside a `hidden` subtree (a hidden-but-mounted
 * workspace is in the DOM but cannot take focus). Then it scrolls it into view and
 * focuses it, exactly once. It gives up after `maxFrames` — a destination that never
 * appears must not leave a loop running, and must not steal focus seconds later from
 * whatever the reader has moved on to.
 *
 * Returns a cancel function; the caller's effect cleanup calls it, so leaving the
 * destination before it appeared abandons the hand-off.
 */
export const FOCUS_HANDOFF_MAX_FRAMES = 60;

export function focusWhenPresent(
  find: () => HTMLElement | null,
  onDone: (focused: boolean) => void = () => undefined,
  maxFrames: number = FOCUS_HANDOFF_MAX_FRAMES,
): () => void {
  let cancelled = false;
  let frameHandle: number | null = null;
  let timerHandle: ReturnType<typeof setTimeout> | null = null;
  let frames = 0;
  const schedule = (fn: () => void) => {
    if (typeof window.requestAnimationFrame === 'function') {
      frameHandle = window.requestAnimationFrame(fn);
    } else {
      timerHandle = setTimeout(fn, 16);
    }
  };
  const attempt = () => {
    if (cancelled) return;
    const target = find();
    if (target !== null && target.isConnected && target.closest('[hidden]') === null) {
      if (typeof target.scrollIntoView === 'function') target.scrollIntoView({ block: 'start' });
      target.focus();
      onDone(true);
      return;
    }
    frames += 1;
    if (frames > maxFrames) {
      onDone(false);
      return;
    }
    schedule(attempt);
  };
  attempt();
  return () => {
    cancelled = true;
    // Each handle is cleared by its OWN canceller — a frame id passed to
    // `clearTimeout` could cancel an unrelated timer that happens to share it.
    if (frameHandle !== null && typeof window.cancelAnimationFrame === 'function') {
      window.cancelAnimationFrame(frameHandle);
    }
    if (timerHandle !== null) clearTimeout(timerHandle);
  };
}
