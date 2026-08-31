import './fields.css';
import { StatusChip } from './StatusChip';
import { EvidenceRow } from './EvidenceRow';
import { FieldCaptureControl, canEnterOnRecord, captureHint } from './FieldCaptureControl';
import { fieldChipKind } from '../lib/status';
import type { DraftField } from '../lib/types';

interface FieldRowProps {
  field: DraftField;
  /**
   * How a value may be entered on THIS record, when the screen can offer it.
   *
   * Absent means this row is read-only wherever it is mounted — which is what every
   * mount that is not the record workbench gets, deliberately: a control needs the
   * record's id and its current version token, and a screen that does not hold both
   * cannot write. It is a prop rather than a context for that reason; the capability
   * is the caller's to grant, not this row's to assume.
   */
  capture?: {
    experimentId: string;
    /** The RECORD's current version token — both write operations here are the record's. */
    version: string;
    /** MUST be the SILENT refetch. See `FieldCaptureControl`'s `onSaved`. */
    onSaved: () => void;
  };
}

/**
 * One field in the envelope shape {value, unit?, status, evidence[]}, with a
 * route to its evidence. Missing/needs-you read honest and expected — never a
 * red error. No value is shown without a path to its evidence.
 *
 * A ROW MAY NOW BE A FIELD THE RECORD DOES NOT HOLD. `GET /draft` returns the group
 * skeleton — a row for every field path this build can extract into or write at — so a
 * created record renders its fields instead of nothing. Such a row carries
 * `present: false` with a `missing` status, and it is rendered exactly as an honestly
 * missing value has always been rendered: no error, no red, no claim that the record
 * holds anything.
 *
 * WHAT IS NEW IS THE SENTENCE UNDER IT, and it is per path rather than true on average.
 * Either the row offers a control (only where a RECORD-level route accepts a value and
 * the schema's own closed set arrived with it) or it says where the value is entered —
 * or that this version records none. The decision is `FieldCaptureControl`'s, from facts
 * the server derives from the sets its write routes enforce; nothing about writability
 * is decided here.
 */
export function FieldRow({ field, capture }: FieldRowProps) {
  const kind = fieldChipKind(field.status, field.source_types);
  const needsYou = field.status === 'needs_confirmation';
  const missing = field.status === 'missing' || field.status === 'rejected';
  const offering = canEnterOnRecord(field.capture) && capture !== undefined;
  /* The PATH is passed because one of the sentences is true of exactly one path — see
     `captureHint`'s own note on the export stamp. Nothing else about the copy varies by
     path; the rest is composed from the served facts. */
  const hint = captureHint(field.capture, offering, field.path);

  return (
    <div className="field-row" data-present={field.present === false ? 'false' : undefined}>
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

        {/*
          THE CONTROL, OR THE SENTENCE — never both, and never neither when the server
          said something. `capture` being absent is what makes every other mount of this
          row read-only; the hint is still shown there, because "this value is entered on
          a run" is true wherever it is read and costs nothing to say.
        */}
        {offering && capture ? (
          <FieldCaptureControl
            field={field}
            experimentId={capture.experimentId}
            version={capture.version}
            onSaved={capture.onSaved}
          />
        ) : (
          hint !== null && <p className="field-capture-hint">{hint}</p>
        )}
      </div>
    </div>
  );
}
