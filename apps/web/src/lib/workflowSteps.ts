/*
 * The canonical workflow sequence, mirrored for client-side derivations.
 *
 * Mirrors `apps/api/isaac_api/workflow.py:17` (`CANONICAL_ORDER`) and
 * `apps/api/isaac_api/workflow.py:26` (`CANONICAL_LABELS`) — ONE permanent
 * ordered sequence of app-native step ids with Title Case labels, never
 * reordered and never persisted.
 *
 * Why a client copy exists at all: the per-record surfaces read the server's
 * own `ordered_steps` (labels included) and must keep doing so — that is record
 * truth and it stays server-derived. This list is only the fixed AXIS a
 * cross-record distribution needs: `GET /api/runtime/records` projects
 * `workflow.current_step` as a bare id with no label and no ordering
 * (`apps/api/isaac_api/runtime_records.py:105-111` — "ONLY current_step + two
 * booleans — no labels, reasons, or values"), so a histogram over that id has
 * nowhere else to get the order or the wording from.
 *
 * It carries NO per-step state: no completed/current/blocked/reopened, no
 * reason. Those are derived per record by `derive_workflow` on the server and
 * are never recomputed here.
 */

export interface WorkflowStep {
  /** The backend's own step id, as projected in `workflow.current_step`. */
  readonly id: string;
  /** The backend's own Title Case label (`workflow.py:26`). */
  readonly label: string;
}

/** The five canonical steps, in canonical order. Never reordered. */
export const CANONICAL_STEPS: readonly WorkflowStep[] = [
  { id: 'load_record', label: 'Load Record' },
  { id: 'complete_metadata', label: 'Complete Metadata' },
  { id: 'review_evidence', label: 'Review Evidence' },
  { id: 'review_export_readiness', label: 'Review Export Readiness' },
  { id: 'export', label: 'Export' },
] as const;
