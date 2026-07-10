import './runner.css';
import { Check, CircleAlert, Circle } from './icons';
import type { RunnerStage } from '../lib/types';

interface StagedRunnerProps {
  stages: RunnerStage[];
  onAnswer?: () => void;
}

/**
 * The staged runner: each row maps to the real pipeline stage/command and its
 * returned result. The current blocker stage is amber "needs you" (the product
 * working as intended), never faked-forward or styled red.
 */
export function StagedRunner({ stages, onAnswer }: StagedRunnerProps) {
  return (
    <div className="runner">
      {stages.map((stage) => {
        const cls =
          stage.isBlocker && stage.state === 'current'
            ? 'blocker'
            : stage.state === 'done'
              ? 'done'
              : stage.state === 'current'
                ? 'done'
                : 'upcoming';
        return (
          <div className={`stage ${cls}`} key={stage.key}>
            <span className="stage-disc" aria-hidden="true">
              {cls === 'done' && <Check size={13} strokeWidth={2.4} />}
              {cls === 'blocker' && <CircleAlert size={14} strokeWidth={2.2} />}
              {cls === 'upcoming' && <Circle size={12} strokeWidth={2} />}
            </span>
            <div className="stage-main">
              <div className="stage-label">{stage.label}</div>
              <div className="stage-cmd">{stage.command}</div>
              {stage.detail && <p className="stage-detail">{stage.detail}</p>}
              {stage.isBlocker && (
                <div className="stage-cta">
                  <button type="button" className="btn btn-primary" onClick={onAnswer}>
                    Answer 5 Fields →
                  </button>
                </div>
              )}
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
