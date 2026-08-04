/*
 * "The workspace was rebuilt" — the one cross-screen invalidation signal.
 *
 * WHY IT EXISTS. The guarded reset used to live on My Experiments and was handed
 * that screen's own `reload`, so a successful reset refetched the list it was
 * looking at. The control now lives in the persistent worked-example bar
 * (`components/TutorialSessionBar.tsx`), which is chrome: it is mounted on every
 * surface and owns no list. Without a signal, a successful reset would leave a
 * silently stale queue — the exact class of defect the refetch was added for.
 *
 * DELIBERATELY TINY, AND DELIBERATELY NOT A STATE STORE. It carries no data, no
 * revision number and no record id: subscribers re-read from the API, which is the
 * only authority on what the workspace now holds. A revision number here would be a
 * second, weaker copy of state the server already reports.
 *
 * ONE PUBLISHER, by design: `ResetDemoDialog` on a 200 execute. It is NOT fired on a
 * refusal, a stale precondition, or an error, because in every one of those cases the
 * backend wrote nothing and there is nothing to invalidate.
 *
 * THE SUBSCRIBERS, LISTED — because "any surface showing workspace-derived data
 * refetches it" is NOT what this module does, and saying so hid a real staleness for
 * a while. The signal reaches whoever subscribed and nobody else:
 *
 *   · `screens/ExperimentsHome.tsx` — the queue.
 *   · `screens/statistics/StatisticsPage.tsx` — the record read only (its four record
 *     cards, workflow spine, evidence totals and export gate all come from
 *     `GET /api/runtime/records`). It was keyed on the workspace SCOPE alone, which a
 *     reset does not change, so it went stale after every reset even though the
 *     control that caused it is mounted on that very screen.
 *
 * Any FUTURE surface that renders workspace-derived record data must subscribe or it
 * will go stale — the scope key does not cover a rebuild, and nothing here will warn
 * you.
 *
 * Record surfaces deliberately do NOT subscribe. They already poll their own record
 * with a conditional GET (P27.6) and adopt a change when the server reports one, so
 * a second mechanism would give them two paths to the same refresh.
 */

const listeners = new Set<() => void>();

/** Subscribe to workspace rebuilds. Returns the unsubscribe function. */
export function subscribeWorkspaceRebuilt(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Announce that the workspace's record set was rebuilt on the server.
 *
 * A throwing listener must not stop the others from hearing it — a screen that
 * fails to refresh is a stale screen, but a screen that never hears is a screen
 * showing records that no longer exist.
 */
export function notifyWorkspaceRebuilt(): void {
  for (const listener of [...listeners]) {
    try {
      listener();
    } catch {
      /* one subscriber's failure is not the others' */
    }
  }
}
