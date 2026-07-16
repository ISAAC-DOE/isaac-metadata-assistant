import './screens.css';
import '../components/evidence.css';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { WorkflowSpine, buildSpine } from '../components/WorkflowSpine';
import { StatusBar } from '../components/StatusBar';
import { FieldGroup } from '../components/FieldGroup';
import { AssistantPanel } from '../components/AssistantPanel';
import { SourceTypeToken } from '../components/EvidenceRow';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleAlert, ExternalLink, FileText } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import {
  draftGroupsToFieldGroups,
  toAdvisoryResult,
  toAuditResult,
  toValidationResult,
} from '../lib/adapt';
import { ASSISTANT_SAMPLES } from '../lib/assistant';
import type { ApiEvidenceEntry, DraftField, RecordBundle } from '../lib/types';

/**
 * S3 · Review Record — the core workbench, live from the record bundle
 * (detail / draft / pending / validate / audit / warnings / evidence / graph —
 * eight endpoints, fetched together, rendered apart). Grouped, calm draft;
 * evidence one tap away in the right panel (above the subordinate assistant,
 * hard-divided); the blocking gate on the left; the trust readout along the
 * bottom with each signal in its own labeled segment, never merged.
 */
export function RecordWorkbench() {
  const { id = '' } = useParams();
  const bundle = useFetch(() => api.getRecordBundle(id), [id]);

  if (bundle.status !== 'data') {
    return (
      <AppShell
        variant="record"
        topBar={<TopBar variant="record" title={LABELS.screenReview} />}
        sidebar={<WorkflowSpine steps={buildSpine('draft')} recordId={id} />}
        mainPad="pad"
      >
        {bundle.status === 'loading' ? (
          <LoadingPanel label="Loading the record from the local backend…" />
        ) : (
          <BackendDown error={bundle.error} onRetry={bundle.reload} />
        )}
      </AppShell>
    );
  }

  return <LoadedWorkbench id={id} bundle={bundle.data} />;
}

function LoadedWorkbench({ id, bundle }: { id: string; bundle: RecordBundle }) {
  const navigate = useNavigate();
  const { detail, pending, validate, audit, warnings, evidence, graph } = bundle;

  const evidenceByPath = useMemo(
    () => new Map<string, ApiEvidenceEntry>(evidence.map((e) => [e.path, e])),
    [evidence],
  );
  const groups = useMemo(
    () => draftGroupsToFieldGroups(bundle.groups, evidenceByPath),
    [bundle.groups, evidenceByPath],
  );
  const fieldCount = groups.reduce((n, g) => n + g.fields.length, 0);

  // User toggles override the group's default expandedness.
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const isExpanded = (block: string, collapsedByDefault: boolean) =>
    toggles[block] ?? !collapsedByDefault;

  const firstPath = groups[0]?.fields[0]?.path;
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const effectivePath = selectedPath ?? firstPath;

  const selectedField = useMemo<DraftField | undefined>(() => {
    for (const group of groups) {
      const found = group.fields.find((f) => f.path === effectivePath);
      if (found) return found;
    }
    return undefined;
  }, [groups, effectivePath]);

  // --- the three signals, each from its own endpoint, each its own segment ---
  // Pre-export, validation is a DRY-RUN and audit has nothing to count — those
  // segments carry the live server result as a note; the reserved PASS/FAIL chip
  // appears only for real (post-export) validation.
  const validationLive = validate.dry_run ? 'pending' : toValidationResult(validate);
  const validationNote = validate.dry_run
    ? `dry-run · ${validate.errors.length} error${validate.errors.length === 1 ? '' : 's'}`
    : undefined;
  const coverageLive = audit.records.length > 0 ? toAuditResult(audit) : 'pending';
  const coverageNote = audit.records.length === 0 ? 'not exported yet' : undefined;
  const advisoryLive = toAdvisoryResult(warnings);

  const phase = detail.exported
    ? `Exported · ${detail.record_id}`
    : pending.length > 0
      ? `Draft assembled · ${pending.length} fields to confirm`
      : 'Draft complete · ready to export';

  const rightPanel = (
    <aside className="record-right" aria-label="Evidence and assistant">
      <div className="evidence-slot">
        <section className="card ev-panel-card" aria-label="Evidence for selected field">
          <div className="ev-panel-head">
            <span className="ev-panel-title">
              <FileText size={15} strokeWidth={2} aria-hidden="true" />
              {LABELS.evidence}
            </span>
            <span className="ev-panel-badge">deterministic</span>
          </div>
          {selectedField ? (
            <>
              <div className="ev-panel-for">
                for <span className="mono">{selectedField.path}</span>
              </div>
              {(selectedField.evidence ?? []).map((ev, i) => (
                <dl className="ev-field" key={i} style={{ marginBottom: 8 }}>
                  <dt style={{ gridColumn: '1 / -1', marginBottom: 2 }}>
                    <SourceTypeToken sourceType={ev.source_type} />
                  </dt>
                  {ev.source_file && (
                    <>
                      <dt>source_file</dt>
                      <dd>{ev.source_file}</dd>
                    </>
                  )}
                  {ev.locator && (
                    <>
                      <dt>locator</dt>
                      <dd>{ev.locator}</dd>
                    </>
                  )}
                  {ev.quote && (
                    <>
                      <dt>quote</dt>
                      <dd className="quote">"{ev.quote}"</dd>
                    </>
                  )}
                  {ev.rule && (
                    <>
                      <dt>rule</dt>
                      <dd style={{ whiteSpace: 'normal' }}>{ev.rule}</dd>
                    </>
                  )}
                </dl>
              ))}
            </>
          ) : (
            <p className="ev-panel-for">Select a field to load its evidence.</p>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
            onClick={() => navigate(ROUTES.evidence(id))}
          >
            <ExternalLink size={14} strokeWidth={2} aria-hidden="true" />
            {LABELS.evidenceTrail} · {evidence.length} entries
          </button>
        </section>
      </div>

      <div className="right-divider" aria-hidden="true" />

      <AssistantPanel
        reply={ASSISTANT_SAMPLES.review.reply}
        prompts={ASSISTANT_SAMPLES.review.prompts}
        freshness={graph.status}
      />
    </aside>
  );

  const spine = buildSpine(detail.exported ? 'validate' : 'draft', {
    draft: { meta: `reviewing ${fieldCount} fields` },
    complete: {
      meta:
        pending.length > 0 ? `${pending.length} fields need you` : 'all fields confirmed',
    },
  });

  return (
    <AppShell
      variant="record"
      topBar={
        <TopBar
          variant="record"
          title={detail.title}
          filename={
            detail.exported && detail.record_id ? `${detail.record_id}.json` : `draft · ${detail.id}`
          }
          stateChip={detail.exported ? 'exported' : 'draft'}
        />
      }
      sidebar={<WorkflowSpine steps={spine} recordId={id} />}
      rightPanel={rightPanel}
      statusBar={
        <StatusBar
          phase={phase}
          phaseDot={pending.length > 0 ? 'attention' : detail.exported ? 'idle' : 'ready'}
          validation={validationLive}
          coverage={coverageLive}
          advisory={advisoryLive}
          validationPendingNote={validationNote}
          coveragePendingNote={coverageNote}
        />
      }
      mainPad="pad"
    >
      {pending.length > 0 && (
        <div className="needsyou-banner" role="note">
          <CircleAlert className="needsyou-icon" size={20} strokeWidth={2.2} aria-hidden="true" />
          <div className="needsyou-body">
            <div className="needsyou-title">
              {pending.length} Fields Need Your Confirmation
            </div>
            <p className="needsyou-text">
              These are values the system refuses to guess. Confirm each before this record can
              export — expected, not a failure.
            </p>
            <ul className="needsyou-list">
              {pending.map((p) => (
                <li key={p.id}>
                  <span className="needsyou-q">{p.question}</span>
                  {p.about && <span className="needsyou-about mono">{p.about}</span>}
                </li>
              ))}
            </ul>
          </div>
          <button
            type="button"
            className="btn btn-primary needsyou-action"
            onClick={() => navigate(ROUTES.complete(id))}
          >
            {LABELS.actionReviewAnswer} →
          </button>
        </div>
      )}

      {groups.map((group) => (
        <FieldGroup
          key={group.block}
          group={group}
          expanded={isExpanded(group.block, group.collapsedByDefault)}
          onToggle={() =>
            setToggles((prev) => ({
              ...prev,
              [group.block]: !isExpanded(group.block, group.collapsedByDefault),
            }))
          }
          selectedPath={effectivePath}
          onSelectField={(field) => setSelectedPath(field.path)}
        />
      ))}
    </AppShell>
  );
}
