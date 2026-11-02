import './screens.css';
// The shared `.chip` shape first, so this screen's tone modifiers (and their borders) always come after it.
import '../components/signals.css';
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
  type RefObject,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { BackendDown, LoadingPanel } from '../components/FetchStates';
import { ChevronRight, Copy, Download, Plus } from '../components/icons';
import { Select } from '../components/Select';
import { SegmentedControl } from '../components/SegmentedControl';
import { InlineCode } from '../components/InlineCode';
import { LABELS, formatWhen } from '../lib/labels';
import { api } from '../lib/api';
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
  portalTermsFor,
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
  noteAttribution,
  parseTermDraftsFile,
  sourceFromDraft,
  type LocalTermDraft,
  type LocalTermDraftsFile,
} from '../lib/termDrafts';

/**
 * SCHEMA PROPOSALS — one page to propose a change to the ISAAC standard (a term, a list or a
 * field), with this server's proposals beside the form and the whole vocabulary folded below it.
 *
 * WHAT THIS SCREEN WILL NOT DO, and each is a claim a test pins by behaviour:
 *
 *   1. IT NEVER APPROVES, APPLIES OR SENDS. There is no such control. A proposal is a
 *      draft on this server; the people who own the ISAAC standard review it in the
 *      ISAAC portal and record any decision there. The two states shown are the
 *      server's own — Pending and Withdrawn — and Pending is worded to claim nothing
 *      about whether anyone has seen it.
 *   2. IT NAMES NOBODY IT CANNOT VERIFY. A proposal records no author unless the server
 *      verified one, and then (only then) the row names them.
 *   3. IT DOES NOT PRETEND TO KEEP WHAT THE SERVER MAY LOSE. Every response carries the
 *      server's own statement of how long a proposal lasts; its first sentence is shown
 *      beside the proposals, and nothing on the page claims more.
 *   4. IT NEVER LOSES WHAT YOU TYPED. It is one page: the form, the proposals and the
 *      vocabulary are all mounted at once, so nothing you look at unmounts the form, and a
 *      refused submit leaves every box as it was, with the server's own sentence beside the
 *      box it is about.
 */

/**
 * The old `?tab=` links still land somewhere sensible: `browse` opens the folded vocabulary and
 * scrolls to it, `proposals` scrolls to the list. The page never writes the parameter.
 */
const LEGACY_TAB_PARAM = 'tab';

/** A request to open the form on a given section and category, with a counter so asking twice re-applies. */
interface Prefill {
  type: SchemaProposalType;
  section: string;
  category: string;
  /** A term carried from the screen where the gap was found (`?term=`). */
  term?: string;
  /** Which screen that was (`?from=`); only the names in `PROPOSE_SOURCES` are shown. */
  from?: ProposeSource;
  /** Where focus goes once the form is filled (Browse's contextual actions): the one box left to fill. */
  focus?: 'term' | 'listKey' | 'where';
  nonce: number;
}

/** Open Look Up an Existing List on a section (and a list in it), with focus on its Section picker. */
interface BrowseRequest {
  section: string | null;
  category: string | null;
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
  const [params] = useSearchParams();
  const legacyTab = params.get(LEGACY_TAB_PARAM);

  const vocabulary = useFetch(() => api.getSchemaVocabulary(), []);
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  /** Bumped whenever a proposal is saved, so the list refetches. */
  const [listVersion, setListVersion] = useState(0);
  const [browseOpen, setBrowseOpen] = useState(legacyTab === 'browse');
  /** "Browse All Lists" from the form: open Look Up on that list's section (and list), focus its Section picker. */
  const [browseRequest, setBrowseRequest] = useState<BrowseRequest | null>(null);
  const openBrowse = useCallback((section: string | null, category: string | null) => {
    setBrowseOpen(true);
    setBrowseRequest((previous) => ({ section, category, nonce: (previous?.nonce ?? 0) + 1 }));
  }, []);
  const browseRef = useRef<HTMLDetailsElement>(null);
  const proposalsRef = useRef<HTMLElement>(null);
  const ids = { propose: useId(), proposals: useId() };

  /**
   * Browse's contextual actions: open the form on that kind, in that section (and on that list, for a term),
   * and put the cursor in the one box left to fill.
   */
  const proposeFromBrowse = useCallback((type: SchemaProposalType, section: string, category: string) => {
    setPrefill((previous) => ({
      type,
      section,
      category,
      focus: type === 'add_term' ? 'term' : type === 'add_category' ? 'listKey' : 'where',
      nonce: (previous?.nonce ?? 0) + 1,
    }));
  }, []);

  /*
   * PROPOSE FROM WHERE THE GAP WAS FOUND. A link from another screen
   * (`?category=…&term=…&from=…`) opens the form on that list with that term.
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

  // An old `?tab=` link, honoured once what moves the page has settled: the vocabulary for Browse; the
  // vocabulary AND the first page of proposals for the list (both change the height above or around it).
  const [proposalsSettled, setProposalsSettled] = useState(false);
  const legacyApplied = useRef(false);
  useEffect(() => {
    if (legacyApplied.current || vocabulary.status === 'loading') return;
    if (legacyTab === 'browse') {
      legacyApplied.current = true;
      setBrowseOpen(true);
      window.setTimeout(() => browseRef.current?.scrollIntoView?.({ block: 'start' }), 0);
    } else if (legacyTab === 'proposals') {
      if (!proposalsSettled) return;
      legacyApplied.current = true;
      window.setTimeout(() => proposalsRef.current?.scrollIntoView?.({ block: 'start' }), 0);
    } else {
      legacyApplied.current = true;
    }
  }, [legacyTab, vocabulary.status, proposalsSettled]);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="schemaProposals" />}
      mainPad="pad"
      width="full"
    >
      <div className="sp-screen">
        <header className="sp-head">
          <h1 className="page-title">{LABELS.navSchemaProposals}</h1>
          <p className="sp-lead">{COPY.lead}</p>
          <p className="sp-boundary">{COPY.boundary}</p>
        </header>

        <div className="sp-layout">
          <div className="sp-main">
            <section className="sp-panel" aria-labelledby={ids.propose}>
              <h2 className="sp-h2" id={ids.propose}>
                {COPY.proposeTitle}
              </h2>
              {vocabulary.status === 'loading' && <LoadingPanel label="Reading the vocabulary…" />}
              {vocabulary.status === 'error' && <BackendDown error={vocabulary.error} onRetry={vocabulary.reload} />}
              {vocabulary.status === 'data' && (
                <ProposePanel
                  vocabulary={vocabulary.data}
                  prefill={prefill}
                  linkRefused={linkRefused}
                  onSaved={() => setListVersion((v) => v + 1)}
                  onBrowseLists={openBrowse}
                />
              )}
            </section>
          </div>

          {/* The vocabulary spans the page under both columns, so section, lists and terms can sit side by side. */}
          {vocabulary.status === 'data' && (
            <details
              className="sp-browse sp-fold"
              ref={browseRef}
              open={browseOpen}
              onToggle={(e) => setBrowseOpen(e.currentTarget.open)}
            >
              <summary>
                <ChevronRight className="sp-chevron" size={16} strokeWidth={2} aria-hidden="true" />
                {COPY.browseTitle}
              </summary>
              <BrowsePanel vocabulary={vocabulary.data} onPropose={proposeFromBrowse} request={browseRequest} />
            </details>
          )}
          <ProposalsPanel
            version={listVersion}
            headingId={ids.proposals}
            sectionRef={proposalsRef}
            onSettled={() => setProposalsSettled(true)}
          />
        </div>
      </div>
    </AppShell>
  );
}

// --- Browse ---------------------------------------------------------------------

/** A list's own name, said the way a person would: "record_type" -> "Record type". The key stays beside it. */
function humanLabel(label: string): string {
  const words = label.replace(/[_.]+/g, ' ').trim();
  return words ? words[0].toUpperCase() + words.slice(1) : label;
}

/** A section's name without its parenthetical ("Record Info (root fields)" -> "Record Info"), for action text. */
function sectionName(label: string): string {
  return label.replace(/\s*\([^)]*\)\s*$/, '');
}

function BrowsePanel({
  vocabulary,
  onPropose,
  request,
}: {
  vocabulary: ApiSchemaVocabulary;
  /** Open the form on this kind and section (and list, for a term), with the cursor in the box left to fill. */
  onPropose: (type: SchemaProposalType, section: string, category: string) => void;
  /** The form's "Browse All Lists": show this section (and list), then focus the Section picker. */
  request: BrowseRequest | null;
}) {
  const ids = { section: useId(), lists: useId(), pane: useId() };
  const sectionPickerRef = useRef<HTMLButtonElement>(null);
  const [sourceId, setSourceId] = useState<SchemaSourceId>(vocabulary.default_source);
  const source = vocabulary.sources[sourceId];
  const sections = source.sections;
  const [sectionId, setSectionId] = useState(sections[0]?.id ?? '');
  const section: ApiSchemaSection | undefined = sections.find((s) => s.id === sectionId) ?? sections[0];
  const [categoryKey, setCategoryKey] = useState<string | null>(null);
  const category: ApiSchemaCategory | undefined =
    section?.categories.find((c) => c.key === categoryKey) ?? section?.categories[0];

  useEffect(() => {
    if (!request) return;
    // The form's lists are the portal's, so a requested section is looked up in the portal source.
    const portalHas = request.section !== null && vocabulary.sources.portal.sections.some((s) => s.id === request.section);
    if (portalHas && request.section !== null) {
      setSourceId('portal');
      setSectionId(request.section);
      setCategoryKey(request.category);
    }
    // After the fold has opened and re-rendered on that section: bring the picker into view and focus it.
    window.setTimeout(() => {
      sectionPickerRef.current?.scrollIntoView?.({ block: 'center' });
      sectionPickerRef.current?.focus({ preventScroll: true });
    }, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- applied once per request
  }, [request?.nonce]);
  // A new term can join only a list the PORTAL has, because the portal is what checks it.
  const proposalSection = vocabulary.proposal_sections.find((s) => s.id === section?.id);
  const canAddTerm = category !== undefined && (proposalSection?.term_lists ?? []).includes(category.key);
  const canAddList = proposalSection !== undefined;
  const canAddField =
    vocabulary.schema_change !== undefined &&
    vocabulary.schema_change !== null &&
    vocabulary.schema_change.object_paths.some((o) => o.section === section?.id);
  const shortSection = section ? sectionName(section.label) : '';

  /** The one quiet fact about the chosen source a person needs: what it is, which copy, and how big. */
  const sourceLine =
    sourceId === 'portal'
      ? `The ISAAC portal's terms${source.snapshot_commit ? `, snapshot ${source.snapshot_commit}` : ''}`
      : `The record schema's fixed lists, version ${vocabulary.schema_version}`;

  const sectionActions = section && (canAddList || canAddField) && (
    <div className="sp-browse-actions">
      {canAddList && (
        <button type="button" className="btn sp-text-btn" onClick={() => onPropose('add_category', section.id, '')}>
          <Plus size={14} strokeWidth={2.25} aria-hidden="true" /> New List in {shortSection}
        </button>
      )}
      {canAddField && (
        <button type="button" className="btn sp-text-btn" onClick={() => onPropose('schema_change', section.id, '')}>
          <Plus size={14} strokeWidth={2.25} aria-hidden="true" /> New Field in {shortSection}
        </button>
      )}
    </div>
  );

  return (
    <div className="sp-browse-body">
      <p className="sp-note">{COPY.browseLead}</p>

      <div className="sp-browse-controls">
        <SegmentedControl
          label="Source"
          options={[
            { value: 'portal', label: LABELS.actionSpSourcePortal },
            { value: 'schema', label: LABELS.actionSpSourceSchema },
          ]}
          value={sourceId}
          onChange={(v) => {
            const id = v as SchemaSourceId;
            setSourceId(id);
            setSectionId(vocabulary.sources[id].sections[0]?.id ?? '');
            setCategoryKey(null);
          }}
        />
        <div className="sp-field sp-browse-section">
          <label htmlFor={ids.section}>Section</label>
          <Select
            ref={sectionPickerRef}
            id={ids.section}
            value={section?.id ?? ''}
            options={sections.map((s) => ({
              value: s.id,
              label: s.label,
              detail: s.categories.length === 1 ? '1 list' : `${s.categories.length} lists`,
            }))}
            onChange={(v) => {
              setSectionId(v);
              setCategoryKey(null);
            }}
          />
        </div>
      </div>
      <p className="sp-meta">
        {sourceLine}: {source.section_count} sections, {source.term_list_count} term lists, {source.term_count} terms.
      </p>

      {section && section.categories.length === 0 && (
        <>
          <p className="sp-note" role="status">
            This section has no fixed lists of allowed terms in this source.
          </p>
          {sectionActions}
        </>
      )}

      {section && section.categories.length > 0 && (
        <div className="sp-browse-grid">
          <div className="sp-browse-lists">
            <h3 className="sp-h3" id={ids.lists}>
              Lists in {shortSection}
            </h3>
            <ul className="sp-cat-list" aria-labelledby={ids.lists}>
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
                      <span className="sp-cat-text">
                        <span className="sp-cat-name">{humanLabel(c.label)}</span>
                        <span className="sp-cat-key">{c.key}</span>
                      </span>
                      <span className="sp-cat-count">
                        {c.kind === 'other' ? 'Mapping, no fixed terms' : c.terms.length === 1 ? '1 term' : `${c.terms.length} terms`}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            {sectionActions}
          </div>

          {category && (
            <section className="sp-browse-pane" aria-labelledby={ids.pane}>
              <div className="sp-browse-pane-head">
                <div className="sp-browse-pane-title">
                  <h3 className="sp-h3" id={ids.pane}>
                    {humanLabel(category.label)}
                  </h3>
                  <span className="sp-cat-key">{category.key}</span>
                </div>
                {canAddTerm && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => onPropose('add_term', section.id, category.key)}
                  >
                    Propose a Term for This List
                  </button>
                )}
              </div>
              {category.description && <p className="sp-note">{category.description}</p>}
              {category.kind === 'other' ? (
                <p className="sp-note">A mapping or a unit grammar, not a list of allowed terms.</p>
              ) : (
                <ul className="sp-term-chips" aria-label={`Allowed terms for ${category.key}`}>
                  {category.terms.map((term) => (
                    <li key={term} className="sp-term-chip">
                      {term}
                    </li>
                  ))}
                </ul>
              )}
              {!canAddTerm && category.kind !== 'other' && (
                <p className="sp-hint">The portal has no list for this entry here, so it would refuse a new term for it.</p>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  );
}

// --- Propose --------------------------------------------------------------------

/** How many of a list's terms the "Already on the list" hint names before it says how many more. */
const TERMS_SHOWN = 12;

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
  onBrowseLists,
}: {
  vocabulary: ApiSchemaVocabulary;
  prefill: Prefill | null;
  /** A link named a list the portal has no term list for, so nothing was filled in. */
  linkRefused: string | null;
  onSaved: () => void;
  /** Open Look Up an Existing List, on the chosen list's section when there is one. */
  onBrowseLists: (section: string | null, category: string | null) => void;
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
    saveHint: useId(),
    filing: useId(),
    kindHint: useId(),
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
  const termRef = useRef<HTMLInputElement>(null);
  const listKeyRef = useRef<HTMLInputElement>(null);
  const whereRef = useRef<HTMLButtonElement>(null);
  const filingRef = useRef<HTMLDivElement>(null);
  /**
   * The drafts of the loaded file a proposal has been saved from (by `key`), so their rows say so and
   * cannot be filed twice. They belong to that file: the loader clears them when another file is read.
   */
  const [savedDraftKeys, setSavedDraftKeys] = useState<ReadonlySet<string>>(() => new Set());
  /** "Stop Using This Draft" hands focus back to that draft's restored button; a counter so asking twice re-applies. */
  const [returnFocus, setReturnFocus] = useState<{ draft: LocalTermDraft; nonce: number } | null>(null);
  // A new field (schema change request).
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [fieldName, setFieldName] = useState('');
  const [valueType, setValueType] = useState<SchemaChangeValueType | ''>('');
  const [unit, setUnit] = useState('');
  const [required, setRequired] = useState<'' | 'yes' | 'no'>('');
  const [example, setExample] = useState('');
  const [scope, setScope] = useState<SchemaChangeScope | ''>('');
  const [migration, setMigration] = useState('');

  /** Whether the reviewer notes are open: the reader's own choice, except that they open when they become needed. */
  const [notesOpen, setNotesOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<SchemaFieldError[]>([]);
  const [topMessage, setTopMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState<ApiSchemaProposalResponse | null>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const savedRef = useRef<HTMLDivElement>(null);

  const section = sections.find((s) => s.id === sectionId);
  const listsInSection = useMemo(() => section?.term_lists ?? [], [section]);
  /** The sections that have a portal term list, each an <optgroup> of the one "List" choice. */
  const listGroups = useMemo(() => sections.filter((s) => s.term_lists.length > 0), [sections]);
  /** A list key in more than one section needs its section in the option's value to stay one choice. */
  const sharedListKeys = useMemo(() => {
    const seen = new Map<string, number>();
    for (const s of sections) for (const key of s.term_lists) seen.set(key, (seen.get(key) ?? 0) + 1);
    return new Set([...seen].filter(([, n]) => n > 1).map(([key]) => key));
  }, [sections]);
  const listValue = (sid: string, key: string) => (sharedListKeys.has(key) ? `${sid}\u001f${key}` : key);
  /** The List picker's options, grouped by section, and what each one means (its section and its key). */
  /** A list's human name, as Browse shows it ("Record type"), from the portal's own label for it; else its key. */
  const listName = useCallback(
    (sid: string, key: string) => {
      const label = vocabulary.sources.portal.sections.find((x) => x.id === sid)?.categories.find((c) => c.key === key)?.label;
      return label ? humanLabel(label) : key;
    },
    [vocabulary],
  );
  const listOptions = useMemo(
    () =>
      listGroups.flatMap((s) =>
        s.term_lists.map((key) => ({ value: listValue(s.id, key), label: listName(s.id, key), detail: key, group: s.label })),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- listValue depends only on sharedListKeys
    [listGroups, sharedListKeys, listName],
  );
  const listByValue = useMemo(() => {
    const m = new Map<string, { section: string; key: string }>();
    for (const s of listGroups) for (const key of s.term_lists) m.set(listValue(s.id, key), { section: s.id, key });
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- listValue depends only on sharedListKeys
  }, [listGroups, sharedListKeys]);
  /** Every block of the schema a new field could go in, as the server derived them. */
  const objectPaths = useMemo(() => schemaChange?.object_paths ?? [], [schemaChange]);
  /** The same blocks, grouped by section for the "Where in the schema" choice. */
  const pathGroups = useMemo(() => {
    const groups: { id: string; label: string; paths: typeof objectPaths }[] = [];
    for (const o of objectPaths) {
      let g = groups.find((x) => x.id === o.section);
      if (!g) {
        g = { id: o.section, label: sections.find((s) => s.id === o.section)?.label ?? o.section, paths: [] };
        groups.push(g);
      }
      g.paths.push(o);
    }
    return groups;
  }, [objectPaths, sections]);
  const parentsInSection = useMemo(() => objectPaths.filter((o) => o.section === sectionId), [objectPaths, sectionId]);
  const parent = parentsInSection.find((o) => o.path === parentPath) ?? null;
  /** What the chosen portal list already holds, so a term it has is not proposed again. */
  const termsOnList = type === 'add_term' && category !== '' ? portalTermsFor(vocabulary, sectionId, category) : null;
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
    if (prefill.focus) {
      // After the form has re-rendered on that kind: the box left to fill is brought into view and focused.
      const target = prefill.focus;
      window.setTimeout(() => {
        const el = target === 'term' ? termRef.current : target === 'listKey' ? listKeyRef.current : whereRef.current;
        el?.scrollIntoView?.({ block: 'center' });
        el?.focus({ preventScroll: true });
      }, 0);
    }
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
  /** Stop using the draft; focus goes back to its row's restored button, or to the description box if that row is gone. */
  function stopUsingDraft() {
    if (localDraft) setReturnFocus((prev) => ({ draft: localDraft.draft, nonce: (prev?.nonce ?? 0) + 1 }));
    setLocalDraft(null);
    window.setTimeout(() => {
      const active = document.activeElement;
      if (active === null || active === document.body) descriptionRef.current?.focus();
    }, 0);
  }

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
    setReturnFocus(null);
    setErrors([]);
    setTopMessage(null);
    setSaved(null);
    // After the form has re-rendered: the note saying what is being proposed is scrolled to the top of the
    // view, and the one box left to the scientist gets focus without scrolling that note away again. The box
    // is described by the note, so a screen reader hears it too.
    window.setTimeout(() => {
      filingRef.current?.scrollIntoView?.({ block: 'start' });
      descriptionRef.current?.focus({ preventScroll: true });
    }, 0);
  }

  const fromLocalDraft = localDraft !== null && type === 'add_term';
  /** The portal section the draft's list is in, by its label, for the "Proposing:" line. */
  const draftSectionLabel = localDraft
    ? (sections.find((s) => s.id === portalSectionFor(vocabulary, localDraft.draft.category))?.label ?? null)
    : null;

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
    /** The draft this save files, when it carries the draft's `source`. */
    let filedDraftKey: string | null = null;
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
      if (source) {
        input.source = source;
        filedDraftKey = localDraft?.draft.key ?? null;
      }
    }
    try {
      const response = await api.createSchemaProposal(input);
      setSaved(response);
      if (filedDraftKey !== null) {
        const key = filedDraftKey;
        setSavedDraftKeys((prev) => new Set(prev).add(key));
      }
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
  const sectionError = errorFor('section');
  const reviewerNotesRequired = isField || fromLocalDraft;
  const notesWanted = reviewerNotesRequired || from !== null;
  // On the rising edge only: becoming needed opens the notes; no longer needed leaves them as they are.
  useEffect(() => {
    if (notesWanted) setNotesOpen(true);
  }, [notesWanted]);
  /** The kinds a reader can choose, in the order they are offered; the third only when the server describes it. */
  const kinds: { type: SchemaProposalType; title: string; hint: string }[] = [
    { type: 'add_term', title: COPY.kindTerm, hint: COPY.kindTermHint },
    { type: 'add_category', title: COPY.kindList, hint: COPY.kindListHint },
    ...(schemaChange ? [{ type: 'schema_change' as const, title: COPY.kindField, hint: COPY.kindFieldHint }] : []),
  ];

  return (
    <>
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
          </div>
        </div>
      )}

      <LocalDraftsLoader
        vocabulary={vocabulary}
        current={fromLocalDraft && localDraft ? localDraft.draft : null}
        savedKeys={savedDraftKeys}
        returnFocus={returnFocus}
        onRead={() => setSavedDraftKeys(new Set())}
        onUse={openLocalDraft}
      />

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
          before saving: the portal takes one word.
        </p>
      )}

      {/*
        WHAT IS BEING PROPOSED, said before the form: the one list and the one word, what the drafts
        file filled in, and the one thing it cannot (the description, which is the scientist's own).
      */}
      {fromLocalDraft && localDraft && (
        <div className="sp-notice sp-filing" role="note" id={ids.filing} ref={filingRef}>
          <p className="sp-filing-title" id={`${ids.filing}-what`}>
            {LABELS.draftFilingLead} add <code className="sp-term">{localDraft.draft.term}</code> to{' '}
            <code className="sp-term">{localDraft.draft.category}</code>
            {draftSectionLabel ? ` (${draftSectionLabel})` : ''}
          </p>
          <p>
            The drafts file from the local import
            {localDraft.bundleId ? (
              <>
                {' '}
                <code className="sp-term">{localDraft.bundleId}</code>
              </>
            ) : null}{' '}
            filled in the list, the term, and the reviewer notes below (from its counts and citations). Change the
            notes if they are wrong.
          </p>
          <p id={`${ids.filing}-left`}>
            The description is left to you: write what the term means and where it is used, in your own words, at
            least {limits.description_min} characters.
          </p>
          {localDraft.missing.length > 0 && (
            <p>
              The file has nothing for{' '}
              {localDraft.missing.map((k) => GATE0_FIELDS.find((g) => g.key === k)?.label ?? k).join(' or ')}, so it
              is empty and marked required: write it yourself.
            </p>
          )}
          <div className="sp-actions">
            <button type="button" className="btn sp-text-btn" onClick={stopUsingDraft}>
              Stop Using This Draft
            </button>
          </div>
        </div>
      )}

      <form className="sp-form" onSubmit={onSubmit} noValidate>
        {/*
          THE ONE CHOICE THAT SHAPES THE REST: each kind is a card whose name is its title alone, and
          whose one-line hint is its description, so a screen reader hears the name, then what it means.
        */}
        <fieldset className="sp-fieldset">
          <legend id={ids.type}>What do you want to propose?</legend>
          <div className="sp-kinds">
            {kinds.map((k) => {
              const hintId = `${ids.kindHint}-${k.type}`;
              const selected = type === k.type;
              return (
                <label className={`sp-kind${selected ? ' is-selected' : ''}`} key={k.type}>
                  <input
                    type="radio"
                    name="schema-proposal-type"
                    checked={selected}
                    onChange={() => setType(k.type)}
                    aria-describedby={hintId}
                  />
                  <span className="sp-kind-text">
                    <span className="sp-kind-name">{k.title}</span>
                    <span className="sp-kind-hint" id={hintId} aria-hidden="true">
                      {k.hint}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
          <FieldError id={`${ids.type}-err`} message={errorFor('proposal_type')} />
        </fieldset>

        {isField && schemaChange && <p className="sp-note">{COPY.schemaChangeLead}</p>}

        {type === 'add_term' && (
          <>
            {/* One choice, not two: the list, grouped by the section it is in. The section sent is the group's. */}
            <div className="sp-field">
              <label htmlFor={ids.category}>List</label>
              <Select
                id={ids.category}
                className="sp-picker-keys"
                value={category === '' ? '' : listValue(sectionId, category)}
                placeholder="Choose a list…"
                options={listOptions}
                onChange={(v) => {
                  const chosen = listByValue.get(v);
                  if (!chosen) {
                    setCategory('');
                    return;
                  }
                  setSectionId(chosen.section);
                  setCategory(chosen.key);
                }}
                aria-invalid={errorFor('category') || sectionError ? true : undefined}
                aria-describedby={`${ids.category}-hint${errorFor('category') ? ` ${ids.category}-err` : ''}${
                  sectionError ? ` ${ids.section}-err` : ''
                }`}
              />
              {/* The hint, and beside it the way to look the lists over before choosing one. */}
              <div className="sp-hint-row">
                {listGroups.length === 0 ? (
                  <p className="sp-hint" id={`${ids.category}-hint`}>
                    The portal vocabulary snapshot has no term lists, so there is no list to add a term to. Propose a
                    new list instead.
                  </p>
                ) : termsOnList !== null ? (
                  <p className="sp-hint" id={`${ids.category}-hint`}>
                    Already on the list ({termsOnList.length})
                    {termsOnList.length === 0 ? (
                      ': nothing yet.'
                    ) : (
                      <>
                        : <span className="sp-term">{termsOnList.slice(0, TERMS_SHOWN).join(', ')}</span>
                        {termsOnList.length > TERMS_SHOWN ? ` and ${termsOnList.length - TERMS_SHOWN} more.` : '.'}
                      </>
                    )}
                  </p>
                ) : (
                  <span id={`${ids.category}-hint`} className="sr-only">
                    The list the new term belongs to.
                  </span>
                )}
                {listGroups.length > 0 && (
                  <button
                    type="button"
                    className="btn sp-text-btn sp-hint-action"
                    onClick={() => onBrowseLists(category !== '' ? sectionId : null, category !== '' ? category : null)}
                  >
                    Browse All Lists
                  </button>
                )}
              </div>
              <FieldError id={`${ids.category}-err`} message={errorFor('category')} />
              <FieldError id={`${ids.section}-err`} message={sectionError} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.term}>New term</label>
              <input
                id={ids.term}
                ref={termRef}
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
          <>
            <div className="sp-field">
              <label htmlFor={ids.section}>Section</label>
              <Select
                id={ids.section}
                value={sectionId}
                options={sections.map((s) => ({ value: s.id, label: s.label }))}
                onChange={setSectionId}
                aria-invalid={sectionError ? true : undefined}
                aria-describedby={sectionError ? `${ids.section}-err` : undefined}
              />
              <FieldError id={`${ids.section}-err`} message={sectionError} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.category}>New list key</label>
              <input
                id={ids.category}
                ref={listKeyRef}
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
          </>
        )}

        {isField && schemaChange && (
          <>
            {/* One choice, not two: the block, grouped by section. The section sent is the block's own. */}
            <div className="sp-field">
              <label htmlFor={ids.parent}>Where in the schema</label>
              <Select
                ref={whereRef}
                id={ids.parent}
                /* `@` + the path, so the record root (path '') is a choice distinct from "none chosen". */
                value={parent === null ? '' : `@${parent.path}`}
                placeholder="Choose a block…"
                options={pathGroups.flatMap((g) =>
                  g.paths.map((o) => ({ value: `@${o.path}`, label: o.path === '' ? 'The record root' : o.path, group: g.label })),
                )}
                onChange={(v) => {
                  const path = v.slice(1);
                  const chosen = objectPaths.find((o) => o.path === path);
                  if (chosen) setSectionId(chosen.section);
                  setParentPath(path);
                }}
                aria-required="true"
                aria-invalid={errorFor('change.parent_path') || sectionError ? true : undefined}
                aria-describedby={`${ids.parent}-hint${errorFor('change.parent_path') ? ` ${ids.parent}-err` : ''}${
                  sectionError ? ` ${ids.section}-err` : ''
                }`}
              />
              <p className="sp-hint" id={`${ids.parent}-hint`}>
                {objectPaths.length === 0
                  ? 'The ISAAC schema declares no block a new field could go in.'
                  : parent === null
                    ? 'The blocks the ISAAC schema declares, by section.'
                    : `${parent.path === '' ? 'The record root' : parent.path} has ${parent.fields.length} field${
                        parent.fields.length === 1 ? '' : 's'
                      } today: ${parent.fields.join(', ')}. ${
                        parent.open
                          ? 'It accepts keys the schema does not declare.'
                          : 'It refuses any key the schema does not declare, so a record cannot carry the new field until the schema changes.'
                      }`}
              </p>
              <FieldError id={`${ids.parent}-err`} message={errorFor('change.parent_path')} />
              <FieldError id={`${ids.section}-err`} message={sectionError} />
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
              <Select
                id={ids.valueType}
                value={valueType}
                placeholder="Choose…"
                options={schemaChange.value_types.map((t) => ({ value: t, label: VALUE_TYPE_LABEL[t] ?? t }))}
                onChange={(v) => setValueType(v as SchemaChangeValueType | '')}
                aria-required="true"
                aria-invalid={errorFor('change.value_type') ? true : undefined}
                aria-describedby={errorFor('change.value_type') ? `${ids.valueType}-err` : undefined}
              />
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

            {/* Nothing is chosen until the person chooses: an unchosen answer is sent as missing, never defaulted. */}
            <div className="sp-field">
              <SegmentedControl
                label="Must every record in this block carry it?"
                options={[
                  { value: 'yes', label: LABELS.actionSpRequired },
                  { value: 'no', label: LABELS.actionSpOptional },
                ]}
                value={required === '' ? null : required}
                onChange={(v) => setRequired(v as 'yes' | 'no')}
                aria-required
                aria-invalid={errorFor('change.required') ? true : undefined}
                aria-describedby={errorFor('change.required') ? `${ids.required}-err` : undefined}
              />
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
              <Select
                id={ids.scope}
                value={scope}
                options={[
                  { value: '', label: 'Not stated' },
                  ...schemaChange.scopes.map((sc) => ({
                    value: sc,
                    label: sc === 'core' ? 'Every science (the core)' : 'One science (a domain profile)',
                  })),
                ]}
                onChange={(v) => setScope(v as SchemaChangeScope | '')}
                aria-invalid={errorFor('change.scope') ? true : undefined}
                aria-describedby={`${ids.scope}-hint${errorFor('change.scope') ? ` ${ids.scope}-err` : ''}`}
              />
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
            aria-describedby={`${ids.description}-hint${fromLocalDraft ? ` ${ids.filing}-what ${ids.filing}-left` : ''}${errorFor('description') ? ` ${ids.description}-err` : ''}`}
          />
          <p className="sp-hint" id={`${ids.description}-hint`}>
            At least {limits.description_min} characters, at most {limits.description_max}. {descriptionCount}{' '}
            so far.
          </p>
          <FieldError id={`${ids.description}-err`} message={errorFor('description')} />
        </div>

        {/* Opened when something in it becomes required, or a link fills part of it in; never closed for the
            reader (a change of kind keeps it as they left it). */}
        <details className="sp-why" open={notesOpen} onToggle={(e) => setNotesOpen(e.currentTarget.open)}>
          <summary>
            <ChevronRight className="sp-chevron" size={16} strokeWidth={2} aria-hidden="true" />
            {LABELS.headingSpReviewerNotes}
            <span className="sp-summary-aside">{reviewerNotesRequired ? ' (some required)' : ' (optional)'}</span>
          </summary>
          <p className="sp-hint">
            Reviewers look for the problem, who it affects and what would change; these notes travel with your{' '}
            {isField ? 'change request' : 'proposal'}.
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
                  // tall enough for what a draft filled in (one citation a line, and a line's room for one that
                  // wraps), up to 8 lines; then it scrolls
                  rows={Math.min(8, Math.max(g.rows, (gate0[g.key] ?? '').split('\n').length + 1))}
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

        {/* What Save does, in one line beside it: one click, no second step. */}
        <div className="sp-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting} aria-describedby={ids.saveHint}>
            {submitting ? 'Saving…' : 'Save Proposal'}
          </button>
          <span className="sp-hint" id={ids.saveHint}>
            {COPY.saveHint}
          </span>
        </div>
      </form>
    </>
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
  if (d.carriedOver) {
    return 'This term is no longer found in the bundle: an earlier drafts file had it, and the latest run of `isaac bundle propose-terms` did not find it, so it is not proposed from here.';
  }
  if (d.answered) {
    return d.reason ?? 'The scientist has since answered every run they asked this term for, so it is not proposed.';
  }
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

/** Which group a draft is listed under. */
type DraftGroup = 'needs' | 'saved' | 'refused' | 'settled';

/** The groups under "Other Terms in the File", in order. The `needs` group is "Ready to Propose", above them. */
const OTHER_GROUPS: { id: Exclude<DraftGroup, 'needs'>; title: string }[] = [
  { id: 'saved', title: LABELS.headingSpSavedFromFile },
  { id: 'refused', title: LABELS.headingSpCannotPropose },
  { id: 'settled', title: LABELS.headingSpNothingNeeded },
];

interface DraftRow {
  draft: LocalTermDraft;
  whyNot: string | null;
}

/*
 * THE GROUP IS DECIDED BY `whyNotFileable` AND NOTHING ELSE, plus what was saved here: a draft it
 * accepts needs the scientist's description, until a proposal is saved from it; a refused one the
 * scientist has already settled (answered since, or no longer in the bundle) needs nothing; every
 * other refusal is the file's or this server's.
 */
function groupDrafts(
  vocabulary: ApiSchemaVocabulary,
  drafts: LocalTermDraft[],
  savedKeys: ReadonlySet<string>,
): Record<DraftGroup, DraftRow[]> {
  const out: Record<DraftGroup, DraftRow[]> = { needs: [], saved: [], refused: [], settled: [] };
  for (const draft of drafts) {
    const whyNot = whyNotFileable(vocabulary, draft);
    const group: DraftGroup =
      whyNot === null
        ? savedKeys.has(draft.key)
          ? 'saved'
          : 'needs'
        : draft.carriedOver || draft.answered
          ? 'settled'
          : 'refused';
    out[group].push({ draft, whyNot });
  }
  return out;
}

/**
 * "2 need your description · 1 saved as a draft · 1 cannot be proposed." — the counts after "From …:". Zero
 * counts are left out.
 */
function draftsCounts(groups: Record<DraftGroup, DraftRow[]>): string {
  const n = (g: DraftGroup) => groups[g].length;
  const verb = (k: number) => (k === 1 ? 'needs' : 'need');
  const parts = [
    n('needs') > 0 ? `${n('needs')} ${verb(n('needs'))} your description` : null,
    n('saved') > 0 ? `${n('saved')} saved as ${n('saved') === 1 ? 'a draft' : 'drafts'}` : null,
    n('refused') > 0 ? `${n('refused')} cannot be proposed` : null,
    n('settled') > 0 ? `${n('settled')} ${verb(n('settled'))} nothing from you` : null,
  ].filter((p): p is string => p !== null);
  return `${parts.join(' · ')}.`;
}

function LocalDraftsLoader({
  vocabulary,
  current,
  savedKeys,
  returnFocus,
  onRead,
  onUse,
}: {
  vocabulary: ApiSchemaVocabulary;
  /** The draft the form below is open on, if any: its row is marked. Matched by identity, so a file read again marks nothing. */
  current: LocalTermDraft | null;
  /** Keys of this file's drafts a proposal was saved from. */
  savedKeys: ReadonlySet<string>;
  /** The draft whose button should take focus back (after "Stop Using This Draft"). */
  returnFocus: { draft: LocalTermDraft; nonce: number } | null;
  /** Another file is being read: what was saved from the last one no longer applies. */
  onRead: () => void;
  onUse: (draft: LocalTermDraft, bundleId: string | null) => void;
}) {
  const ids = { input: useId(), hint: useId(), group: useId() };
  const [fileName, setFileName] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<LocalTermDraftsFile | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  /** Closed until wanted; once a file has been read it is opened, and nothing here closes it again. */
  const [open, setOpen] = useState(false);

  async function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ''; // choosing the same file again reads it again
    if (!file) return;
    setOpen(true);
    setFileName(file.name);
    setLoaded(null);
    setProblem(null);
    onRead();
    if (file.size > TERM_DRAFTS_MAX_BYTES) {
      setProblem(`This file is ${Math.ceil(file.size / 1024)} KB, larger than a drafts file can be, so it was not read.`);
      return;
    }
    let text: string;
    try {
      text = await readFileText(file);
    } catch {
      setProblem('This browser could not read the file.');
      return;
    }
    const parsed = parseTermDraftsFile(text);
    if (!parsed.ok) {
      setProblem(parsed.message);
      return;
    }
    setLoaded(parsed.file);
  }

  const groups = useMemo(
    () => (loaded ? groupDrafts(vocabulary, loaded.drafts, savedKeys) : null),
    [loaded, vocabulary, savedKeys],
  );
  // The summary is worked out from the same groups the lists are drawn from, so its counts are the rows shown.
  const summary =
    !loaded || !groups ? null : loaded.drafts.length === 0 ? (
      'The drafts file lists no terms outside the vocabulary.'
    ) : (
      <>
        From{' '}
        {loaded.bundleId ? (
          <>
            the local import <code className="sp-term">{loaded.bundleId}</code>
          </>
        ) : (
          (fileName ?? 'the drafts file')
        )}
        : {draftsCounts(groups)}
      </>
    );
  const ready = groups?.needs ?? [];
  const othersCount = groups ? groups.saved.length + groups.refused.length + groups.settled.length : 0;
  const readyHeadingId = `${ids.group}-needs`;
  /* The Other fold's groups sit one step under "Ready to Propose" when it is there, and take its level when not. */
  const GroupHeading = ready.length > 0 ? 'h4' : 'h3';

  return (
    <details className="sp-drafts sp-fold" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <ChevronRight className="sp-chevron" size={16} strokeWidth={2} aria-hidden="true" />
        {LABELS.headingSpDraftsFile}
      </summary>
      <div className="sp-drafts-body">
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
        {/* Always in the page, so the screen reader hears it fill; shown once there is something to say. */}
        <p className={summary ? 'sp-drafts-summary' : 'sr-only'} role="status" aria-live="polite">
          {summary}
        </p>
        {problem && (
          <p className="sp-field-error" role="alert">
            {problem}
          </p>
        )}

        {loaded && ready.length > 0 && (
          <div className="sp-draft-group">
            <h3 className="sp-h3" id={readyHeadingId}>
              {LABELS.headingSpReady} ({ready.length})
            </h3>
            <p className="sp-note">{COPY.readyLead}</p>
            <ul className="sp-list sp-draft-list" aria-labelledby={readyHeadingId}>
              {ready.map(({ draft }) => (
                <ReadyDraftItem
                  key={draft.key}
                  draft={draft}
                  isCurrent={draft === current}
                  focusNonce={returnFocus?.draft === draft ? returnFocus.nonce : null}
                  onUse={() => onUse(draft, loaded.bundleId)}
                />
              ))}
            </ul>
          </div>
        )}

        {/* Everything that asks nothing of the reader now, folded into one place. No buttons in here. */}
        {loaded && groups && othersCount > 0 && (
          <details className="sp-draft-others sp-fold">
            <summary>
              <ChevronRight className="sp-chevron" size={16} strokeWidth={2} aria-hidden="true" />
              {LABELS.headingSpOtherTerms} ({othersCount})
            </summary>
            {OTHER_GROUPS.map((g) => {
              const rows = groups[g.id];
              if (rows.length === 0) return null;
              const headingId = `${ids.group}-${g.id}`;
              return (
                <div className="sp-draft-subgroup" key={g.id}>
                  <GroupHeading className="sp-h4" id={headingId}>
                    {g.title}
                  </GroupHeading>
                  <ul className="sp-list sp-draft-list" aria-labelledby={headingId}>
                    {rows.map(({ draft, whyNot }) => (
                      <OtherDraftItem key={draft.key} draft={draft} whyNot={whyNot} group={g.id} />
                    ))}
                  </ul>
                </div>
              );
            })}
          </details>
        )}
      </div>
    </details>
  );
}

/** The file's own sentences on what was answered since the term was asked for, shown verbatim. */
function SinceAsked({ draft }: { draft: LocalTermDraft }) {
  if (draft.answerNotes.length === 0) return null;
  return (
    <p className="sp-draft-since">
      <span className="sp-draft-since-lead">{LABELS.draftFactSinceAsked}:</span>{' '}
      <InlineCode text={draft.answerNotes.join(' ')} />
    </p>
  );
}

/** What the file reports wrong with a term it drafted (or refused without a reason of its own). */
function FileProblems({ draft }: { draft: LocalTermDraft }) {
  if (draft.problems.length === 0 || !(draft.drafted || !draft.reason)) return null;
  return (
    <p className="sp-hint">
      Problems the file reports: <InlineCode text={draft.problems.map((p) => p.message).join(' ')} />
    </p>
  );
}

/** A draft the reader can propose: what it adds, who asked, where it was read, and the one button. */
function ReadyDraftItem({
  draft,
  isCurrent,
  focusNonce,
  onUse,
}: {
  draft: LocalTermDraft;
  isCurrent: boolean;
  /** Set (and changed) when this row's button should take focus back. */
  focusNonce: number | null;
  onUse: () => void;
}) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (focusNonce !== null) buttonRef.current?.focus();
  }, [focusNonce]);
  const counts = countsSentence(draft);
  const lists = draft.missingFrom.map((m) => (m === 'portal' ? "the portal's list" : m === 'schema' ? "the ISAAC schema's list" : m));
  const citationsTotal = draft.citationsTotal ?? draft.citations.length;
  const citationsShown = draft.citations.slice(0, 3);
  return (
    <li className="sp-draft" aria-current={isCurrent ? 'true' : undefined}>
      <div className="sp-draft-head">
        <h4 className="sp-h4">
          <code className="sp-term">{draft.term}</code>
        </h4>
        <span className="sp-draft-path">
          <span aria-hidden="true">→ </span>
          <span className="sr-only">for </span>
          {draft.fieldPath}
        </span>
      </div>
      <p className="sp-draft-line">
        Adds <code className="sp-term">{draft.term}</code> to <code className="sp-term">{draft.fieldPath}</code>
        {lists.length > 0 ? `, which is not on ${lists.join(' or ')} today.` : '.'}
      </p>
      <p className="sp-draft-line sp-draft-muted">
        {/* A ready draft's counts sentence never carries a full stop of its own (only a carried-over one does,
            and a carried-over draft is never ready), so exactly one is added here. */}
        {counts ? `${counts}.` : 'The file gives no count.'}{' '}
        {draft.scientistNotes.length > 0 ? (
          <>
            Your words:{' '}
            {draft.scientistNotes.map((n, i) => (
              <span key={i}>
                {i > 0 ? '; ' : ''}
                <span className="sp-quote">“{n.termAsSaid}”</span>
                {n.note !== null && (
                  <>
                    {', with the note '}
                    <span className="sp-quote">“{n.note}”</span>
                  </>
                )}
                {` (${noteAttribution(n)})`}
              </span>
            ))}
            .
          </>
        ) : (
          'The file holds none of your words for this term.'
        )}
      </p>
      <SinceAsked draft={draft} />
      <FileProblems draft={draft} />
      {draft.citations.length > 0 ? (
        <details className="sp-draft-cites">
          <summary>
            <ChevronRight className="sp-chevron" size={14} strokeWidth={2} aria-hidden="true" />
            {LABELS.headingSpWhereRead} ({citationsTotal})
          </summary>
          <p className="sp-item-text">
            {/* "and N more" counts what is not shown: the file's total less the lines above it */}
            {citationsShown.map(citationLine).join('\n') +
              (citationsTotal > citationsShown.length ? `\nand ${citationsTotal - citationsShown.length} more` : '')}
          </p>
        </details>
      ) : (
        <p className="sp-hint">The file cites nothing for this term.</p>
      )}
      <div className="sp-actions">
        {isCurrent ? (
          <span className="chip sp-chip-current">{LABELS.chipDraftBeingProposed}</span>
        ) : (
          <button type="button" className="btn btn-action" onClick={onUse} ref={buttonRef}>
            Propose This Term
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * A draft that asks nothing of the reader now: saved from this file, refused, or settled. One compact
 * block — the term, then why — and no button: a saved one cannot be filed twice, and the others cannot be
 * filed from here at all.
 */
function OtherDraftItem({
  draft,
  whyNot,
  group,
}: {
  draft: LocalTermDraft;
  whyNot: string | null;
  group: Exclude<DraftGroup, 'needs'>;
}) {
  return (
    <li className={`sp-draft sp-draft-compact sp-draft-${group}`}>
      <p className="sp-draft-line">
        <code className="sp-term sp-draft-term">{draft.term}</code>
      </p>
      {/* A refusal leads with its reason. A settled term (answered since, or no longer in the bundle) is not
          refused for a fault, so it says calmly that there is nothing to propose. */}
      {group === 'saved' ? (
        <p className="sp-draft-line sp-draft-muted">Saved as a draft on this server.</p>
      ) : (
        whyNot !== null && (
          <p className="sp-draft-line sp-draft-muted">
            <strong>{group === 'settled' ? 'Nothing to propose.' : 'Cannot be proposed from here.'}</strong>{' '}
            <InlineCode text={whyNot} />
          </p>
        )
      )}
      <SinceAsked draft={draft} />
      {group === 'refused' && <FileProblems draft={draft} />}
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

/** The server's persistence statement up to its first full stop: the fact, without the explanation after it. */
function firstSentence(message: string): string {
  const end = message.indexOf('. ');
  return end === -1 ? message : message.slice(0, end + 1);
}

/** The capacity sentence earns its place only near the limit, when it changes what a person does. */
function nearCapacity(capacity: { pending: number; max_pending: number }): boolean {
  return capacity.max_pending > 0 && capacity.pending >= 0.8 * capacity.max_pending;
}

function ProposalsPanel({
  version,
  headingId,
  sectionRef,
  onSettled,
}: {
  version: number;
  headingId: string;
  /** The section itself, so an old `?tab=proposals` link can scroll to it. */
  sectionRef: RefObject<HTMLElement>;
  /** The first page has arrived (or failed): the column's height is known. */
  onSettled: () => void;
}) {
  const first = useFetch(() => api.listSchemaProposals({ limit: PAGE_SIZE, offset: 0 }), [version]);
  const [more, setMore] = useState<ApiSchemaProposal[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  /** A proposal changed in place by a withdraw, keyed by id, so the list needs no refetch. */
  const [changed, setChanged] = useState<Record<string, ApiSchemaProposal>>({});

  const firstData = first.status === 'data' ? first.data : null;
  const settledOnce = useRef(false);
  useEffect(() => {
    if (settledOnce.current || first.status === 'loading') return;
    settledOnce.current = true;
    onSettled();
  }, [first.status, onSettled]);
  const firstRef = useRef(firstData);
  firstRef.current = firstData;
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
    const startedOn = firstRef.current;
    try {
      const page = await api.listSchemaProposals({ limit: PAGE_SIZE, offset: nextOffset });
      // A first page read again meanwhile (a save here) already replaced the list: this page belongs to the old one.
      if (firstRef.current !== startedOn) return;
      // Newest first by offset: a proposal saved elsewhere since shifts a row onto the next page; it is listed once.
      setMore((prev) => {
        const listed = new Set([...(startedOn?.proposals ?? []), ...prev].map((x) => x.id));
        return [...prev, ...page.proposals.filter((x) => !listed.has(x.id))];
      });
      setNextOffset(page.next_offset);
    } catch {
      setMoreFailed(true);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="sp-proposals" aria-labelledby={headingId} ref={sectionRef}>
      <div className="sp-proposals-head">
        <h2 className="sp-h2" id={headingId}>
          {COPY.proposalsTitle}
        </h2>
        {/* Always mounted, so a screen reader hears it fill; empty until there is a count to give. */}
        <span className="sp-count" role="status">
          {firstData && firstData.total > 0 && (
            <>
              {firstData.total}
              <span className="sr-only"> {firstData.total === 1 ? 'proposal' : 'proposals'}, newest first</span>
            </>
          )}
        </span>
      </div>
      {first.status === 'loading' && <LoadingPanel label="Loading proposals…" />}
      {first.status === 'error' && <BackendDown error={first.error} onRetry={first.reload} />}
      {firstData && (
        <>
          <div className="sp-proposals-facts">
            <p>{firstSentence(firstData.persistence.message)}</p>
            {nearCapacity(firstData.capacity) && (
              <p>
                {firstData.capacity.pending} of {firstData.capacity.max_pending} pending places used.{' '}
                {firstData.capacity.scope}
              </p>
            )}
          </div>

          {firstData.total === 0 ? (
            <p className="sp-note">No proposals on this server yet.</p>
          ) : (
            <>
              <ul className="sp-list sp-proposal-list">
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
                  <button type="button" className="btn btn-action" onClick={showMore} disabled={loadingMore}>
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
  const summaryRef = useRef<HTMLElement>(null);

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
      // the Withdraw control is gone: focus the proposal itself (its summary), whose status now reads Withdrawn
      requestAnimationFrame(() => summaryRef.current?.focus());
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
      <details className="sp-proposal">
        <summary ref={summaryRef}>
          <ChevronRight className="sp-chevron" size={16} strokeWidth={2} aria-hidden="true" />
          <span className="sp-proposal-sum">
            <span className="sp-item-headline">{proposalHeadline(proposal)}</span>
            <span className="sp-proposal-meta">
              <span className={`sp-status sp-status-${proposal.status}`}>{STATUS_LABEL[proposal.status]}</span>
              <span className="sp-item-meta">
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
              </span>
            </span>
          </span>
        </summary>
        <div className="sp-proposal-body">
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
          {proposal.attribution === 'verified' && proposal.proposed_by && (
            <p className="sp-item-meta">Proposed by {proposal.proposed_by}</p>
          )}

          <div className="sp-actions">
            {proposal.proposal_type === 'schema_change' ? (
              <ChangeRequestActions proposalId={proposal.id} />
            ) : (
              <PortalActions proposalId={proposal.id} />
            )}
            {proposal.status === 'pending' && !confirming && (
              <button
                type="button"
                className="btn btn-danger-quiet"
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
                <button type="button" className="btn sp-text-btn" onClick={keep} disabled={busy}>
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
        </div>
      </details>
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
      <button type="button" className="btn btn-action" onClick={copy} disabled={busy}>
        <Copy size={14} strokeWidth={2} aria-hidden="true" /> Copy Change Request
      </button>
      <button type="button" className="btn btn-action" onClick={() => download('md')} disabled={busy}>
        <Download size={14} strokeWidth={2} aria-hidden="true" /> Download Markdown
      </button>
      <button type="button" className="btn btn-action" onClick={() => download('json')} disabled={busy}>
        <Download size={14} strokeWidth={2} aria-hidden="true" /> Download JSON
      </button>
      <span className="sp-portal-status" role="status">
        {state.kind === 'copied' &&
          'Copied the change request as Markdown. It is for the standard\'s owners, not the portal.'}
        {state.kind === 'downloaded' &&
          `Downloaded the change request as ${state.what}.`}
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
      <button type="button" className="btn btn-action" onClick={copy} disabled={busy}>
        <Copy size={14} strokeWidth={2} aria-hidden="true" /> Copy Portal Payload
      </button>
      <button type="button" className="btn btn-action" onClick={download} disabled={busy}>
        <Download size={14} strokeWidth={2} aria-hidden="true" /> Download JSON
      </button>
      <span className="sp-portal-status" role="status">
        {state.kind === 'copied' && `Copied. ${destination}`}
        {state.kind === 'downloaded' && `Downloaded. ${destination}`}
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
