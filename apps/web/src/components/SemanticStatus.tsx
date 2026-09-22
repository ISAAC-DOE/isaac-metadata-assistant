import './signals.css';
import './semantic-status.css';
import {
  ArrowLeftRight,
  Check,
  CircleAlert,
  CircleDashed,
  CornerRightUp,
  Equal,
  EyeOff,
  Hourglass,
  Inbox,
  Lock,
  Minus,
  TriangleAlert,
  type LucideIcon,
} from './icons';

/**
 * ONE STATE VOCABULARY FOR WORKFLOW AND CAPTURE SURFACES (2026-09-22).
 *
 * The owner's brief: *"show first: state · action · blocker · value · source"*,
 * with every state carried by an icon AND a word AND a subtle tint — never colour
 * alone — from ONE set of semantic tones rather than a new hue per surface.
 *
 * ── HOW IT RELATES TO WHAT ALREADY EXISTS ───────────────────────────────────
 *
 * `StatusChip` (`lib/status.ts`) is the EVIDENCE vocabulary — verified /
 * confirmed / inferred / missing / pass / fail — and it is not replaced. This is
 * the STATE vocabulary a scientist reads on a workflow or capture surface. It
 * reuses `.chip`'s geometry from `signals.css` (pill, 12.5px/500, icon gap), so
 * the two read as one family, and adds only the tone mapping in
 * `semantic-status.css`.
 *
 * ── THE TONES, AND THE ONE DELIBERATE SUBSTITUTION ──────────────────────────
 *
 *   success  Complete · Ready · Sources Agree
 *   warning  Needs Review · Awaiting Judgment
 *   danger   Conflict · Invalid
 *   info     Inherited
 *   neutral  Missing · Unmapped · Unavailable · Not Applicable · Not Shown Here
 *
 * Success is the teal `--verified-*` family, NOT the green `--pass-*` family:
 * `tokens.css` reserves pass/fail green for the official validation verdict
 * (signal 1, a hard gate), and a "Complete" on a workflow row is not that verdict.
 * And it sits on `--surface`, not on `--verified-bg`: `--verified-text` on its own
 * tint is 4.21:1, the one tinted pair `palette-contrast.test.ts` records as a known
 * A11Y-01 exception, while on white it is 4.85:1. Every tone's ink clears 4.5:1 on
 * the pill's own fill (computed: warning 4.68, danger 7.16, info 6.54, neutral
 * 5.02), and the pill carries its own fill, so the page ground cannot lower it.
 */
export type SemanticState =
  | 'complete'
  | 'ready'
  | 'sourcesAgree'
  | 'needsReview'
  | 'awaitingJudgment'
  | 'conflict'
  | 'missing'
  | 'invalid'
  | 'inherited'
  | 'unmapped'
  | 'unavailable'
  | 'notApplicable'
  | 'notShownHere';

export type SemanticTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

export const SEMANTIC_STATUS: Readonly<
  Record<SemanticState, { label: string; tone: SemanticTone; icon: LucideIcon }>
> = {
  complete: { label: 'Complete', tone: 'success', icon: Check },
  ready: { label: 'Ready', tone: 'success', icon: Check },
  sourcesAgree: { label: 'Sources Agree', tone: 'success', icon: Equal },
  needsReview: { label: 'Needs Review', tone: 'warning', icon: CircleAlert },
  awaitingJudgment: { label: 'Awaiting Judgment', tone: 'warning', icon: Hourglass },
  conflict: { label: 'Conflict', tone: 'danger', icon: ArrowLeftRight },
  invalid: { label: 'Invalid', tone: 'danger', icon: TriangleAlert },
  missing: { label: 'Missing', tone: 'neutral', icon: CircleDashed },
  inherited: { label: 'Inherited', tone: 'info', icon: CornerRightUp },
  unmapped: { label: 'Unmapped', tone: 'neutral', icon: Inbox },
  unavailable: { label: 'Unavailable', tone: 'neutral', icon: Lock },
  notApplicable: { label: 'Not Applicable', tone: 'neutral', icon: Minus },
  notShownHere: { label: 'Not Shown Here', tone: 'neutral', icon: EyeOff },
};

export function SemanticStatus({
  state,
  label,
  size = 'md',
}: {
  state: SemanticState;
  /**
   * A caller's own wording for the same state (e.g. `Locked` for `unavailable`,
   * or `2 Awaiting Judgment`). The tone and icon still come from `state`, so a
   * relabel can never change what colour or shape a state carries.
   */
  label?: string;
  size?: 'sm' | 'md';
}) {
  const meta = SEMANTIC_STATUS[state];
  const Icon = meta.icon;
  return (
    <span
      className={`chip semantic-status semantic-status-${size}`}
      data-tone={meta.tone}
      data-state={state}
    >
      <Icon size={size === 'sm' ? 12 : 13} strokeWidth={2.2} aria-hidden="true" />
      <span>{label ?? meta.label}</span>
    </span>
  );
}
