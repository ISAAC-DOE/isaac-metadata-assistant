/**
 * Settings → Integrations → the API Access widget (2026-10-12; it was the whole
 * API Access tab before that — P36V PR3 slice C, restructured by P36V-1 slices
 * 11 & 13).
 *
 * This surface exists to tell the truth about a capability this build does NOT
 * have. The backend audit that decided its content:
 *
 *   `apps/api/isaac_api/auth.py` is a single process-wide shared credential read
 *   from one environment variable at construction time and compared with
 *   `secrets.compare_digest` on every request except `GET {base}/api/health` and
 *   `OPTIONS`. There is no per-key identity, no hashed storage, no expiry, no
 *   scopes, and — confirmed by grepping the whole of `apps/api` — no operation
 *   anywhere that creates, lists, revokes or rotates a credential. The generated
 *   contract the Endpoint Explorer renders is the proof: it lists every
 *   operation this API has, and none of them is key management.
 *
 * So the classification is UNAVAILABLE, and the widget states it as a STATE:
 *
 *   · the headline says there are no API keys in this build, once;
 *   · ONE line says what credential does exist and that this page sends none;
 *   · no key is ever generated, displayed, or partially displayed;
 *   · nothing is read from or written to `localStorage`, `sessionStorage`, or a
 *     cookie — this module contains no storage or cookie access at all;
 *   · there is no input, no field, and NO CONTROL THAT CANNOT FUNCTION.
 *
 * ── WHAT WAS REMOVED, AND WHY IT IS A REMOVAL OF A CONTROL, NOT OF A CLAIM ──
 *
 * The retired tab said "no keys / not available" SIX times: a status heading
 * and its paragraph, a really-`disabled` "Create API Key" button with its own
 * reason, and an intentional empty "Your API Keys" list with a title and a
 * body. The button and the list are gone. A disabled button says "this exists,
 * you may not use it" — the opposite of the truth — and a list that can never
 * hold an item is the same absence restated. The CLAIM they all made is kept,
 * stated once by the headline, with its proof (`statusBody`) behind the info
 * toggle. Real key management is still deliberately NOT stubbed.
 *
 * ── WHERE EVERYTHING ELSE WENT ─────────────────────────────────────────────
 *
 *   · Quick Start and the Program an Agent guide are the widget's two VIEWS,
 *     closed until a reader chooses one; both stay mounted (`hidden`).
 *   · How Access Works Today (the five access rows) and the Technical
 *     Requirements are the widget's Details.
 *
 * LANDMARKS. The widget is one named region; Quick Start's section keeps its
 * own name inside it. Nothing else here is a landmark.
 */
import { useState, type ReactNode } from 'react';

import { Widget, widgetIds } from '../../components/Widget';
import { LoadingPanel, BackendDown } from '../../components/FetchStates';
import { ChevronRight, FileText, Lock, Play } from '../../components/icons';
import {
  API_ACCESS_COPY,
  API_ACCESS_ROWS,
  API_KEY_REQUIREMENTS,
  SETTINGS_WIDGET_COPY as COPY,
} from '../../lib/settingsContent';
import type { ApiOpenApiResponse } from '../../lib/types';
import type { useFetch } from '../../lib/useFetch';
import { ApiProgramAgentView, ApiQuickStartView } from './ApiDocs';

type OpenApiState = ReturnType<typeof useFetch<ApiOpenApiResponse>>;

/** The widget heading's id — also the region's accessible name. */
export const API_WIDGET_HEADING_ID = 'settings-apiaccess-heading';

export function ApiKeysPanel({
  state,
  onOpenExplorer,
}: {
  /** The page-level `GET /api/openapi` read — the two views are derived from it. */
  state: OpenApiState;
  onOpenExplorer: () => void;
}) {
  const [view, setView] = useState<string | null>(null);

  /** Quick Start's "Program an Agent" jump: switch views in place, and move
   *  focus to the control that now says which view is open. */
  function openProgram() {
    setView('program');
    (document.getElementById(widgetIds.tab(API_WIDGET_HEADING_ID, 'program')) as HTMLElement | null)?.focus();
  }

  /** A view that needs the contract waits for it, honestly, inside the view. */
  function contractBody(render: (schema: ApiOpenApiResponse) => ReactNode) {
    if (state.status === 'loading') return <LoadingPanel label="Loading the API contract…" />;
    if (state.status === 'error') return <BackendDown error={state.error} onRetry={state.reload} />;
    return render(state.data);
  }

  /* The two reference views — `Widget`'s toggle-button switcher, controlled here
     so Quick Start's "Program an Agent" jump can switch views in place. */
  const views = [
    {
      id: 'quick-start',
      label: COPY.apiViewQuickStart,
      icon: <Play size={14} strokeWidth={2} />,
      content: contractBody((schema) => (
        <ApiQuickStartView
          schema={schema}
          onOpenExplorer={onOpenExplorer}
          onOpenProgram={openProgram}
        />
      )),
    },
    {
      id: 'program',
      label: COPY.apiViewProgram,
      icon: <FileText size={14} strokeWidth={2} />,
      content: contractBody((schema) => (
        <ApiProgramAgentView schema={schema} onOpenExplorer={onOpenExplorer} />
      )),
    },
  ];

  return (
    <Widget
      id={API_WIDGET_HEADING_ID}
      title={COPY.apiTitle}
      icon={<Lock size={18} strokeWidth={2} />}
      sub={COPY.apiSub}
      info={<p>{API_ACCESS_COPY.statusBody}</p>}
      headline={
        <h3 className="widget-state settings-state-heading">{API_ACCESS_COPY.statusHeading}</h3>
      }
      details={{
        summary: COPY.apiHowAccessWorks,
        content: (
          <>
            <dl className="settings-defs">
              {API_ACCESS_ROWS.map((row) => (
                <div className="settings-def" key={row.term}>
                  <dt>{row.term}</dt>
                  <dd>{row.detail}</dd>
                </div>
              ))}
            </dl>
            <h3 className="settings-view-heading">{COPY.apiTechnicalRequirements}</h3>
            <p className="settings-view-note">{API_ACCESS_COPY.requirementsNote}</p>
            <ul className="settings-steps">
              {API_KEY_REQUIREMENTS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {/* FINDING E — the requirement that is NOT the application's, so the
                five app-owned ones are not read as the whole path to shipping. */}
            <p className="settings-view-note">{API_ACCESS_COPY.requirementsBoundary}</p>
          </>
        ),
      }}
      viewSwitcher="buttons"
      collapsible
      view={view}
      onViewChange={setView}
      onViewCollapse={() => setView(null)}
      views={views}
      footer={
        <button type="button" className="settings-jump-btn" onClick={onOpenExplorer}>
          Endpoint Explorer
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
      }
    >
      <p className="settings-state-line">{API_ACCESS_COPY.credentialLine}</p>

    </Widget>
  );
}
