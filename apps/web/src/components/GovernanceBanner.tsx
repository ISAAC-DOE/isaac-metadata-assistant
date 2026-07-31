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
 * Wording constraints that are load-bearing, not style:
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
        <strong>Synthetic workspace.</strong> The records shown here are synthetic, uploads are
        disabled, and real SLAC/SSRL or private artifacts require written data-governance approval
        before they can be read, indexed, or sent to any model. Separately, this deployment may run
        a protected, read-only diagnostic against an isolated SLAC test database containing
        production-derived records: those records are processed transiently in pod memory, only
        sanitized aggregate results are returned, no record is modified, no per-record content is
        displayed, and nothing is sent to any model. Database-backed record display remains
        disabled pending an explicit visibility decision.
      </p>
      <button type="button" className="gov-action" onClick={onReadPolicy}>
        {LABELS.actionReadPolicy}
      </button>
    </div>
  );
}
