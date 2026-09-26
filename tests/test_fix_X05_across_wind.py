"""X05 (HR-B-09, HR-C-12; ruling R10): IS 875 (Part 3):2015 10.3 across-wind load case.

Corpus 10.3: "Mc [=] 0.5 gh ph b h^2 (1.06 - 0.06 k) sqrt(pi Cfs / beta)" and "The across wind load distribution ...
can be obtained from Mc using linear distribution of loads as given below: Fz,c = (3 Mc / h^2)(z / h)".
10.4: "The along wind and across wind loads have to be applied simultaneously on the building/structure during design."

Hand values: integral_0^h Fz,c dz = 1.5 Mc / h (base shear), integral_0^h Fz,c z dz = Mc (base moment)."""
import copy
import math

import pytest

from _ex1_fixture import ex1_cfg_is


def test_level_forces_reproduce_base_shear_and_moment():
    import india_wind_tables as WT
    zs = [4.5, 8.0, 11.5, 15.0, 19.0]                    # unequal storeys, h = 19 m
    Mc = 1234.0
    r = WT.across_wind_level_forces(zs, Mc)
    assert r["V_kN"] + r["F_ground_kN"] == pytest.approx(1.5 * Mc / 19.0, rel=1e-12)      # 3Mc/h^3 * h^2/2
    assert r["M_base_kNm"] == pytest.approx(Mc, rel=1e-12)                                  # 3Mc/h^3 * h^3/3
    assert sum(f * z for f, z in zip(r["F_kN"], zs)) == pytest.approx(Mc, rel=1e-12)
    # top level: half of the top storey's linear load, weighted to the top: L (w0 + 2 w1) / 6
    a = 3 * Mc / 19.0 ** 3
    assert r["F_kN"][-1] == pytest.approx(4.0 * (a * 15.0 + 2 * a * 19.0) / 6.0, rel=1e-12)


def test_Mc_formula_hand_value():
    import india_wind_tables as WT
    fc, ph, b, h, k, Cfs, beta = 0.25, 850.0, 30.0, 90.0, 0.5, 0.0015, 0.02
    gh = math.sqrt(2 * math.log(3600 * 0.25))            # = sqrt(2 ln 900) = 3.68847
    Mc = 0.5 * gh * ph * b * h * h * (1.06 - 0.03) * math.sqrt(math.pi * Cfs / beta) / 1000.0
    r = WT.across_wind_Mc(Cfs=Cfs, beta=beta, fc_hz=fc, b_m=b, h_m=h, k=k, ph_Pa=ph)
    assert r["gh"] == pytest.approx(3.68847, abs=1e-5)
    assert r["Mc_kNm"] == pytest.approx(Mc, rel=1e-12)
    assert r["Mc_kNm"] == pytest.approx(190451.3, rel=1e-6)
    assert "OCR-broken" in r["gh_basis"] and "10.3" in r["cite"]


def _cfs_record(**kw):
    rec = {"found": False, "note": "Fig. 10 not in the corpus text",
           "Cfs": {"value": 0.0015, "source": "EOR reading of Fig. 10 (square section, TI 0.12), calc WN-3",
                   "cite": "IS 875 (Part 3):2015 10.3, Fig. 10"},
           "k": 0.5, "beta": 0.02, "ph_Pa": 850.0,
           "X": {"fc_hz": 0.30}, "Y": {"fc_hz": 0.35}}
    rec.update(kw)
    return rec


def test_cfs_record_computes_Mc_per_direction():
    import india_wind_tables as WT
    r = WT.resolve_across_wind(_cfs_record(), {}, h_m=18.0, b_m={"X": 20.0, "Y": 30.0})
    assert r["found"] is True
    x = r["by_dir"]["X"]
    ref = WT.across_wind_Mc(Cfs=0.0015, beta=0.02, fc_hz=0.30, b_m=20.0, h_m=18.0, k=0.5, ph_Pa=850.0)["Mc_kNm"]
    assert x["Mc_kNm"] == pytest.approx(ref) and x["found"] is True
    assert "EOR reading of Fig. 10" in x["source"] and "Fig. 10" in x["cite"] and x["Cfs"]["value"] == 0.0015
    assert r["by_dir"]["Y"]["inputs"]["b_m"] == 30.0 and r["by_dir"]["Y"]["inputs"]["fc_hz"] == 0.35
    # no source -> not evaluated (R10)
    bad = _cfs_record(Cfs={"value": 0.0015, "source": "", "cite": "Fig. 10"})
    r2 = WT.resolve_across_wind(bad, {}, h_m=18.0, b_m={"X": 20.0, "Y": 30.0})
    assert r2["found"] is False and "Cfs.source" in r2["reason"]


def test_gate_accepts_cfs_record():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    ws = cfg["load_plan"]["wind_summary"]
    ws["gust_factor"] = {"G": 2.4, "VB_x_kN": 1.0, "VB_y_kN": 1.0}
    ws["across_wind"] = _cfs_record()
    ok, why, req = E.india_dynamic_wind_gate(cfg, 0.8)
    assert req and ok, why
    ws["across_wind"] = _cfs_record(beta=None)
    ok, why, _ = E.india_dynamic_wind_gate(cfg, 0.8)
    assert not ok and any("beta" in w for w in why)


def _combos(cfg):
    import india_loads as IL
    return IL.expanded_combinations(cfg)


def test_across_rows_generated_and_forces():
    import india_loads as IL
    cfg, _ = ex1_cfg_is()
    plan = cfg["load_plan"]
    plan["wind_summary"]["across_wind"] = {"found": True, "Mc_kNm": 900.0, "cite": "IS 875-3 10.3"}
    cs = _combos(cfg)
    ac = [c for c in cs if "across_wind" in (c.get("tags") or [])]
    # every along-wind row (strength + SLS) repeated with +/- across of the same wind direction
    along = [c for c in cs if c.get("lateral_kind") == "W" and c.get("fW") is not None
             and "across_wind" not in (c.get("tags") or [])]
    assert len(ac) == 2 * len(along) and len(ac) > 0
    for c in ac:
        t = [t for t in c["terms"] if t["ref"].endswith("_across")]
        assert len(t) == 1 and t[0]["ref"] == c["lateral_ref"] + "_across"
        assert abs(t[0]["f"]) == pytest.approx(abs(c["fW"]))
        assert "10.4" in c["cite"]
    assert any(c.get("service") for c in ac) and any(not c.get("service") for c in ac)
    # the pattern: acts normal to the wind, sums to 1.5 Mc/h less the ground share, overturning = Mc
    sf = plan["story_forces"]["W_X_across"]
    zs = [3.6 * k for k in range(1, 6)]
    Fy = [sf[str(k)][1] / 1000.0 for k in range(1, 6)]
    assert all(sf[str(k)][0] == 0.0 for k in range(1, 6))
    assert sum(f * z for f, z in zip(Fy, zs)) == pytest.approx(900.0, rel=1e-9)
    assert sum(Fy) == pytest.approx(1.5 * 900.0 / 18.0 - 3.6 * (3 * 900.0 / 18.0 ** 3 * 3.6) / 6.0, rel=1e-9)
    # the solved case carries along (X) and across (Y) together
    lab = "1.2DL+1.2LL+1.2W_X-1.2W_X_across"
    c = [x for x in cs if x["label"] == lab][0]
    case = IL.case_from_combination(c, plan)
    Fx_along = plan["story_forces"]["W_X"]["3"][0] * 1.2
    assert case[4][3][0] == pytest.approx(Fx_along) and case[4][3][1] == pytest.approx(-1.2 * sf["3"][1])
    import india_combos as IC
    meta = IC.last_expansion_meta()["across_wind"]
    assert meta["evaluated"] and meta["summary"]["W_Y_across"]["force_dir"] == "X"


@pytest.mark.parametrize("aw", [None, {"found": False, "result": "NOT EVALUATED"}, {"found": True, "Mc_kNm": "TBD"}])
def test_no_across_rows_when_not_evaluated(aw):
    cfg, _ = ex1_cfg_is()
    plan = cfg["load_plan"]
    if aw is not None:
        plan["wind_summary"]["across_wind"] = aw
    base = copy.deepcopy(plan["story_forces"])
    cs = _combos(cfg)
    assert not any("across" in c["label"] or "across_wind" in (c.get("tags") or []) for c in cs)
    assert plan["story_forces"] == base


def test_explicit_list_without_across_rows_is_refused():
    import india_combos as IC
    cfg, _ = ex1_cfg_is()
    plan = cfg["load_plan"]
    plan["wind_summary"]["across_wind"] = {"eor": {"value": 700.0, "source": "EOR calc 7", "cite": "IS 875-3 10.3"}}
    cs = _combos(cfg)
    assert not [m for s, m in IC.validate_combinations(cs, cfg, plan) if s == "ERROR"]
    stripped = [c for c in cs if "across_wind" not in (c.get("tags") or [])]
    errs = [m for s, m in IC.validate_combinations(stripped, cfg, plan) if s == "ERROR"]
    assert any("10.4" in m and "W_X_across" in m for m in errs)


def test_wind_serviceability_and_collectors_include_across():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_diaphragm as DIA
    cfg, _ = ex1_cfg_is()
    r0 = E.india_wind_serviceability(cfg)
    cfg["load_plan"]["wind_summary"]["across_wind"] = {"found": True, "Mc_kNm": 5000.0, "cite": "IS 875-3 10.3"}
    _combos(cfg)
    r1 = E.india_wind_serviceability(cfg)
    for d in ("X", "Y"):
        assert "across_wind" not in r0[d] and r1[d]["across_wind"]["pattern"] == "W_%s_across" % d
        assert r1[d]["top_mm"] >= r0[d]["top_mm"] - 1e-9
    pc = DIA.pattern_collector_forces(cfg, "W", "W_X_across")
    assert isinstance(pc, dict)
