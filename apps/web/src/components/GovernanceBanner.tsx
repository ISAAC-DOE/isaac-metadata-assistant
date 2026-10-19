import './chrome.css';
import { ShieldCheck } from './icons';
import { LABELS } from '../lib/labels';

interface GovernanceBannerProps {
  onReadPolicy?: () => void;
}

/**
 * The data-governance notice. Protective, not alarming — neutral slate, shield
 * icon, NOT red. Explains ("real data needs written approval"); never scolds,
 * never offers a "proceed with real data" shortcut.
 *
 * Slice 2A (I5) retired the unqualified "Synthetic mode." headline. It was no
 * longer true of the DEPLOYMENT: a protected, read-only diagnostic may run
 * against an isolated test database holding production-derived records. The
 * qualified copy below separates the two — what you SEE is synthetic; what the
 * deployment may DO is a read-only, aggregate-only diagnostic — and states the
 * bounds of the second. The compact wording here is substantively equivalent to
 * the full paragraph on Governance & Safety → Policy; keep them in step.
 *
 * ONE LINE, SCOPED TO THE WORKSPACE (2026-10-12 clutter audit). The paragraph
 * above described two things — the workspace a reader sees, and a diagnostic the
 * deployment may run — in six lines at the top of an on-ramp whose job is to offer
 * a worked example. Measured across the app, the diagnostic was stated on five
 * surfaces and the upload refusal on eight. The banner now states ONLY the
 * workspace half, in one line, and points at the policy for the rest:
 *
 *   ~~"…and real SLAC/SSRL or private artifacts require written data-governance
 *   approval… Separately, this deployment may run a protected, read-only
 *   diagnostic… Database-backed record display remains disabled pending an
 *   explicit visibility decision."~~
 *
 * WHY DROPPING THE DIAGNOSTIC HALF IS NOT AN UNDER-DISCLOSURE. The rule
 * `db-recon-truthfulness.test.tsx` enforces is that a surface which NAMES the
 * diagnostic must state every bound of it; naming it without its bounds is the
 * over-claim. A surface scoped to the workspace makes no statement about the
 * diagnostic at all, so it owes no bounds — and the capability with all seven of
 * its bounds is stated where it belongs, on the policy this banner links to and in
 * the Help popover. What this banner must still never do is describe the
 * DEPLOYMENT as synthetic: it says "the records shown here", which is the
 * workspace, and that test keeps the qualifier in its place.
 *
 * Wording constraints that are load-bearing, not style, for any surface that DOES
 * name the diagnostic:
 *  - "may run" / "is configured to", never "is running" or "is connected":
 *    configuration is not reachability, and nothing here measures either.
 *  - "isolated SLAC test database containing production-derived records",
 *    never "the production database" — this app has no production access.
 *  - the app does NOT verify that isolation; the guarantee is an external
 *    pg_hba grant, so nothing here may claim the app checked it.
 */
export function GovernanceBanner({ onReadPolicy }: GovernanceBannerProps) {
  return (
    <div className="gov-banner" role="note">
      <ShieldCheck className="gov-icon" size={18} strokeWidth={2} aria-hidden="true" />
      <p className="gov-body">
        <strong>Synthetic workspace.</strong> The records shown here are synthetic and uploads are
        disabled.
      </p>
      <button type="button" className="gov-action" onClick={onReadPolicy}>
        {LABELS.actionReadPolicy}
      </button>
    </div>
  );
}
