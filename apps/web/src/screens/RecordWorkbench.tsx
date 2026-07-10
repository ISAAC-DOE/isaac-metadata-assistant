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
import { CircleAlert, ExternalLink, FileText } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';
import { ASSISTANT_SAMPLES } from '../lib/assistant';
import { DEMO_DRAFT_FILE, DEMO_TITLE } from '../lib/mock';
import type { DraftField } from '../lib/types';

/**
 * S3 · Review Record — the core workbench. Grouped, calm draft; evidence one tap
 * away in the right panel (above the subordinate assistant, hard-divided); the
 * blocking gate always visible on the left; the trust readout along the bottom.
 */
export function RecordWorkbench() {
  const navigate = useNavigate();
  const { id = '' } = useParams();
  const detail = api.getExperiment(id);
  const graph = api.getGraphStatus();

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(detail.groups.map((g) => [g.block, !g.collapsedByDefault])),
  );
  const [selectedPath, setSelectedPath] = useState('system.facility.beamline');

  const selectedField = useMemo<DraftField | undefined>(() => {
    for (const group of detail.groups) {
      const found = group.fields.find((f) => f.path === selectedPath);
      if (found) return found;
    }
    return undefined;
  }, [detail.groups, selectedPath]);

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
              <button
                type="button"
                className="btn btn-secondary"
                style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
                onClick={() => navigate(ROUTES.evidence(id))}
              >
                <ExternalLink size={14} strokeWidth={2} aria-hidden="true" />
                {LABELS.actionOpenSource}
              </button>
            </>
          ) : (
            <p className="ev-panel-for">Select a field to load its evidence.</p>
          )}
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

  return (
    <AppShell
      variant="record"
      topBar={
        <TopBar variant="record" title={DEMO_TITLE} filename={`draft · ${DEMO_DRAFT_FILE}`} stateChip="draft" />
      }
      sidebar={<WorkflowSpine steps={buildSpine('draft')} />}
      rightPanel={rightPanel}
      statusBar={
        <StatusBar
          phase="Draft assembled · 5 fields to confirm"
          validation="pending"
          coverage="pending"
          advisory="pending"
          validationPendingNote="runs after export"
        />
      }
      mainPad="pad"
    >
      <div className="needsyou-banner" role="note">
        <CircleAlert className="needsyou-icon" size={20} strokeWidth={2.2} aria-hidden="true" />
        <div className="needsyou-body">
          <div className="needsyou-title">5 Fields Need Your Confirmation</div>
          <p className="needsyou-text">
            These are values the system refuses to guess. Confirm each before this record can export
            — expected, not a failure.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary needsyou-action"
          onClick={() => navigate(ROUTES.complete(id))}
        >
          {LABELS.actionReviewAnswer} →
        </button>
      </div>

      {detail.groups.map((group) => (
        <FieldGroup
          key={group.block}
          group={group}
          expanded={expanded[group.block]}
          onToggle={() =>
            setExpanded((prev) => ({ ...prev, [group.block]: !prev[group.block] }))
          }
          selectedPath={selectedPath}
          onSelectField={(field) => setSelectedPath(field.path)}
        />
      ))}
    </AppShell>
  );
}
