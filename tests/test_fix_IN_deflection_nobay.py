"""IN-DEFL-NOBAY (gold issue IN_CFS_Ex14): IS 800:2007 5.6.1 / Table 6 imposed-load deflection of a beam that
bounds no present floor bay (grade tie between stepped bases, edge of a partial footprint).  The gravity analysis
(static_model.apply_gravity_state: width = nb x bay / 2 = 0) puts no floor load on it; the deflection screen loaded it
with a FULL bay (w_LL = L x bay).  Now its imposed-load tributary is 0 (no Table 6 row for it); beams that bound a
bay are unchanged (edge = half bay, interior = two half bays)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steel_engine"))

pytest.importorskip("openseespy.opensees")

TIE = "NPB200X100X18.43"


def _cfg(**kw):
    import engine3d as E
    E.activate_si_units()
    # level 1: bay (0, 0) framed; node (2, 0) present without (2, 1) -> beam (1,0)-(2,0) bounds no complete bay
    plan = lambda k, NX, NY: ({(0, 0), (1, 0), (2, 0), (0, 1), (1, 1)} if k <= 1 else {(0, 0), (1, 0), (0, 1), (1, 1)})
    cfg = dict(units="N-mm", jurisdiction="india", NX=2, NY=1, SX=6000.0, SY=5000.0, heights=[3500.0, 3500.0],
               D_floor=4.0, D_roof=3.0, L_floor=5.0, Lr=0.75, clad=0.0, self_weight=False, base="pinned",
               col="WPB200X200X61.3", beam="NPB300X150X36.53", brace="WPB200X200X61.3",
               beam_sec=lambda i, j, k, d: TIE if (k == 1 and d == "X" and i == 1 and j == 0) else "NPB300X150X36.53",
               releases=lambda i, j, k, d: ("both", "none"), plan=plan,
               braces=lambda k, NX, NY: [])
    cfg.update(kw)
    return cfg


@pytest.mark.parametrize("ds", [None, "Y"])
def test_beam_bounding_no_bay_has_no_imposed_load_row(ds):
    import engine3d as E
    cfg = _cfg(**({"deck_span": ds} if ds else {}))
    worst, n, rows = E.beam_deflection_si(cfg)
    assert n > 0
    assert not [r for r in rows if r["section"] == TIE], rows          # was: w = 5 kN/m2 x 5 m = 25 N/mm, full bay
    # the framed bay's edge girders keep their half bay: 5.0 x 2.5 m = 12.5 N/mm (floor, span 6 m, X)
    fl = [r for r in rows if r["section"] == "NPB300X150X36.53" and not r["roof"] and r["span_mm"] == 6000.0]
    assert fl and max(r["w_LL_N_per_mm"] for r in fl) == pytest.approx(12.5, rel=1e-6)


def test_analysis_puts_no_floor_load_on_the_tie():
    """The same beam in the gravity state: zero floor load (only its own weight, switched off here)."""
    import openseespy.opensees as ops
    import static_model as SM
    import engine3d as E
    cfg = _cfg()
    m = SM.build_static(cfg, "Linear", 4)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    SM.apply_gravity_state(cfg, m, 0.0, 1.0, 0.0, self_weight=False)
    assert SM._solve_newton() == 0
    tie = [b for b in m["beams"] if b["k"] == 1 and b["dir"] == "X" and b["i"] == 1 and b["j"] == 0]
    assert tie
    R = SM._responses(m)
    assert max(abs(R[t][3]) for t in tie[0]["segs"]) < 1e-6        # no shear: no load on it
