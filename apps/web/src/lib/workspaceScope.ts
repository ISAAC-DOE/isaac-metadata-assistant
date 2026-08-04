/*
 * WHICH WORKSPACE A SURFACE IS READING, and what a surface owes the reader when
 * that changes underneath it.
 *
 * THE FACT EVERY READ DEPENDS ON. The five built-in example records exist ONLY
 * inside a worked-example session (see `lib/tutorialController.ts`). Every record
 * read answers about whichever scope the request carried, and leaving a session
 * does not merely make its records stale — the backend discards the session's
 * directory, so those records CEASE TO EXIST. There is nothing left to re-read.
 *
 * TWO CORRECT RESPONSES, FOR TWO DIFFERENT KINDS OF SURFACE.
 *
 *   · A LIST is meaningful in both scopes, so it re-reads and shows whatever the
 *     new scope holds. `screens/ExperimentsHome.tsx` does exactly this by keying
 *     its fetch on `useWorkspaceScope()`.
 *
 *   · A RECORD surface is not. Its whole identity is a record id that belonged to
 *     the scope it was opened in. Re-reading that id in the ordinary workspace
 *     produces a 404 and the honest "Record Not Found" panel — true, but it
 *     strands the reader on a surface about a record that was never theirs to
 *     lose, and reads as though something went wrong. Nothing did: they closed a
 *     walkthrough and its temporary workspace went with it. So a record surface
 *     hands them back to My Experiments — see `useWorkspaceScopeChanged`.
 *
 * WHAT THIS REPLACED, so it is not undone. The record surfaces keyed their fetch
 * on the record id alone, so leaving a session changed no dependency and the
 * screen kept rendering everything it had already loaded: the `<h1>`, the "N
 * Fields Need Your Confirmation" panel with its real field paths, every field
 * group, and the workflow spine — a destroyed record presented as current, while
 * background requests 404ed in the console.
 */

import { useRef } from 'react';

import { useTutorialState } from './tutorialController';

/**
 * The workspace scope every scope-sensitive read must key on: `null` for the
 * ordinary workspace, otherwise the open worked-example session id.
 *
 * Read from the tutorial store rather than from `api.getTutorialScope()`, because
 * the store is what notifies React when it changes. The store is a MIRROR of the api
 * scope, not a second opinion about it: `tutorialController` sets the api scope and
 * the store's `sessionId` together on every transition, and its `initialState()`
 * seeds `sessionId` from `getTutorialScope()` so the two also agree on the FIRST
 * RENDER after a reload — see the long comment there for the three user-visible
 * claims that boot-window disagreement produced, of which the worst was a `404` on a
 * LIST read reported to the reader as a missing record.
 */
export function useWorkspaceScope(): string | null {
  return useTutorialState().sessionId;
}

/**
 * Has the workspace scope changed since this surface mounted?
 *
 * True in BOTH directions on purpose. Leaving a session destroys the record the
 * surface was showing; entering one changes the workspace the id is looked up in,
 * where it is equally absent. Either way the id in the URL no longer names
 * anything in the workspace now being addressed, so neither direction may keep
 * rendering what was loaded before.
 *
 * The comparison is against the scope AT MOUNT rather than the previous render, so
 * one glance at the value is enough for a caller to decide — a surface cannot
 * "miss" the change by rendering at the wrong moment.
 *
 * THAT MAKES THE MOUNT VALUE LOAD-BEARING, which is why the store seeds it from the
 * api scope. While `initialState()` hard-coded `sessionId: null`, a record surface
 * mounting during the boot window recorded `null` even though `api.ts` was already
 * inside the persisted session; `resumeTutorialSession` then confirming that session
 * still EXISTS looked like a scope change and bounced the reader off the record they
 * had just reloaded, in the one case where nothing about their workspace had changed.
 */
export function useWorkspaceScopeChanged(): boolean {
  const scope = useWorkspaceScope();
  const mountedIn = useRef(scope);
  return scope !== mountedIn.current;
}
