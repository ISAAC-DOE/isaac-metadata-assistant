import './queue.css';
import { ExperimentRow } from './ExperimentRow';
import type { QueueGroup, QueueGroupKey } from '../lib/types';

interface ExperimentQueueProps {
  groups: QueueGroup[];
}

const GROUP_DOT: Record<QueueGroupKey, string> = {
  needsAttention: 'dot-attention',
  inReview: 'dot-review',
  ready: 'dot-ready',
  done: 'dot-idle',
};

/**
 * Every record/draft grouped by the state that says what to do next. Empty
 * groups are hidden (upstream). Group membership is derived, never a hand-set
 * flag; no aggregate health score, trend chart, or gauge.
 */
export function ExperimentQueue({ groups }: ExperimentQueueProps) {
  return (
    <div className="queue">
      {groups.map((group) => (
        <section
          className="queue-group"
          key={group.key}
          aria-label={`${group.label}, ${group.count}`}
        >
          <div className="queue-group-head">
            <span className={`dot ${GROUP_DOT[group.key]}`} aria-hidden="true" />
            <span className="queue-group-label">{group.label}</span>
            <span className="queue-group-count">{group.count}</span>
          </div>
          <div className="queue-rows">
            {group.rows.map((exp) => (
              <ExperimentRow exp={exp} key={exp.id} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
