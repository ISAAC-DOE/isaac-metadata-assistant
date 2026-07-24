import './fields.css';
import { StatusChip } from './StatusChip';
import { EvidenceRow } from './EvidenceRow';
import { fieldChipKind } from '../lib/status';
import type { DraftField } from '../lib/types';

interface FieldRowProps {
  field: DraftField;
}

/**
 * One field in the envelope shape {value, unit?, status, evidence[]}, with a
 * route to its evidence. Missing/needs-you read honest and expected — never a
 * red error. No value is shown without a path to its evidence.
 */
export function FieldRow({ field }: FieldRowProps) {
  const kind = fieldChipKind(field.status, field.source_types);
  const needsYou = field.status === 'needs_confirmation';
  const missing = field.status === 'missing' || field.status === 'rejected';

  return (
    <div className="field-row">
      <div className="field-label-col">
        <div className="field-label">{field.label}</div>
        <div className="field-path">{field.path}</div>
      </div>

      <div className="field-value-col">
        <div className="field-value-row">
          {needsYou || missing ? (
            <span className="field-value awaiting">
              {needsYou ? 'awaiting your confirmation' : 'honestly missing'}
            </span>
          ) : (
            <span className="field-value">
              {String(field.value)}
              {field.unit ? ` ${field.unit}` : ''}
            </span>
          )}
          <StatusChip kind={kind} />
        </div>

        {field.helper && <p className="field-helper">{field.helper}</p>}

        {field.evidence && field.evidence.length > 0 && !needsYou && (
          <div className="field-evidence">
            {field.evidence.map((ev, i) => (
              <EvidenceRow evidence={ev} key={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
