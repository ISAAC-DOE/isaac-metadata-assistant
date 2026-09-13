import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { DocumentTitle } from './lib/useDocumentTitle';
import { ROUTE_PATTERNS, ROUTES } from './lib/routes';
import { ExperimentsHome } from './screens/ExperimentsHome';
import { HistoricalImport } from './screens/HistoricalImport';
import { LoadMaterials } from './screens/LoadMaterials';
import { RecordWorkbench } from './screens/RecordWorkbench';
import { GuidedCompletion } from './screens/GuidedCompletion';
import { EvidenceExplorer } from './screens/EvidenceExplorer';
import { ExportReadiness } from './screens/ExportReadiness';
import { ProjectMemory } from './screens/ProjectMemory';
import { GovernancePage } from './screens/GovernancePage';
import { StatisticsPage } from './screens/statistics/StatisticsPage';
import { SettingsPage } from './screens/SettingsPage';
import { NotFound } from './screens/NotFound';

/** The route table. Record sub-surfaces (complete/evidence/export) are nested
 * under /record/:id. Exported separately so tests can mount it under a router. */
export function AppRoutes() {
  return (
    <>
      {/*
        WCAG 2.4.2 *Page Titled*. `<DocumentTitle />` MUST stay an EARLIER
        SIBLING of `<Routes />`: React flushes effects in tree order, so this
        writes the route-derived title first and a screen's `useDocumentTitle`
        refinement (today only the record screen, which adds the record's name
        once its bundle has loaded) overwrites it in the same commit. Swapping
        these two lines silently reverses that precedence.
        `lib/useDocumentTitle.ts` carries the full reasoning;
        `__tests__/document-title.test.tsx` pins the outcome rather than the
        ordering, which is the property that actually matters.
      */}
      <DocumentTitle />
      <Routes>
        <Route path="/" element={<Navigate to={ROUTES.experiments} replace />} />
        <Route path={ROUTE_PATTERNS.experiments} element={<ExperimentsHome />} />
        <Route path={ROUTE_PATTERNS.imports} element={<HistoricalImport />} />
        <Route path={ROUTE_PATTERNS.load} element={<LoadMaterials />} />
        <Route path={ROUTE_PATTERNS.record} element={<RecordWorkbench />} />
        <Route path={ROUTE_PATTERNS.complete} element={<GuidedCompletion />} />
        <Route path={ROUTE_PATTERNS.evidence} element={<EvidenceExplorer />} />
        <Route path={ROUTE_PATTERNS.export} element={<ExportReadiness />} />
        <Route path={ROUTE_PATTERNS.memory} element={<ProjectMemory />} />
        <Route path={ROUTE_PATTERNS.governance} element={<GovernancePage />} />
        <Route path={ROUTE_PATTERNS.statistics} element={<StatisticsPage />} />
        <Route path={ROUTE_PATTERNS.settings} element={<SettingsPage />} />
        {/*
          QA-020 — AN HONEST NOT-FOUND STATE, replacing a silent redirect.

          This was `<Navigate to={ROUTES.experiments} replace />`, so every
          unrecognised path became My Experiments with NO message, and `replace`
          erased the attempted URL so Back could not recover it. Found by
          navigating hosted `/krish/validator`.

          `/` above still redirects, and that is deliberate: the site root is a
          recognised address with an obvious destination, whereas an
          unrecognised one is a question only the reader can answer.

          Measured before changing it: over ~175 shipped non-test files, literal
          `to=`/`href=` targets outside the ten legitimate routes = 0, and
          template-literal targets = 0 — all navigation goes through `ROUTES`
          helpers. So this screen FIXES a defect rather than surfacing a pile of
          broken internal links.
        */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
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
