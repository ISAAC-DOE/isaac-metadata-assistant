import { downCopy } from '../components/FetchStates';
import { isHostedBuild, type ApiError } from './api';
import { useDocumentTitle } from './useDocumentTitle';
import { useWorkspaceScope } from './workspaceScope';

/**
 * A RECORD SCREEN WHOSE READ SETTLED IN AN ERROR IS NOT TITLED AS THAT SCREEN.
 *
 * N4 (owner QA 2026-09-22) fixed the TAB title for `/record/<id>` only; PR #277's
 * review found `/record/<missing>/export` and `/record/<missing>/complete` still
 * titled "Review Export Readiness" / "Complete Metadata" above a "Record Not
 * Found" panel, and `/record/<missing>` still saying "Review Record" in its
 * breadcrumb. One implementation for all three screens.
 *
 * `title` — for ANY settled error, the SAME string `BackendDown` renders, from
 * the same `downCopy`, so the tab and the panel cannot disagree (set here as the
 * document title). `null` while there is no settled error.
 *
 * `recordAbsent` — the API answered that THIS RECORD IS NOT THERE (`not_found`, or
 * a worked-example id outside its walkthrough). Only then does a screen also drop
 * its record chrome: the breadcrumb names the state instead of linking to a record
 * that does not exist, and the rail (live workspace links, a skeleton spine that
 * will never settle) is omitted. For every OTHER error — the backend not running,
 * a sign-in lapse — the record may well exist, so the breadcrumb keeps its link
 * back to it (P23B) and nothing else changes.
 */
export function useSettledErrorTitle(error: ApiError | null | undefined): {
  title: string | null;
  recordAbsent: boolean;
} {
  const scope = useWorkspaceScope();
  const copy = error == null ? null : downCopy(error, isHostedBuild, scope);
  const title = copy === null ? null : copy.title;
  useDocumentTitle(title === null ? null : [title]);
  return {
    title,
    recordAbsent:
      copy !== null && (copy.kind === 'not_found' || copy.kind === 'example_workspace_ended'),
  };
}
