/**
 * Settings → API → Documentation (P36V PR3 slice C).
 *
 * Three surfaces over ONE source of truth — the document `GET /api/openapi`
 * returns. There is no hand-maintained endpoint catalog anywhere in the client,
 * no CDN, no embedded API-explorer library, and no second description of any
 * operation:
 *
 *   · Quick Start        — the handful of facts a caller needs first, every one
 *                          of them derived from that document.
 *   · Endpoint Explorer  — the P36R master-detail browser, REFINED: grouped by
 *                          the document's real `tags` (see `lib/apiDocsModel.ts`
 *                          for why the old path-segment inference had to go),
 *                          with Purpose, the authentication requirement,
 *                          parameters, request body, responses, error states,
 *                          generated code examples, and raw JSON only behind a
 *                          `Technical Schema` disclosure.
 *   · Connect an Agent   — a collapsed guide, in its own module.
 *
 * The base URL is always the RELATIVE path the contract itself declares; no
 * origin or host literal is ever displayed or assumed, and the generated samples
 * read the origin from an environment variable instead.
 */
import {
  useCallback,
  useMemo,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';

import { Search } from '../../components/icons';
import {
  codeSamples,
  collectExamples,
  flattenOpenApi,
  groupEndpoints,
  isErrorCode,
  quickStartFacts,
  resolveSchema,
  stringify,
  tagDescriptions,
  SAMPLE_BASE_ENV,
  type ApiEndpoint,
  type QuickStartFacts,
  type SampleId,
} from '../../lib/apiDocsModel';
import type { ApiOpenApiResponse, OpenApiMediaType } from '../../lib/types';
import { ConnectAnAgent } from './ConnectAnAgent';
import { CopyAnnouncer, CopyButton, MethodBadge, RovingTabs } from './apiShared';

const API_DETAIL_ID = 'settings-api-detail';
const API_DETAIL_NAME_ID = 'settings-api-detail-name';
const API_LIST_HEADING_ID = 'settings-api-endpoints-heading';
const CONNECT_SUMMARY_ID = 'settings-api-connect-summary';

const slug = (value: string) => value.replace(/[^a-zA-Z0-9]+/g, '-');
const endpointRowId = (key: string) => `settings-api-row-${slug(key)}`;
const groupHeadingId = (key: string) => `settings-api-group-${slug(key)}`;

export function ApiDocsPanel({ schema, onOpenKeys }: { schema: ApiOpenApiResponse; onOpenKeys: () => void }) {
  const rows = useMemo(() => flattenOpenApi(schema), [schema]);
  const descriptions = useMemo(() => tagDescriptions(schema), [schema]);
  const facts = useMemo(() => quickStartFacts(schema, rows), [schema, rows]);

  // ONE polite region for every copy affordance on this panel, so adding a copy
  // button never adds a live region.
  const [copyMessage, setCopyMessage] = useState('');
  const onCopied = useCallback((what: string) => setCopyMessage(`Copied ${what}.`), []);

  const [connectOpen, setConnectOpen] = useState(false);
  const openConnect = useCallback(() => {
    setConnectOpen(true);
    (document.getElementById(CONNECT_SUMMARY_ID) as HTMLElement | null)?.focus();
  }, []);

  return (
    <>
      <CopyAnnouncer message={copyMessage} />
      <QuickStart
        facts={facts}
        onCopied={onCopied}
        onOpenKeys={onOpenKeys}
        onOpenConnect={openConnect}
      />
      <ApiBrowser
        schema={schema}
        rows={rows}
        descriptions={descriptions}
        onCopied={onCopied}
      />
      <ConnectAnAgent
        open={connectOpen}
        onOpenChange={setConnectOpen}
        summaryId={CONNECT_SUMMARY_ID}
        facts={{
          requestMediaTypes: facts.requestMediaTypes,
          errorCodes: facts.errorCodes,
          authRequiredCount: facts.authRequiredCount,
          operationCount: facts.operationCount,
        }}
      />
    </>
  );
}

// --- Quick Start -------------------------------------------------------------

/**
 * Only values this running app can actually report. In particular the base URL
 * is the relative path the contract's own paths share — `/api` locally, or
 * `/<base>/api` where a deployment sets a base path — and NOT an origin, which
 * would be both wrong for any other caller and a disclosure of deployment
 * topology. When the paths share no single base, that is said rather than
 * papered over with a plausible default.
 */
function QuickStart({
  facts,
  onCopied,
  onOpenKeys,
  onOpenConnect,
}: {
  facts: QuickStartFacts;
  onCopied: (what: string) => void;
  onOpenKeys: () => void;
  onOpenConnect: () => void;
}) {
  const first = facts.firstRequest;
  const firstSample = first ? codeSamples(first)[0] : null;
  return (
    <section className="api-quickstart" aria-labelledby="settings-api-quickstart-heading">
      <h3 id="settings-api-quickstart-heading" className="api-section-title">
        Quick Start
      </h3>
      <p className="settings-source-line mono">{facts.contractLine}</p>

      <dl className="api-quickstart-rows">
        <QuickStartRow label="Base URL">
          {facts.basePath ? (
            <>
              <code className="mono api-quickstart-value">{facts.basePath}</code>
              <span className="api-quickstart-note">
                Relative to the origin serving this page. Every path in the Endpoint Explorer
                already begins with it, so a request needs the origin and nothing else.
              </span>
            </>
          ) : (
            <span className="api-quickstart-note">
              The contract's paths share no single base, so there is no one base URL to
              report. Use each path exactly as the Endpoint Explorer lists it.
            </span>
          )}
        </QuickStartRow>

        <QuickStartRow label="API Version">
          <code className="mono api-quickstart-value">
            {facts.apiVersion ? `v${facts.apiVersion}` : 'not declared'}
          </code>
          <span className="api-quickstart-note">
            The app version this contract was generated from, described as OpenAPI{' '}
            {facts.openApiVersion}.
          </span>
        </QuickStartRow>

        <QuickStartRow label="Authentication">
          <code className="mono api-quickstart-value">Authorization: Bearer</code>
          <span className="api-quickstart-note">
            One credential belonging to the deployment, sent on every call that needs it.{' '}
            {facts.authRequiredCount} of {facts.operationCount} operations document a 401, and the
            Explorer marks which. No key can be issued from this app — see API Keys.
          </span>
        </QuickStartRow>

        <QuickStartRow label="Content Type">
          {facts.requestMediaTypes.length > 0 ? (
            <>
              {facts.requestMediaTypes.map((mediaType) => (
                <code className="mono api-quickstart-value" key={mediaType}>
                  {mediaType}
                </code>
              ))}
              <span className="api-quickstart-note">
                The only request media types this contract declares. Read operations send no body.
              </span>
            </>
          ) : (
            <span className="api-quickstart-note">
              No operation in this contract declares a request body.
            </span>
          )}
        </QuickStartRow>
      </dl>

      {first && firstSample && (
        <div className="api-quickstart-first">
          <div className="api-samples-head">
            <span className="api-samples-lang">
              A First Request &middot; <MethodBadge method={first.method} />{' '}
              <code className="mono">{first.path}</code>
            </span>
            <CopyButton
              what="the first-request sample"
              value={firstSample.code}
              onCopied={onCopied}
            />
          </div>
          <pre className="mono api-samples-code">{firstSample.code}</pre>
          <p className="api-quickstart-note">
            {first.authRequired
              ? 'Every read operation in this contract documents a 401, so this one needs a credential too.'
              : 'Chosen because the contract documents no 401 for it: it answers before any credential exists.'}{' '}
            <code className="mono">${SAMPLE_BASE_ENV}</code> stands for the origin serving this
            page; the sample never hard-codes one.
          </p>
        </div>
      )}

      <nav className="api-quickstart-jump" aria-label="More API detail">
        <button type="button" className="settings-jump-btn" onClick={onOpenKeys}>
          API Keys
        </button>
        <button type="button" className="settings-jump-btn" onClick={onOpenConnect}>
          Connect an Agent
        </button>
      </nav>
    </section>
  );
}

function QuickStartRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="api-quickstart-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

// --- Endpoint Explorer -------------------------------------------------------

function ApiBrowser({
  schema,
  rows,
  descriptions,
  onCopied,
}: {
  schema: ApiOpenApiResponse;
  rows: ApiEndpoint[];
  descriptions: Record<string, string>;
  onCopied: (what: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [focusIndex, setFocusIndex] = useState(0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.path.toLowerCase().includes(q) ||
        (r.summary ?? '').toLowerCase().includes(q) ||
        r.group.toLowerCase().includes(q) ||
        r.method.includes(q),
    );
  }, [rows, query]);

  const groups = useMemo(() => groupEndpoints(filtered, descriptions), [filtered, descriptions]);

  // Selection follows the filter without an effect: the explicitly selected
  // endpoint when it is still visible, otherwise the first visible one,
  // otherwise nothing. Never an endpoint the user cannot see in the list.
  const selected =
    filtered.find((r) => r.key === selectedKey) ?? (filtered.length > 0 ? filtered[0] : null);

  const cursor = filtered.length === 0 ? 0 : Math.min(focusIndex, filtered.length - 1);

  /** Roving tabindex: exactly ONE row is in the tab order; Arrow/Home/End move
   *  that cursor without selecting. Same contract as the Schema Reference
   *  Fields list and the Concepts master list — one interaction model. */
  const onListKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
      let next: number | null = null;
      if (e.key === 'ArrowDown') next = Math.min(index + 1, filtered.length - 1);
      else if (e.key === 'ArrowUp') next = Math.max(index - 1, 0);
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = filtered.length - 1;
      if (next === null || filtered.length === 0) return;
      e.preventDefault();
      setFocusIndex(next);
      (document.getElementById(endpointRowId(filtered[next].key)) as HTMLButtonElement | null)?.focus();
    },
    [filtered],
  );

  return (
    <section className="api-explorer" aria-labelledby="settings-api-explorer-heading">
      <h3 id="settings-api-explorer-heading" className="api-section-title">
        Endpoint Explorer
      </h3>

      <div className="settings-search" role="search">
        <label className="settings-search-label" htmlFor="api-docs-search">
          Search endpoints
        </label>
        <div className="settings-search-input-wrap">
          <Search size={14} strokeWidth={2.2} aria-hidden="true" className="settings-search-icon" />
          <input
            id="api-docs-search"
            type="search"
            className="settings-search-input"
            placeholder="Filter by group, path, method, or summary…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedKey(null);
              setFocusIndex(0);
            }}
          />
        </div>
      </div>

      {/* The only EXPLICIT `aria-live` region here. Note the copy announcer's
          `role="status"` carries an implicit `aria-live="polite"`, so this surface
          has TWO polite regions with distinct purposes: this one reports the search
          result count, that one confirms a copy. Both are asserted (exactly one of
          each kind) rather than claimed to be a single region. */}
      <p className="settings-doc-count" aria-live="polite">
        {filtered.length} of {rows.length} endpoint{rows.length === 1 ? '' : 's'}
      </p>

      {filtered.length === 0 && (
        <p className="settings-doc-empty">No endpoints match &ldquo;{query}&rdquo;.</p>
      )}

      {filtered.length > 0 && (
        <div className="api-browser-split">
          {/* Named the same way the detail pane is, so both halves of the
              master-detail pair announce what they are. */}
          <section className="api-browser-master" aria-labelledby={API_LIST_HEADING_ID}>
            <h4 id={API_LIST_HEADING_ID} className="api-browser-pane-heading">
              Endpoints
              <span className="api-browser-pane-count mono">
                {groups.length} group{groups.length === 1 ? '' : 's'}
              </span>
            </h4>
            <div className="api-browser-list">
              {groups.map((group) => (
                <section
                  className="api-browser-group"
                  key={group.key}
                  aria-labelledby={groupHeadingId(group.key)}
                >
                  <h5 id={groupHeadingId(group.key)} className="api-browser-group-heading">
                    {group.key}
                    <span className="api-browser-group-count">{group.rows.length}</span>
                  </h5>
                  <ul className="api-browser-rows">
                    {group.rows.map(({ row, index }) => (
                      <ApiEndpointRow
                        key={row.key}
                        row={row}
                        selected={selected?.key === row.key}
                        tabIndex={index === cursor ? 0 : -1}
                        onSelect={() => {
                          setSelectedKey(row.key);
                          setFocusIndex(index);
                        }}
                        onKeyDown={(e) => onListKeyDown(e, index)}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </section>

          {/* `tabIndex={-1}`: a programmatic focus target that adds no tab stop;
              its accessible name is the selected endpoint's own heading. */}
          <div
            className="api-browser-detail"
            id={API_DETAIL_ID}
            role="region"
            tabIndex={-1}
            aria-labelledby={API_DETAIL_NAME_ID}
          >
            {selected && (
              <ApiEndpointDetail
                row={selected}
                schema={schema}
                groupDescription={descriptions[selected.group]}
                onCopied={onCopied}
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function ApiEndpointRow({
  row,
  selected,
  tabIndex,
  onSelect,
  onKeyDown,
}: {
  row: ApiEndpoint;
  selected: boolean;
  tabIndex: number;
  onSelect: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLButtonElement>) => void;
}) {
  // Selection comes from the native <button> (browsers synthesize a click from
  // Enter and Space); `onKeyDown` only moves the roving cursor.
  return (
    <li className="api-browser-row">
      <button
        id={endpointRowId(row.key)}
        type="button"
        className={`api-browser-rowbtn${selected ? ' selected' : ''}`}
        aria-current={selected ? 'true' : undefined}
        aria-controls={API_DETAIL_ID}
        tabIndex={tabIndex}
        onClick={onSelect}
        onKeyDown={onKeyDown}
      >
        <MethodBadge method={row.method} />
        <span className="api-browser-rowtext">
          <code className="mono api-docs-path">{row.path}</code>
          {row.summary && <span className="api-docs-summary-text">{row.summary}</span>}
        </span>
      </button>
    </li>
  );
}

function ApiEndpointDetail({
  row,
  schema,
  groupDescription,
  onCopied,
}: {
  row: ApiEndpoint;
  schema: ApiOpenApiResponse;
  groupDescription?: string;
  onCopied: (what: string) => void;
}) {
  const ok = row.responses.filter((r) => !isErrorCode(r.code));
  const errors = row.responses.filter((r) => isErrorCode(r.code));
  return (
    <>
      <h4 id={API_DETAIL_NAME_ID} className="api-browser-detail-name">
        <MethodBadge method={row.method} />
        <code className="mono api-browser-detail-path">{row.path}</code>
      </h4>

      {/* The group is the operation's REAL tag, and the sentence beside it is
          that tag's own registered description — not a label invented here. */}
      <p className="api-browser-detail-group">
        <span className="api-browser-detail-grouptag">{row.group}</span>
        {groupDescription && (
          <span className="api-browser-detail-groupdesc">{groupDescription}</span>
        )}
      </p>

      {row.summary && <p className="api-browser-detail-summary">{row.summary}</p>}

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Purpose</h5>
        {row.description ? (
          <p className="api-docs-description">{row.description}</p>
        ) : (
          <p className="api-docs-no-params">The contract states no purpose for this operation.</p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Authentication</h5>
        <p className="api-browser-section-note">
          {row.authRequired
            ? 'A credential is required when this deployment enables authentication: the contract documents a 401 for this operation. Send it as an Authorization: Bearer header.'
            : 'The contract documents no 401 for this operation, so it stays reachable without a credential even where authentication is enabled.'}
        </p>
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Parameters</h5>
        {row.parameters.length > 0 ? (
          <div className="api-docs-params-wrap">
            <table className="api-docs-params">
              <caption className="sr-only">Parameters for {row.path}</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">In</th>
                  <th scope="col">Required</th>
                  <th scope="col">Description</th>
                </tr>
              </thead>
              <tbody>
                {row.parameters.map((p) => (
                  <tr key={`${p.in}:${p.name}`}>
                    <td className="mono">{p.name}</td>
                    <td>{p.in}</td>
                    <td>{p.required ? 'Yes' : 'No'}</td>
                    <td className="api-docs-param-desc">{p.description ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="api-docs-no-params">No parameters.</p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Request Body</h5>
        {row.requestBody ? (
          <>
            {row.requestBody.description && (
              <p className="api-browser-section-note">{row.requestBody.description}</p>
            )}
            <p className="api-browser-section-note">
              {row.requestBody.required ? 'Required.' : 'Optional.'}
            </p>
            <ContentBlocks content={row.requestBody.content} schema={schema} idBase="reqbody" />
          </>
        ) : row.method === 'get' ? (
          <p className="api-docs-no-params">No request body.</p>
        ) : (
          // Seven of this API's write operations declare no `requestBody`: two
          // read the RAW request and describe it in prose, and five take no body
          // at all. The document carries no signal that separates those two
          // cases, so the wording below covers both without picking one —
          // inventing a schema, or asserting "no body", would each be a guess.
          <p className="api-docs-no-params">
            The contract declares no request body for this operation. Where one is expected, it is
            described under Purpose rather than as a schema; nothing is inferred either way.
          </p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Responses</h5>
        {ok.length > 0 ? (
          <ResponseList entries={ok} schema={schema} />
        ) : (
          <p className="api-docs-no-params">The contract documents no non-error response.</p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Error States</h5>
        {errors.length > 0 ? (
          <ResponseList entries={errors} schema={schema} />
        ) : (
          <p className="api-docs-no-params">The contract documents no error response.</p>
        )}
      </section>

      <CodeSamples row={row} onCopied={onCopied} />

      <p className="api-browser-detail-source">
        Rendered verbatim from <code className="mono">GET /api/openapi</code> — this app's own
        generated contract. Every status, description and example above is the contract's own
        wording, including where it says an outcome never occurs.
      </p>
    </>
  );
}

function ResponseList({
  entries,
  schema,
}: {
  entries: ApiEndpoint['responses'];
  schema: ApiOpenApiResponse;
}) {
  return (
    <ul className="api-browser-responses">
      {entries.map((res) => (
        <li key={res.code} className="api-browser-response">
          <span className="api-browser-status mono">{res.code}</span>
          <div className="api-browser-response-body">
            {res.description ? (
              <p className="api-browser-section-note">{res.description}</p>
            ) : (
              <p className="api-browser-section-note">The contract gives this status no wording.</p>
            )}
            <ContentBlocks content={res.content} schema={schema} idBase={`res-${res.code}`} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Per-media-type schema + example disclosures. Collapsed by default, and the
 *  raw JSON is explicitly labelled `Technical Schema` so it never leads. */
function ContentBlocks({
  content,
  schema,
  idBase,
}: {
  content?: Record<string, OpenApiMediaType>;
  schema: ApiOpenApiResponse;
  idBase: string;
}) {
  const entries = Object.entries(content ?? {});
  if (entries.length === 0) return null;
  return (
    <>
      {entries.map(([mediaType, media]) => {
        const resolved = resolveSchema(media?.schema, schema);
        const examples = collectExamples(media);
        return (
          <div className="api-browser-media" key={`${idBase}:${mediaType}`}>
            <p className="api-browser-mediatype mono">{mediaType}</p>
            {resolved.value !== undefined && (
              <details className="api-browser-disclosure">
                <summary>
                  Technical Schema
                  {resolved.resolvedFrom && (
                    <span className="api-browser-reftag mono">{resolved.resolvedFrom}</span>
                  )}
                </summary>
                <pre className="mono api-browser-json">{stringify(resolved.value)}</pre>
              </details>
            )}
            {examples.map((ex) => (
              <details className="api-browser-disclosure" key={ex.name}>
                <summary>
                  Example
                  <span className="api-browser-reftag mono">{ex.name}</span>
                </summary>
                <pre className="mono api-browser-json">{stringify(ex.value)}</pre>
              </details>
            ))}
          </div>
        );
      })}
    </>
  );
}

// --- generated code examples -------------------------------------------------

const SAMPLE_TABS: { id: SampleId; label: string }[] = [
  { id: 'curl', label: 'cURL' },
  { id: 'python', label: 'Python' },
  { id: 'javascript', label: 'JavaScript' },
];

/**
 * Three runnable-shaped samples per operation, generated from that operation's
 * own contract (see `codeSamples`). Collapsed by default, and compact: one
 * language at a time behind a roving tablist, never three code walls at once.
 * No SDK and no dependency is referenced, because none exists.
 */
function CodeSamples({ row, onCopied }: { row: ApiEndpoint; onCopied: (what: string) => void }) {
  const samples = useMemo(() => codeSamples(row), [row]);
  const [active, setActive] = useState<SampleId>('curl');
  const current = samples.find((s) => s.id === active) ?? samples[0];
  const base = `settings-api-sample-${slug(row.key)}`;
  const tabId = (id: SampleId) => `${base}-tab-${id}`;
  const panelId = (id: SampleId) => `${base}-panel-${id}`;
  return (
    <details className="api-samples">
      <summary className="api-samples-summary">Code Examples</summary>
      <p className="api-browser-section-note">
        Generated from this operation's method, path, required parameters and declared media
        type. Standard library only — no client library exists for this API.
      </p>
      <RovingTabs
        className="api-samples-tabs"
        label="Code example language"
        tabs={SAMPLE_TABS}
        active={active}
        onSelect={setActive}
        tabId={tabId}
        panelId={panelId}
      />
      <div
        className="api-samples-panel"
        id={panelId(current.id)}
        role="tabpanel"
        aria-labelledby={tabId(current.id)}
      >
        <div className="api-samples-head">
          <span className="api-samples-lang">{current.label}</span>
          <CopyButton
            what={`the ${current.label} sample`}
            value={current.code}
            onCopied={onCopied}
          />
        </div>
        <pre className="mono api-samples-code">{current.code}</pre>
      </div>
    </details>
  );
}
