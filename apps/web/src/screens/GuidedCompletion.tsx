import './screens.css';
import '../components/assistant.css';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine, buildSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { GuidedPrompt } from '../components/GuidedPrompt';
import { StatusChip } from '../components/StatusChip';
import { Check } from '../components/icons';
import { ROUTES } from '../lib/routes';
// S4 stays on committed synthetic sample data this slice; a later task wires it live.
import {
  COMPLETION_CURRENT_INDEX,
  DEMO_TITLE,
  getCompletionAnswers,
  getPendingBlockers,
} from '../lib/mock';

/**
 * S4 · Complete Missing Fields — guided, one-question-at-a-time completion of the
 * fields that block export. Forms-first. "I don't know" leaves the field
 * honestly missing (no invention); the assistant proposes but never fills a value.
 */
export function GuidedCompletion() {
  const navigate = useNavigate();
  const { id = '' } = useParams();
  const pending = getPendingBlockers();
  const answers = getCompletionAnswers();
  const currentIndex = COMPLETION_CURRENT_INDEX;
  const total = pending.length;
  const current = pending[currentIndex];
  const upcoming = pending.slice(currentIndex + 1);
  const remaining = total - answers.length;

  const spine = buildSpine('complete', {
    draft: { meta: '26 fields reviewed' },
    complete: { number: answers.length, meta: `${answers.length} of ${total} answered` },
    export: { meta: `${remaining} fields to go` },
  });

  return (
    <AppShell
      variant="record"
      topBar={<TopBar variant="record" title={DEMO_TITLE} filename="completing blockers" />}
      sidebar={<WorkflowSpine steps={spine} />}
      statusBar={
        <StatusBar
          phase={`${remaining} of ${total} fields still to confirm`}
          note="Export unlocks automatically once every field is confirmed or honestly left missing."
        />
      }
      mainPad="centered"
    >
      <div className="centered-col narrow">
        <div className="completion-header">
          <h1 className="completion-title">Answer 5 Questions to Finish This Record</h1>
          <span className="completion-counter">
            {answers.length} / {total}
          </span>
        </div>

        <div className="progress" role="img" aria-label={`${answers.length} of ${total} answered`}>
          {pending.map((_, i) => (
            <span
              key={i}
              className={`progress-seg${
                i < answers.length ? ' answered' : i === currentIndex ? ' current' : ''
              }`}
            />
          ))}
        </div>

        {answers.map((ans) => (
          <div className="answered-row" key={ans.id}>
            <span className="answered-check" aria-hidden="true">
              <Check size={13} strokeWidth={2.6} />
            </span>
            <span className="answered-label">{ans.label}</span>
            <span className="answered-stored">stored {ans.storedValue}</span>
            <span className="answered-trailing">
              <StatusChip kind="confirmed" />
              <button type="button" className="answered-edit">
                Edit
              </button>
            </span>
          </div>
        ))}

        <div style={{ marginTop: 10 }}>
          <GuidedPrompt blocker={current} index={currentIndex} total={total} />
        </div>

        {upcoming.map((blocker, i) => (
          <div className="upcoming-row" key={blocker.id}>
            <span className="upcoming-num" aria-hidden="true">
              {currentIndex + 2 + i}
            </span>
            <span className="upcoming-label">{blocker.question}</span>
            <span className="upcoming-path">{blocker.path}</span>
          </div>
        ))}

        <div style={{ marginTop: 18 }}>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(ROUTES.record(id))}>
            ← Back to Review Record
          </button>
        </div>
      </div>
    </AppShell>
  );
}
