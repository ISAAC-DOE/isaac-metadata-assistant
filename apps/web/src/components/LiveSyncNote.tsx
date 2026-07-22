/*
 * P27.6 — the honest "live updates paused" indicator, shared by every record
 * surface that runs the useRecordSync poller. It appears ONLY when the poller is
 * degraded (>= 3 consecutive failures). It never implies the shown state is
 * freshly verified — it says the opposite: this is the last loaded state, and a
 * manual Refresh is the way to update. `role="status"` keeps it announced but
 * unobtrusive (it is not an error).
 */

interface LiveSyncNoteProps {
  degraded: boolean;
  onRefresh: () => void;
}

export function LiveSyncNote({ degraded, onRefresh }: LiveSyncNoteProps) {
  if (!degraded) return null;
  return (
    <div className="livesync-degraded" role="status">
      <span className="livesync-degraded-text">
        Live updates paused — showing the last loaded state, not a freshly verified one.
      </span>
      <button type="button" className="btn btn-secondary livesync-degraded-refresh" onClick={onRefresh}>
        Refresh
      </button>
    </div>
  );
}
