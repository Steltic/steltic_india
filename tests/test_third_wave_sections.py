"""Third wave (2026-10), agent SECT: Indian section families for the hot-rolled golds IN_Ex7 ... IN_Ex20.

P3 (HR side)  a tie between two load combinations is broken by the fixed order of the combination list, whatever
              PYTHONHASHSEED is (design_pipeline.member_check_records keeps every combination in list order)
P6 sizer      steel_engine/hr_autosize.py: catalogue by role (IS 808 MB / WB / HB, IS 1161 CHS), the order of
              preference (rolled E250 -> rolled E350 -> built-up), built-up labels, the cfg rewrite, the grade map,
              the connection designers (fin plates and CHS brace ends checked with the engine's own capacity
              functions), the base / splice adapters and their step-up rules
"""
import json
import math
import os
import subprocess
import sys

import pytest

import _ex1_fixture  # noqa: F401  (puts steel_engine on sys.path)

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "steel_engine")


def _az():
    import hr_autosize as AZ
    return AZ


# ------------------------------------------------------------------------------------------------ P3 (HR side)
_TOP_RECORDS_SCRIPT = r"""
import json, sys
sys.path.insert(0, ENGINE_DIR)
import design_pipeline as DP
labels = ["1.5DL+1.5LL", "1.5DL+1.5LL+N_X", "1.5DL+1.5LL-N_X", "1.5DL+1.5LL+N_Y", "1.5DL+1.5LL-N_Y"] + \
         ["1.2DL+1.2LL%s1.2EQ_%s[%s]+0.3EQ_Z" % (s, d, e) for s in "+-" for d in "XY" for e in ("ea", "eb")]
recs = {l: [-1000.0, 50.0, 10.0, 5.0] + [0.0] * 9 for l in labels}     # all tied
print(json.dumps(list(DP._top_records(recs, k=8))))
"""


def test_p3_top_records_keep_the_combination_order_for_any_hash_seed():
    outs = set()
    for seed in ("0", "1", "2", "3"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", "ENGINE_DIR = %r\n" % ENGINE + _TOP_RECORDS_SCRIPT], env=env, capture_output=True,
                           text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1
    order = json.loads(outs.pop())
    # the kept combinations appear in the order of the combination list
    full = ["1.5DL+1.5LL", "1.5DL+1.5LL+N_X", "1.5DL+1.5LL-N_X", "1.5DL+1.5LL+N_Y", "1.5DL+1.5LL-N_Y"] + \
           ["1.2DL+1.2LL%s1.2EQ_%s[%s]+0.3EQ_Z" % (s, d, e) for s in "+-" for d in "XY" for e in ("ea", "eb")]
    assert order == [l for l in full if l in order]


def test_p3_tied_member_check_governs_with_the_first_combination_in_the_list():
    import design_pipeline as DP
    import india_is800 as I8
    import static_model as SM
    recs = {"1.5DL+1.5LL": [-200e3, 40e6, 0.0, 30e3, 40e6, -40e6, 0.0, 0.0, 40e6, 30e3, 0.0, 0.0, 0.0],
            "1.5DL+1.5LL+N_X": [-200e3, 40e6, 0.0, 30e3, 40e6, -40e6, 0.0, 0.0, 40e6, 30e3, 0.0, 0.0, 0.0]}
    m = {"id": "e1", "tag": 1, "section": "MB300", "grade": "E250 B0", "role": "beam", "L_mm": 6000.0, "Kz": 1.0,
         "Ky": 1.0, "LLT_sag_mm": 1500.0, "LLT_hog_mm": 1500.0}
    for order in (list(recs), list(reversed(list(recs)))):
        rr = {k: recs[k] for k in order}
        cf = SM.combo_forces_for_member_check(DP._top_records(rr), "beam")
        r = I8.member_check_is800(m, cf, cfg={})
        assert r["governing_combo"] == order[0]


# ------------------------------------------------------------------------------------------------ catalogue
def test_rolled_families_lightest_first_and_only_their_family():
    AZ = _az()
    mb = AZ.rolled("MB")
    assert mb[0] == "MB100" and mb[-1] == "MB600"
    assert all(l.startswith("MB") for l in mb)
    ms = [AZ.mass_kg_m(l) for l in mb]
    assert ms == sorted(ms)
    hb = AZ.rolled("HB")
    assert hb and all(l.startswith("HB") for l in hb)
    chs = AZ.rolled("CHS")
    assert chs[0].startswith("CHS") and AZ.mass_kg_m(chs[0]) <= AZ.mass_kg_m(chs[-1])


def test_order_of_preference_rolled_e250_then_e350_then_built_up():
    AZ = _az()
    c = AZ.candidates({"role": "column", "families": ["HB"], "built_up": "box"})
    tiers = [t for (_, _, t) in c]
    assert tiers == sorted(tiers)
    assert c[0][1] == "E250 B0" and c[0][0].startswith("HB")
    e350 = [x for x in c if x[2] == 1]
    assert e350 and all(x[1] == "E350 B0" and x[0].startswith("HB") for x in e350)
    bu = [x for x in c if x[2] == 2]
    assert bu and all(x[0].startswith("BOX") for x in bu)
    assert {x[1] for x in bu} == {"E250 B0", "E350 B0"}
    assert bu[0][1] == "E250 B0" and bu[1] == (bu[0][0], "E350 B0", 2)
    # braces: IS 1161 tubes only, no IS 2062 grade (the tube grade comes from the cfg)
    b = AZ.candidates({"role": "brace"})
    assert b and all(l.startswith("CHS") and g is None for (l, g, _) in b)
    # beams: MB / WB rolled, then welded plate I
    bm = AZ.candidates({"role": "beam", "built_up": "welded_I", "max_depth_mm": 600})
    assert bm[0][0].startswith(("MB", "WB")) and any(l.startswith("WI") for (l, _, _) in bm)


def test_built_up_labels_parse_register_and_mass():
    AZ = _az()
    import sections as S
    assert AZ.box_label(450, 450, 28) == "BOX450X450X28"
    # depth first, as the golds' labels: BOX450X400X25 is 450 deep (major axis plane), 400 wide
    assert AZ.parse_built_up("BOX450X400X25") == ("box", (400.0, 450.0, 25.0, 25.0))
    assert AZ.box_label(400, 450, 25) == "BOX450X400X25"
    AZ.register("BOX450X400X25")
    assert S.props("BOX450X400X25")["d"] == 450.0 and S.props("BOX450X400X25")["bf"] == 400.0
    assert AZ.wi_label(700, 300, 25, 14) == "WI700X300X25X14"
    AZ.register("BOX430X430X28")
    p = S.props("BOX430X430X28")
    A = 2 * 430 * 28 + 2 * (430 - 56) * 28
    assert abs(p["A"] - A) < 1e-6
    assert abs(AZ.mass_kg_m("BOX430X430X28") - A * 7.85e-3) < 1e-6
    cs = AZ.custom_sections({"a": "BOX430X430X28", "b": "MB300", "c": "WI700X300X25X14"})
    assert set(cs) == {"BOX430X430X28", "WI700X300X25X14"}
    assert cs["WI700X300X25X14"]["type"] == "welded_I" and cs["BOX430X430X28"]["tf_mm"] == 28.0


def test_built_up_catalogue_is_sorted_and_respects_limits():
    AZ = _az()
    boxes = AZ.built_up_catalogue("box", min_depth=300, max_depth=450)
    ms = [AZ.mass_kg_m(l) for l in boxes]
    assert ms == sorted(ms)
    for l in boxes:
        k, (B, D, tf, tw) = AZ.parse_built_up(l)
        assert 300 <= B <= 450 and (B - 2 * tf) / tf >= 6.0


# ------------------------------------------------------------------------------------------------ cfg rewrite
SRC = '''"""doc"""
import math
# the groups
SECTIONS = {"col": "HB300", "beam": "MB400"}   # trailing comment
X = 1
GRADE_BY_SECTION = {}
CONNECTIONS = {"beam_shear": {}}
cfg = dict(a=SECTIONS["col"])
'''


def test_rewrite_source_replaces_only_the_named_literals_and_keeps_comments():
    AZ = _az()
    out = AZ.rewrite_source(SRC, {"SECTIONS": {"col": "BOX400X400X25", "beam": "MB450"},
                                  "GRADE_BY_SECTION": {"lateral_col:BOX400X400X25": "E350 B0"}})
    assert "# the groups" in out and '"""doc"""' in out and "X = 1" in out
    lit = AZ.read_literals(out, ("SECTIONS", "GRADE_BY_SECTION", "CONNECTIONS"))
    assert lit["SECTIONS"] == {"col": "BOX400X400X25", "beam": "MB450"}
    assert lit["GRADE_BY_SECTION"] == {"lateral_col:BOX400X400X25": "E350 B0"}
    assert lit["CONNECTIONS"] == {"beam_shear": {}}
    with pytest.raises(KeyError):
        AZ.rewrite_source(SRC, {"NOPE": 1})


def test_grade_map_keys_by_engine_role_and_skips_the_job_grade():
    AZ = _az()
    x = {"c1": ("BOX450X450X28", "E350 B0"), "c2": ("HB300", "E250 B0"), "b": ("MB400", None),
         "br": ("CHS219.1X8", None)}
    roles = {"c1": ["lateral_col"], "c2": ["gravity_col"], "b": ["floor"], "br": ["brace"]}
    g = AZ.grade_map(x, roles, "E250 B0", base={"MC200": "E250 B0"})
    assert g == {"MC200": "E250 B0", "lateral_col:BOX450X450X28": "E350 B0"}


# ------------------------------------------------------------------------------------------------ connections
def test_fin_plate_designer_passes_the_engine_checks_and_fits_the_web():
    AZ = _az()
    import india_connections as C
    for sec, V in (("MB300", 120e3), ("MB450", 350e3), ("MB600", 600e3)):
        sp = AZ.design_fin_plate(sec, V)
        assert sp is not None
        assert AZ.fin_plate_fits(sec, sp["bolts"]["n_bolts"] // sp.get("bolt_lines", 1), sp["bolts"]["d_mm"])
        kw = {k: v for k, v in sp.items() if k in ("t_plate_mm", "h_plate_mm", "fy_plate_MPa", "fu_plate_MPa", "bolts",
                                                    "block_shear_areas", "cjp")}
        r = C.fin_plate_shear_checks(V_N=V, **kw)
        assert r["ok"] is True and r["dc"] <= 0.9 + 1e-9
        e, p, d0 = AZ.BOLT_GEOM[sp["bolts"]["d_mm"]]
        rows = sp["bolts"]["n_bolts"] // sp.get("bolt_lines", 1)
        assert sp["h_plate_mm"] == 2 * e + (rows - 1) * p
        import india_connection_design as CD
        sl = CD.hsfg_slip_checks(sp["bolts"], sp["bolt_type"], V / 1.5, V, slip_surface=sp["slip_surface"])
        assert sl["slip_service_10_4_3"]["dc"] <= 0.9 + 1e-9
        # the spec goes through the engine's own beam-end connection wiring (bolt dict: IS 800 10.3 inputs only)
        r2 = CD.beam_shear_connection_checks({"connections": {"beam_shear": {sec: sp}}}, {"section": sec}, V)
        assert r2["ok"] is True


def test_chs_brace_end_spec_geometry():
    AZ = _az()
    sp = AZ.brace_end_chs_spec("CHS219.1X8", 20.0, 400.0)
    import sections as S
    p = S.props("CHS219.1X8")
    assert sp["An_mm2"] == pytest.approx(p["A"] - 2 * 8.0 * 22.0, abs=0.1)
    assert sp["gusset"]["Avg_mm2"] == 2 * 400.0 * 20.0 and sp["gusset"]["w_start_mm"] == pytest.approx(219.1)
    bw = 219.1 + 2 * 400.0 * math.tan(math.radians(30))
    # a 20 mm gusset is in the IS 2062:2025 > 16-40 mm band: fy 240 (the engine's fy_is2062)
    assert sp["moment_capacity_Nmm"] == pytest.approx(20.0 * bw ** 2 / 4 * 240.0 / 1.1)
    assert AZ.plate_fy(16.0) == 250.0 and AZ.plate_fy(16.5) == 240.0 and AZ.plate_fy(45.0, "E350 B0") == 320.0
    assert sp["welds"]["n_sides"] == 4 and sp["weld_type"] == "cjp"


def test_cover_plate_joint_develops_the_factor_on_the_beam_plastic_moment():
    AZ = _az()
    import india_connections as C
    import sections as S
    for beam in ("MB400", "MB600", "WB500"):
        sp = AZ.cover_plate_joint_spec(beam)
        p = S.props(beam)
        cp = sp["cover_plate"]
        r = C.cover_plate_moment_capacity(Zp_beam_mm3=p["Zx"], fy_beam_MPa=250.0, d_beam_mm=p["d"],
                                          plate_b_mm=cp["plate_b_mm"], plate_t_mm=cp["plate_t_mm"],
                                          fy_plate_MPa=cp["fy_plate_MPa"])
        assert r["capacity_Nmm"] >= 1.32 * p["Zx"] * 250.0 / 1.1 * 0.999 or cp["plate_t_mm"] >= 50


def test_base_adapter_keeps_projections_and_bumps_by_failing_row():
    AZ = _az()
    tpl = {"B_mm": 600.0, "L_mm": 700.0, "t_plate_mm": 40.0, "fy_plate_MPa": 240.0, "fixed": False,
           "anchors": {"n_total": 4, "n_tension": 2, "d_mm": 24, "grade": "8.8", "n_per_row": 2, "Anb_mm2": 353.0,
                       "embedment": {"method": "bond", "L_mm": 600.0}}}
    import sections as S
    sp = AZ.adapt_base(tpl, "HB200", "HB300")             # a pinned base keeps its projections
    dB = S.props("HB300")["bf"] - S.props("HB200")["bf"]
    dL = S.props("HB300")["d"] - S.props("HB200")["d"]
    assert sp["B_mm"] >= 600.0 + dB - 1e-9 and sp["L_mm"] >= 700.0 + dL - 1e-9
    assert sp["B_mm"] % 50 == 0 and sp["L_mm"] % 50 == 0
    assert AZ.adapt_base(tpl, "HB300", "HB200") == tpl                 # a smaller column keeps the plate
    b = AZ.bump_base(tpl, ["column base (base-e1): plate_thickness", "column base (base-e1): anchor_tension_10_3_5",
                           "column base (base-e1): anchorage_embedment"])
    assert b["t_plate_mm"] > 40.0 and b["anchors"]["d_mm"] == 30 and b["anchors"]["Anb_mm2"] == 561.0
    assert b["anchors"]["embedment"]["L_mm"] == 700.0           # 600 x 1.1 (default ratio) x 1.05, to 50 mm
    b2 = AZ.bump_base(tpl, [("column base (base-e1): anchorage_embedment", 1.9, False)])
    assert b2["anchors"]["embedment"]["L_mm"] == 1200.0          # 600 x 1.9 x 1.05 = 1197 -> 1200
    assert tpl["t_plate_mm"] == 40.0                                    # the template is not changed in place


def test_fixed_base_on_a_new_column_becomes_a_perimeter_ring_and_steps_up_from_the_failing_rows():
    AZ = _az()
    import sections as S
    tpl = {"B_mm": 1100.0, "L_mm": 1300.0, "t_plate_mm": 100.0, "fy_plate_MPa": 230.0, "fck_MPa": 30.0, "fixed": True,
           "anchors": {"n_total": 16, "n_tension": 8, "d_mm": 48, "grade": "8.8", "f_mm": 460.0, "pitch_mm": 125.0,
                       "edge_mm": 100.0, "n_per_row": 8, "Anb_mm2": 1473.0,
                       "embedment": {"method": "bond", "L_mm": 1500.0}}}
    sp = AZ.adapt_base(tpl, "NPB750X270X202.49", "BOX500X500X14")
    an = sp["anchors"]
    assert sp["layout"] == "ring" and sp["B_mm"] == sp["L_mm"] == 900.0
    assert an["n_total"] == 4 * an["n_per_row"] - 4 and an["pitch_mm"] >= 2.5 * an["d_mm"] - 1e-9   # IS 800 10.2.2
    assert an["edge_mm"] >= 1.7 * (an["d_mm"] + 3) - 1e-9                                             # IS 800 10.2.4.2
    assert an["embedment"] == {"method": "bond", "L_mm": 1500.0} and sp["fck_MPa"] == 30.0
    up = AZ.bump_base(sp, [("column base (base-e3): y:plate_thickness", 2.7, False),
                           ("column base (base-e3): anchorage_embedment", 1.25, False)], col="BOX500X500X14")
    assert up["t_plate_mm"] == 150.0                     # 100 x sqrt(2.7) x 1.03 = 169 -> the largest plate, 150
    assert up["anchors"]["embedment"]["L_mm"] == 2000.0  # 1500 x 1.25 x 1.05 = 1969 -> 2000
    assert S.props("BOX500X500X14")["d"] + 2 * 150.0 <= up["L_mm"]


def test_splice_adapter_resizes_flange_plates_to_the_new_flange():
    AZ = _az()
    import sections as S
    tpl = {"type": "flange_plates", "plate": {"A_mm2": 3600.0, "fy_MPa": 250.0, "t_mm": 12.0},
           "bolts": {"n_bolts": 6, "d_mm": 20, "grade": "8.8", "t_mm": 10.5}}
    sp = AZ.adapt_splice(tpl, "WPB300X300X69.8", "HB250")
    p = S.props("HB250")
    assert sp["plate"]["A_mm2"] == pytest.approx(p["bf"] * 12.0, abs=0.1)
    assert sp["bolts"]["t_mm"] == pytest.approx(min(p["tf"], 12.0), abs=0.01)
    up = AZ.bump_splice(sp, ["column splice: bolts_10_3", "column splice: plate_yield_6_2"])
    assert up["bolts"]["n_bolts"] == 8 and up["plate"]["t_mm"] == 14.0
    assert AZ.adapt_splice({"none": True, "note": "x"}, "HB250", "HB300") == {"none": True, "note": "x"}


# ------------------------------------------------------------------------------------------------ P8 report items
def test_p8_practice_context_and_fire_resistance_boxes_print_in_plain_words():
    import report_second_wave as RS
    cfg = {"practice_context": "An 18-storey office would usually have a reinforced concrete core.",
           "fire_resistance": {"statement": "The FRL is set under IS 800:2007 16.2 by the fire consultant.",
                               "cite": "IS 800:2007 16.1, 16.1.1 and 16.2"}}
    h = RS.context_html(cfg)
    assert "Practice context" in h and "reinforced concrete core" in h
    assert "Fire resistance" in h and "16.2" in h and "16.1.1" in h
    assert RS.context_html({}) == ""
    assert "cfg[" not in h and "_" not in h.replace("chk-h", "")


def test_p8_cladding_basis_is_printed_with_the_wind_limits(monkeypatch):
    import report as R
    import engine3d as E
    ws = {"X": {"storey_drift": [0.001], "top_mm": 40.0, "H_mm": 40000.0, "limit_top_mm": 80.0, "ratio_top": 0.5,
                "limit_storey": 1 / 300.0, "ratio_storey": 0.3,
                "cite": "IS 800:2007 Table 6 (5.6.1): building_wind_brittle -> H/500; storey drift h/300"}}
    monkeypatch.setattr(E, "india_run_cached", lambda cfg: {"wind_serviceability": ws})
    h = R._india_wind_serviceability_html({"cladding_basis": "the facade is treated as brittle cladding: Height/500"})
    assert "Limit basis: the facade is treated as brittle cladding: Height/500" in h
    assert "Limit basis" not in R._india_wind_serviceability_html({})


def test_p8_ex20_style_cfg_selects_the_brittle_row():
    import engine3d as E
    st, top, key = E._wind_limits({"building_type": "office", "cladding_brittle": True})
    assert key == "building_wind_brittle" and top == 500.0 and st == 300.0
    st, top, key = E._wind_limits({"building_type": "office"})
    assert key == "building_wind_elastic" and top == 300.0


# ------------------------------------------------------------------------------------------------ lead request (2026-11)
def test_recorded_values_print_in_words_not_as_a_raw_dict():
    import report_second_wave as RS
    import report_public as P
    assert RS.value_words({"X": 0.002, "Y": 0.002}) == "0.002 (X) and 0.002 (Y)"
    assert RS.value_words([1.5, 2.0, 3]) == "1.5, 2 and 3"
    assert RS.value_words(0.75) == "0.75" and RS.value_words("Type II") == "Type II"
    cfg = {"eor_assumptions": [{"query": "across wind Cfs below the plotted range (x < 2)",
                                "value": {"X": 0.002, "Y": 0.002}, "source": "design engineer: x < 2",
                                "cite": "IS 875 (Part 3):2015 Fig. 10", "verify": True}]}
    h = RS.assumptions_html(cfg, {})
    assert "0.002 (X) and 0.002 (Y)" in h
    assert P.leaks(h, kinds=["raw dict"]) == []


def test_public_text_scan_catches_a_raw_dict_and_ignores_page_style():
    import report_public as P
    bad = "<table><tr><td>across wind Cfs</td><td>{&quot;X&quot;: 0.002, &quot;Y&quot;: 0.002}</td></tr></table>"
    assert P.leaks(bad, kinds=["raw dict"]) == [("raw dict", '{"X": 0.002, "Y": 0.002}')]
    assert P.leaks("<p>{'id': 'e1', 'dc': 0.9}</p>", kinds=["raw dict"])
    ok = ("<style>h1{border-bottom:3px solid #2c5aa0} td{padding:4px}</style><script>window.MathJax={tex:{inlineMath:"
          "[['\\\\(','\\\\)']]}};</script><p>0.002 (X) and 0.002 (Y)</p>")
    assert P.leaks(ok, kinds=["raw dict"]) == []


# ------------------------------------------------------------------------------------------------ sizer fixes 2026-11-01
def test_brace_system_of_a_combined_system_is_the_braced_component():
    AZ = _az()
    assert AZ.brace_system("SMRF+SCBF") == "SCBF"       # section12_checks checks the braces under SCBF, not SMRF
    assert AZ.brace_system("OMF+OCBF") == "OCBF"
    assert AZ.brace_system("SCBF") == "SCBF"


def test_local_member_ratio_governs_over_every_member_check_call_of_an_element(tmp_path):
    """The IS 1893 7.11.2 gravity-column check calls the member check again for the same element: both calls are
    kept, and the local ratio is the governing one (before, the second call replaced the strength check)."""
    AZ = _az()
    import pickle
    mem = {"id": "e9", "tag": 9, "section": "HB200", "grade": "E250 B0", "role": "column", "L_mm": 6000.0,
           "Kz": 1.0, "Ky": 1.0}
    import static_model as SM
    n = len(SM.REC_FIELDS)
    strength = {"1.5DL+1.5WL": [-200e3] + [0.0] * (n - 1)}
    small = {"7.11.2 1.0DL+1.0LL+R.EQ_X": [-50e3] + [0.0] * (n - 1)}
    one = {"member": mem, "kind": "col", "records": small}
    both = {"member": mem, "kind": "col", "records": small,
            "more": [{"member": dict(mem, role_group="gravity_col"), "kind": "col", "records": strength}]}
    out = []
    for cap in (one, both):
        d = tmp_path / ("r%d" % len(out))
        d.mkdir()
        pickle.dump({"elems": {9: cap}, "s12": None}, open(d / "capture.pkl", "wb"))
        lm = AZ.Local(str(d), {9: "g"}, {"g": {"role": "column"}}, {"g": "HB200"}, {}, {})
        out.append(lm.member_dc(9, "HB200", None)[0])
    assert out[1] > out[0] * 2.0


def test_torsion_requirement_stiffens_the_frames_of_the_other_direction():
    """IS 1893 Table 5(i): Delta_max / Delta_ave above 1.2 under Y loading -> the X-direction frames (and the lateral
    columns) keep a larger stiffness from then on; the Y braces are not asked for more."""
    AZ = _az()

    class LM:
        s12 = ("SMRF+SCBF", {"members": [
            {"id": "e1", "tag": 1, "role": "beam", "frame_dir": "X"},
            {"id": "e2", "tag": 2, "role": "column"},
            {"id": "e3", "tag": 3, "role": "brace", "frame_dir": "Y"}]}, {})
        groups_of = {1: "raf", 2: "col", 3: "brace"}
        specs = {"raf": {"role": "beam", "lateral": True}, "col": {"role": "column", "lateral": True},
                 "brace": {"role": "brace", "lateral": True}}
    x = {"raf": ("MB400", None), "col": ("HB300", None), "brace": ("HB150", None)}
    st = {}
    req = AZ.torsion_requirements(LM(), {"torsion_fail": True, "torsion": {"X": 1.05, "Y": 1.25}}, x, st)
    assert sorted(req) == ["col", "raf"]
    f = min(max(0.25 / (AZ.TORSION_TARGET - 1.0), 1.05), 1.6)
    assert req["raf"] == pytest.approx(AZ.stiffness("MB400", "I") * f, rel=1e-6)
    # kept on later passes, also when the torsion check passes
    assert AZ.torsion_requirements(LM(), {"torsion_fail": False, "torsion": {"Y": 1.1}}, x, st) == req


def test_preflight_accepts_the_tube_grade_and_process_for_chs_braces():
    """IN_Ex11 (OCBF, CHS braces): the cfg declares tube_grade / tube_process (IS 1161 YSt 310, HFS), which the
    member grade lookup uses first; brace_grade stays the rolled-brace grade.  Preflight no longer blocks it."""
    import preflight as PF
    base = {"steel_grade": "E250 B0", "system": "OCBF", "braces": True, "brace": "CHS168.3X4.5"}
    ok = PF.chs_brace_grade_declared
    assert not ok(dict(base, brace_grade="E250 B0", brace_process=None))
    assert ok(dict(base, brace_grade="E250 B0", brace_process=None, tube_grade="YSt 310", tube_process="HFS"))
    assert ok(dict(base, brace_grade="YSt 310", brace_process="HFS"))
    assert ok(dict(base, brace="WPB180X180X35.52"))


def test_section_families_box_prints_the_brace_basis():
    import report_second_wave as RS
    cfg = {"section_families": {"statement": "The braces are IS 808 rolled sections in IS 2062 E250 B0, not IS 1161 "
                                             "tubes (IS 800:2007 12.8.2.1; IS 18168:2023 5.2(b)).",
                                "cite": "IS 808:2021; IS 1161:2014 Table 2"}}
    h = RS.context_html(cfg)
    assert "Section families" in h and "12.8.2.1" in h and "5.2(b)" in h and "IS 1161:2014 Table 2" in h
    assert RS.context_html({}) == ""


# ------------------------------------------------------------------------------------------------ P3: frame builder
_FB_SCRIPT = r"""
import sys
sys.path.insert(0, ENGINE_DIR)
import frame_build as FB
spec = {"NX": 3, "NY": 2, "heights_m": [4.0, 4.0], "col": "HB300", "beam": "MB400",
        "gold": {"moment_lines": ML, "xbays": {"1-2": [["Y", 3, 0], ["X", 1, 2]]}}}
g = FB.make_gold(spec)
print(";".join("%d,%d:%s" % (i, j, g["col_strong"](i, j)) for i in range(4) for j in range(3)))
"""


def _fb_orient(ml, seed):
    import subprocess
    src = ("ENGINE_DIR = %r\nML = %r\n" % (ENGINE, ml)) + _FB_SCRIPT
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    out = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return dict(kv.split(":") for kv in out.stdout.strip().splitlines()[-1].split(";"))


def test_frame_build_column_orientation_is_the_same_for_every_hash_seed_and_follows_the_rule():
    """Column orientation rule (frame_build.col_strong): the first DECLARED moment line through the column, else the
    first braced bay that uses it in the order listed, else X.  Before, the moment lines were read from a set, so a
    column on both an X and a Y moment line took whichever the hash seed put first."""
    ml = [["Y", 0], ["X", 0]]
    runs = [_fb_orient(ml, s) for s in (0, 1, 2, 3, 7)]
    assert all(r == runs[0] for r in runs)
    r = runs[0]
    assert r["0,0"] == "Y"                  # on both moment lines: the first declared (Y0) wins
    assert r["1,0"] == "X" and r["0,2"] == "Y"
    assert r["3,1"] == "Y"                  # no moment line: the Y-braced bay at x-line 3 (listed first)
    assert r["2,2"] == "X"                  # the X-braced bay along y-line 2
    assert r["2,1"] == "X"                  # neither: X
    assert _fb_orient([["X", 0], ["Y", 0]], 5)["0,0"] == "X"   # declared the other way round


def test_base_gussets_stay_within_the_outstand_limit_and_add_gussets_past_it():
    """A gusset is an outstanding welded element (IS 800 Table 2, h / t <= 13.6 eps, the engine's
    gusset_outstand_table2 row): stepping the height for bending never goes past it; past it a gusset is added on
    each face.  Before, the height grew without bound at the thickest plate (IN_Ex19 stem: 262 m)."""
    AZ = _az()
    st = {"layout": "cross", "n_per_side": 3, "n_per_side_y": 3, "t_mm": 63.0, "h_mm": 262100.0, "fy_MPa": 230.0,
          "note": "12 gussets 262100 x 63 (IS 2062 E250, fy 230), CJP"}
    out = AZ._step_stiffeners(st, [])
    assert out["h_mm"] <= 13.6 * (250.0 / 230.0) ** 0.5 * 63.0 and "262100" not in out["note"]
    big = AZ._step_stiffeners(dict(st, h_mm=850.0), [("y:gusset_bending", 1.7, False)])
    assert big["h_mm"] == 850.0 and big["n_per_side"] == 4 and big["note"].startswith("16 gussets")
    thin = AZ._step_stiffeners(dict(st, t_mm=25.0, h_mm=350.0), [("gusset_weld_to_plate_10_5_7", 1.19, False)])
    assert thin["t_mm"] == 32.0 and thin["h_mm"] == 350.0


def test_monotone_column_stacks_keep_lower_storeys_at_least_as_stiff():
    """IS 1893 Table 6(i): K_i < K_i+1 is a soft storey.  A lateral column group never ends up less stiff than the
    same columns above it (stacks from the group names: _1_3 / _4_6, _0 / _1, _lo / _hi)."""
    AZ = _az()
    specs = {"fc_1_3": {"role": "column", "lateral": True}, "fc_4_6": {"role": "column", "lateral": True},
             "fc_7_9": {"role": "column", "lateral": True}, "gc_1_3": {"role": "column"},
             "col_lo": {"role": "column", "lateral": True}, "col_hi": {"role": "column", "lateral": True}}
    assert AZ.column_stacks(specs) == {"fc": ["fc_1_3", "fc_4_6", "fc_7_9"], "col": ["col_lo", "col_hi"]}
    x = {"fc_1_3": ("HB300", None), "fc_4_6": ("HB250", None), "fc_7_9": ("HB350", "E350 B0"),
         "gc_1_3": ("HB150", None), "col_lo": ("HB400", None), "col_hi": ("HB300", None)}
    y = AZ.monotone_columns(x, specs, log_fn=lambda *a: None)
    assert y["fc_4_6"] == ("HB350", "E350 B0") and y["fc_1_3"] == ("HB350", "E350 B0")
    assert y["col_lo"] == ("HB400", None) and y["gc_1_3"] == ("HB150", None)


def test_local_member_ratio_uses_the_engines_own_calls_when_captured(tmp_path):
    """The worker records the exact (member, combination forces) of every engine call to member_check_is800 for an
    element; the local check then evaluates those (whatever combination filter the pipeline applies) and ignores
    its own reconstruction from the records."""
    AZ = _az()
    import pickle
    import static_model as SM
    n = len(SM.REC_FIELDS)
    mem = {"id": "e9", "tag": 9, "section": "HB200", "grade": "E250 B0", "role": "column", "L_mm": 6000.0,
           "Kz": 1.0, "Ky": 1.0}
    small = {"c1": [-50e3] + [0.0] * (n - 1)}
    cf_big = [{"combo": "c2", "P_N": 400e3, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0, "My_i_Nmm": 0.0, "My_j_Nmm": 0.0,
               "Vy_N": 0.0, "Vz_N": 0.0}]
    out = []
    for calls in ({}, {9: [{"member": mem, "cf": cf_big}]}):
        d = tmp_path / ("c%d" % len(out))
        d.mkdir()
        pickle.dump({"elems": {9: {"member": mem, "kind": "col", "records": small}}, "s12": None, "calls": calls},
                    open(d / "capture.pkl", "wb"))
        lm = AZ.Local(str(d), {9: "g"}, {"g": {"role": "column"}}, {"g": "HB200"}, {}, {})
        out.append(lm.member_dc(9, "HB200", None)[0])
    assert out[1] > out[0] * 4.0


def test_doubler_grade_follows_the_columns_the_beams_frame_into():
    """Engine checks (2026-11): a panel-zone doubler is checked at its own grade (E250 when none is declared).  The
    sizer declares E350 B0 on a beam_column spec only when every column that the label's beams frame into is E350,
    else E250 B0; a spec without a doubler is left alone."""
    AZ = _az()

    class LM:
        groups_of = {1: "fb", 2: "fc", 3: "gb", 4: "gc", 5: "fc"}
        s12 = (None, {"members": [{"id": "e%d" % t} for t in (1, 2, 3, 4, 5)],
                      "joints": [{"id": "j1", "beams": [{"member_id": "e1"}], "columns": [{"member_id": "e2"},
                                                                                          {"member_id": "e5"}]},
                                 {"id": "j2", "beams": [{"member_id": "e3"}], "columns": [{"member_id": "e2"},
                                                                                          {"member_id": "e4"}]}]})
    x = {"fb": ("WB500", "E250 B0"), "fc": ("BOX450X450X28", "E350 B0"), "gb": ("MB400", "E250 B0"),
         "gc": ("HB300", "E250 B0")}
    conns = {"beam_column": {"WB500": {"doubler_t_mm": 20.0}, "beam:MB400": {"doubler_t_mm": 16.0},
                             "default": {"doubler_t_mm": 12.0}, "WB600": {"doubler_t_mm": 0.0}}}
    AZ.doubler_grades(LM(), x, conns)
    bc = conns["beam_column"]
    assert bc["WB500"]["doubler_grade"] == "E350 B0"            # both columns at its joint are E350
    assert bc["beam:MB400"]["doubler_grade"] == "E250 B0"       # one E250 column at its joint
    assert "doubler_grade" not in bc["default"] and "doubler_grade" not in bc["WB600"]


def test_fin_plate_takes_three_or_four_bolt_lines_only_when_two_do_not_fit():
    """A beam-end shear connection tries one and two bolt lines first; three or four lines (the published IN_Ex19
    collector fins, 4 x 3 M24 in double shear) only when no one- or two-line plate passes."""
    AZ = _az()
    AZ.register("WI550X325X22X14")
    small = AZ.design_fin_plate("WI550X325X22X14", 300e3, {})
    assert small is not None and int(small.get("bolt_lines") or 1) <= 2
    big = AZ.design_fin_plate("WI550X325X22X14", 1730e3, {})
    assert big is not None and int(big.get("bolt_lines") or 1) >= 3
    assert AZ._fin_plate_tier("WI550X325X22X14", 1730e3, 1730e3 / 1.5, {}, "clean_mill_scale", (1, 2), 0.9) is None


def test_ebf_link_takes_the_least_overstrength_within_the_mass_span():
    """EBF links: every brace, beam outside the link, column and base follows the link overstrength 1.1 Ry Vp.  Among
    the passing candidates of the lightest passing one's tier within 1.3 x its mass, the least Vp is taken."""
    AZ = _az()
    spec = {"role": "link", "families": ["MB", "WB", "HB"]}
    zreq = 1.5e6                      # rolled: the lightest passing MB450 (Vp 585 kN) gives way to HB400 (511 kN)

    class LM:
        def group_ok(self, g, lab, grade, margin):
            AZ.register(lab)
            return AZ.props(lab)["Zx"] >= zreq, (0.5, 0.1)
    cands = [(l, gr, t) for (l, gr, t) in AZ.candidates(spec) if t == 0]
    first = next((l, gr) for (l, gr, t) in cands if (AZ.register(l) or True) and AZ.props(l)["Zx"] >= zreq)
    dem = {"N": 0.0, "Mz": 0.0, "My": 0.0}
    got, note = AZ._least_overstrength_link(LM(), "lk", spec, first, dem, {}, set(), None)
    assert AZ.mass_kg_m(got[0]) <= 1.3 * AZ.mass_kg_m(first[0]) + 1e-9
    assert AZ.link_vp(got[0]) < 0.97 * AZ.link_vp(first[0]) and note
    assert AZ.props(got[0])["Zx"] >= zreq and AZ.family_of(got[0]) in ("MB", "WB", "HB")
