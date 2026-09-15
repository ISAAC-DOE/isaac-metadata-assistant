import './runs.css';
import { runFindingText } from '../lib/runFields';
import {
  composeFindingQuestion,
  findingRunFieldPath,
  findingSubject,
  type AskContext,
  type FindingState,
} from '../lib/findingPresentation';
import { useAssistantAsk } from '../lib/assistantAsk';
import { CornerDownRight, MessageSquare } from './icons';
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
 * ── A ROW IS FOUR PARTS NOW, AND IT USED TO BE ONE SENTENCE ────────────────
 *
 * The project owner, 2026-09-15: *"in regards to the check failed — I don't even
 * know what it's asking. What does it mean? I think you should point to the
 * specific field that it's talking about … it should be simple. And if they want
 * more information, then they can ask the agent."*
 *
 *   1. SUBJECT   what the finding is about — the server's own `kind` through the
 *                ONE vocabulary (`adapt.blockerKindLabel`), or its `path` in
 *                mono. An entry with neither says NOTHING about its subject.
 *   2. STATE     a short word, supplied by the CALLER because the caller is the
 *                one that knows which list this is. See `FindingState`.
 *   3. MESSAGE   the server's own sentence, VERBATIM. Never paraphrased, never
 *                shortened, never re-cased.
 *   4. ACTIONS   `Go to field` only when a real destination exists on this
 *                screen, and `Ask ISAAC` only when a screen has an Assistant
 *                mounted to receive the question.
 *
 * IT STILL COMPUTES NOTHING. No severity is decided here, no verdict is
 * derived, and no message is composed: the caller supplies the heading and the
 * state word, and every row is the server's own text.
 *
 * ── WHAT IT MUST NEVER DO ──────────────────────────────────────────────────
 *
 * `Ask ISAAC` PRE-FILLS the Assistant composer and does not send. There is no
 * language model in any deployment of this build; the resolver is a bounded
 * deterministic intent catalog that refuses honestly when it cannot answer, and
 * nothing here adds a fallback that explains a finding itself. Neither control
 * writes, validates, accepts or submits anything.
 *
 * `titleAs` defaults to `'p'`, which is what `RunCard` rendered before the list
 * moved here. `ValidateReview` passes `'h4'`: its groups are `h3`, so a `p`
 * there would leave a findings block with no heading for a screen reader to
 * navigate to.
 */
export function FindingList({
  title,
  findings,
  titleAs = 'p',
  state,
  ask,
  onGoToField,
}: {
  title: string;
  findings: ApiRunCheckFinding[];
  titleAs?: 'p' | 'h4';
  /**
   * The short word every row in THIS list wears. Required, because a list
   * rendered without one used to be a bare sentence with no state at all —
   * which is the defect this prop exists to close — and because only the
   * caller can say which of the route's four lists it is holding.
   */
  state: FindingState;
  /**
   * What the composed question is allowed to name. Everything in it is read
   * from state the caller already holds; nothing is looked up here.
   */
  ask?: AskContext;
  /**
   * Focus the run-level input for `path` on this screen. Supplied ONLY by a
   * surface that is actually rendering that input — so a `Go to field` control
   * can never point at something that is not there. Omitted ⇒ no such control
   * on any row, which is the honest state for every other caller.
   */
  onGoToField?: (path: string) => void;
}) {
  const askIsaac = useAssistantAsk();
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
          const subject = findingSubject(finding);
          /*
           * THE SUBJECT IS WITHHELD WHEN IT IS THE MESSAGE. `runFindingText`
           * falls back to `finding.path` when there is no prose, so an entry
           * carrying only a path would otherwise render that path twice, once
           * as a heading and once as its own explanation.
           */
          const subjectShown = subject !== null && subject.text !== text ? subject : null;
          const fieldPath = findingRunFieldPath(finding);
          const canGo = onGoToField !== undefined && fieldPath !== null;
          return (
            <li
              key={i}
              className={text === null ? 'run-check-item run-check-item-opaque' : 'run-check-item'}
            >
              <div className="run-check-item-head">
                {subjectShown !== null && (
                  <span
                    className={
                      subjectShown.mono
                        ? 'run-check-item-subject mono'
                        : 'run-check-item-subject'
                    }
                  >
                    {subjectShown.text}
                  </span>
                )}
                <span className="run-check-item-state">{state}</span>
              </div>
              {/* A finding this build cannot describe is still COUNTED and still
                  shown. Dropping it would quietly shrink the number of things
                  standing between this run and a valid record. */}
              <span className="run-check-item-text">
                {text ?? 'The server reported a finding this build cannot describe.'}
              </span>
              {(canGo || askIsaac !== null) && (
                <span className="run-check-item-actions">
                  {/* RENDERED ONLY WHEN THE DESTINATION IS REAL. A row with no
                      run-level field on this screen gets no button at all —
                      not a disabled one, which would still read as an offer. */}
                  {canGo && (
                    <button
                      type="button"
                      className="run-check-item-action"
                      onClick={() => onGoToField(fieldPath)}
                    >
                      <CornerDownRight size={13} strokeWidth={2} aria-hidden="true" />
                      Go to field
                    </button>
                  )}
                  {askIsaac !== null && (
                    <button
                      type="button"
                      className="run-check-item-action"
                      /* The accessible name says WHAT it is about, because six
                         identical "Ask ISAAC" buttons in one list are six
                         controls a screen-reader user cannot tell apart. */
                      aria-label={
                        subjectShown === null
                          ? `Ask ISAAC about this ${state.toLowerCase()} finding`
                          : `Ask ISAAC about ${subjectShown.text}`
                      }
                      onClick={() =>
                        askIsaac(
                          /* `fieldPath` is the SAME value that gates `Go to
                             field` above, so the button and the question cannot
                             disagree about whether this finding names a field.
                             It is what makes the composed question answerable —
                             see `composeFindingQuestion`. */
                          composeFindingQuestion(state, subject, text, ask ?? {}, fieldPath),
                        )
                      }
                    >
                      <MessageSquare size={13} strokeWidth={2} aria-hidden="true" />
                      Ask ISAAC
                    </button>
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
