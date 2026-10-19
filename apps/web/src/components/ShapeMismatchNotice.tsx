import './confirmed-answers.css';
import type { ShapeFinding } from '../lib/mutationErrors';

/**
 * WHAT THE OFFICIAL SCHEMA REFUSED IN A STRUCTURED ANSWER, part by part (QA audit A-03).
 *
 * The server checks a reduced spectrum or a descriptor against the official ISAAC
 * schema's own rule for its field when it is answered or corrected, and refuses with
 * `422 official_shape_mismatch` naming each failing record path and quoting the
 * schema's message. Before that check existed the same value was accepted and failed
 * only at export, as raw validator text, after the scientist had moved on.
 *
 * EVERY MESSAGE IS RENDERED VERBATIM (DEC-30/DEC-35) — the schema's words, never a
 * paraphrase — with its record path beside it. A message the server ended early says
 * so rather than reading as complete. The opening sentence claims only what the 422
 * guarantees: nothing was written. It deliberately does NOT call the record invalid —
 * this is a check of one value's shape, not a verdict on the record.
 */
export function ShapeMismatchNotice({
  findings,
  more,
  correcting,
}: {
  findings: ShapeFinding[];
  /** At least one more part does not fit than is listed. No count is claimed: the
   *  server stops looking one past what it reports. */
  more: boolean;
  /** A correction keeps the value already stored; an answer leaves the question open. */
  correcting: boolean;
}) {
  return (
    <div
      className="completion-submit-error shape-mismatch"
      role="alert"
      data-testid="shape-mismatch-notice"
    >
      <p className="shape-mismatch-lead">
        {correcting
          ? 'That correction was not applied — the official ISAAC schema does not accept this shape for this field, so nothing was written and the stored value is unchanged.'
          : 'That answer was not applied — the official ISAAC schema does not accept this shape for this field, so nothing was written and the question is still open.'}{' '}
        Fix the parts below and confirm again.
      </p>
      <ul className="shape-mismatch-list">
        {findings.map((f, i) => (
          <li key={`${f.path}-${i}`}>
            <code className="mono shape-mismatch-path">{f.path}</code>{' '}
            <span className="shape-mismatch-message">
              {f.message}
              {f.message_truncated && ' … (message shortened by the server)'}
            </span>
          </li>
        ))}
      </ul>
      {more && (
        <p className="shape-mismatch-more">
          More parts do not fit than the {findings.length} listed; fix these and confirm
          again to see the rest.
        </p>
      )}
    </div>
  );
}
