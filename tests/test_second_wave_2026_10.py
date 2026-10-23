"""Second wave (2026-10) report-only fixes from the industry-alignment review of the published India examples.

H1  headline = worst strength ratio; slenderness printed beside it with its limit (Ex9's 0.865 was a KL/r ratio)
H2  item 12: soil basis + next softer soil; bare-frame Ta with the infilled-frame Ta of 7.6.2(c); gust factor G
H3  item 9: composite deck floors designed as bare steel; full-bay deck span as a point for the design engineer
H4  item 14: capability-demonstration titles for Ex9, Ex10, Ex12 (+ units), Ex19 (+ stem)
H5  item 13: cost-of-compliance and strengthening-option sections from the job folder files
H6  item 16: citation style; ROADMAP note on the next IS 800
H7  Ex9: the ridge is tied to the diaphragm along the span only
H8  leftovers: design-engineer assumptions, snow record, Section 12 units, 7.11.2 wording, Table 7 minimum, names
"""
import json
import os

import pytest

import _ex1_fixture  # noqa: F401  (puts steel_engine on sys.path)


def _chk(name, value, limit, dc, clause="IS 800:2007 7.1.2, 8.2, 8.4, 9.3; Table 2/3/10", combo=None):
    c = {"name": name, "value": value, "limit": limit, "dc": dc, "ok": dc <= 1.0, "clause": clause}
    if combo:
        c["combo"] = combo
    return c


def _ex9_like_pkg():
    """Ex9 as published: the brace's member D/C 0.865 is its Table 3 KL/r ratio; the roof girder's 0.810 is strength."""
    return {"members": [
        {"id": "brace-WPB140X140X24.66", "inputs": {"section": "WPB140X140X24.66", "governing_combo": "1.5DL-1.5W_Y"},
         "DC": 0.86536, "checks": [
             _chk("IS 800 9.3 interaction / member resistance (governing combination 1.2DL+1.2LL+1.2SL+1.2WM90-R)",
                  0.161, 1.0, 0.161),
             _chk("IS 800 Table 3 slenderness KL/r (combination 1.5DL-1.5W_Y) -- governing", 155.765, 180, 0.86536,
                  clause="IS 800:2007 3.8 / Table 3")]},
        {"id": "roof-NPB600X220X154.47", "inputs": {"section": "NPB600X220X154.47", "governing_combo": "1.5DL+1.5LL+1.5SL"},
         "DC": 0.80971, "checks": [
             _chk("IS 800 9.3 interaction / member resistance (governing combination 1.5DL+1.5LL+1.5SL)", 0.80971, 1.0,
                  0.80971),
             _chk("IS 800 Table 3 slenderness KL/r", 66.4, 300, 0.221, clause="IS 800:2007 3.8 / Table 3")]}],
        "capacity_design": {"section12": {"checks": [
            {"id": "brace_KL_r", "value": 155.765, "limit": 160, "dc": 0.9735, "ok": True, "member": "brace-WPB140X140X24.66",
             "clause": "IS 800:2007 12.8.2.2"},
            {"id": "is18168_table2_beam", "value": {"b/tf": 4.67, "d/tw": 37.47}, "limit": {"b/tf": 7.76, "d/tw": 38.38},
             "dc": 0.9761, "ok": True, "member": "roof-NPB600X220X154.47", "clause": "IS 18168:2023 Table 2 / 5.3"},
            {"id": "12.11.2.3_panel_zone", "value": 0.91, "limit": 1.0, "dc": 0.9098, "ok": True, "member": "j1",
             "clause": "IS 800:2007 12.11.2.3"}]}},
        "connections": [{"id": "conn-lateral_col-BOX450X400X25", "type": "column splice / base", "DC": 0.897}],
        "drift_table": [{"storey": 1, "dir": "X", "drift": 0.0003, "limit": 0.004, "dc": 0.07, "ok": True}],
        "design_status": {"status": "complete", "n_reasons": 0, "reasons": [], "authority": "a", "warnings": []}}


# ------------------------------------------------------------------------------------------------ H1
def test_headline_is_the_worst_strength_ratio_not_the_slenderness():
    import report_second_wave as RS
    h = RS.headline(_ex9_like_pkg())
    assert h["strength"]["dc"] == pytest.approx(0.8097, abs=1e-4)
    assert h["strength"]["member"] == "roof-NPB600X220X154.47"
    assert h["strength"]["combination"] == "1.5DL+1.5LL+1.5SL"
    sl = h["slenderness"]
    assert sl["member"] == "brace-WPB140X140X24.66" and sl["KL_r"] == pytest.approx(155.8, abs=0.05)
    assert sl["limit"] == 180 and sl["ratio"] == pytest.approx(0.8654, abs=1e-4)
    assert h["member_dc_max"]["dc"] == pytest.approx(0.8654, abs=1e-4)      # the old single 'member D/C'
    s12 = h["section12"]
    assert s12["slenderness"]["check"] == "brace_KL_r" and s12["slenderness"]["dc"] == pytest.approx(0.9735)
    assert s12["detailing"]["check"] == "is18168_table2_beam"
    assert s12["strength"]["check"] == "12.11.2.3_panel_zone"
    assert h["connections"]["dc"] == pytest.approx(0.897) and h["drift"]["dc"] == pytest.approx(0.07)


def test_member_without_checks_falls_back_to_its_dc():
    import report_second_wave as RS
    st, _, sl, _ = RS.member_ratios({"id": "m", "DC": 0.5, "checks": []})
    assert st == 0.5 and sl is None


def test_status_block_and_member_table_print_both_ratios():
    import report_india as RI
    pkg = _ex9_like_pkg()
    sb = RI._status_block(pkg)
    assert "Headline:" in sb and "worst member strength ratio 0.810" in sb
    assert "KL/r 155.8 against the IS 800 Table 3 limit of 180" in sb and "Governing ratios" in sb
    assert sb.index("0.810") < sb.index("155.8")                          # strength first
    mt = RI._members(pkg)
    assert "strength ratio" in mt and "KL/r / limit (ratio)" in mt
    assert "155.8 / 180 (0.865)" in mt and "0.161" in mt


def test_headline_json_written(tmp_path):
    import report_second_wave as RS
    RS.write_headline(str(tmp_path), _ex9_like_pkg())
    h = json.load(open(tmp_path / "design" / "headline.json"))
    assert h["strength"]["member"] == "roof-NPB600X220X154.47" and h["slenderness"]["limit"] == 180


# ------------------------------------------------------------------------------------------------ H2
def _ss(**kw):
    ss = {"Z": 0.16, "I": 1.2, "R": 5.0, "soil": "II", "zone": "III", "Ta_x_s": 1.1302, "Ta_y_s": 1.1302,
          "Ta_formula": "0.085 h^0.75 (IS 1893 7.6.2(a), bare steel MRF)"}
    ss.update(kw)
    return {"load_plan": {"seismic_summary": ss}, "clad": 0.5}


def test_soil_basis_and_next_softer_type():
    import report_second_wave as RS
    n = RS.base_shear_notes(_ss(), dims={})
    s = n["soil"]
    assert s["type"] == "II" and s["next"] == "III" and "confirm by site investigation" in s["basis"]
    assert "medium soil assumed" in s["basis"]
    for r in s["rows"]:                                    # beyond the plateau: 1.67/T against 1.36/T
        assert r["VB_ratio"] == pytest.approx(1.67 / 1.36, rel=1e-3)
    flat = RS.base_shear_notes(_ss(Ta_x_s=0.423, Ta_y_s=0.473, Ta_formula="0.09 h/sqrt(d) (7.6.2(c))"), dims={})
    assert all(r["VB_ratio"] == pytest.approx(1.0) for r in flat["soil"]["rows"])   # on the plateau: no change
    assert RS.base_shear_notes(_ss(soil="III"), dims={})["soil"]["next"] is None
    assert RS.base_shear_notes(dict(_ss(), soil_basis="Type II per geotechnical report GR-12"),
                               dims={})["soil"]["basis"] == "Type II per geotechnical report GR-12"


def test_bare_frame_ta_states_the_facade_and_the_infilled_ta():
    """Ex16 (h 31.5 m, d 30 m): 7.6.2(c) Ta 0.518 s puts Sa/g on the plateau, V_B x 2.08 (review: x 2.1)."""
    import report_second_wave as RS
    n = RS.base_shear_notes(_ss(), dims={"X": 30.0, "Y": 30.0})
    assert [r["dir"] for r in n["ta"]] == ["X", "Y"]
    r = n["ta"][0]
    assert r["h_m"] == pytest.approx(31.5, abs=0.05)
    assert r["Ta_infill_s"] == pytest.approx(0.09 * 31.5 / 30.0 ** 0.5, rel=2e-3)
    assert r["Sa_g_infill"] == 2.5 and r["VB_ratio"] == pytest.approx(2.5 / (1.36 / 1.1302), rel=1e-3)
    h = RS.base_shear_html(_ss(), dims={"X": 30.0, "Y": 30.0})
    assert "masonry infill" in h and "7.6.2(c)" in h and "&times; 2.08" in h and "not stiffening the frame" in h


def test_ta_formula_by_direction():
    import report_second_wave as RS
    f = RS._formula_by_dir("X: 0.085 h^0.75 (7.6.2(a)); Y: 0.09 h/sqrt(d) (7.6.2(c)); h = 8.0 m eave")
    assert RS._bare_frame(f["X"])[0] and not RS._bare_frame(f["Y"])[0]
    f = RS._formula_by_dir("Y (OMRF): 0.085 h^0.75 (7.6.2(a)); X (OCBF): 0.09 h/sqrt(d) (7.6.2(c)); h = 10.75 m mean roof")
    assert RS._bare_frame(f["Y"])[0] and not RS._bare_frame(f["X"])[0]
    f = RS._formula_by_dir("0.085 h^0.75 (IS 1893 7.6.2(a), bare steel MRF; h = mean roof height 8.6 m)")
    assert RS._bare_frame(f["X"])[0] and RS._bare_frame(f["Y"])[0]
    braced = RS.base_shear_notes(_ss(Ta_formula="0.09 h/sqrt(d) (IS 1893 7.6.2(c), all other buildings)"),
                                 dims={"X": 30.0, "Y": 30.0})
    assert braced["ta"] == []


def test_facade_basis_with_a_brick_dado():
    import report_second_wave as RS
    cfg = {"delegated_design": [{"item": "230 mm brick dado wall to 3.0 m on the plinth beam"}]}
    assert "brick dado" in RS.facade_basis(cfg)
    assert RS.facade_basis({"facade_basis": "glazed curtain wall"}) == "glazed curtain wall"


def test_gust_factor_and_method_printed():
    import report_second_wave as RS
    ws = {"gust_factor": {"G": 2.932, "G_x": 2.932, "G_y": 2.7899, "fa_x_hz": 0.5995, "beta": 0.01,
                          "Cf": {"X": 1.213, "Y": 1.335}, "VB_x_kN": 1883.1, "components_x": [1, 2]},
          "method": "dynamic (10.2 gust factor) both directions: f1 < 1 Hz (9.1(b))"}
    h = RS.gust_factor_html({"load_plan": {"wind_summary": ws}})
    assert "gust factor G (10.2)" in h and "2.932" in h and "Table 36" in h and "10.2 gust factor" in h
    assert "1,883.1<" in h and "X 1.213 / Y 1.335" in h
    assert "components_x" not in h
    h2 = RS.gust_factor_html({"load_plan": {"wind_summary": {"method": "10.2 gust factor where f1 < 1 Hz (9.1(b))"}}})
    assert "9.1(b)" in h2
    assert RS.gust_factor_html({"load_plan": {"wind_summary": {"k1": 1.0}}}) == ""


def test_wind_base_shear_row_on_a_wind_governed_job():
    import report_india as RI
    cfg = {"load_plan": {"seismic_summary": {"VB_x_kN": 35.5, "VB_y_kN": 35.5},
                         "wind_summary": {"VB_x_kN": 171.4, "VB_y_kN": 223.5}}}
    h = RI._governing(cfg)
    assert "171.4" in h and "223.5" in h and "wind (1.5 WL)" in h


def test_across_wind_not_required_wording():
    import report_second_wave as RS
    ws = {"across_wind": {"required": False, "result": "NOT REQUIRED -- IS 875-3 9.1: h/b = 2.32 < 5 and f >= 1.0 Hz"}}
    t = RS.across_wind_text(ws, "no numeric Mc")
    assert t.startswith("not required: IS 875-3 9.1") and "NOT EVALUATED" not in t
    assert RS.across_wind_text({}, "no numeric Mc") == "NOT EVALUATED: no numeric Mc"


# ------------------------------------------------------------------------------------------------ H3
def _deck_cfg(**kw):
    c = {"floor_system": "one-way composite metal deck", "deck_span": "X", "SX": 7500.0, "SY": 7500.0,
         "composite_scope": "bare_steel",
         "construction_stage": {"cite": "unshored wet concrete + 0.75 kN/m2; compression flange unrestrained"}}
    c.update(kw)
    return c


def test_deck_layout_full_bay_and_secondaries():
    import report_second_wave as RS
    d = RS.deck_layout(_deck_cfg())
    assert d["composite"] and d["full_bay"] and d["span_m"] == 7.5
    d = RS.deck_layout(_deck_cfg(construction_stage={"cite": "flange restrained by the secondary beams at 3.0 m"}))
    assert not d["full_bay"] and d["span_m"] == 3.0
    d = RS.deck_layout(_deck_cfg(construction_stage={"cite": "restrained only at the secondary beams (2.83 m)"}))
    assert d["span_m"] == 2.83
    d = RS.deck_layout(_deck_cfg(delegated_design=[{"item": "composite metal deck + concrete topping, one-way on the "
                                                            "2.5 m secondary beams"}]))
    assert d["span_m"] == 2.5
    d = RS.deck_layout(_deck_cfg(deck={"secondary_spacing_mm": 2500.0}))
    assert d["span_m"] == 2.5 and d["basis"] == "cfg['deck'] secondary_spacing_mm"
    assert RS.deck_layout({"floor_system": "one-way metal roof deck on purlins"})["composite"] is False


def test_full_bay_deck_is_a_non_blocking_point():
    import consistency as CC
    w = CC.package_warnings(_deck_cfg(), {})
    assert any(x.startswith("deck span:") and "7.5 m" in x for x in w)
    w2 = CC.package_warnings(_deck_cfg(construction_stage={"cite": "secondary beams at 3.0 m"}), {})
    assert not any(x.startswith("deck span:") for x in w2)


def test_composite_scope_statement():
    import report_second_wave as RS
    pkg = {"composite_design": {"chI_worksheet": {"slots": [
        {"component": "construction_stage", "DC": 0.872, "detail": {"LLT_mm": 6000.0, "section": "NPB450X190X67.16",
                                                                    "combo": "1.5Dwet+1.5Lconst"}}]}}}
    h = RS.composite_scope_html(_deck_cfg(), pkg)
    for t in ("bare steel", "IS 11384", "shear connectors", "fire protection", "Deck span 7.50 m", "0.872",
              "deck supplier"):
        assert t in h, t
    assert RS.composite_scope_html({"floor_system": "one-way purlins + profiled metal sheeting"}, {}) == ""


# ------------------------------------------------------------------------------------------------ H4
def test_capability_framing():
    import report_second_wave as RS
    for job in ("IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla", "IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore",
                "IN_Ex12_SMF_3levels_Zplan_school_Chandigarh", "IN_Ex19_EBF_12levels_Tplan_Guwahati"):
        fr = RS.framing_for(job)
        assert "capability demonstration" in fr["title"] and fr["practice"]
    assert "unit B" in RS.framing_for("IN_Ex12_SMF_3levels_Zplan_school_Chandigarh/unitB_link")["title"]
    assert "unit C" in RS.framing_for("IN_Ex12_SMF_3levels_Zplan_school_Chandigarh/unitC_gym")["title"]
    assert "stem" in RS.framing_for("IN_Ex19_EBF_12levels_Tplan_Guwahati/units/stem")["title"]
    assert RS.framing_for("IN_Ex13_SCBF_5levels_Delhi") is None
    h = RS.framing_html("IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla")
    assert "not typical Indian practice" in h and "unchanged" in h
    t = RS.titles()
    assert len(t) == 7 and all(set(v) == {"title", "blurb"} for v in t.values())
    assert RS.framing_for("X", {"report_framing": {"title": "T", "what": "w", "practice": "p"}})["title"] == "T"


# ------------------------------------------------------------------------------------------------ H5
COMPLIANCE = {
    "title": "Cost of compliance: this design beside an ordinary-frame (R = 3) design",
    "basis": "The same shed re-sized as an ordinary moment frame with R = 3 and no IS 18168 detailing.",
    "rows": [{"variant": "As designed: SMRF, R = 5, IS 18168", "R": 5.0, "steel_t": 140.2, "kg_m2": 63.8,
              "worst_strength_dc": 0.89, "governing": "knee column / 9.3", "status": "COMPLETE",
              "code_status": "compliant"},
             {"variant": "Ordinary frame, R = 3, no IS 18168", "R": 3.0, "steel_t": 112.0, "kg_m2": 51.0,
              "worst_strength_dc": 0.95, "governing": "rafter / 9.3", "status": "COMPLETE",
              "code_status": "not permitted in Zone IV (IS 1893 Table 9 Note 1); shown only as the cost of compliance"}],
    "difference": {"kg_m2": 12.8, "percent": 25.1},
    "source": "steltic_india feat/2026-10-peb-variations abc1234, peb_lever_study.py, 2026-10-24"}
STRENGTHEN = {
    "title": "Strengthening option: IN_Ex1 strengthened for 0.15 kN/m2 of panels", "pv_kNm2": 0.15,
    "basis": "Knee columns and rafters re-sized for the panels.", "status": "COMPLETE", "worst_strength_dc": 0.97,
    "changes": [{"item": "knee column (frame lines 2-7)", "from": "WI956X250X14X6", "to": "WI956X250X16X6",
                 "added_kg": 420.0}],
    "added_steel_t": 2.6, "added_kg_m2": 1.2, "source": "variations study"}


def test_cost_of_compliance_section(tmp_path):
    import report_second_wave as RS
    assert RS.compliance_html(str(tmp_path)) == ""
    (tmp_path / "compliance_comparison.json").write_text(json.dumps(COMPLIANCE))
    h = RS.compliance_html(str(tmp_path))
    for t in ("Cost of compliance", "Ordinary frame, R = 3", "63.8", "51.0", "not permitted in Zone IV",
              "12.8 kg/m²", "25.1 %", "peb_lever_study.py", "re-sized as an ordinary"):
        assert t in h, t
    (tmp_path / "compliance_comparison.json").write_text("{broken")
    assert "could not be read" in RS.compliance_html(str(tmp_path))


def test_strengthening_option_in_the_pv_section(tmp_path):
    import report_first_wave as FW
    import report_second_wave as RS
    d = tmp_path / "design"
    d.mkdir()
    (d / "pv_capacity.json").write_text(json.dumps({"capacity_kNm2": 0.02, "first_failure_kNm2": 0.03}))
    (tmp_path / "strengthening_option.json").write_text(json.dumps(STRENGTHEN))
    pv = FW.pv_check_section({}, str(tmp_path))
    so = RS.strengthening_html(str(tmp_path))
    assert pv and "Strengthening option: IN_Ex1" in so
    for t in ("knee column (frame lines 2-7)", "WI956X250X16X6", "420", "2.60 t (1.20 kg/m²)", "0.970"):
        assert t in so, t


# ------------------------------------------------------------------------------------------------ H6
def test_codes_table_citations():
    import report_india as RI
    h = RI._codes_table({}, {})
    assert "IS 875 (Part 1):1987" in h and "IS 2062 (Part 1):2025" in h and "(Part 4):2021" in h
    assert "(Part 1):2026" not in h and "IS 18168" not in h
    pkg = {"capacity_design": {"section12": {"checks": [{"id": "is18168_table2_beam", "ok": True}]}}}
    assert "IS 18168:2023" in RI._codes_table({}, pkg)


def test_citation_normalisation():
    import report_second_wave as RS
    t = RS.normalise_citations("IS 875 (Part 1):2026 / Part 2:1987; Snow (IS 875 Part 4:2021); IS 875-3 6.3.4; "
                               "IS 2062:2025; IS 875 Parts 2 and 4; IS 875 Parts 1-5; IS 1893 Part 1")
    assert t == ("IS 875 (Part 1):1987 / (Part 2):1987; Snow (IS 875 (Part 4):2021); IS 875 (Part 3) 6.3.4; "
                 "IS 2062 (Part 1):2025; IS 875 (Parts 2 and 4); IS 875 (Parts 1 to 5); IS 1893 (Part 1)")
    assert RS.normalise_citations("IS 875 (Part 3):2015") == "IS 875 (Part 3):2015"
    h = RS.tidy_html("<a href='IS 875-3.html'>IS 875-3 Table 5 by the EOR</a>")
    assert h == "<a href='IS 875-3.html'>IS 875 (Part 3) Table 5 by the design engineer</a>"


def test_readme_roadmap_note():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    txt = open(os.path.join(here, "README.md"), encoding="utf-8").read()
    assert "Roadmap" in txt and "fourth revision of IS 800" in txt and "CED 7" in txt


# ------------------------------------------------------------------------------------------------ H7
def test_ridge_restraint_line():
    import report_second_wave as RS
    cfg = {"roof_planes": [{"axis": "X", "ridge_sec": "WPB180X180X35.52"}],
           "secondary_members": [{"id": "roof purlin (IS 808 channel MC)", "section": "MC200", "spacing_mm": 1500.0}]}
    h = RS.ridge_restraint_html(cfg, {})
    assert "along the span (X) only" in h and "across the span (Y)" in h and "WPB180X180X35.52" in h
    assert "roof-plane bracing" in h and "MC200 at 1.5 m" in h
    assert RS.ridge_restraint_html(cfg, {"peb": {"members": {}}}) == ""
    assert RS.ridge_restraint_html({}, {}) == ""


# ------------------------------------------------------------------------------------------------ H8
def test_design_engineer_assumptions_printed():
    import report_second_wave as RS
    cfg = {"eor_assumptions": [{"item": "topography: site geometry for k3", "value": "ridge crest, slope > 17 deg",
                                "source": "EOR site assumption (no survey)", "cite": "IS 875-3 6.3.3.1", "verify": True}],
           "load_plan": {"retrieval": [{"query": "Indore basic wind speed Annex A", "found": False, "verify": True,
                                        "value": 39.0, "source": "EOR: Fig. 1 map reading"}]}}
    h = RS.assumptions_html(cfg)
    assert "topography" in h and "design engineer site assumption" in h and "IS 875 (Part 3) 6.3.3.1" in h
    assert "Indore basic wind speed" in h and "EOR" not in h


def test_snow_record_printed():
    import report_second_wave as RS
    sn = {"s0_kNm2": 1.3604, "zone_Z": 1.0, "zone_source": "IS 875-4:2021 Fig. 1 (corpus transcription: Shimla Z = 1)",
          "altitude_m": 2200.0, "mu_roof": 0.8, "s_roof_kNm2": 1.0883,
          "drift": {"mu1": 0.8, "mu2": 4.0, "l3_m": 6.0, "s_wall_kNm2": 5.44, "s_uniform_kNm2": 1.09}}
    h = RS.snow_html({"load_plan": {"snow_summary": sn}})
    for t in ("snow zone Z", "Shimla Z = 1", "1.360", "2,200", "4.00", "5.44"):
        assert t in h, t


def test_section12_values_in_report_units():
    import report_second_wave as RS
    assert RS.s12_value("brace_compression", 50210.1) == "50.2 kN"
    assert RS.s12_value("connection_moment", 1287360000.0) == "1,287.4 kN·m"
    assert RS.s12_value("is18168_table2_beam", {"b/tf": 4.67, "d/tw": 37.47}) == "b/tf 4.67, d/tw 37.47"
    assert RS.s12_value("12.11.3.2_SCWB", 1.398) == "1.398"
    assert RS.s12_value("11.3_link_length", 900.0) == "900 mm"
    assert RS.s12_value("material_E250B", "E250 B0") == "E250 B0"


def test_deformation_compatibility_says_why_nothing_is_checked():
    import report_india as RI
    pkg = {"deformation_compatibility": {"clause": "IS 1893 7.11.2", "zone": "IV", "checks": [],
                                         "note": "every column belongs to a lateral-load-resisting line"}}
    h = RI._serviceability({"heights": [3000.0], "load_plan": {}}, pkg, {})
    assert "every column belongs to a lateral-load-resisting line" in h and "in this zone" not in h


def test_seismic_table_per_direction_and_table7():
    import report_india as RI
    ss = {"Z": 0.24, "I": 1.0, "R": 4.5, "R_x": 5.0, "R_y": 4.5, "soil": "II", "zone": "IV", "Sa_g_x": 2.5,
          "Sa_g_y": 2.5, "Ah_x": 0.06, "Ah_y": 0.0667, "rho_min": 0.016,
          "Ta_formula": "X: 0.085 h^0.75 (7.6.2(a)); Y: 0.09 h/sqrt(d) (7.6.2(c))"}
    h = RI._seismic_table({"load_plan": {"seismic_summary": ss}, "heights": [5000.0]}, {}, {})
    assert "R, X (Table 9)" in h and "R, Y (Table 9)" in h and "Ah X" in h
    assert "Table 7" in h and "the minimum does not govern" in h and "7.6.2(a)" in h


def test_system_names():
    import report_second_wave as RS
    n = RS.system_names("SMRF+SCBF")
    assert "IS 1893 Table 9 (i)(d)" in n and "SMF (IS 800 12.11)" in n and "SCBF (IS 800 12.8)" in n
    assert "EBF (IS 800 12.9" in RS.system_names("EBF")
    assert RS.system_names("OMRF+OCBF").count("IS 1893 Table 9") == 2


def test_new_report_text_has_no_us_residue():
    import india_contract_residue as CR
    import report_second_wave as RS
    import report_india as RI
    frags = [RS.headline_html(_ex9_like_pkg()), RI._status_block(_ex9_like_pkg()),
             RS.base_shear_html(_ss(), dims={"X": 30.0, "Y": 30.0}),
             RS.composite_scope_html(_deck_cfg(), {}), RS.framing_html("IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla"),
             RS.ridge_restraint_html({"roof_planes": [{"axis": "X", "ridge_sec": "R"}]}, {}),
             RS.gust_factor_html({"load_plan": {"wind_summary": {"gust_factor": {"G": 2.9, "beta": 0.01}}}})]
    for k in RS.FRAMING.values():
        frags.append(k["title"] + " " + k["blurb"])
    for f in frags:
        assert f and CR.residue_hits(f) == [], (CR.residue_hits(f), f[:200])


def test_flexible_run_on_a_regular_plan_says_why():
    import report_india as RI
    pkg = {"seismic_analysis": {"flexible_diaphragm": {"status": "not run", "error": "x", "cite": "Table 5(ii) text",
                                                       "trigger": "cfg['flexible_diaphragm_analysis'] = True"}},
           "irregularity": {"reentrant": {"irregular": False}}}
    h = RI._seismic_table({"load_plan": {}, "heights": [8000.0]}, pkg, {})
    assert "Why this run was made" in h and "declared in the job" in h and "does not require it here" in h


def test_effective_lengths_and_ridge_height_printed():
    import report_second_wave as RS
    m = {"governing_element_result": {"capacities": {"compression": {"axes": {"z": {"KL_mm": 12369.3},
                                                                               "y": {"KL_mm": 3000.0}}}}}}
    assert RS.kl_cell(m) == "12.37 / 3.00" and RS.kl_cell({}) == "—"
    cfg = {"roof_planes": [{"eave_z_mm": 8000.0, "ridge_z_mm": 11000.0}]}
    assert RS.height_text(cfg, 8000.0) == "8.00 m to the eave, 11.00 m to the ridge"
    assert RS.height_text({}, 31500.0) == "31.50 m"


def test_identical_directions_give_one_ta_note():
    import report_second_wave as RS
    h = RS.base_shear_html(_ss(), dims={"X": 30.0, "Y": 30.0})
    assert "Ta, X and Y direction" in h and h.count("7.6.2(c) would apply") == 1
    h2 = RS.base_shear_html(_ss(), dims={"X": 36.0, "Y": 27.0})
    assert h2.count("7.6.2(c) would apply") == 2
