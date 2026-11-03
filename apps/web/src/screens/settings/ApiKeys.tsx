/**
 * 2026-11-02 (owner's direction: no standing disclaimers): API Access shows ONE
 * plain state line and ONE disclosure holding Quick Start and Program an Agent in
 * sequence. ~~The view buttons, "How Access Works Today", the key-requirement list
 * and the footer Endpoint Explorer jump~~ are retired; the explorer is on Advanced,
 * and the guide's own jumps still open it.
 *
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
import { useRef, type ReactNode } from 'react';

import { Widget } from '../../components/Widget';
import { LoadingPanel, BackendDown } from '../../components/FetchStates';
import { Lock } from '../../components/icons';
import { API_ACCESS_COPY, SETTINGS_WIDGET_COPY as COPY } from '../../lib/settingsContent';
import type { ApiOpenApiResponse } from '../../lib/types';
import type { useFetch } from '../../lib/useFetch';
import { ApiProgramAgentView, ApiQuickStartView } from './ApiDocs';

type OpenApiState = ReturnType<typeof useFetch<ApiOpenApiResponse>>;

export const API_WIDGET_HEADING_ID = 'settings-apiaccess-heading';

export function ApiKeysPanel({
  state,
  onOpenExplorer,
}: {
  state: OpenApiState;
  onOpenExplorer: () => void;
}) {
  const programRef = useRef<HTMLDivElement>(null);

  /** Quick Start's "Program an Agent" jump: the guide is the next section down. */
  function openProgram() {
    const target = programRef.current;
    target?.scrollIntoView?.({ block: 'start' });
    target?.focus();
  }

  function contractBody(render: (schema: ApiOpenApiResponse) => ReactNode) {
    if (state.status === 'loading') return <LoadingPanel label="Loading the API contract…" />;
    if (state.status === 'error') return <BackendDown error={state.error} onRetry={state.reload} />;
    return render(state.data);
  }

  return (
    <Widget
      id={API_WIDGET_HEADING_ID}
      title={COPY.apiTitle}
      icon={<Lock size={18} strokeWidth={2} />}
      headline={<p className="settings-state-line">{API_ACCESS_COPY.stateLine}</p>}
      details={{
        summary: COPY.apiSetup,
        content: (
          <div className="settings-sequence">
            <section className="settings-sequence-item">
              {contractBody((schema) => (
                <ApiQuickStartView
                  schema={schema}
                  onOpenExplorer={onOpenExplorer}
                  onOpenProgram={openProgram}
                />
              ))}
            </section>
            <section className="settings-sequence-item">
              <div ref={programRef} tabIndex={-1} className="settings-sequence-anchor">
                {contractBody((schema) => (
                  <ApiProgramAgentView schema={schema} onOpenExplorer={onOpenExplorer} />
                ))}
              </div>
            </section>
          </div>
        ),
      }}
    />
  );
}
