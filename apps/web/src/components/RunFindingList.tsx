import './runs.css';
import { runFindingText } from '../lib/runFields';
import type { ApiRunCheckFinding } from '../lib/types';

/**
 * ONE list of findings, rendered ONE way — moved here out of `RunCard` rather
 * than copied, because two surfaces now render the SAME server payload.
 *
 * `RunCard`'s Check Run and the experiment-level `ValidateReview` both show
 * `POST …/runs/{id}/check`'s `blockers`, `draft.errors` and `draft.warnings`.
 * Those are the same `ApiRunCheckFinding` union from the same route, and a second
 * renderer beside this one would be free to drift from it — including on the one
 * behaviour below that exists because it was got wrong once (a finding this build
 * cannot describe is COUNTED and SHOWN, never dropped, because dropping it
 * silently shrinks the number of things standing between a run and a valid
 * record).
 *
 * IT COMPUTES NOTHING. No severity is decided here, no verdict is derived, and no
 * message is composed: the caller supplies the heading that says whether these
 * findings gate anything, and every row is the server's own text.
 *
 * `titleAs` defaults to `'p'`, which is exactly what `RunCard` rendered before the
 * move, so that card's markup is byte-for-byte unchanged. `ValidateReview` passes
 * `'h4'`: its groups are `h3`, so a `p` there would leave a findings block with no
 * heading for a screen reader to navigate to.
 */
export function FindingList({
  title,
  findings,
  titleAs = 'p',
}: {
  title: string;
  findings: ApiRunCheckFinding[];
  titleAs?: 'p' | 'h4';
}) {
  if (findings.length === 0) return null;
  const Title = titleAs;
  return (
    <div className="run-check-group">
      <Title className="run-check-group-title">
        {title} · {findings.length}
      </Title>
      <ul className="run-check-list">
        {findings.map((finding, i) => {
          const text = runFindingText(finding);
          return (
            <li
              key={i}
              className={text === null ? 'run-check-item run-check-item-opaque' : 'run-check-item'}
            >
              {/* A finding this build cannot describe is still COUNTED and still
                  shown. Dropping it would quietly shrink the number of things
                  standing between this run and a valid record. */}
              {text ?? 'The server reported a finding this build cannot describe.'}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
