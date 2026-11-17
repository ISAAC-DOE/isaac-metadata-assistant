/**
 * HISTORICAL IMPORT, WITH THE SKILL — the copy for `/imports` (2026-11-16).
 *
 * Historical import is done on the scientist's own computer, by the Claude Code skill
 * `.claude/skills/isaac-historical-import/`. The site does not import anything itself; this
 * page says how to use the skill. Built from `docs/local-skill-quickstart.md` and the skill's
 * own `SKILL.md` and `reference/troubleshooting.md`: when those change, this changes with them.
 *
 * Every command is a real script in the repository root (`scripts/…`), and
 * `__tests__/historical-import-guide.test.tsx` holds that true.
 */

export const GUIDE_COMMANDS = {
  install: 'scripts/setup_isaac_local.sh --install-skill',
  selftest: 'scripts/isaac_selftest.sh',
  check: 'scripts/setup_isaac_local.sh --check',
  claude: 'claude',
  skill: '/isaac-historical-import',
} as const;

export const GUIDE_COPY = {
  lead: 'Turn a past beamtime folder into ISAAC records, on your own computer, with the ISAAC skill in Claude Code.',

  whatTitle: 'What it does',
  what:
    "ISAAC's program reads your beamtime folder on your computer. Claude reads what the program can't, " +
    'such as logbooks, slides, spreadsheets and figures. You decide every value that is uncertain.',

  getTitle: 'What you get',
  get: 'ISAAC records for every group that passes its checks, and a list of what is still missing and why.',

  installTitle: 'Install',
  installFolder: 'Get a copy of the ISAAC folder from your group, open Terminal in that folder, and run:',
  installNote:
    'It sets up the ISAAC folder, and installs the skill for Claude Code and an offline portal checker. It needs internet, and no administrator password.',
  selftestLead: 'Then check it works, on made-up data:',
  selftestNote: 'You want to see “0 failed” at the end.',
  checkLead: 'To see what is installed, any time:',
  updates:
    'When the skill or your ISAAC folder is out of date, the skill tells you and updates it (it asks first before updating the ISAAC folder).',

  runTitle: 'Run it',
  runStart: 'In Terminal, go to the folder that holds your beamtime folder and start Claude Code:',
  runSkill: 'Type the skill’s name:',
  runFolder: 'Tell it which folder to import. It tells you where you are as it goes.',

  stepsTitle: 'The steps',
  steps: [
    { name: 'Permission', text: 'It asks whether Claude may read this data.' },
    { name: 'Import', text: 'ISAAC reads the folder and says what it found.' },
    { name: 'Spot check', text: 'Claude reads a few key facts from the raw files and compares them with what the program found.' },
    { name: 'Files the program couldn’t read', text: 'Claude reads the Word, PowerPoint and Excel files, PDFs and images.' },
    { name: 'Groups', text: 'You confirm which scans belong in one record.' },
    { name: 'Spectra and QC', text: 'You approve each processed curve and say its QC status.' },
    { name: 'Questions', text: 'Only what a record needs, asked once where the answer is shared.' },
    { name: 'Checks and export', text: 'Each record is checked against the schema and the portal’s rules, and the ones that pass are written out.' },
  ],

  dataTitle: 'What stays on your computer, and what doesn’t',
  dataCaption: 'Where your data goes',
  dataRows: [
    { what: 'Your files', where: 'Read by ISAAC’s program on your computer.' },
    { what: 'Anything Claude opens', where: 'Sent to the Claude service. That includes what Claude sees in a command’s output.' },
    { what: 'Your records', where: 'Nothing is uploaded unless you upload it.' },
  ],

  askedTitle: 'What you’ll be asked',
  asked: [
    'Permission to let Claude read the data.',
    'Your name, which is recorded with each decision.',
    'Which scans belong together.',
    'Whether a curve looks right, and its QC status.',
    'The facts no file states, such as who produced the data or the sample form.',
  ],

  knowTitle: 'Good to know',
  know: [
    'The spectrum-processing method is a draft until the ISAAC processing reviewers approve it. Approving a curve means you looked at it and accept it for that record.',
    'Claude’s spot check is a check, not proof. The summary says how many facts it read on its own.',
  ],

  browserTitle: 'Optional: answer the questions in your browser',
  browser:
    'You can answer the same questions in a browser on your own computer, on the Local Imports page. ' +
    'It runs the same checks. To set it up, see “Local Imports” in docs/ui-local-dev.md in the ISAAC folder.',
  browserLink: 'Open Local Imports',

  troubleTitle: 'If something goes wrong',
  /** `text` is shown as words, then `cmd` as a command to copy. One or both. */
  trouble: [
    { what: 'ISAAC isn’t set up on this computer', cmd: 'scripts/setup_isaac_local.sh' },
    { what: 'The output folder isn’t empty, or is inside your data', text: 'Choose a new, empty folder outside your data.' },
    { what: 'The portal check is missing', cmd: 'scripts/install_portal_validator.sh' },
    { what: 'Curves and quality checks need an extra install', cmd: 'scripts/setup_isaac_local.sh --with-processing' },
    {
      what: 'The skill says its instructions are out of date',
      text: 'Nothing to do: the skill updates itself and carries on. To update it by hand, run:',
      cmd: 'scripts/setup_isaac_local.sh --install-skill',
    },
  ] as readonly { what: string; cmd?: string; text?: string }[],
  troubleElse: 'For anything else, send the exact message to the ISAAC team.',
} as const;
