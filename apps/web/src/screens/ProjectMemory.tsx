import './screens.css';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Network } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';

/**
 * Project Memory — a deliberately separate destination from the experiment queue
 * (never blended into S1). This is the memory/query plane (Graphify + docs);
 * it returns leads to verify, never verdicts. Minimal placeholder for this build.
 * The freshness readout is live from `GET /api/graph/status` — never a
 * hardcoded claim.
 */
export function ProjectMemory() {
  const graph = useFetch(() => api.getGraphStatus(), []);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="memory" />}
      mainPad="pad"
    >
      <div className="placeholder">
        <span className="eyebrow">Memory / Query Plane</span>
        <h2>{LABELS.navMemory}</h2>
        <p>
          Project Memory is the assistant's memory and navigation surface — Graphify plus project
          docs. It is deliberately separate from the experiment queue and never appears inside it. It
          surfaces related records, prior documents, and "how is this connected?" answers as leads to
          verify — it never validates, completes, or supplies a value.
        </p>
        <div className="card placeholder-card">
          {graph.status === 'loading' && <LoadingPanel label="Checking memory status…" />}
          {graph.status === 'error' && <BackendDown error={graph.error} onRetry={graph.reload} />}
          {graph.status === 'data' && (
            <>
              <GraphStatusChip status={graph.data.status} note={graph.data.note} />
              <p>
                Graphify is a memory plane, not a truth plane — every lead points back to a cited
                file to confirm.
              </p>
            </>
          )}
        </div>
        <p style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-tertiary)' }}>
          <Network size={15} strokeWidth={2} aria-hidden="true" />
          Browse depth is out of scope for this first build.
        </p>
      </div>
    </AppShell>
  );
}
