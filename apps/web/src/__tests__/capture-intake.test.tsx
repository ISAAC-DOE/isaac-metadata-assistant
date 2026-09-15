/**
 * THE CAPTURE INTAKE CHOOSER — the three routes in, and what each may claim.
 *
 * The owner asked for capture to come first, with a choice between bringing
 * files and recording by voice. Measured over HTTP, BOTH of those are externally
 * blocked in this build and the unnamed third is not:
 *
 *     POST .../transcript       -> 200   typed/pasted text -> note -> proposals
 *     POST /api/transcription   -> 501   no_provider_configured
 *     POST /api/uploads         -> 403   unconditional
 *
 * So the honesty tests here are not decoration: a chooser is exactly the surface
 * where a false affordance costs a scientist the most, because they pick a route
 * and commit to it before discovering it does not work.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useState } from 'react';
import { CaptureIntake } from '../components/CaptureIntake';

/** Any well-formed record id: the fourth intake card builds a link from it. */
const FIXTURE_EXPERIMENT_ID = '01SYNTHTESTEXP000000000000';
import { TranscriptCapturePanel } from '../components/TranscriptCapturePanel';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { ROUTES } from '../lib/routes';

function renderIntake(
  overrides: Partial<Parameters<typeof CaptureIntake>[0]> = {},
) {
  const onOpenCapture = vi.fn();
  const onOpenRecorder = vi.fn();
  const view = render(
    <MemoryRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      {/* `experimentId` before the spread, so an override can still replace it —
          the fourth intake route (2026-09-14) links to this record's own
          `?view=runs`, so the component now requires the id. */}
      <CaptureIntake
        onOpenCapture={onOpenCapture}
        onOpenRecorder={onOpenRecorder}
        experimentId={FIXTURE_EXPERIMENT_ID}
        {...overrides}
      />
    </MemoryRouter>,
  );
  return { ...view, onOpenCapture, onOpenRecorder };
}

const card = (route: string) =>
  document.querySelector<HTMLElement>(
    `.capture-intake-card[data-route="${route}"]`,
  )!;

describe("the intake chooser offers three routes", () => {
  it("names all three, each with its own action", () => {
    renderIntake();
    for (const [route, title] of [
      ["write", CAPTURE_COPY.intakeWriteTitle],
      ["voice", CAPTURE_COPY.intakeVoiceTitle],
      ["files", CAPTURE_COPY.intakeFilesTitle],
    ] as const) {
      const el = card(route);
      expect(el, `no card for ${route}`).toBeTruthy();
      expect(within(el).getByRole("heading", { level: 3 }).textContent).toBe(
        title,
      );
    }
  });

  it("writing and recording open the capture panel; files LEAVES for Historical Import", () => {
    const { onOpenCapture, onOpenRecorder } = renderIntake();

    fireEvent.click(within(card("write")).getByRole("button"));
    expect(onOpenCapture).toHaveBeenCalledTimes(1);

    fireEvent.click(within(card("voice")).getByRole("button"));
    expect(onOpenRecorder).toHaveBeenCalledTimes(1);

    // A real link, because it leaves this record for a separately-routed
    // destination — middle-clickable and bookmarkable, not a left-click button.
    const link = within(card("files")).getByRole("link");
    expect(link.getAttribute("href")).toBe(ROUTES.imports);
  });

  it("MUTATION-GUARDED — the route that WORKS today is the one styled primary", () => {
    /*
     * The ordering claim. `write` is the only route that reaches a proposal in
     * this build, so it must be the primary action; making the voice or files
     * card primary would steer a scientist into a door that does not open.
     */
    renderIntake();
    expect(within(card("write")).getByRole("button").className).toContain(
      "btn-primary",
    );
    expect(within(card("voice")).getByRole("button").className).not.toContain(
      "btn-primary",
    );
    expect(within(card("files")).getByRole("link").className).not.toContain(
      "btn-primary",
    );

    // ...and it is FIRST in the document, not merely styled.
    const cards = Array.from(document.querySelectorAll(".capture-intake-card"));
    expect(cards[0]!.getAttribute("data-route")).toBe("write");
  });
});

describe("what the chooser must NOT claim", () => {
  it("MUTATION-GUARDED — never says transcription, speech-to-text or a model is available", () => {
    /*
     * THE CLAIM THAT WOULD COST THE MOST. `POST /api/transcription` answers
     * `501 no_provider_configured` in every deployment, Dean deferred D1–D9, and
     * `ai-integration-decision-packet.md` §6 bans a fake `Connected` state.
     *
     * Banned as CLAIM SHAPES rather than as words: the voice card has to be able
     * to SAY "speech-to-text" in order to explain that it is off, so a bare
     * substring ban would forbid the honest sentence — the polarity trap this
     * repository has been caught by twice today.
     */
    renderIntake();
    const text = document.querySelector(".capture-intake")!.textContent ?? "";
    for (const claim of [
      /transcri\w* (?:is|are) (?:on|enabled|available|ready|configured)/i,
      /we (?:will )?transcribe/i,
      /automatically transcrib/i,
      /speech-to-text (?:is|will be) (?:on|enabled|available|ready)/i,
      /(?:model|provider) (?:is )?connected/i,
      /turns? your (?:voice|speech|audio) into text/i,
    ]) {
      expect(text, `the chooser claims: ${claim}`).not.toMatch(claim);
    }

    // ...and the HONEST statement is present, so the ban cannot be satisfied by
    // deleting the explanation.
    expect(text).toContain(CAPTURE_COPY.intakeVoiceLimit);
    expect(text.toLowerCase()).toContain("not turned on in this deployment");
  });

  it("POSITIVE CONTROL — those patterns catch the claims they forbid", () => {
    // Six `not.toMatch` assertions passing is indistinguishable from six regexes
    // that match nothing.
    const MUST_CATCH: ReadonlyArray<readonly [RegExp, string]> = [
      [
        /transcri\w* (?:is|are) (?:on|enabled|available|ready|configured)/i,
        "Transcription is available",
      ],
      [/we (?:will )?transcribe/i, "we transcribe it for you"],
      [/automatically transcrib/i, "automatically transcribed"],
      [
        /speech-to-text (?:is|will be) (?:on|enabled|available|ready)/i,
        "Speech-to-text is ready",
      ],
      [/(?:model|provider) (?:is )?connected/i, "provider connected"],
      [
        /turns? your (?:voice|speech|audio) into text/i,
        "turns your voice into text",
      ],
    ];
    for (const [pattern, phrasing] of MUST_CATCH) {
      expect(
        pattern.test(phrasing),
        `${pattern} missed ${JSON.stringify(phrasing)}`,
      ).toBe(true);
    }
    // And the shipped limit sentence is NOT caught — the honest wording survives.
    for (const [pattern] of MUST_CATCH) {
      expect(pattern.test(CAPTURE_COPY.intakeVoiceLimit), `${pattern}`).toBe(
        false,
      );
    }
  });

  it("MUTATION-GUARDED — the files route never says files are uploaded or read", () => {
    // `POST /api/uploads` is an unconditional 403 and Historical Import keeps a
    // pointer, a checksum and notes WITHOUT reading bytes.
    renderIntake();
    const text = (
      within(card("files")).getByRole("heading", { level: 3 }).parentElement
        ?.textContent ?? ""
    ).toLowerCase();
    for (const banned of [
      "upload",
      "we read your files",
      "we open",
      "attach",
    ]) {
      expect(text, `the files card claims: ${banned}`).not.toContain(banned);
    }
    expect(text).toContain("reference");
  });

  it('is not a workflow step: no tick, no lock, no aria-current="step"', () => {
    // Being FIRST and being a STEP are different claims, and only the first was
    // asked for. `workflow.py` keeps a state off the spine when no signal can
    // decide it, and "finished capturing" is not decidable.
    const { container } = renderIntake();
    expect(container.querySelector('[aria-current="step"]')).toBeNull();
    expect(container.querySelector('[aria-disabled="true"]')).toBeNull();
    for (const button of Array.from(container.querySelectorAll("button"))) {
      expect(button.disabled, "a disabled control with no stated reason").toBe(
        false,
      );
    }
  });
});

/* ── the chooser DRIVING the panel, which is the part a unit of either misses ── */

/** The real pair, wired as `RecordWorkbench` wires them. */
function Wired() {
  const [open, setOpen] = useState(false);
  return (
    <MemoryRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <CaptureIntake
        onOpenCapture={() => setOpen(true)}
        onOpenRecorder={() => setOpen(true)}
        experimentId={FIXTURE_EXPERIMENT_ID}
      />
      <TranscriptCapturePanel
        experimentId="01TESTTESTTESTTESTTESTTEST"
        open={open}
        onOpenChange={setOpen}
      />
    </MemoryRouter>
  );
}

describe("the chooser and the capture panel, wired together", () => {
  it("MUTATION-GUARDED — exactly ONE primary control, because two was the defect", async () => {
    /*
     * SEEN IN A BROWSER BEFORE IT WAS FIXED. The first build of this rendered
     * "Start Writing" and the panel's own "Capture Experiment Notes" ten pixels
     * apart, both blue, both doing the same thing. `ExperimentsHome` had already
     * argued against exactly this: "Two controls for one action is not a styling
     * nit — it makes a reader stop and work out which one is the real one."
     */
    render(<Wired />);
    expect(document.querySelectorAll(".btn-primary")).toHaveLength(1);
    expect(
      Array.from(document.querySelectorAll("button")).map((b) => b.textContent),
      "the panel rendered its own entry while the chooser owns it",
    ).not.toContain("Capture Experiment Notes");
  });

  it("opens on Start Writing, closes, and REOPENS — verified in a browser first", async () => {
    // The reopen is why the panel takes a controlled `open` rather than a
    // `defaultOpen`: a reader who closes it and presses Start Writing again
    // expects it back, and `defaultOpen` only acts on mount.
    render(<Wired />);
    const start = () =>
      Array.from(document.querySelectorAll("button")).find(
        (b) => b.textContent === "Start Writing",
      )!;
    const close = () =>
      Array.from(document.querySelectorAll("button")).find(
        (b) => b.textContent === "Close Capture",
      );

    fireEvent.click(start());
    expect(close(), "the panel did not open").toBeTruthy();

    fireEvent.click(close()!);
    expect(close(), "the panel did not close").toBeFalsy();

    fireEvent.click(start());
    expect(
      close(),
      "the panel did not REOPEN — this is the defaultOpen failure mode",
    ).toBeTruthy();
  });
});
