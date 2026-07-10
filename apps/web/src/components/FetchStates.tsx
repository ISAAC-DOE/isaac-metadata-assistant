import './fetchstates.css';
import { TriangleAlert } from './icons';
import { RUN_COMMAND } from '../lib/api';
import type { ApiError } from '../lib/api';

/** Calm inline loading state — a processing dot + a label. */
export function LoadingPanel({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="fetch-state" role="status" aria-live="polite">
      <span className="dot dot-processing" aria-hidden="true" />
      <span className="fetch-state-label">{label}</span>
    </div>
  );
}

/**
 * The honest failure state. A network failure (`unreachable`) shows the exact
 * command to start the local backend — never fabricated data. A 404 is a
 * missing record, a distinct message. Nothing here implies a verdict.
 */
export function BackendDown({ error, onRetry }: { error?: ApiError; onRetry?: () => void }) {
  const notFound = error?.status === 404;
  const title = notFound ? 'Record Not Found' : 'Backend Not Running';
  return (
    <div className="fetch-state error" role="alert">
      <span className="fetch-state-icon" aria-hidden="true">
        <TriangleAlert size={22} strokeWidth={2.2} />
      </span>
      <div className="fetch-state-body">
        <h2 className="fetch-state-title">{title}</h2>
        {notFound ? (
          <p className="fetch-state-text">
            This experiment id is not in the local workspace — it may not have been created yet.
          </p>
        ) : (
          <>
            <p className="fetch-state-text">
              The local ISAAC API is not responding. This prototype reads only server-derived
              truth — it will never show placeholder data. Start the backend, then retry:
            </p>
            <pre className="fetch-state-cmd mono">{RUN_COMMAND}</pre>
          </>
        )}
        {onRetry && (
          <button type="button" className="btn btn-secondary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
