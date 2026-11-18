"""McMaster tables and the mback / mback_xrs component fits on synthetic spectra.

Vendored from xas-reduction (Oscar); the tests that read the package's tests/data spectra (real BL4-3 Ti K
averages, soft-XAS deliverables) are not vendored (src/xas_analysis/PROVENANCE.md)."""
import pytest

np = pytest.importorskip("numpy", reason="needs the optional `processing` extra")
pytest.importorskip("scipy", reason="needs the optional `processing` extra")
pytest.importorskip("yaml", reason="needs the optional `processing` extra")


from xas_analysis.model.mback import mback  # noqa: E402
from xas_analysis.physics.mcmaster import atomic_number, element, elements, mcmaster  # noqa: E402

# ---------------- McMaster
def test_symbols_match_table():
    for el in elements()[:94]:
        assert atomic_number(el["symbol"]) == el["Z"]
    assert atomic_number("ir") == 77 and atomic_number(26) == 26


def test_mcmaster_values_and_edges():
    # NIST XCOM total attenuation, Cu at 10 keV = 215.9 cm^2/g; McMaster agrees to a few %
    assert mcmaster("Cu", [10.0])[0] == pytest.approx(215.9, rel=0.05)
    ti = element("Ti")
    K = ti["K_edge"]
    below, above = mcmaster("Ti", [K - 1e-4, K + 1e-4])
    assert above / below > 5                      # K-edge jump
    E = np.linspace(5.0, 6.0, 50)
    assert np.all(np.diff(mcmaster("Ti", E)) < 0)  # monotone decay above the edge
    with pytest.raises(ValueError):
        mcmaster("Ti", [0.01])                    # below the M edge


# ---------------- mback
def _synthetic(continuous):
    E = np.linspace(4850, 5200, 351)
    E_keV = E / 1000
    K = element("Ti")["K_edge"]
    mu = mcmaster("Ti", E_keV)
    m = E_keV < K
    mu = mu - np.polyval(np.polyfit(E_keV[m], mu[m], 2), E_keV)
    mu[m] = 0
    mu /= mu.max()
    Es = E_keV - K
    pre = 0.3 + 0.8 * Es
    post = pre - 0.3 * Es - 2.0 * Es ** 2 if continuous else 0.25 + 0.5 * Es - 2.0 * Es ** 2
    return E, mu, 0.7 * mu + np.where(m, pre, post)


def test_mback_recovers_synthetic_components():
    E, mu, raw = _synthetic(continuous=True)
    r = mback("Ti", E, raw, None, (1, 2), "K")
    assert r.info["A_edge"] == pytest.approx(0.7, rel=1e-9)
    assert np.allclose(r.norm_xas, mu, atol=1e-9)


def test_mback_legacy_recovers_discontinuous_synthetic():
    E, mu, raw = _synthetic(continuous=False)
    r = mback("Ti", E, raw, None, (1, 2), "K", bg_continuity=False)
    assert r.info["A_edge"] == pytest.approx(0.7, rel=1e-9)
    assert np.allclose(r.norm_xas, mu, atol=1e-9)


def test_mback_single_polynomial():
    E, mu, raw = _synthetic(continuous=True)
    raw = raw - np.where(E / 1000 < element("Ti")["K_edge"], 0,
                         -0.3 * (E / 1000 - element("Ti")["K_edge"])
                         - 2.0 * (E / 1000 - element("Ti")["K_edge"]) ** 2)  # bg = pre everywhere
    r = mback("Ti", E, raw, None, (1, 0), "K")
    assert r.info["A_edge"] == pytest.approx(0.7, rel=1e-9)


# ---------------- mback_xrs: Victoreen background + McMaster step, XRS objective
def test_mback_xrs_recovers_synthetic():
    from xas_analysis.model.mback import atomic_step
    from xas_analysis.model.mback_xrs import mback_xrs
    E = np.linspace(11160, 11500, 341)
    mu, _ = atomic_step(77, E / 1000, element("Ir")["L_edge"][2])
    raw = 0.02 + 0.05 * (E / 1000 / element("Ir")["L_edge"][2]) ** -3 + 0.7 * mu
    r = mback_xrs("Ir", E, raw, [11166, 11206, 11275, 11487], "L3")
    assert r.info["A_edge"] == pytest.approx(0.7, rel=1e-9)
    assert np.allclose(r.norm_xas, mu, atol=1e-9)
