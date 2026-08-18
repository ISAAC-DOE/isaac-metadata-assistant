import './runner.css';
import { Check, Circle, CircleAlert } from './icons';
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
 * the same never-set flag.
 *
 * AND REMOVING IT LEFT A REAL DEFECT, WHICH THIS PARAGRAPH USED TO DENY. It said
 * "every stage now renders `done` or `upcoming` from the server's own `ok`, which is
 * the only signal the API supplies". The first half was false. `demoStepsToStages`
 * mapped `ok: false` to `current`, the `cls` line below collapsed `current` into
 * `done`, and `done` renders `Check` — this app's success glyph (`icons.tsx` binds
 * `Check` to both `verified` and `pass`). So a FAILING step got a tick, beside its
 * own failure text: the API's `detail` for those steps is literally
 * "draft ok: false" and "official schema valid: False" (`routes.py`). The failure
 * signal was computed and discarded, and the sentence claiming otherwise made it
 * harder to see.
 *
 * There is now a fourth state, `failed`, produced from `ok` and rendered with
 * `CircleAlert` and its own class. It is deliberately NOT folded into `upcoming`
 * either: "has not run yet" and "ran and failed" are different facts, and a reader
 * who cannot tell them apart cannot act. Pinned by
 * `__tests__/staged-runner-dead-control.test.tsx`.
 */
export function StagedRunner({ stages }: StagedRunnerProps) {
  return (
    <div className="runner">
      {stages.map((stage) => {
        // `current` still reads as `done` — an in-flight step has genuinely got
        // that far — but `failed` is its own class and never borrows the tick.
        const cls =
          stage.state === 'failed'
            ? 'failed'
            : stage.state === 'done' || stage.state === 'current'
              ? 'done'
              : 'upcoming';
        return (
          <div className={`stage ${cls}`} key={stage.key}>
            <span className="stage-disc" aria-hidden="true">
              {cls === 'done' && <Check size={13} strokeWidth={2.4} />}
              {cls === 'upcoming' && <Circle size={12} strokeWidth={2} />}
              {cls === 'failed' && <CircleAlert size={13} strokeWidth={2.4} />}
            </span>
            <div className="stage-main">
              <div className="stage-label">
                {/*
                  THE GLYPH IS `aria-hidden`, SO THE STATE NEEDS TEXT. Without this
                  the whole fix would have been sighted-only: a screen reader got the
                  label, the command and the detail, but nothing saying the step
                  failed — and the detail strings the API sends ("draft ok: false")
                  are not reliably self-explanatory read aloud in isolation.
                  Only the failure is announced; "passed" is the unremarkable case
                  and announcing it on every step would bury the one that matters.
                */}
                {stage.state === 'failed' && <span className="sr-only">Failed: </span>}
                {stage.label}
              </div>
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
