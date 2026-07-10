import './screens.css';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { Network } from '../components/icons';
import { LABELS } from '../lib/labels';

/**
 * Project Memory — a deliberately separate destination from the experiment queue
 * (never blended into S1). This is the memory/query plane (Graphify + docs);
 * it returns leads to verify, never verdicts. Minimal placeholder for this build.
 */
export function ProjectMemory() {
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
          <span className="dot dot-memory" aria-hidden="true" />
          <span className="mono" style={{ fontSize: 12, color: 'var(--text-slate)' }}>
            project memory: fresh
          </span>
          <p>
            Search across records, evidence, and project memory from the top bar (<span className="mono">⌘K</span>).
            Graphify is a memory plane, not a truth plane — every lead points back to a cited file to
            confirm.
          </p>
        </div>
        <p style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-tertiary)' }}>
          <Network size={15} strokeWidth={2} aria-hidden="true" />
          Browse depth is out of scope for this first build.
        </p>
      </div>
    </AppShell>
  );
}
