import './signals.css';
import { CHIP_META, type ChipKind } from '../lib/status';
import { CHIP_ICON } from './icons';

interface StatusChipProps {
  kind: ChipKind;
  label?: string;
}

/**
 * A per-field / per-record status pill: icon + label, never color alone
 * (status-system.md). `missing` is dashed and honest; `needsYou` is amber,
 * never a red error. Reserved verdict green is used only by `pass`.
 */
export function StatusChip({ kind, label }: StatusChipProps) {
  const meta = CHIP_META[kind];
  const Icon = CHIP_ICON[kind];
  return (
    <span className={`chip ${meta.className}`}>
      <Icon size={13} strokeWidth={2.2} aria-hidden="true" />
      <span>{label ?? meta.label}</span>
    </span>
  );
}
