"""O2 (owner ruling 2026-09-26): gantry / crane-girder weight is declared as nodal dead loads (with its eccentricity),
never also as element self-weight.  Gantry elements modelled for strut action are listed under
cfg['self_weight_in_nodal_loads'] = {'tags': [...] | 'sections': [...], 'cite', 'note'} and get no self-weight in the
gravity state, W or the modal mass.  Preflight: ERROR when off-diaphragm / gantry-section elements with nodal dead
loads at their ends still carry self-weight (double count); ERROR when a listed element has no nodal load at its ends
(weight lost); WARN when gantry elements carry their own self-weight without nodal loads (accepted, ruling prefers
nodal loads).

Hand model (IN_Ex14 pattern): 1 x 2 bays (21 m x 9 m), one level at 11.5 m, crane brackets at 8.0 m with off-grid
tags 200000 + 100 i + j (tag level 2 > NF = 1), pinned 9 m gantry struts between the brackets of line i = 0."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))

GANTRY = "NPB700X250X171.48"
GTAGS = (98000, 98001)
BRK = {j: 200000 + j for j in range(3)}
WG = 20.0e3                                      # declared girder + rail + cap weight per bracket (N)


@pytest.fixture(scope="module")
def E():
    pytest.importorskip("openseespy.opensees")
    import india_units as IU
    IU.activate_si()
    import engine3d as E
    return E


def _builder(with_gantry=True):
    def cb(cfg, transf):
        import engine3d as E
        import example_build as EB
        import openseespy.opensees as ops
        info = EB.example_build(cfg, transf)
        for j in range(3):
            x, y, _ = ops.nodeCoord(E.ntag(0, j, 1))
            ops.node(BRK[j], x + 500.0, y, 8000.0)          # off-diaphragm bracket node, tag level 2 > NF
            t = 97000 + j                                   # bracket stub to the column head
            E.add_column(t, BRK[j], E.ntag(0, j, 1), "WPB300X300X100.85", "X")
            info["ele"].append((t, "col", "WPB300X300X100.85", BRK[j], E.ntag(0, j, 1)))
        if with_gantry:
            for j in range(2):                              # gantry girders: pinned struts between the brackets
                E.add_beam(GTAGS[j], BRK[j], BRK[j + 1], GANTRY, releases=("both", "none"))
                info["ele"].append((GTAGS[j], "beam", GANTRY, BRK[j], BRK[j + 1]))
        return info
    return cb


def _nodal():
    return [{"node": BRK[j], "Fz_N": -WG * (1.0 if j == 1 else 0.5), "My_Nmm": 600.0 * WG * (1.0 if j == 1 else 0.5),
             "level": 1, "note": "gantry girder + rail + cap, e = 600 mm"} for j in range(3)]


def _cfg(**kw):
    c = dict(NX=1, NY=2, SX=21000.0, SY=9000.0, heights=[11500.0], units="N-mm", jurisdiction="india",
             clad=0.0, D_roof=0.55, D_floor=0.55, L_floor=0.0, Lr=0.75, deck_span="Y", base="fixed",
             col="WPB300X300X100.85", beam="NPB450X190X67.16", self_weight=True, custom_build=_builder(),
             nodal_dead_loads=_nodal())
    c.update(kw)
    return c


KEY_TAGS = {"tags": list(GTAGS), "cite": "owner ruling O2", "note": "gantry weight in nodal_dead_loads"}
KEY_SECS = {"sections": [GANTRY], "cite": "owner ruling O2"}


def _strut_weight(E):
    return 2 * E.Ipack(GANTRY)[0] * E.STEEL_N_PER_MM3 * 9000.0      # two 9 m struts, 78.5 kN/m3


def _base_reaction(cfg, fD=1.0):
    import openseespy.opensees as ops
    import static_model as SM
    model = SM.build_static(cfg, "Linear", 4)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    SM.apply_gravity_state(cfg, model, fD, 0.0, 0.0, self_weight=True)
    assert SM._solve() == 0
    ops.reactions()
    base = [n for n in ops.getNodeTags() if n < 100000 and n // 100000 == 0 and abs(ops.nodeCoord(n)[2]) < 1e-6]
    return sum(ops.nodeReaction(n)[2] for n in base)


@pytest.mark.parametrize("key", [KEY_TAGS, KEY_SECS])
def test_W_and_modal_mass_drop_by_exactly_the_strut_self_weight(E, key):
    import openseespy.opensees as ops
    c0, c1 = _cfg(), _cfg(self_weight_in_nodal_loads=key)
    W0, W1 = sum(E.seismic_weights(c0)[0]), sum(E.seismic_weights(c1)[0])
    assert W0 - W1 == pytest.approx(_strut_weight(E), rel=1e-9)
    # the nodal dead loads stay in W in both runs (declared once)
    assert E.seismic_weight_components(c1, 1)["nodal_dead"] == pytest.approx(2 * WG)
    # modal mass: the builder's diaphragm mass reads floor_w
    E.build(c0, "Linear"); m0 = ops.nodeMass(E.mtag(1))[0]
    E.build(c1, "Linear"); m1 = ops.nodeMass(E.mtag(1))[0]
    assert (m0 - m1) * E.g == pytest.approx(_strut_weight(E), rel=1e-6)


def test_gravity_reactions_drop_by_exactly_the_strut_self_weight(E):
    R0 = _base_reaction(_cfg())
    R1 = _base_reaction(_cfg(self_weight_in_nodal_loads=KEY_TAGS))
    assert R0 - R1 == pytest.approx(_strut_weight(E), rel=1e-6)
    # and with the key the model equals one without gantry elements at all (weight = the nodal loads only)
    R2 = _base_reaction(_cfg(custom_build=_builder(with_gantry=False)))
    assert R1 == pytest.approx(R2, rel=1e-9)
    Rf = _base_reaction(_cfg(self_weight_in_nodal_loads=KEY_TAGS), fD=1.5)
    assert Rf == pytest.approx(1.5 * R1, rel=1e-9)                 # factored with the dead load


def test_one_way_gravity_shear_has_no_self_weight_for_listed_strut(E):
    import static_model as SM
    b = {"k": 2, "L": 9000.0, "dir": "Y", "_A": E.Ipack(GANTRY)[0], "etag": GTAGS[0], "sec": GANTRY}
    assert SM.one_way_gravity(_cfg(), b, 1.2, 0.5, 0.5)[1] > 0.0
    assert SM.one_way_gravity(_cfg(self_weight_in_nodal_loads=KEY_TAGS), b, 1.2, 0.5, 0.5) == (0.0, 0.0)


def _msgs(E, cfg, sev):
    return [m for s, m in E.self_weight_nodal_findings(cfg) if s == sev]


def test_preflight_error_when_gantry_weight_double_counted(E):
    err = _msgs(E, _cfg(), "ERROR")
    assert len(err) == 1 and "double-counted" in err[0] and "self_weight_in_nodal_loads" in err[0]
    assert str(GTAGS[0]) in err[0] and str(GTAGS[1]) in err[0]
    assert not E.self_weight_nodal_findings(_cfg(self_weight_in_nodal_loads=KEY_TAGS))
    assert not E.self_weight_nodal_findings(_cfg(self_weight_in_nodal_loads=KEY_SECS))
    # the declared crane gantry_section alone also flags it (on-diaphragm gantry members too)
    err = _msgs(E, _cfg(crane={"gantry_section": GANTRY}), "ERROR")
    assert len(err) == 1 and "double-counted" in err[0]


def test_preflight_warn_when_gantry_carries_its_own_weight(E):
    c = _cfg(nodal_dead_loads=[], crane={"gantry_section": GANTRY})
    assert not _msgs(E, c, "ERROR")
    warn = _msgs(E, c, "WARN")
    assert len(warn) == 1 and "owner ruling O2" in warn[0] and "nodal_dead_loads" in warn[0]
    # no crane data and no nodal loads: silent (plain off-diaphragm struts with self-weight)
    assert not E.self_weight_nodal_findings(_cfg(nodal_dead_loads=[]))


def test_preflight_error_when_listed_weight_would_be_lost(E):
    err = _msgs(E, _cfg(nodal_dead_loads=[], self_weight_in_nodal_loads=KEY_TAGS), "ERROR")
    assert len(err) == 1 and "would be lost" in err[0]
    # a listed section shared with the floor beams (no nodal loads there) is caught the same way
    err = _msgs(E, _cfg(self_weight_in_nodal_loads={"sections": ["NPB450X190X67.16", GANTRY]}), "ERROR")
    assert len(err) == 1 and "would be lost" in err[0]
    # a listed section shared with columns (IN_Ex14: gantry and portal columns are one section) -> list tags
    err = _msgs(E, _cfg(self_weight_in_nodal_loads={"sections": ["WPB300X300X100.85"]}), "ERROR")
    assert any("also match non-beam" in m and "tags" in m for m in err)
    warn = _msgs(E, _cfg(self_weight_in_nodal_loads={"tags": list(GTAGS) + [12345]}), "WARN")
    assert len(warn) == 1 and "12345" in warn[0]
    with pytest.raises(ValueError):
        E.sw_in_nodal_loads({"self_weight_in_nodal_loads": [98000]})


def test_preflight_india_checks_runs_the_rule(E):
    import preflight as PF
    c = _cfg(no_seismic=True, steel_grade="E250 B0", model={"bases": "fixed", "joints": "rigid", "gravity": "one-way"})
    res = PF.india_checks(c)
    assert any(s == "ERROR" and "O2:" in m and "double-counted" in m for s, m in res)
    c = _cfg(no_seismic=True, steel_grade="E250 B0", model={"bases": "fixed", "joints": "rigid", "gravity": "one-way"},
             self_weight_in_nodal_loads=KEY_TAGS)
    assert not any("O2" in m for s, m in PF.india_checks(c))


def test_contract_documents_ruling_o2():
    root = Path(__file__).resolve().parents[1]
    txt = (root / "contract" / "AGENT_START.md").read_text(encoding="utf-8")
    assert "owner ruling O2" in txt and "self_weight_in_nodal_loads" in txt
