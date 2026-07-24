import './screens.css';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { GovernanceBanner } from '../components/GovernanceBanner';
import { LABELS } from '../lib/labels';

/** Governance & Safety — the synthetic-only policy as a destination. Minimal
 * placeholder for this build; the banner also appears inline on Load Materials. */
export function GovernancePage() {
  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="governance" />}
      mainPad="pad"
    >
      <div className="placeholder">
        <span className="eyebrow">Data Governance</span>
        <h1>{LABELS.navGovernance}</h1>
        <p>
          This prototype is synthetic-only by default. Real SLAC/SSRL or private artifacts require
          written data-governance approval before they can be read, indexed, or sent to any model.
          Nothing is uploaded to a model or index without that approval — a real-looking file is
          intercepted here and nothing is extracted.
        </p>
        <div style={{ marginTop: 18 }}>
          <GovernanceBanner />
        </div>
      </div>
    </AppShell>
  );
}
