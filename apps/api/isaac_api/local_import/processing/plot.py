"""The scientist-review PNG for one group: individual scans + merged + flags, and the
normalised result (+ the scientist's Athena normalisation when matched). matplotlib Agg."""

from __future__ import annotations

from pathlib import Path


def review_plot(path: Path, *, title: str, grid, M, merged, point_flags, scan_flags, norm, flat, e0, athena=None, np=None) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return False
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    for s in range(M.shape[0]):
        style = dict(lw=0.8, alpha=0.6)
        if scan_flags and scan_flags[s]:
            style.update(color="#c0392b", ls="--", alpha=0.9)
        ax1.plot(grid, M[s], label=f"scan {s + 1}{' (flagged)' if scan_flags and scan_flags[s] else ''}", **style)
        if point_flags is not None and point_flags[s].any():
            ax1.plot(grid[point_flags[s]], M[s][point_flags[s]], "x", color="#c0392b", ms=7)
    ax1.plot(grid, merged, color="black", lw=1.6, label="merged (mean)")
    ax1.set_ylabel("mu(E) (raw, protocol channel)")
    ax1.set_title(title, fontsize=9)
    if M.shape[0] <= 12:
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
    fig.text(0.01, 0.005, "DRAFT protocol isaac.xas.v0 — not reviewed by a beamline scientist. x = flagged point (kept).", fontsize=7)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=110, metadata={"Software": None})
    plt.close(fig)
    return True
