import './chrome.css';
import { ShieldCheck } from './icons';
import { LABELS } from '../lib/labels';

interface GovernanceBannerProps {
  onReadPolicy?: () => void;
}

/**
 * The synthetic-only / no-real-data policy notice. Protective, not alarming —
 * neutral slate, shield icon, NOT red. Explains ("real data needs written
 * approval"); never scolds, never offers a "proceed with real data" shortcut.
 */
export function GovernanceBanner({ onReadPolicy }: GovernanceBannerProps) {
  return (
    <div className="gov-banner" role="note">
      <ShieldCheck className="gov-icon" size={18} strokeWidth={2} aria-hidden="true" />
      <p className="gov-body">
        <strong>Synthetic mode.</strong> Only synthetic or approved data may be loaded. Real
        SLAC/SSRL or private artifacts require written data-governance approval before they can be
        read, indexed, or sent to any model.
      </p>
      <button type="button" className="gov-action" onClick={onReadPolicy}>
        {LABELS.actionReadPolicy}
      </button>
    </div>
  );
}
