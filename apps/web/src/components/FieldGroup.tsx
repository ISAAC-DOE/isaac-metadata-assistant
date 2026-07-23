import './fields.css';
import { ChevronDown, ChevronRight } from './icons';
import { StatusChip } from './StatusChip';
import { FieldRow } from './FieldRow';
import type { FieldGroupData } from '../lib/types';

interface FieldGroupProps {
  group: FieldGroupData;
  expanded: boolean;
  onToggle: () => void;
}

/**
 * A record block (system / sample / measurement / assets / descriptors) as a
 * card. Collapsed blocker groups show only the header + an amber "N Needs You"
 * chip, so the draft never turns into a wall of errors. No rail marks a blocker
 * group — the amber chip + summary carry it.
 */
export function FieldGroup({
  group,
  expanded,
  onToggle,
}: FieldGroupProps) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <section className="field-group" aria-label={`${group.block} — ${group.humanLabel}`}>
      <button type="button" className="fg-header" aria-expanded={expanded} onClick={onToggle}>
        <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
        <span className="fg-block">{group.block}</span>
        <span className="fg-sublabel">{group.humanLabel}</span>
        {expanded ? (
          <span className="fg-summary">{group.summary}</span>
        ) : group.needsYouCount > 0 ? (
          <span className="fg-summary" style={{ display: 'inline-flex' }}>
            <StatusChip kind="needsYou" label={`${group.needsYouCount} Needs You`} />
          </span>
        ) : (
          <span className="fg-summary">{group.summary}</span>
        )}
      </button>

      {expanded && (
        <div className="fg-body">
          {group.fields.map((field) => (
            <FieldRow key={field.path} field={field} />
          ))}
        </div>
      )}
    </section>
  );
}
