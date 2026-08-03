/*
 * P27.6 — the honest "live updates paused" indicator, shared by every record
 * surface that runs the useRecordSync poller. It appears ONLY when the poller is
 * degraded (>= 3 consecutive failures). It never implies the shown state is
 * freshly verified — it says the opposite: this is the last loaded state, and a
 * manual Refresh is the way to update. `role="status"` keeps it announced but
 * unobtrusive (it is not an error).
 *
 * R1b adds a SECOND, distinct state: `refreshFailed` — a background refresh that
 * the reader triggered, or that a write triggered on their behalf, did not land.
 * It is deliberately the same component and the same place on the screen, because
 * both states make the same claim (what you are looking at is the last loaded
 * state), and a reader should not have to learn two notices for one fact.
 *
 * TWO THINGS DIFFER, and both are on purpose:
 *
 *  - `role="alert"`, not `"status"`. The degraded note describes a background
 *    condition nobody asked about. A failed refresh is the outcome of an action
 *    the reader just took — pressing Re-Validate, or confirming a value — so it
 *    must interrupt. Silence there is what let a PASS card sit unchanged after a
 *    Re-Validate that never reached the API.
 *  - the wording names the action rather than the poller.
 *
 * `refreshFailed` takes precedence when both hold: the reader's own action is the
 * more immediate fact, and it already implies the state on screen is not fresh.
 */

interface LiveSyncNoteProps {
  degraded: boolean;
  onRefresh: () => void;
  /**
   * The last background refresh (a poll-signalled refetch, a post-write refetch,
   * or an explicit Re-Validate) failed. The data on screen is the last one that
   * loaded successfully. Sourced from `useFetch`'s `refreshFailed`, or from a
   * screen's own non-blanking fetch path.
   */
  refreshFailed?: boolean;
}

export function LiveSyncNote({ degraded, onRefresh, refreshFailed = false }: LiveSyncNoteProps) {
  if (!degraded && !refreshFailed) return null;
  return (
    <div
      className={`livesync-degraded${refreshFailed ? ' livesync-refresh-failed' : ''}`}
      role={refreshFailed ? 'alert' : 'status'}
    >
      <span className="livesync-degraded-text">
        {refreshFailed
          ? 'That refresh did not reach the ISAAC API — this is the last loaded state, not a newly checked one. Try again.'
          : 'Live updates paused — showing the last loaded state, not a freshly verified one.'}
      </span>
      <button type="button" className="btn btn-secondary livesync-degraded-refresh" onClick={onRefresh}>
        Refresh
      </button>
    </div>
  );
}
