import './screens.css';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { LABELS } from '../lib/labels';

/** Settings — minimal local config. Not in the first build's critical path. */
export function SettingsPage() {
  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="settings" />}
      mainPad="pad"
    >
      <div className="placeholder">
        <span className="eyebrow">Local Configuration</span>
        <h2>{LABELS.navSettings}</h2>
        <p>
          Local, offline settings only — no telemetry, no analytics, no cloud sync. The data regime
          is fixed to synthetic in this build. Minimal placeholder for the first build.
        </p>
        <div className="card placeholder-card">
          <span className="mono" style={{ fontSize: 12, color: 'var(--text-slate)' }}>
            {LABELS.version}
          </span>
          <p>local · offline · no telemetry</p>
        </div>
      </div>
    </AppShell>
  );
}
