import './screens.css';
import './schema-proposals.css';
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { BackendDown, LoadingPanel } from '../components/FetchStates';
import { Copy, Download } from '../components/icons';
import { LABELS, formatWhen } from '../lib/labels';
import { api, isHostedBuild } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { serverMessageOf } from '../lib/mutationErrors';
import {
  SCHEMA_PROPOSALS_COPY as COPY,
  PROPOSAL_KIND_LABEL,
  PROPOSE_SOURCES,
  STATUS_LABEL,
  VALUE_TYPE_LABEL,
  changeRequestJsonFilename,
  changeRequestJsonText,
  changeRequestMarkdownFilename,
  isProposeSource,
  portalBodyFilename,
  portalBodyText,
  canProposeTerm,
  portalSectionFor,
  proposalHeadline,
  schemaFieldErrors,
  type ApiSchemaCategory,
  type ApiSchemaChange,
  type ApiSchemaProposal,
  type ApiSchemaProposalGate0,
  type ApiSchemaProposalResponse,
  type ProposeSource,
  type SchemaChangeInput,
  type SchemaChangeScope,
  type SchemaChangeValueType,
  type SchemaSourceId,
  type ApiSchemaSection,
  type ApiSchemaVocabulary,
  type SchemaFieldError,
  type SchemaProposalInput,
  type SchemaProposalType,
} from '../lib/schemaProposals';
import {
  TERM_DRAFTS_MAX_BYTES,
  countsSentence,
  citationLine,
  gate0FromDraft,
  parseTermDraftsFile,
  sourceFromDraft,
  type LocalTermDraft,
  type LocalTermDraftsFile,
} from '../lib/termDrafts';

/**
 * SCHEMA PROPOSALS — browse the vocabulary, draft a proposal to change it, and
 * track the drafts.
 *
 * WHAT THIS SCREEN WILL NOT DO, and each is a claim a test pins by behaviour:
 *
 *   1. IT NEVER APPROVES, APPLIES OR SENDS. There is no such control. A proposal is a
 *      draft on this server; the people who own the ISAAC standard review it in the
 *      ISAAC portal and record any decision there. The two states shown are the
 *      server's own — Pending and Withdrawn — and Pending is worded to claim nothing
 *      about whether anyone has seen it.
 *   2. IT NAMES NOBODY. Who is using this server is not verified, so a proposal records
 *      no author and the list says so rather than showing a blank or a guess.
 *   3. IT DOES NOT PRETEND TO KEEP WHAT THE SERVER MAY LOSE. Every response carries the
 *      server's own statement of how long a proposal lasts, and the screen shows it
 *      beside the proposals and again after saving one.
 *   4. IT NEVER LOSES WHAT YOU TYPED. The three panels stay mounted when you change tab,
 *      and a refused submit leaves every box as it was, with the server's own sentence
 *      beside the box it is about.
 */

type TabId = 'browse' | 'propose' | 'proposals';
const TAB_PARAM = 'tab';
const TABS: { id: TabId; label: string }[] = [
  { id: 'browse', label: COPY.tabBrowse },
  { id: 'propose', label: COPY.tabPropose },
  { id: 'proposals', label: COPY.tabProposals },
];
const isTab = (v: string | null): v is TabId => TABS.some((t) => t.id === v);
const tabDomId = (id: TabId) => `schema-proposals-tab-${id}`;
const panelDomId = (id: TabId) => `schema-proposals-panel-${id}`;

/** A request to open the form on a given section and category, with a counter so asking twice re-applies. */
interface Prefill {
  type: SchemaProposalType;
  section: string;
  category: string;
  /** A term carried from the screen where the gap was found (`?term=`). */
  term?: string;
  /** Which screen that was (`?from=`); only the names in `PROPOSE_SOURCES` are shown. */
  from?: ProposeSource;
  nonce: number;
}

/** What a `?category=&term=&from=` link asked for, read once per distinct link. */
interface LinkRequest {
  key: string;
  category: string;
  term: string;
  from: ProposeSource | null;
}

export function SchemaProposals() {
  const [params, setParams] = useSearchParams();
  const requested = params.get(TAB_PARAM);
  const tab: TabId = isTab(requested) ? requested : 'browse';

  const vocabulary = useFetch(() => api.getSchemaVocabulary(), []);
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  /** Bumped whenever a proposal is saved, so the list refetches. */
  const [listVersion, setListVersion] = useState(0);

  const selectTab = useCallback(
    (next: TabId) => {
      const nextParams = new URLSearchParams(params);
      nextParams.set(TAB_PARAM, next);
      setParams(nextParams, { replace: true });
    },
    [params, setParams],
  );

  const startProposal = useCallback(
    (type: SchemaProposalType, section: string, category: string) => {
      setPrefill((previous) => ({ type, section, category, nonce: (previous?.nonce ?? 0) + 1 }));
      selectTab('propose');
    },
    [selectTab],
  );

  /*
   * PROPOSE FROM WHERE THE GAP WAS FOUND. A link from another screen
   * (`?tab=propose&category=…&term=…&from=…`) opens the form on that list with that term.
   * The section is looked up in the server's own `proposal_sections`, never taken from the
   * link, and a list the portal has no term list for fills in NOTHING: the form says why.
   */
  const linkCategory = params.get('category');
  const linkTerm = params.get('term');
  const linkFrom = params.get('from');
  const link: LinkRequest | null =
    linkCategory !== null && linkTerm !== null
      ? {
          key: `${linkCategory}\u0000${linkTerm}\u0000${linkFrom ?? ''}`,
          category: linkCategory,
          term: linkTerm,
          from: isProposeSource(linkFrom) ? linkFrom : null,
        }
      : null;
  const appliedLink = useRef<string | null>(null);
  const [linkRefused, setLinkRefused] = useState<string | null>(null);
  const vocabularyData = vocabulary.status === 'data' ? vocabulary.data : null;
  useEffect(() => {
    if (link === null || vocabularyData === null || appliedLink.current === link.key) return;
    appliedLink.current = link.key;
    const section = portalSectionFor(vocabularyData, link.category);
    if (section === null) {
      setLinkRefused(link.category);
      return;
    }
    setLinkRefused(null);
    setPrefill((previous) => ({
      type: 'add_term',
      section,
      category: link.category,
      term: link.term,
      from: link.from ?? undefined,
      nonce: (previous?.nonce ?? 0) + 1,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the link, applied once per link
  }, [link?.key, vocabularyData]);

  function onTabKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') nextIndex = (index + 1) % TABS.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') nextIndex = (index - 1 + TABS.length) % TABS.length;
    else if (e.key === 'Home') nextIndex = 0;
    else if (e.key === 'End') nextIndex = TABS.length - 1;
    if (nextIndex === null) return;
    e.preventDefault();
    const next = TABS[nextIndex];
    selectTab(next.id);
    (document.getElementById(tabDomId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="schemaProposals" />}
      mainPad="pad"
      width="wide"
    >
      <div className="sp-screen">
        <header className="sp-head">
          <h1 className="page-title">{LABELS.navSchemaProposals}</h1>
          <p className="sp-lead">{COPY.lead}</p>
          <p className="sp-boundary">{COPY.boundary}</p>
        </header>

        <div className="section-tabs" role="tablist" aria-label="Schema Proposals sections">
          {TABS.map((t, i) => {
            const selected = t.id === tab;
            return (
              <button
                key={t.id}
                id={tabDomId(t.id)}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={panelDomId(t.id)}
                tabIndex={selected ? 0 : -1}
                className={`section-tab${selected ? ' active' : ''}`}
                onClick={() => selectTab(t.id)}
                onKeyDown={(e) => onTabKeyDown(e, i)}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {/* All three panels stay mounted and are hidden rather than unmounted, so a half-written
            proposal survives a trip to Browse. */}
        <div
          id={panelDomId('browse')}
          role="tabpanel"
          aria-labelledby={tabDomId('browse')}
          hidden={tab !== 'browse'}
        >
          {vocabulary.status === 'loading' && <LoadingPanel label="Reading the vocabulary…" />}
          {vocabulary.status === 'error' && <BackendDown error={vocabulary.error} onRetry={vocabulary.reload} />}
          {vocabulary.status === 'data' && (
            <BrowsePanel vocabulary={vocabulary.data} onPropose={startProposal} />
          )}
        </div>

        <div
          id={panelDomId('propose')}
          role="tabpanel"
          aria-labelledby={tabDomId('propose')}
          hidden={tab !== 'propose'}
        >
          {vocabulary.status === 'loading' && <LoadingPanel label="Reading the vocabulary…" />}
          {vocabulary.status === 'error' && <BackendDown error={vocabulary.error} onRetry={vocabulary.reload} />}
          {vocabulary.status === 'data' && (
            <ProposePanel
              vocabulary={vocabulary.data}
              prefill={prefill}
              linkRefused={linkRefused}
              onSaved={() => setListVersion((v) => v + 1)}
              onViewProposals={() => selectTab('proposals')}
            />
          )}
        </div>

        <div
          id={panelDomId('proposals')}
          role="tabpanel"
          aria-labelledby={tabDomId('proposals')}
          hidden={tab !== 'proposals'}
        >
          <ProposalsPanel version={listVersion} />
        </div>
      </div>
    </AppShell>
  );
}

// --- Browse ---------------------------------------------------------------------

function BrowsePanel({
  vocabulary,
  onPropose,
}: {
  vocabulary: ApiSchemaVocabulary;
  onPropose: (type: SchemaProposalType, section: string, category: string) => void;
}) {
  const sectionSelectId = useId();
  const sourceName = useId();
  const [sourceId, setSourceId] = useState<SchemaSourceId>(vocabulary.default_source);
  const source = vocabulary.sources[sourceId];
  const sections = source.sections;
  const [sectionId, setSectionId] = useState(sections[0]?.id ?? '');
  const section: ApiSchemaSection | undefined = sections.find((s) => s.id === sectionId) ?? sections[0];
  const [categoryKey, setCategoryKey] = useState<string | null>(null);
  const category: ApiSchemaCategory | undefined =
    section?.categories.find((c) => c.key === categoryKey) ?? section?.categories[0];
  // A new term can join only a list the PORTAL has, because the portal is what checks it.
  const termListsHere = new Set(
    vocabulary.proposal_sections.find((s) => s.id === section?.id)?.term_lists ?? [],
  );
  const canAddTerm = category !== undefined && termListsHere.has(category.key);

  return (
    <section className="sp-panel sp-panel-wide" aria-label={COPY.tabBrowse}>
      <p className="sp-note">{COPY.browseLead}</p>

      <fieldset className="sp-fieldset">
        <legend>Which list?</legend>
        {(['portal', 'schema'] as const).map((id) => (
          <label className="sp-radio" key={id}>
            <input
              type="radio"
              name={sourceName}
              checked={sourceId === id}
              onChange={() => {
                setSourceId(id);
                setSectionId(vocabulary.sources[id].sections[0]?.id ?? '');
                setCategoryKey(null);
              }}
            />
            <span>{vocabulary.sources[id].label}</span>
          </label>
        ))}
      </fieldset>
      <p className="sp-note">{source.detail}</p>
      <p className="sp-meta">
        {source.section_count} sections, {source.term_list_count} term lists, {source.term_count} terms.
      </p>

      <div className="sp-field">
        <label htmlFor={sectionSelectId}>Section</label>
        <select
          id={sectionSelectId}
          className="input sp-select"
          value={section?.id ?? ''}
          onChange={(e) => {
            setSectionId(e.target.value);
            setCategoryKey(null);
          }}
        >
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label} ({s.categories.length} {s.categories.length === 1 ? 'entry' : 'entries'})
            </option>
          ))}
        </select>
      </div>

      {section && section.categories.length === 0 && (
        <p className="sp-note" role="status">
          This section has no fixed lists of allowed terms in this source. You can still propose a new list for it.
        </p>
      )}

      {section && section.categories.length > 0 && (
        <div className="sp-browse-grid">
          <div>
            <h2 className="sp-h2" id="sp-categories-heading">
              Categories
            </h2>
            <ul className="sp-cat-list" aria-labelledby="sp-categories-heading">
              {section.categories.map((c) => {
                const current = c.key === category?.key;
                return (
                  <li key={c.key}>
                    <button
                      type="button"
                      className={`sp-cat${current ? ' is-current' : ''}`}
                      aria-pressed={current}
                      onClick={() => setCategoryKey(c.key)}
                    >
                      <span className="sp-cat-key">{c.key}</span>
                      <span className="sp-cat-count">{c.kind === 'other' ? 'no list' : c.terms.length}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {category && (
            <div>
              <h2 className="sp-h2">{category.key}</h2>
              {category.description && <p className="sp-note">{category.description}</p>}
              {category.kind === 'other' ? (
                <p className="sp-note">
                  This entry is a mapping or a unit grammar, not a list of allowed terms, so it has no terms to show.
                </p>
              ) : (
                <table className="sp-table">
                  <caption className="sr-only">Allowed terms for {category.key}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Allowed term</th>
                    </tr>
                  </thead>
                  <tbody>
                    {category.terms.map((term) => (
                      <tr key={term}>
                        <td className="sp-term">{term}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {canAddTerm ? (
                <div className="sp-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => onPropose('add_term', section.id, category.key)}
                  >
                    Propose a New Term for This List
                  </button>
                </div>
              ) : (
                category.kind !== 'other' && (
                  <p className="sp-hint">
                    The portal vocabulary snapshot has no list for this entry in this section, so the portal would
                    refuse a new term for it. Switch to the portal list to propose a term.
                  </p>
                )
              )}
            </div>
          )}
        </div>
      )}

      {section && (
        <div className="sp-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onPropose('add_category', section.id, '')}
          >
            Propose a New List in {section.label}
          </button>
          {vocabulary.schema_change && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => onPropose('schema_change', section.id, '')}
            >
              Propose a New Field in {section.label}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

// --- Propose --------------------------------------------------------------------

const GATE0_FIELDS: { key: keyof ApiSchemaProposalGate0; label: string; rows: number; hint: string }[] = [
  {
    key: 'problem',
    label: 'The problem, with counts and examples',
    rows: 3,
    hint: 'What goes wrong today? How many records, and which?',
  },
  {
    key: 'examples',
    label: 'Examples',
    rows: 2,
    hint: 'Record ids or a sentence from a record that shows it.',
  },
  {
    key: 'affected_records_estimate',
    label: 'Records affected (estimate)',
    rows: 1,
    hint: 'A rough number is fine, for example "about 40".',
  },
  {
    key: 'flip_list',
    label: 'What would change',
    rows: 2,
    hint: 'Which stored records or checks would behave differently once this is added?',
  },
];

function ProposePanel({
  vocabulary,
  prefill,
  linkRefused,
  onSaved,
  onViewProposals,
}: {
  vocabulary: ApiSchemaVocabulary;
  prefill: Prefill | null;
  /** A link named a list the portal has no term list for, so nothing was filled in. */
  linkRefused: string | null;
  onSaved: () => void;
  onViewProposals: () => void;
}) {
  const ids = {
    type: useId(),
    section: useId(),
    category: useId(),
    term: useId(),
    description: useId(),
    parent: useId(),
    fieldName: useId(),
    valueType: useId(),
    unit: useId(),
    required: useId(),
    example: useId(),
    scope: useId(),
    migration: useId(),
  };
  const limits = vocabulary.limits;
  const sections = vocabulary.proposal_sections;
  /** The server describes the third type; a server that does not is offered only the portal's two. */
  const schemaChange = vocabulary.schema_change ?? null;

  const [type, setType] = useState<SchemaProposalType>('add_term');
  const [sectionId, setSectionId] = useState(sections.find((s) => s.term_lists.length > 0)?.id ?? sections[0]?.id ?? '');
  const [category, setCategory] = useState('');
  const [term, setTerm] = useState('');
  const [description, setDescription] = useState('');
  const [gate0, setGate0] = useState<Record<string, string>>({});
  const [from, setFrom] = useState<ProposeSource | null>(null);
  /** The local-import draft the form was opened on, with the reviewer notes its file could not fill. */
  const [localDraft, setLocalDraft] = useState<{
    draft: LocalTermDraft;
    bundleId: string | null;
    missing: (keyof ApiSchemaProposalGate0)[];
  } | null>(null);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  // A new field (schema change request).
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [fieldName, setFieldName] = useState('');
  const [valueType, setValueType] = useState<SchemaChangeValueType | ''>('');
  const [unit, setUnit] = useState('');
  const [required, setRequired] = useState<'' | 'yes' | 'no'>('');
  const [example, setExample] = useState('');
  const [scope, setScope] = useState<SchemaChangeScope | ''>('');
  const [migration, setMigration] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<SchemaFieldError[]>([]);
  const [topMessage, setTopMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState<ApiSchemaProposalResponse | null>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const savedRef = useRef<HTMLDivElement>(null);

  const section = sections.find((s) => s.id === sectionId);
  const listsInSection = useMemo(() => section?.term_lists ?? [], [section]);
  /** The blocks of the schema in this section a new field could go in, as the server derived them. */
  const parentsInSection = useMemo(
    () => (schemaChange?.object_paths ?? []).filter((o) => o.section === sectionId),
    [schemaChange, sectionId],
  );
  const parent = parentsInSection.find((o) => o.path === parentPath) ?? null;
  const isField = type === 'schema_change';
  const unitAllowed = valueType === 'number' || valueType === 'integer' || valueType === 'array';

  // An "open the form on this list" request from Browse, or a link from another screen.
  useEffect(() => {
    if (!prefill) return;
    setType(prefill.type === 'schema_change' && !schemaChange ? 'add_category' : prefill.type);
    setSectionId(prefill.section);
    setCategory(prefill.category);
    setParentPath(null);
    if (prefill.term !== undefined) setTerm(prefill.term);
    setFrom(prefill.from ?? null);
    setLocalDraft(null);
    if (prefill.from && prefill.term !== undefined) {
      // THE SOURCE SURFACE IS NOTED where reviewers read it, in words the reader can change.
      setGate0((prev) => ({
        ...prev,
        examples: `Found in ${PROPOSE_SOURCES[prefill.from as ProposeSource]} on the ISAAC Metadata Assistant, as "${prefill.term}".`,
      }));
    }
    setErrors([]);
    setTopMessage(null);
    setSaved(null);
  }, [prefill, schemaChange]);

  // The category for "add a term" must be one of the section's lists. Keep it valid when the
  // section changes; an explicit empty choice is kept so the reader sees it is not chosen yet.
  useEffect(() => {
    if (type !== 'add_term') return;
    if (category !== '' && !listsInSection.includes(category)) setCategory('');
  }, [type, listsInSection, category]);

  // The parent block must be in the chosen section; changing section clears a choice that is not.
  useEffect(() => {
    if (parentPath !== null && !parentsInSection.some((o) => o.path === parentPath)) setParentPath(null);
  }, [parentsInSection, parentPath]);

  useEffect(() => {
    if (errors.length > 0 || topMessage) summaryRef.current?.focus();
  }, [errors, topMessage]);

  useEffect(() => {
    if (saved) savedRef.current?.focus();
  }, [saved]);

  /*
   * OPEN THE FORM ON ONE DRAFT FROM A LOCAL IMPORT. The section is the server's own for the
   * list (never the file's), the list and the term are the file's, the description is EMPTY,
   * and the reviewer notes are the file's counts and citations. Nothing is sent: the scientist
   * writes the description and saves, or does not.
   */
  function openLocalDraft(draft: LocalTermDraft, bundleId: string | null) {
    const section = portalSectionFor(vocabulary, draft.category);
    if (section === null) return;
    const filled = gate0FromDraft(draft, bundleId, limits);
    setType('add_term');
    setSectionId(section);
    setCategory(draft.category);
    setParentPath(null);
    setTerm(draft.term);
    setDescription('');
    setGate0({ ...filled.gate0 });
    setFrom(null);
    setLocalDraft({ draft, bundleId, missing: filled.missing });
    setErrors([]);
    setTopMessage(null);
    setSaved(null);
    // The one box left to the scientist gets focus, after the form has re-rendered.
    window.setTimeout(() => descriptionRef.current?.focus(), 0);
  }

  const fromLocalDraft = localDraft !== null && type === 'add_term';

  const errorFor = (field: string) => errors.find((e) => e.field === field)?.message;
  const changeFields = ['change', ...['kind', 'parent_path', 'field_name', 'value_type', 'unit', 'required', 'example', 'scope', 'migration'].map((k) => `change.${k}`)];
  const shown = new Set([
    'proposal_type',
    'section',
    'category',
    'term',
    'description',
    ...GATE0_FIELDS.map((g) => `gate0.${g.key}`),
    ...(isField ? changeFields.filter((f) => f !== 'change' && f !== 'change.kind') : []),
  ]);
  const elsewhere = errors.filter((e) => e.field === null || !shown.has(e.field));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setErrors([]);
    setTopMessage(null);
    setSaved(null);
    const note: ApiSchemaProposalGate0 = {};
    for (const g of GATE0_FIELDS) {
      const text = (gate0[g.key] ?? '').trim();
      if (text) note[g.key] = text;
    }
    let input: SchemaProposalInput;
    if (isField) {
      // EVERY CHOICE IS THE READER'S. An unchosen type or "required?" is sent as missing, so the
      // server's own sentence asks for it; nothing is defaulted here.
      const change: Partial<SchemaChangeInput> & { kind: 'add_field' } = { kind: 'add_field' };
      if (parentPath !== null) change.parent_path = parentPath;
      if (fieldName.trim()) change.field_name = fieldName.trim();
      if (valueType) change.value_type = valueType;
      if (required) change.required = required === 'yes';
      if (unit.trim() && unitAllowed) change.unit = unit.trim();
      if (example.trim()) change.example = example.trim();
      if (scope) change.scope = scope;
      if (migration.trim()) change.migration = migration.trim();
      input = {
        proposal_type: 'schema_change',
        section: sectionId,
        description: description.trim(),
        change: change as SchemaChangeInput,
        ...(Object.keys(note).length > 0 ? { gate0: note } : {}),
      };
    } else {
      input = {
        proposal_type: type,
        section: sectionId,
        category: category.trim(),
        description: description.trim(),
        ...(type === 'add_term' ? { term: term.trim() } : {}),
        ...(Object.keys(note).length > 0 ? { gate0: note } : {}),
      };
      const source = fromLocalDraft && localDraft ? sourceFromDraft(localDraft.draft, localDraft.bundleId) : null;
      if (source) input.source = source;
    }
    try {
      const response = await api.createSchemaProposal(input);
      setSaved(response);
      setTerm('');
      setDescription('');
      setGate0({});
      setFrom(null);
      setLocalDraft(null);
      setFieldName('');
      setExample('');
      setMigration('');
      onSaved();
    } catch (err) {
      const fieldErrors = schemaFieldErrors(err);
      setErrors(fieldErrors);
      setTopMessage(
        serverMessageOf(err) ??
          'The proposal could not be saved, and nothing was written. Check your connection and try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  const descriptionCount = description.trim().length;
  const savedIsField = saved?.proposal.proposal_type === 'schema_change';

  return (
    <section className="sp-panel" aria-label={COPY.tabPropose}>
      <p className="sp-note">{COPY.proposeLead}</p>

      {linkRefused !== null && (
        <p className="sp-note" role="status">
          The link that opened this form named {linkRefused}, which is not a term list in the portal vocabulary
          snapshot, so nothing was filled in. The portal would refuse a new term for it.
        </p>
      )}

      {saved && (
        <div className="sp-saved" role="status" tabIndex={-1} ref={savedRef}>
          <p className="sp-saved-title">{savedIsField ? COPY.schemaChangeSaved : COPY.savedNotice}</p>
          {saved.withdrawn_removed ? (
            <p>
              To stay within the server&apos;s limit, {saved.withdrawn_removed} of the oldest withdrawn proposals{' '}
              {saved.withdrawn_removed === 1 ? 'was' : 'were'} removed.
            </p>
          ) : null}
          {saved.ignored_fields && saved.ignored_fields.length > 0 && (
            <p>Ignored, because the server sets them: {saved.ignored_fields.join(', ')}.</p>
          )}
          <div className="sp-actions">
            {savedIsField ? (
              <ChangeRequestActions proposalId={saved.proposal.id} />
            ) : (
              <PortalActions proposalId={saved.proposal.id} />
            )}
            <button type="button" className="btn btn-secondary" onClick={onViewProposals}>
              View Proposals
            </button>
          </div>
        </div>
      )}

      <LocalDraftsLoader vocabulary={vocabulary} onUse={openLocalDraft} />

      {(topMessage || elsewhere.length > 0) && (
        <div className="sp-error-summary" role="alert" tabIndex={-1} ref={summaryRef}>
          <p className="sp-error-title">{topMessage}</p>
          {elsewhere.length > 0 && (
            <ul>
              {elsewhere.map((er, i) => (
                <li key={`${er.code}-${i}`}>{er.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {from !== null && !isField && (
        <p className="sp-note" role="note">
          Opened from {PROPOSE_SOURCES[from]}, with the list and the value as they appeared there. Check the term
          before saving: the portal takes one word, and nothing here has changed what you saw.
        </p>
      )}

      {fromLocalDraft && localDraft && (
        <div className="sp-notice" role="note">
          <p>
            Opened on a draft from a local import: the list <code className="sp-term">{localDraft.draft.category}</code>{' '}
            and the term <code className="sp-term">{localDraft.draft.term}</code> as the drafts file holds them. The
            description is empty: write what the term means and where it is used, in your own words. The reviewer
            notes below come from the file&apos;s counts and citations; change them if they are wrong.
          </p>
          {localDraft.missing.length > 0 && (
            <p>
              The file has nothing for{' '}
              {localDraft.missing.map((k) => GATE0_FIELDS.find((g) => g.key === k)?.label ?? k).join(' or ')}, so it
              is empty and marked required: write it yourself.
            </p>
          )}
          <div className="sp-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setLocalDraft(null)}>
              Stop Using This Draft
            </button>
          </div>
        </div>
      )}

      <form className="sp-form" onSubmit={onSubmit} noValidate>
        <fieldset className="sp-fieldset">
          <legend id={ids.type}>What do you want to propose?</legend>
          <label className="sp-radio">
            <input
              type="radio"
              name="schema-proposal-type"
              checked={type === 'add_term'}
              onChange={() => setType('add_term')}
            />
            <span>Add a term to an existing list</span>
          </label>
          <label className="sp-radio">
            <input
              type="radio"
              name="schema-proposal-type"
              checked={type === 'add_category'}
              onChange={() => setType('add_category')}
            />
            <span>Add a new list of allowed terms</span>
          </label>
          {schemaChange && (
            <label className="sp-radio">
              <input
                type="radio"
                name="schema-proposal-type"
                checked={type === 'schema_change'}
                onChange={() => setType('schema_change')}
              />
              <span>Add a new field to the ISAAC schema (a schema change request)</span>
            </label>
          )}
          <FieldError id={`${ids.type}-err`} message={errorFor('proposal_type')} />
        </fieldset>

        {isField && schemaChange && (
          <div className="sp-notice" role="note">
            <p>{schemaChange.not_a_portal_proposal}</p>
            <p>{COPY.schemaChangeLead}</p>
          </div>
        )}

        <div className="sp-field">
          <label htmlFor={ids.section}>Section</label>
          <select
            id={ids.section}
            className="input sp-select"
            value={sectionId}
            onChange={(e) => setSectionId(e.target.value)}
            aria-invalid={errorFor('section') ? true : undefined}
            aria-describedby={errorFor('section') ? `${ids.section}-err` : undefined}
          >
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <FieldError id={`${ids.section}-err`} message={errorFor('section')} />
        </div>

        {type === 'add_term' && (
          <>
            <div className="sp-field">
              <label htmlFor={ids.category}>Category</label>
              <select
                id={ids.category}
                className="input sp-select"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                aria-invalid={errorFor('category') ? true : undefined}
                aria-describedby={`${ids.category}-hint${errorFor('category') ? ` ${ids.category}-err` : ''}`}
              >
                <option value="">Choose a list…</option>
                {listsInSection.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
              {listsInSection.length === 0 ? (
                <p className="sp-hint" id={`${ids.category}-hint`}>
                  The portal vocabulary snapshot has no term lists in this section. Choose another section, or propose a
                  new list.
                </p>
              ) : (
                <span id={`${ids.category}-hint`} className="sr-only">
                  The list the new term belongs to.
                </span>
              )}
              <FieldError id={`${ids.category}-err`} message={errorFor('category')} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.term}>New term</label>
              <input
                id={ids.term}
                className="input input-mono"
                value={term}
                maxLength={limits.term_max}
                placeholder="for example rotating_cylinder"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => setTerm(e.target.value)}
                aria-invalid={errorFor('term') ? true : undefined}
                aria-describedby={`${ids.term}-hint${errorFor('term') ? ` ${ids.term}-err` : ''}`}
              />
              <p className="sp-hint" id={`${ids.term}-hint`}>
                {vocabulary.term_rule}
              </p>
              <FieldError id={`${ids.term}-err`} message={errorFor('term')} />
            </div>
          </>
        )}

        {type === 'add_category' && (
          <div className="sp-field">
            <label htmlFor={ids.category}>New list key</label>
            <input
              id={ids.category}
              className="input input-mono"
              value={category}
              maxLength={limits.category_max}
              placeholder="for example context.transport.viscosity"
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => setCategory(e.target.value)}
              aria-invalid={errorFor('category') ? true : undefined}
              aria-describedby={`${ids.category}-hint${errorFor('category') ? ` ${ids.category}-err` : ''}`}
            />
            <p className="sp-hint" id={`${ids.category}-hint`}>
              A dotted path of field names. It starts with the section&apos;s own block name
              {section?.block ? ` (${section.block}.)` : ''}.
            </p>
            <FieldError id={`${ids.category}-err`} message={errorFor('category')} />
          </div>
        )}

        {isField && schemaChange && (
          <>
            <div className="sp-field">
              <label htmlFor={ids.parent}>Where in the schema</label>
              <select
                id={ids.parent}
                className="input sp-select"
                /* `@` + the path, so the record root (path '') is a choice distinct from "none chosen". */
                value={parentPath === null ? '' : `@${parentPath}`}
                onChange={(e) => setParentPath(e.target.value === '' ? null : e.target.value.slice(1))}
                aria-required="true"
                aria-invalid={errorFor('change.parent_path') ? true : undefined}
                aria-describedby={`${ids.parent}-hint${errorFor('change.parent_path') ? ` ${ids.parent}-err` : ''}`}
              >
                <option value="">Choose a block…</option>
                {parentsInSection.map((o) => (
                  <option key={o.path} value={`@${o.path}`}>
                    {o.path === '' ? 'The record root' : o.path}
                  </option>
                ))}
              </select>
              <p className="sp-hint" id={`${ids.parent}-hint`}>
                {parentsInSection.length === 0
                  ? 'The ISAAC schema has no block in this section. Choose another section.'
                  : parent === null
                    ? 'The blocks the ISAAC schema declares in this section.'
                    : `${parent.path === '' ? 'The record root' : parent.path} has ${parent.fields.length} field${
                        parent.fields.length === 1 ? '' : 's'
                      } today: ${parent.fields.join(', ')}. ${
                        parent.open
                          ? 'It accepts keys the schema does not declare.'
                          : 'It refuses any key the schema does not declare, so a record cannot carry the new field until the schema changes.'
                      }`}
              </p>
              <FieldError id={`${ids.parent}-err`} message={errorFor('change.parent_path')} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.fieldName}>New field name</label>
              <input
                id={ids.fieldName}
                className="input input-mono"
                value={fieldName}
                maxLength={limits.field_name_max ?? 80}
                placeholder="for example c_rate"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => setFieldName(e.target.value)}
                aria-required="true"
                aria-invalid={errorFor('change.field_name') ? true : undefined}
                aria-describedby={`${ids.fieldName}-hint${errorFor('change.field_name') ? ` ${ids.fieldName}-err` : ''}`}
              />
              <p className="sp-hint" id={`${ids.fieldName}-hint`}>
                One word: a letter, then letters, digits or underscores.
                {parent !== null && fieldName.trim() !== ''
                  ? ` The full path would be ${parent.path ? `${parent.path}.` : ''}${fieldName.trim()}.`
                  : ''}
              </p>
              <FieldError id={`${ids.fieldName}-err`} message={errorFor('change.field_name')} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.valueType}>Kind of value</label>
              <select
                id={ids.valueType}
                className="input sp-select"
                value={valueType}
                onChange={(e) => setValueType(e.target.value as SchemaChangeValueType | '')}
                aria-required="true"
                aria-invalid={errorFor('change.value_type') ? true : undefined}
                aria-describedby={errorFor('change.value_type') ? `${ids.valueType}-err` : undefined}
              >
                <option value="">Choose…</option>
                {schemaChange.value_types.map((t) => (
                  <option key={t} value={t}>
                    {VALUE_TYPE_LABEL[t] ?? t}
                  </option>
                ))}
              </select>
              <FieldError id={`${ids.valueType}-err`} message={errorFor('change.value_type')} />
            </div>

            {unitAllowed && (
              <div className="sp-field">
                <label htmlFor={ids.unit}>Unit (optional)</label>
                <input
                  id={ids.unit}
                  className="input input-mono"
                  value={unit}
                  maxLength={limits.unit_max ?? 40}
                  placeholder="for example mA/g"
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(e) => setUnit(e.target.value)}
                  aria-invalid={errorFor('change.unit') ? true : undefined}
                  aria-describedby={errorFor('change.unit') ? `${ids.unit}-err` : undefined}
                />
                <FieldError id={`${ids.unit}-err`} message={errorFor('change.unit')} />
              </div>
            )}

            {/* A real radio group, so `aria-required` / `aria-invalid` are valid on it (they are not on a fieldset). */}
            <div
              className="sp-fieldset"
              role="radiogroup"
              aria-labelledby={ids.required}
              aria-required="true"
              aria-invalid={errorFor('change.required') ? true : undefined}
              aria-describedby={errorFor('change.required') ? `${ids.required}-err` : undefined}
            >
              <p className="sp-legend" id={ids.required}>Must every record in this block carry it?</p>
              <label className="sp-radio">
                <input type="radio" name="schema-change-required" checked={required === 'yes'} onChange={() => setRequired('yes')} />
                <span>Yes, required</span>
              </label>
              <label className="sp-radio">
                <input type="radio" name="schema-change-required" checked={required === 'no'} onChange={() => setRequired('no')} />
                <span>No, optional</span>
              </label>
              <FieldError id={`${ids.required}-err`} message={errorFor('change.required')} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.example}>Example value (optional)</label>
              <input
                id={ids.example}
                className="input input-mono"
                value={example}
                maxLength={limits.example_max ?? 500}
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => setExample(e.target.value)}
                aria-invalid={errorFor('change.example') ? true : undefined}
                aria-describedby={errorFor('change.example') ? `${ids.example}-err` : undefined}
              />
              <FieldError id={`${ids.example}-err`} message={errorFor('change.example')} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.scope}>Who needs it (optional)</label>
              <select
                id={ids.scope}
                className="input sp-select"
                value={scope}
                onChange={(e) => setScope(e.target.value as SchemaChangeScope | '')}
                aria-invalid={errorFor('change.scope') ? true : undefined}
                aria-describedby={`${ids.scope}-hint${errorFor('change.scope') ? ` ${ids.scope}-err` : ''}`}
              >
                <option value="">Not stated</option>
                {schemaChange.scopes.map((sc) => (
                  <option key={sc} value={sc}>
                    {sc === 'core' ? 'Every science (the core)' : 'One science (a domain profile)'}
                  </option>
                ))}
              </select>
              <p className="sp-hint" id={`${ids.scope}-hint`}>
                The standard&apos;s process puts a field only one science needs in that science&apos;s profile.
              </p>
              <FieldError id={`${ids.scope}-err`} message={errorFor('change.scope')} />
            </div>
          </>
        )}

        <div className="sp-field">
          <label htmlFor={ids.description}>{isField ? 'Definition (required)' : 'Description (required)'}</label>
          <textarea
            id={ids.description}
            ref={descriptionRef}
            className="input sp-textarea"
            rows={4}
            value={description}
            maxLength={limits.description_max}
            placeholder={
              isField
                ? 'What the field holds, in which unit, and when a record carries it.'
                : 'Say what this means and where it is used. A reviewer writes the definition from it.'
            }
            onChange={(e) => setDescription(e.target.value)}
            aria-required="true"
            aria-invalid={errorFor('description') ? true : undefined}
            aria-describedby={`${ids.description}-hint${errorFor('description') ? ` ${ids.description}-err` : ''}`}
          />
          <p className="sp-hint" id={`${ids.description}-hint`}>
            At least {limits.description_min} characters, at most {limits.description_max}. {descriptionCount}{' '}
            so far.
          </p>
          <FieldError id={`${ids.description}-err`} message={errorFor('description')} />
        </div>

        <details className="sp-why" open={isField || from !== null || fromLocalDraft ? true : undefined}>
          <summary>
            {isField
              ? 'Why (for reviewers): the problem is required for a new field'
              : fromLocalDraft
                ? 'Why (for reviewers): the examples and records affected are required for a draft from a local import'
                : 'Why (for reviewers), optional'}
          </summary>
          <p className="sp-hint">
            Reviewers of changes to the standard look for the problem, who it affects and what would change.
            These answers travel with your {isField ? 'change request' : 'description'}.
          </p>
          {GATE0_FIELDS.map((g) => {
            const fieldId = `${ids.description}-gate0-${g.key}`;
            const err = errorFor(`gate0.${g.key}`);
            const requiredHere =
              (isField && g.key === 'problem') ||
              (fromLocalDraft && (g.key === 'examples' || g.key === 'affected_records_estimate'));
            return (
              <div className="sp-field" key={g.key}>
                <label htmlFor={fieldId}>
                  {g.label}
                  {requiredHere ? ' (required)' : ''}
                </label>
                <textarea
                  id={fieldId}
                  className="input sp-textarea"
                  rows={g.rows}
                  value={gate0[g.key] ?? ''}
                  onChange={(e) => setGate0((prev) => ({ ...prev, [g.key]: e.target.value }))}
                  aria-required={requiredHere ? true : undefined}
                  aria-invalid={err ? true : undefined}
                  aria-describedby={`${fieldId}-hint${err ? ` ${fieldId}-err` : ''}`}
                />
                <p className="sp-hint" id={`${fieldId}-hint`}>
                  {g.hint}
                </p>
                <FieldError id={`${fieldId}-err`} message={err} />
              </div>
            );
          })}
          {isField && (
            <div className="sp-field">
              <label htmlFor={ids.migration}>Migration, version and rollback (optional)</label>
              <textarea
                id={ids.migration}
                className="input sp-textarea"
                rows={3}
                value={migration}
                maxLength={limits.migration_max ?? 2000}
                onChange={(e) => setMigration(e.target.value)}
                aria-invalid={errorFor('change.migration') ? true : undefined}
                aria-describedby={`${ids.migration}-hint${errorFor('change.migration') ? ` ${ids.migration}-err` : ''}`}
              />
              <p className="sp-hint" id={`${ids.migration}-hint`}>
                The standard&apos;s process asks a schema change for these. Leave it empty if you do not know; the
                document will say it was not written.
              </p>
              <FieldError id={`${ids.migration}-err`} message={errorFor('change.migration')} />
            </div>
          )}
        </details>

        <div className="sp-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save Proposal'}
          </button>
          <span className="sp-hint">Saving keeps a draft here. It does not send it to anyone.</span>
        </div>
      </form>
    </section>
  );
}

// --- Load drafts from a local import ---------------------------------------------

/** Read a chosen file to text, in this browser — the same fallback the Validator uses. */
function readFileText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error('The file could not be read.'));
    reader.readAsText(file);
  });
}

/** Why a draft cannot be filed here, or null when it can. The file's own reason comes first. */
function whyNotFileable(vocabulary: ApiSchemaVocabulary, d: LocalTermDraft): string | null {
  if (!d.drafted || d.body === null) {
    return d.reason ?? 'The drafts file did not draft this term, and gives no reason.';
  }
  if (d.body.proposal_type !== 'add_term' || d.body.category !== d.category || d.body.term !== d.term) {
    return 'The draft in the file does not match its own field and term, so it is not filed from here.';
  }
  if (portalSectionFor(vocabulary, d.category) === null) {
    return `The vocabulary on this server has no portal term list ${d.category}, so the portal would refuse a new term for it.`;
  }
  if (!canProposeTerm(vocabulary, d.category, d.term)) {
    return 'The vocabulary on this server would refuse this term now: the list may already hold it, or the term is not one word. The file was written against an earlier list.';
  }
  if (d.count === null || d.count < 1) {
    return 'The drafts file gives no count for this term, so there is nothing to say how often it was read.';
  }
  return null;
}

function LocalDraftsLoader({
  vocabulary,
  onUse,
}: {
  vocabulary: ApiSchemaVocabulary;
  onUse: (draft: LocalTermDraft, bundleId: string | null) => void;
}) {
  const ids = { heading: useId(), input: useId(), hint: useId() };
  const [fileName, setFileName] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<LocalTermDraftsFile | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [announce, setAnnounce] = useState('');

  async function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ''; // choosing the same file again reads it again
    if (!file) return;
    setFileName(file.name);
    setLoaded(null);
    setProblem(null);
    setAnnounce('');
    if (file.size > TERM_DRAFTS_MAX_BYTES) {
      setProblem(`This file is ${Math.ceil(file.size / 1024)} KB, larger than a drafts file can be, so it was not read.`);
      return;
    }
    let text: string;
    try {
      text = await readFileText(file);
    } catch {
      setProblem('This browser could not read the file. Nothing was read and nothing was sent.');
      return;
    }
    const parsed = parseTermDraftsFile(text);
    if (!parsed.ok) {
      setProblem(parsed.message);
      return;
    }
    setLoaded(parsed.file);
    const can = parsed.file.drafts.filter((d) => whyNotFileable(vocabulary, d) === null).length;
    const total = parsed.file.drafts.length;
    setAnnounce(
      total === 0
        ? 'The drafts file lists no terms outside the vocabulary.'
        : `Read ${total} ${total === 1 ? 'term' : 'terms'} from ${file.name}: ${can} can be proposed, ${total - can} cannot. Nothing was sent.`,
    );
  }

  return (
    <section className="sp-notice sp-drafts" aria-labelledby={ids.heading}>
      <h2 className="sp-h2" id={ids.heading}>
        {COPY.localImportTitle}
      </h2>
      <p>{COPY.localImportLead}</p>
      <p>{isHostedBuild ? COPY.localImportWhereHosted : COPY.localImportWhereLocal}</p>
      <div className="sp-field">
        <label htmlFor={ids.input}>Drafts file (JSON)</label>
        <input
          id={ids.input}
          type="file"
          accept="application/json,.json"
          className="sp-file"
          aria-describedby={ids.hint}
          onChange={onFileChange}
        />
        <p className="sp-hint" id={ids.hint}>
          The file <code>isaac bundle propose-terms &lt;bundle&gt; --out &lt;file.json&gt;</code> wrote.
          {fileName ? ` Last chosen: ${fileName}.` : ''}
        </p>
      </div>
      <p className="sr-only" role="status" aria-live="polite">
        {announce}
      </p>
      {problem && (
        <p className="sp-field-error" role="alert">
          {problem}
        </p>
      )}
      {loaded && loaded.drafts.length === 0 && <p>The drafts file lists no terms outside the vocabulary.</p>}
      {loaded && loaded.drafts.length > 0 && (
        <ul className="sp-list" aria-label="Drafts in the file">
          {loaded.drafts.map((d) => (
            <LocalDraftItem
              key={d.key}
              draft={d}
              whyNot={whyNotFileable(vocabulary, d)}
              onUse={() => onUse(d, loaded.bundleId)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function LocalDraftItem({ draft, whyNot, onUse }: { draft: LocalTermDraft; whyNot: string | null; onUse: () => void }) {
  const counts = countsSentence(draft);
  const lists = draft.missingFrom.map((m) => (m === 'portal' ? "the portal's list" : m === 'schema' ? "the ISAAC schema's list" : m));
  return (
    <li className="sp-item">
      <h3 className="sp-item-title">
        <code className="sp-term">{draft.term}</code>
      </h3>
      <dl className="sp-why-list">
        <dt>Field</dt>
        <dd>
          <code className="sp-term">{draft.fieldPath}</code>
        </dd>
        <dt>How often</dt>
        <dd>
          {counts ?? 'The file gives no count.'}
          {draft.runs === null ? ' Runs: not stated in the file.' : ''}
        </dd>
        {lists.length > 0 && (
          <>
            <dt>Not on</dt>
            <dd>{lists.join(' or ')}</dd>
          </>
        )}
        <dt>Your words</dt>
        <dd>
          {draft.scientistNotes.length > 0
            ? draft.scientistNotes.map((n) => `“${n}”`).join(' ')
            : 'The file has none for this term.'}
        </dd>
        <dt>Where it was read</dt>
        <dd>
          {draft.citations.length === 0
            ? 'The file cites nothing for this term.'
            : draft.citations.slice(0, 3).map(citationLine).join('\n') +
              ((draft.citationsTotal ?? draft.citations.length) > 3
                ? `\nand ${(draft.citationsTotal ?? draft.citations.length) - 3} more`
                : '')}
        </dd>
        {draft.problems.length > 0 && (draft.drafted || !draft.reason) && (
          <>
            <dt>Problems the file reports</dt>
            <dd>{draft.problems.map((p) => p.message).join(' ')}</dd>
          </>
        )}
      </dl>
      {whyNot === null ? (
        <div className="sp-actions">
          <button type="button" className="btn btn-secondary" onClick={onUse}>
            Propose This Term
          </button>
          <span className="sp-hint">Opens the form below with the description empty. Nothing is sent until you save.</span>
        </div>
      ) : (
        <p className="sp-item-text">
          <strong>Cannot be proposed from here.</strong> {whyNot}
        </p>
      )}
    </li>
  );
}

function FieldError({ id, message }: { id: string; message: string | undefined }) {
  if (!message) return null;
  return (
    <p className="sp-field-error" id={id}>
      {message}
    </p>
  );
}

// --- Proposals ------------------------------------------------------------------

const PAGE_SIZE = 25;

function ProposalsPanel({ version }: { version: number }) {
  const first = useFetch(() => api.listSchemaProposals({ limit: PAGE_SIZE, offset: 0 }), [version]);
  const [more, setMore] = useState<ApiSchemaProposal[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  /** A proposal changed in place by a withdraw, keyed by id, so the list needs no refetch. */
  const [changed, setChanged] = useState<Record<string, ApiSchemaProposal>>({});

  const firstData = first.status === 'data' ? first.data : null;
  useEffect(() => {
    // A fresh first page replaces everything that was appended after the previous one.
    setMore([]);
    setChanged({});
    setMoreFailed(false);
    setNextOffset(firstData ? firstData.next_offset : null);
  }, [firstData]);

  async function showMore() {
    if (nextOffset === null || loadingMore) return;
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const page = await api.listSchemaProposals({ limit: PAGE_SIZE, offset: nextOffset });
      setMore((prev) => [...prev, ...page.proposals]);
      setNextOffset(page.next_offset);
    } catch {
      setMoreFailed(true);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="sp-panel" aria-label={COPY.tabProposals}>
      {first.status === 'loading' && <LoadingPanel label="Loading proposals…" />}
      {first.status === 'error' && <BackendDown error={first.error} onRetry={first.reload} />}
      {firstData && (
        <>
          <div className="sp-notice">
            <p>{firstData.persistence.message}</p>
            <p>
              {firstData.capacity.pending} of {firstData.capacity.max_pending} pending places used. {firstData.capacity.scope}
            </p>
            <p>{COPY.unverifiedAuthor}</p>
          </div>

          {firstData.total === 0 ? (
            <p className="sp-note">No proposals on this server yet. Use Propose a Change to draft one.</p>
          ) : (
            <>
              <p className="sp-meta" role="status">
                {firstData.total} {firstData.total === 1 ? 'proposal' : 'proposals'}, newest first.
              </p>
              <ul className="sp-list">
                {[...firstData.proposals, ...more].map((p) => (
                  <ProposalRow
                    key={p.id}
                    proposal={changed[p.id] ?? p}
                    onChanged={(next) => setChanged((prev) => ({ ...prev, [p.id]: next }))}
                  />
                ))}
              </ul>
              {moreFailed && (
                <p className="sp-field-error" role="alert">
                  The next proposals could not be loaded. Try again.
                </p>
              )}
              {nextOffset !== null && (
                <div className="sp-actions">
                  <button type="button" className="btn btn-secondary" onClick={showMore} disabled={loadingMore}>
                    {loadingMore ? 'Loading…' : 'Show More'}
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

function ProposalRow({
  proposal,
  onChanged,
}: {
  proposal: ApiSchemaProposal;
  onChanged: (next: ApiSchemaProposal) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // what just happened to this proposal, said in a live region and kept on the row
  const [said, setSaid] = useState('');
  const confirmRef = useRef<HTMLButtonElement>(null);
  const withdrawRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  function keep() {
    setConfirming(false);
    setSaid('Kept. The proposal is still pending.');
    // the Withdraw button is rendered again once the confirmation closes
    requestAnimationFrame(() => withdrawRef.current?.focus());
  }

  async function withdraw() {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    setSaid('');
    try {
      const response = await api.withdrawSchemaProposal(proposal.id);
      setConfirming(false);
      onChanged(response.proposal);
      setSaid('Withdrawn. The proposal is no longer pending.');
      // the Withdraw control is gone: focus the proposal itself, whose status now reads Withdrawn
      requestAnimationFrame(() => titleRef.current?.focus());
    } catch (err) {
      setConfirming(false);
      setFailure(serverMessageOf(err) ?? 'The proposal could not be withdrawn. Nothing was changed.');
      // Hand focus back to a control that still exists.
      requestAnimationFrame(() => withdrawRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  const gate0 = proposal.gate0;
  return (
    <li className="sp-item">
      <div className="sp-item-head">
        <h2 className="sp-item-title" tabIndex={-1} ref={titleRef}>
          {proposalHeadline(proposal)}
        </h2>
        <span className={`sp-status sp-status-${proposal.status}`}>{STATUS_LABEL[proposal.status]}</span>
      </div>
      <p className="sp-item-meta">
        {proposal.section}
        {` · ${PROPOSAL_KIND_LABEL[proposal.proposal_type] ?? proposal.proposal_type}`}
        {proposal.proposed_at && (
          <>
            {' · drafted '}
            <time dateTime={proposal.proposed_at} title={proposal.proposed_at}>
              {formatWhen(proposal.proposed_at) ?? proposal.proposed_at}
            </time>
          </>
        )}
        {proposal.withdrawn_at && (
          <>
            {' · withdrawn '}
            <time dateTime={proposal.withdrawn_at} title={proposal.withdrawn_at}>
              {formatWhen(proposal.withdrawn_at) ?? proposal.withdrawn_at}
            </time>
          </>
        )}
      </p>
      <p className="sp-item-text">{proposal.description}</p>
      {proposal.source && (
        <p className="sp-item-meta">
          {COPY.localImportFiledFrom}
          {proposal.source.bundle_id ? ` (${proposal.source.bundle_id})` : ''}
          {proposal.source.occurrences !== null ? `: ${proposal.source.occurrences} readings` : ''}
          {proposal.source.runs !== null ? ` in ${proposal.source.runs} runs` : ''}.
        </p>
      )}
      {proposal.proposal_type === 'schema_change' && proposal.change && <ChangeSummary change={proposal.change} />}
      {gate0 && (
        <dl className="sp-why-list">
          {gate0.problem && (
            <>
              <dt>The problem</dt>
              <dd>{gate0.problem}</dd>
            </>
          )}
          {gate0.examples && (
            <>
              <dt>Examples</dt>
              <dd>{gate0.examples}</dd>
            </>
          )}
          {gate0.affected_records_estimate && (
            <>
              <dt>Records affected</dt>
              <dd>{gate0.affected_records_estimate}</dd>
            </>
          )}
          {gate0.flip_list && (
            <>
              <dt>What would change</dt>
              <dd>{gate0.flip_list}</dd>
            </>
          )}
        </dl>
      )}
      <p className="sp-item-meta">
        {proposal.attribution === 'verified' && proposal.proposed_by
          ? `Proposed by ${proposal.proposed_by}`
          : 'Author not recorded (not verified).'}
      </p>

      <div className="sp-actions">
        {proposal.proposal_type === 'schema_change' ? (
          <ChangeRequestActions proposalId={proposal.id} />
        ) : (
          <PortalActions proposalId={proposal.id} />
        )}
        {proposal.status === 'pending' && !confirming && (
          <button
            type="button"
            className="btn btn-secondary"
            ref={withdrawRef}
            onClick={() => setConfirming(true)}
          >
            Withdraw
          </button>
        )}
        {proposal.status === 'pending' && confirming && (
          <span className="sp-confirm" role="group" aria-label="Confirm withdrawing this proposal">
            <span>Withdraw this proposal? This cannot be undone.</span>
            <button type="button" className="btn btn-danger" ref={confirmRef} onClick={withdraw} disabled={busy}>
              {busy ? 'Withdrawing…' : 'Confirm Withdraw'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={keep} disabled={busy}>
              Keep It
            </button>
          </span>
        )}
      </div>
      {failure && (
        <p className="sp-field-error" role="alert">
          {failure}
        </p>
      )}
      <p className="sp-item-meta" role="status" data-testid="sp-row-status">
        {said}
      </p>
    </li>
  );
}

/** A schema change request's own facts, from the stored change and nothing else. */
function ChangeSummary({ change }: { change: ApiSchemaChange }) {
  return (
    <dl className="sp-why-list">
      <dt>Field</dt>
      <dd className="sp-term">{change.path ?? 'unknown'}</dd>
      <dt>Kind of value</dt>
      <dd>
        {change.value_type ? VALUE_TYPE_LABEL[change.value_type] ?? change.value_type : 'not stated'}
        {change.unit ? `, in ${change.unit}` : ''}
      </dd>
      <dt>Required</dt>
      <dd>{change.required === true ? 'Yes' : change.required === false ? 'No' : 'Not stated'}</dd>
      {change.example && (
        <>
          <dt>Example</dt>
          <dd className="sp-term">{change.example}</dd>
        </>
      )}
      {change.parent_open_today === false && (
        <>
          <dt>Today</dt>
          <dd>The schema refuses undeclared keys in {change.parent_path || 'the record root'}.</dd>
        </>
      )}
    </dl>
  );
}

/**
 * Copy the change-request document as Markdown, or download it as Markdown or JSON. It is
 * fetched when asked for — the server's exact text, never rebuilt here — and it is NOT a
 * portal payload: there is no "paste into the portal" here, because the portal has no
 * proposal type for a new field.
 */
function ChangeRequestActions({ proposalId }: { proposalId: string }) {
  const [state, setState] = useState<
    | { kind: 'idle' }
    | { kind: 'busy' }
    | { kind: 'copied'; notes: string[] }
    | { kind: 'downloaded'; what: string; notes: string[] }
    | { kind: 'manual'; text: string; notes: string[] }
    | { kind: 'failed' }
  >({ kind: 'idle' });

  async function copy() {
    setState({ kind: 'busy' });
    let request: Awaited<ReturnType<typeof api.getSchemaProposalChangeRequest>>;
    try {
      request = await api.getSchemaProposalChangeRequest(proposalId);
    } catch {
      setState({ kind: 'failed' });
      return;
    }
    try {
      await navigator.clipboard.writeText(request.markdown);
      setState({ kind: 'copied', notes: request.notes });
    } catch {
      setState({ kind: 'manual', text: request.markdown, notes: request.notes });
    }
  }

  async function download(format: 'md' | 'json') {
    setState({ kind: 'busy' });
    try {
      const request = await api.getSchemaProposalChangeRequest(proposalId);
      const text = format === 'md' ? request.markdown : changeRequestJsonText(request);
      const name =
        format === 'md'
          ? changeRequestMarkdownFilename(request.filename_stem)
          : changeRequestJsonFilename(request.filename_stem);
      const url = URL.createObjectURL(
        new Blob([text], { type: format === 'md' ? 'text/markdown' : 'application/json' }),
      );
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState({ kind: 'downloaded', what: format === 'md' ? 'Markdown' : 'JSON', notes: request.notes });
    } catch {
      setState({ kind: 'failed' });
    }
  }

  const busy = state.kind === 'busy';
  const notes = state.kind === 'copied' || state.kind === 'downloaded' || state.kind === 'manual' ? state.notes : [];
  return (
    <span className="sp-portal">
      <button type="button" className="btn btn-secondary" onClick={copy} disabled={busy}>
        <Copy size={14} strokeWidth={2} aria-hidden="true" /> Copy Change Request
      </button>
      <button type="button" className="btn btn-secondary" onClick={() => download('md')} disabled={busy}>
        <Download size={14} strokeWidth={2} aria-hidden="true" /> Download Markdown
      </button>
      <button type="button" className="btn btn-secondary" onClick={() => download('json')} disabled={busy}>
        <Download size={14} strokeWidth={2} aria-hidden="true" /> Download JSON
      </button>
      <span className="sp-portal-status" role="status">
        {state.kind === 'copied' &&
          'Copied the change request as Markdown. ISAAC has not sent it. It is for the standard\'s owners, not the portal.'}
        {state.kind === 'downloaded' &&
          `Downloaded the change request as ${state.what}. ISAAC has not sent it anywhere.`}
        {state.kind === 'failed' && 'The change request could not be prepared. Nothing was copied.'}
        {state.kind === 'manual' && 'Your browser did not allow copying. Select the text below and copy it.'}
      </span>
      {notes.length > 0 && (
        <ul className="sp-portal-notes">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {state.kind === 'manual' && (
        <textarea
          className="input input-mono sp-textarea"
          readOnly
          rows={10}
          aria-label="Change request"
          value={state.text}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
    </span>
  );
}

// --- Copy / download ------------------------------------------------------------

/**
 * Copy the portal body, or download it as JSON. The body is fetched when asked for — it is
 * the server's exact answer, never rebuilt here — and is the ONLY thing either control hands
 * out. Neither sends anything anywhere: copying puts text on the reader's clipboard, and the
 * person who pastes it into the portal is the person who sends it.
 */
function PortalActions({ proposalId }: { proposalId: string }) {
  /** What the server said about where this payload goes. Shown with every outcome. */
  type Where = { restSupported: boolean; notes: string[] };
  const [state, setState] = useState<
    | { kind: 'idle' }
    | { kind: 'busy' }
    | { kind: 'copied'; where: Where }
    | { kind: 'downloaded'; where: Where }
    | { kind: 'manual'; text: string; where: Where }
    | { kind: 'failed' }
  >({ kind: 'idle' });

  async function load() {
    const payload = await api.getSchemaProposalPortalPayload(proposalId);
    return {
      text: portalBodyText(payload),
      where: { restSupported: payload.portal.rest_supported, notes: payload.notes },
    };
  }

  async function copy() {
    setState({ kind: 'busy' });
    let loaded: Awaited<ReturnType<typeof load>>;
    try {
      loaded = await load();
    } catch {
      setState({ kind: 'failed' });
      return;
    }
    try {
      await navigator.clipboard.writeText(loaded.text);
      setState({ kind: 'copied', where: loaded.where });
    } catch {
      // No clipboard permission: show the text for the reader to select and copy by hand,
      // rather than saying it was copied.
      setState({ kind: 'manual', text: loaded.text, where: loaded.where });
    }
  }

  async function download() {
    setState({ kind: 'busy' });
    try {
      const { text, where } = await load();
      const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = portalBodyFilename(proposalId);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState({ kind: 'downloaded', where });
    } catch {
      setState({ kind: 'failed' });
    }
  }

  const busy = state.kind === 'busy';
  const where = state.kind === 'copied' || state.kind === 'downloaded' || state.kind === 'manual' ? state.where : null;
  /** The destination, from the server's own flag: new terms go to the portal's web endpoint; a new list does not. */
  const destination = where
    ? where.restSupported
      ? 'Paste it into the ISAAC portal.'
      : "The portal's web endpoint takes new terms only: enter this in the portal's Ontology Editor (its Propose a Change form), using these fields."
    : null;
  return (
    <span className="sp-portal">
      <button type="button" className="btn btn-secondary" onClick={copy} disabled={busy}>
        <Copy size={14} strokeWidth={2} aria-hidden="true" /> Copy Portal Payload
      </button>
      <button type="button" className="btn btn-secondary" onClick={download} disabled={busy}>
        <Download size={14} strokeWidth={2} aria-hidden="true" /> Download JSON
      </button>
      <span className="sp-portal-status" role="status">
        {state.kind === 'copied' && `Copied. ISAAC has not sent it. ${destination}`}
        {state.kind === 'downloaded' && `Downloaded. ISAAC has not sent it anywhere. ${destination}`}
        {state.kind === 'failed' && 'The portal payload could not be prepared. Nothing was copied.'}
        {state.kind === 'manual' && 'Your browser did not allow copying. Select the text below and copy it.'}
      </span>
      {where && where.notes.length > 0 && (
        <ul className="sp-portal-notes">
          {where.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {state.kind === 'manual' && (
        <textarea
          className="input input-mono sp-textarea"
          readOnly
          rows={8}
          aria-label="Portal payload"
          value={state.text}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
    </span>
  );
}
