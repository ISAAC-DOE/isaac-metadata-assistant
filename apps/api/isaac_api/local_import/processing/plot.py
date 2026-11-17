"""The scientist-review PNG for one group: individual scans + merged + flags, and the
normalised result (+ the scientist's Athena normalisation when matched). matplotlib Agg.

Each scan is named by its real scan number (``scan_labels``, from the caller), and the scan-selection proposal
(``scan_proposals``) is marked: a scan proposed for leaving out is dotted with triangle markers, one to look at
dash-dotted, a flagged one dashed, each said in the legend. The kinds differ by dash pattern (and marker), not by colour
alone. The proposals are NOT applied: the footnote (``merge_note``) says the merge is raw mu of every scan used. The
PNG is never hashed into a run or result id."""

from __future__ import annotations

from pathlib import Path

#: How many scans get a legend entry each; above it only the marked scans (proposed, flagged) are named.
LEGEND_SCANS = 12
EXCLUDE_PROPOSED = "exclude_proposed"
NEEDS_LOOK = "needs_look"
EXCLUDE_LABEL = "(proposed: leave out)"
LOOK_LABEL = "(proposed: look at)"
FLAGGED_LABEL = "(flagged)"
#: The leave-out line: densely dotted (flagged is "--", a look is "-."), with a marker on every Nth-of-the-line point.
EXCLUDE_DASH = (0, (1, 1.5))
EXCLUDE_MARK_EVERY = 0.1  # matplotlib: a marker every 10% of the line's length, whatever the grid


def scan_style(position: int, *, label: str | None, proposal: str | None, flagged: bool) -> tuple[str, dict]:
    """``(legend label, line style)`` of one scan: plain (solid), flagged (red dashed), proposed for leaving out
    (purple dotted with a downward-triangle marker), proposed for a look (amber dash-dot). The three marked kinds
    differ by dash pattern (and the leave-out kind by marker), never by colour alone, so they stay apart in greyscale
    and for a reader who does not see the colours. A scan both flagged and proposed carries both words."""
    name = label or f"scan position {position + 1}"
    style: dict = dict(lw=0.8, alpha=0.6)
    words = []
    if proposal == EXCLUDE_PROPOSED:
        style.update(color="#7d3c98", ls=EXCLUDE_DASH, lw=1.4, alpha=0.95, marker="v", ms=4, markevery=EXCLUDE_MARK_EVERY)
        words.append(EXCLUDE_LABEL)
    elif proposal == NEEDS_LOOK:
        style.update(color="#b9770e", ls="-.", lw=1.3, alpha=0.95)
        words.append(LOOK_LABEL)
    if flagged:
        if proposal not in (EXCLUDE_PROPOSED, NEEDS_LOOK):
            style.update(color="#c0392b", ls="--", alpha=0.9)
        words.append(FLAGGED_LABEL)
    return " ".join([name, *words]), style


def review_plot(path: Path, *, title: str, grid, M, merged, point_flags, scan_flags, norm, flat, e0, athena=None, np=None,
                scan_labels=None, scan_proposals=None, merge_note: str | None = None) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return False
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    n = M.shape[0]
    plain_named = False
    for s in range(n):
        flagged = bool(scan_flags and scan_flags[s])
        proposal = scan_proposals[s] if scan_proposals and s < len(scan_proposals) else None
        label, style = scan_style(s, label=scan_labels[s] if scan_labels and s < len(scan_labels) else None,
                                  proposal=proposal, flagged=flagged)
        marked = flagged or proposal in (EXCLUDE_PROPOSED, NEEDS_LOOK)
        if n > LEGEND_SCANS and not marked:
            # too many scans to name each: the marked ones keep their names, the rest share one entry
            label = "_nolegend_" if plain_named else f"other scans ({sum(1 for k in range(n) if not _marked(k, scan_flags, scan_proposals))})"
            plain_named = True
        ax1.plot(grid, M[s], label=label, **style)
        if point_flags is not None and point_flags[s].any():
            ax1.plot(grid[point_flags[s]], M[s][point_flags[s]], "x", color="#c0392b", ms=7)
    ax1.plot(grid, merged, color="black", lw=1.6, label="merged (mean)")
    ax1.set_ylabel("mu(E) (raw, protocol channel)")
    ax1.set_title(title, fontsize=9)
    ax1.legend(fontsize=7, loc="best")
    if norm is not None:
        ax2.plot(grid, norm, color="#2c3e50", lw=1.0, label="ISAAC normalized")
        ax2.plot(grid, flat, color="#2980b9", lw=1.2, label="ISAAC flattened")
    if athena is not None:
        ax2.plot(athena["energy"], athena["flat"], color="#e67e22", lw=1.0, ls="--", label=f"Athena: {athena['label'][:40]}")
    if e0 is not None:
        ax2.axvline(e0, color="grey", lw=0.6, ls=":")
    ax2.set_xlabel("Energy (eV)")
    ax2.set_ylabel("normalized mu(E)")
    ax2.legend(fontsize=7, loc="best")
    fig.text(0.01, 0.022, "DRAFT protocol isaac.xas.v0 — not reviewed by a beamline scientist. x = flagged point (kept).", fontsize=7)
    if merge_note:
        fig.text(0.01, 0.005, merge_note, fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=110, metadata={"Software": None})
    plt.close(fig)
    return True


def _marked(s: int, scan_flags, scan_proposals) -> bool:
    flagged = bool(scan_flags and scan_flags[s])
    proposal = scan_proposals[s] if scan_proposals and s < len(scan_proposals) else None
    return flagged or proposal in (EXCLUDE_PROPOSED, NEEDS_LOOK)
