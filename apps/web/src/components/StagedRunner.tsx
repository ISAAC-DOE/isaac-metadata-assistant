import './runner.css';
import { Check, Circle } from './icons';
import type { RunnerStage } from '../lib/types';

interface StagedRunnerProps {
  stages: RunnerStage[];
}

/**
 * The staged runner: each row maps to the real pipeline stage/command and its
 * returned result. Read-only — it reports what `POST /api/demo/run` returned and
 * offers no control of its own; anything actionable belongs to the screen around
 * it (`screens/LoadMaterials.tsx` renders the "Open the Record" route below).
 *
 * R1b — WHAT WAS REMOVED, and why it could not have worked. A `stage.isBlocker`
 * branch rendered a `btn btn-primary` reading `Answer 5 Fields →`. Three separate
 * things were wrong with it:
 *
 *   1. `isBlocker` was never set by anything. `RunnerStage`'s only producer is
 *      `lib/adapt.ts::demoStepsToStages`, which emits `{key,label,command,state,
 *      detail}`. The flag existed solely on the type.
 *   2. `onAnswer` was never passed. The only call site rendered
 *      `<StagedRunner stages={…} />`, so `onClick` was `undefined` — a primary
 *      button that did nothing when pressed.
 *   3. The `5` was a hard-coded literal, unrelated to the record's actual pending
 *      count.
 *
 * The amber "blocker" stage treatment went with it: it was reachable only through
 * the same never-set flag. Every stage now renders `done` or `upcoming` from the
 * server's own `ok`, which is the only signal the API supplies. Pinned by
 * `__tests__/staged-runner-dead-control.test.tsx`.
 */
export function StagedRunner({ stages }: StagedRunnerProps) {
  return (
    <div className="runner">
      {stages.map((stage) => {
        const cls = stage.state === 'done' || stage.state === 'current' ? 'done' : 'upcoming';
        return (
          <div className={`stage ${cls}`} key={stage.key}>
            <span className="stage-disc" aria-hidden="true">
              {cls === 'done' && <Check size={13} strokeWidth={2.4} />}
              {cls === 'upcoming' && <Circle size={12} strokeWidth={2} />}
            </span>
            <div className="stage-main">
              <div className="stage-label">{stage.label}</div>
              <div className="stage-cmd">{stage.command}</div>
              {stage.detail && <p className="stage-detail">{stage.detail}</p>}
            </div>
            {(stage.result || stage.subResult) && (
              <div className="stage-right">
                {stage.result && <span className="stage-result">{stage.result}</span>}
                {stage.subResult && <span className="stage-subresult">{stage.subResult}</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
