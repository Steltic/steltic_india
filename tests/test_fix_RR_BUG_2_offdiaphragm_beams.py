"""RR-BUG-2: beams between off-diaphragm nodes (contract tag convention k*100000 + 100 i + j with a k-part above NF,
e.g. crane-bracket gantry girders) keep their node-tag level k > NF.  static_model.one_way_gravity indexed
cfg['heights'][k - 1] without the 1 <= k <= NF guard apply_gravity_state has -> IndexError (HR Ex14).  They must not
crash and must not pick up floor / roof / cladding load; they carry their self-weight only."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))


def _cfg(**kw):
    c = dict(NX=1, NY=2, SX=21000.0, SY=9000.0, heights=[11500.0], units="N-mm", jurisdiction="india",
             clad=0.3, D_roof=0.55, D_floor=0.55, L_floor=0.0, Lr=0.75, deck_span="Y", base="fixed",
             col="WPB300X300X100.85", beam="NPB450X190X67.16", self_weight=True)
    c.update(kw)
    return c


def test_one_way_gravity_repro_no_crash_no_floor_load():
    import static_model as SM
    full = {(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)}
    cfg = _cfg()
    b = {"k": 2, "L": 9000.0, "i": 0, "j": 0, "dir": "Y"}
    # the report repro: IndexError before the fix
    M, V = SM.one_way_gravity(cfg, b, 1.0, 1.0, 1.0, present={0: full, 1: full, 2: full})
    assert (M, V) == (0.0, 0.0)                         # no section area known -> nothing at all
    A = 10000.0
    b["_A"] = A
    M, V = SM.one_way_gravity(cfg, b, 1.5, 1.5, 1.5, fEv=0.1, present={0: full, 1: full, 2: full})
    w = 1.6 * A * SM.STEEL_UNIT_WEIGHT_N_PER_MM3            # self-weight only (no roof D/Lr, no cladding)
    assert M == pytest.approx(w * 9000.0 ** 2 / 8.0) and V == pytest.approx(w * 9000.0 / 2.0)
    # a real roof-level edge beam at the same position still gets roof + cladding load
    Mr, _ = SM.one_way_gravity(cfg, dict(b, k=1), 1.5, 1.5, 1.5, present={0: full, 1: full})
    assert Mr > 2 * M                                   # + cladding (1.5 x 0.3 kN/m2 x 11.5 m / 2)
    assert SM.on_diaphragm_level(cfg, 1) and not SM.on_diaphragm_level(cfg, 2) and not SM.on_diaphragm_level(cfg, 0)


def _bracket_builder():
    import example_build as EB
    import openseespy.opensees as ops

    def cb(cfg, transf):
        import engine3d as E
        info = EB.example_build(cfg, transf)
        tags = {}
        for j in range(3):
            x, y, _ = ops.nodeCoord(E.ntag(0, j, 1))
            n = 2 * 100000 + 100 * 0 + j                   # off-diaphragm bracket node, tag level 2 > NF = 1
            ops.node(n, x + 500.0, y, 8000.0)
            tags[j] = n
            t = 97000 + j                                  # hanger / bracket stub to the column head
            E.add_column(t, n, E.ntag(0, j, 1), "WPB300X300X100.85", "X")
            info["ele"].append((t, "col", "WPB300X300X100.85", n, E.ntag(0, j, 1)))
        for j in range(2):
            t = 98000 + j                                  # gantry girders between the brackets
            E.add_beam(t, tags[j], tags[j + 1], "NPB450X190X67.16", releases=("both", "none"))
            info["ele"].append((t, "beam", "NPB450X190X67.16", tags[j], tags[j + 1]))
        return info
    return cb


def test_crane_bracket_model_solves_and_gantry_carries_self_weight_only():
    pytest.importorskip("openseespy.opensees")
    import india_units as IU
    IU.activate_si()
    import engine3d as E
    import static_model as SM

    cfg = _cfg(custom_build=_bracket_builder())

    class Case(tuple):
        meta = {}
    cases = [Case(("1.5DL+1.5LL", 1.5, 1.5, 1.5, {}, False))]
    per_case, kinds, _info = SM.solve_cases_si(cfg, cases, nseg=4, floor_system="one-way")   # IndexError before
    rec = per_case["1.5DL+1.5LL"]
    g = [fs for fs, kd in kinds.items() if kd[0] == "beam" and all(n // 100000 == 2 for n in fs)]
    assert len(g) == 2
    A = E.Ipack("NPB450X190X67.16")[0]
    w = 1.5 * A * SM.STEEL_UNIT_WEIGHT_N_PER_MM3
    for fs in g:
        Mmaj = rec[fs]["Mmaj"] if isinstance(rec[fs], dict) else rec[fs][1]
        # simply supported 9 m girder under its own weight: w L^2 / 8 -- no roof or cladding load
        assert Mmaj == pytest.approx(w * 9000.0 ** 2 / 8.0, rel=0.02)
