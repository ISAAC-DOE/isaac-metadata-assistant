import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ROUTE_PATTERNS, ROUTES } from './lib/routes';
import { ExperimentsHome } from './screens/ExperimentsHome';
import { LoadMaterials } from './screens/LoadMaterials';
import { RecordWorkbench } from './screens/RecordWorkbench';
import { GuidedCompletion } from './screens/GuidedCompletion';
import { EvidenceExplorer } from './screens/EvidenceExplorer';
import { ExportReadiness } from './screens/ExportReadiness';
import { ProjectMemory } from './screens/ProjectMemory';
import { GovernancePage } from './screens/GovernancePage';
import { StatisticsPage } from './screens/statistics/StatisticsPage';
import { SettingsPage } from './screens/SettingsPage';

/** The route table. Record sub-surfaces (complete/evidence/export) are nested
 * under /record/:id. Exported separately so tests can mount it under a router. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={ROUTES.experiments} replace />} />
      <Route path={ROUTE_PATTERNS.experiments} element={<ExperimentsHome />} />
      <Route path={ROUTE_PATTERNS.load} element={<LoadMaterials />} />
      <Route path={ROUTE_PATTERNS.record} element={<RecordWorkbench />} />
      <Route path={ROUTE_PATTERNS.complete} element={<GuidedCompletion />} />
      <Route path={ROUTE_PATTERNS.evidence} element={<EvidenceExplorer />} />
      <Route path={ROUTE_PATTERNS.export} element={<ExportReadiness />} />
      <Route path={ROUTE_PATTERNS.memory} element={<ProjectMemory />} />
      <Route path={ROUTE_PATTERNS.governance} element={<GovernancePage />} />
      <Route path={ROUTE_PATTERNS.statistics} element={<StatisticsPage />} />
      <Route path={ROUTE_PATTERNS.settings} element={<SettingsPage />} />
      <Route path="*" element={<Navigate to={ROUTES.experiments} replace />} />
    </Routes>
  );
}

/** Router basename from Vite's base ('/' locally and under vitest; '/krish/'
 * in the deployed build). Trailing slash stripped: '' means no basename. */
const BASENAME = import.meta.env.BASE_URL.replace(/\/+$/, '');

export default function App() {
  return (
    <BrowserRouter
      basename={BASENAME}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </BrowserRouter>
  );
}
