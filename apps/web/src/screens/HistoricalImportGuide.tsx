import './screens.css';
import './historical-import-guide.css';
import { useCallback, useState, type ReactNode } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { CopyAnnouncer, CopyButton } from './settings/apiShared';
import { LABELS } from '../lib/labels';
import { IMPORT_SESSION_PARAM, IMPORT_STAGE_PARAM, ROUTES } from '../lib/routes';
import { useLocalImportsAvailable } from '../lib/localImports';
import { GUIDE_COMMANDS, GUIDE_COPY as COPY } from '../lib/historicalImportGuide';

/**
 * HISTORICAL IMPORT — HOW TO DO IT WITH THE SKILL (2026-11-16, owner direction).
 *
 * Historical import is done by the Claude Code skill on the scientist's own computer, and the
 * skill handles the whole journey. This page replaces the old in-browser import flow, which
 * read only ISAAC's built-in example files, and says how to install and run the skill instead.
 *
 * OLD LINKS STILL LAND HERE. The in-browser flow kept the open import and its stage in
 * `?import=<id>&stage=<stage>`. Those parameters now mean nothing, so a link that carries them
 * is replaced by the bare `/imports` (the hash, if any, is kept). It is never a 404.
 */
export function HistoricalImportGuide() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  if (params.has(IMPORT_SESSION_PARAM) || params.has(IMPORT_STAGE_PARAM)) {
    params.delete(IMPORT_SESSION_PARAM);
    params.delete(IMPORT_STAGE_PARAM);
    const rest = params.toString();
    return <Navigate replace to={{ pathname: ROUTES.imports, search: rest ? `?${rest}` : '', hash: location.hash }} />;
  }
  return <GuidePage />;
}

function GuidePage() {
  const [copyMessage, setCopyMessage] = useState('');
  const onCopied = useCallback((what: string) => setCopyMessage(`Copied ${what}.`), []);
  const localImports = useLocalImportsAvailable();

  const cmd = (value: string, what: string) => <Command value={value} what={what} onCopied={onCopied} />;

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="imports" />}
      mainPad="pad"
      width="wide"
    >
      <div className="hig">
        <CopyAnnouncer message={copyMessage} />
        <header className="hig-head">
          <h1 className="page-title">{LABELS.navImports}</h1>
          <p className="hig-lead">{COPY.lead}</p>
        </header>

        <Section id="hig-what" title={COPY.whatTitle}>
          <p>{COPY.what}</p>
        </Section>

        <Section id="hig-get" title={COPY.getTitle}>
          <p>{COPY.get}</p>
        </Section>

        <Section id="hig-install" title={COPY.installTitle}>
          <ol className="hig-sequence">
            <li>
              <p>{COPY.installFolder}</p>
              {cmd(GUIDE_COMMANDS.install, 'the install command')}
              <p className="hig-note">{COPY.installNote}</p>
            </li>
            <li>
              <p>{COPY.selftestLead}</p>
              {cmd(GUIDE_COMMANDS.selftest, 'the self-test command')}
              <p className="hig-note">{COPY.selftestNote}</p>
            </li>
          </ol>
          <p>{COPY.checkLead}</p>
          {cmd(GUIDE_COMMANDS.check, 'the check command')}
          <p>{COPY.updates}</p>
        </Section>

        <Section id="hig-run" title={COPY.runTitle}>
          <ol className="hig-sequence">
            <li>
              <p>{COPY.runStart}</p>
              {cmd(GUIDE_COMMANDS.claude, 'the command that starts Claude Code')}
            </li>
            <li>
              <p>{COPY.runSkill}</p>
              {cmd(GUIDE_COMMANDS.skill, 'the skill name')}
            </li>
            <li>
              <p>{COPY.runFolder}</p>
            </li>
          </ol>
        </Section>

        <Section id="hig-steps" title={COPY.stepsTitle}>
          <ol className="hig-steps">
            {COPY.steps.map((step) => (
              <li key={step.name}>
                <span className="hig-step-name">{step.name}.</span> {step.text}
              </li>
            ))}
          </ol>
        </Section>

        <Section id="hig-data" title={COPY.dataTitle}>
          <table className="hig-table">
            <caption className="sr-only">{COPY.dataCaption}</caption>
            <thead>
              <tr>
                <th scope="col">What</th>
                <th scope="col">Where it goes</th>
              </tr>
            </thead>
            <tbody>
              {COPY.dataRows.map((row) => (
                <tr key={row.what}>
                  <th scope="row">{row.what}</th>
                  <td>{row.where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section id="hig-asked" title={COPY.askedTitle}>
          <ul className="hig-list">
            {COPY.asked.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Section>

        <Section id="hig-know" title={COPY.knowTitle}>
          <ul className="hig-list">
            {COPY.know.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Section>

        <Section id="hig-browser" title={COPY.browserTitle}>
          <p>{COPY.browser}</p>
          {/* Only where this computer is actually serving the page: a link that would
              land on "not in this build" helps nobody. */}
          {localImports && (
            <p>
              <Link to={ROUTES.localImports}>{COPY.browserLink}</Link>
            </p>
          )}
        </Section>

        <Section id="hig-trouble" title={COPY.troubleTitle}>
          <dl className="hig-trouble" aria-label={COPY.troubleCaption}>
            {COPY.trouble.map((row) => (
              <div className="hig-trouble-row" key={row.what}>
                <dt>{row.what}</dt>
                <dd>
                  {row.cmd && cmd(row.cmd, `the command ${row.cmd}`)}
                  {row.text && <p>{row.text}</p>}
                </dd>
              </div>
            ))}
          </dl>
          <p>{COPY.troubleElse}</p>
        </Section>
      </div>
    </AppShell>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="hig-section" aria-labelledby={id}>
      <h2 className="hig-title" id={id}>
        {title}
      </h2>
      {children}
    </section>
  );
}

/** One command, as text a reader can select, with a copy button beside it. */
function Command({ value, what, onCopied }: { value: string; what: string; onCopied: (what: string) => void }) {
  return (
    <div className="hig-cmd">
      <code className="hig-cmd-text">{value}</code>
      <CopyButton what={what} value={value} onCopied={onCopied} />
    </div>
  );
}
