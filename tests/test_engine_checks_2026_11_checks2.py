"""Engine checks 2 (2026-11-06, branch fix/2026-11-engine-checks-2): the reviewer's three low items of re-check 3 and
the group strength line found by the MSME re-size of IN_Ex21.

R3-1  the side-wall check of a hand-built pattern compares its (windward, leeward) Cpe with Table 5 directly and with
      the two exchanged (IN_Ex6 writes the reversed wind by exchanging the fields), for the warning and for the angle.
R3-2  the report's Section 12 table reports a not-applicable row (no_seismic) as not applicable, not as 'not evaluated
      (missing inputs block COMPLETE)'.
R3-3  a column piece that runs past a lower roof or a wall step with no node there is judged band by band, so every
      wall area reaches a member once (IN_Ex9's hall column (12, 30) in one piece 0-8 m: -X face 480 m2, was 457.5).
G-1   a member group's strength line shows its worst strength element, not the strength ratio of the element whose
      Table 3 ratio governs the group (IN_Ex21's bottom chord printed 0.19 at e44; e190 / e134 were at 0.734).
"""
import copy
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "steel_engine"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_engine_checks_2026_11_followup3 import _box_cols, _fixture, _noeq_md      # noqa: E402


# ============================================================================================================ R3-1
def _ex6_patterns():
    """IN_Ex6's member_wind_patterns (cfg.py): per axis and Cpi, the wind and its reversal written by exchanging the
    windward / leeward fields (HR-B-12).  pd 0.9256 (its frame pd is immaterial to the implied Cpe)."""
    pd, out = 0.9256, []
    for axis, (ww, wl) in (("X", (0.7, -0.25)), ("Y", (0.7, -0.1))):
        for s in (0.5, -0.5):
            out.append({"name": "WM%s%s" % (axis, "+" if s > 0 else "-"), "wind_axis": axis, "Cpi": s, "pd_kNm2": pd,
                        "wall_windward_kNm2": round((ww - s) * pd, 4), "wall_leeward_kNm2": round((wl - s) * pd, 4)})
            out.append({"name": "WM%sR%s" % (axis, "+" if s > 0 else "-"), "wind_axis": axis, "Cpi": s, "pd_kNm2": pd,
                        "wall_windward_kNm2": round((wl - s) * pd, 4), "wall_leeward_kNm2": round((ww - s) * pd, 4)})
    return out


def test_R3_1_IN_Ex6_reversed_patterns_match_with_the_fields_exchanged():
    """All 8 of IN_Ex6's patterns (its 16 with the two signs) on its plan (18 x 32 m, h 9 m): no warning; theta 0 and
    side Cpe -0.6 along X, theta 90 and -0.5 along Y; a reversed pattern is recorded as exchanged and its members'
    Table 5 surfaces are exchanged with it (the engine's 'windward' face is wall B / D there)."""
    import static_model as SM
    cols = _box_cols(18000.0, 32000.0, 9000.0, 3, 4)
    for pat in _ex6_patterns():
        ax = 0 if pat["wind_axis"] == "X" else 1
        for sg in (1, -1):
            r = SM.side_wall_pressure({}, dict(pat, sign=sg), cols, ax)
            assert r["applied"] and "warning" not in r, (pat["name"], r.get("warning"))
            assert (r["theta_deg"], r["Cpe"]) == ((0, -0.6) if ax == 0 else (90, -0.5)), pat["name"]
            rev = "R" in pat["name"]
            assert r["check"]["pattern_fields_exchanged"] is rev
            ww, wl = SM._wall_zone(pat, r, "windward"), SM._wall_zone(pat, r, "leeward")
            a_, b_ = ("A", "B") if ax == 0 else ("C", "D")
            assert (ww[0], wl[0]) == ((b_, a_) if rev else (a_, b_)), pat["name"]
            assert ww[1] == pytest.approx(-0.25 if ax == 0 else -0.1) if rev else ww[1] == pytest.approx(0.7)


def test_R3_1_the_exchanged_match_also_chooses_the_angle():
    """A pattern along Y on IN_Ex6's plan whose own coefficients are theta 0's exchanged (-0.25 / +0.7): taken
    directly, both angles miss by 0.95 and the plan's order would keep theta 90 (side Cpe -0.5, then a warning, off by
    0.15 exchanged); with the exchanged pair theta 0 matches exactly -- side Cpe -0.6, no warning."""
    import static_model as SM
    pd, cpi = 0.9256, 0.5
    pat = {"name": "W", "wind_axis": "Y", "Cpi": cpi, "pd_kNm2": pd, "wall_windward_kNm2": (-0.25 - cpi) * pd,
           "wall_leeward_kNm2": (0.7 - cpi) * pd}
    r = SM.side_wall_pressure({}, pat, _box_cols(18000.0, 32000.0, 9000.0, 3, 4), 1)
    assert r["theta_deg"] == 0 and r["Cpe"] == -0.6 and "warning" not in r
    assert r["check"]["pattern_fields_exchanged"] is True
    # a pattern that matches neither angle either way still warns (R2-4), and says it tried both
    odd = dict(pat, wall_windward_kNm2=(0.9 - cpi) * pd, wall_leeward_kNm2=(-0.6 - cpi) * pd)
    w = SM.side_wall_pressure({}, odd, _box_cols(18000.0, 32000.0, 9000.0, 3, 4), 1)
    assert w["warning"].startswith("WARN") and "with the two exchanged" in w["warning"]


# ============================================================================================================ R3-2
def _s12_html(rows):
    import report_india as RI
    return RI._is800_s12_detailing({}, {"capacity_design": {"system": "SMF", "R": 5.0, "section12": {"checks": rows}}})


def test_R3_2_report_states_not_applicable_rows_as_such():
    """A no_seismic job's SMF column gate and IS 18168 Table 2 (ii) row (R2-1: not applicable, not open): the report
    reads 'not applicable (no_seismic declared ...)', never '1 not evaluated (missing inputs block COMPLETE)'."""
    import india_is800_s12 as S12
    m, p, md = _noeq_md("W", no_seismic=True)
    gate = next(c for c in S12.column_checks("SMF", md, {}) if c["id"] == "smf_column_class")
    t2 = S12._table2_column_row(m, p, 250.0, md, "IS 18168:2023 5.3")
    h = _s12_html([gate, t2])
    assert "2 checks, 0 failing, 0 not evaluated" in h and "2 not applicable (no_seismic declared" in h
    assert h.count("not applicable (no_seismic declared") >= 3                    # the summary and each row
    assert "1 not evaluated" not in h and "2 not evaluated" not in h


def test_R3_2_report_keeps_not_evaluated_rows_and_its_old_columns():
    """A seismic job's member without an earthquake record stays 'not evaluated' (it blocks COMPLETE), and a table
    with no not-applicable row keeps its columns (no gold report changes)."""
    import india_is800_s12 as S12
    m, p, md = _noeq_md("W")
    gate = next(c for c in S12.column_checks("SMF", md, {}) if c["id"] == "smf_column_class")
    h = _s12_html([gate])
    assert "1 checks, 0 failing, 1 not evaluated (missing inputs block COMPLETE)." in h
    assert "not applicable" not in h


# ============================================================================================================ R3-3
def _scan(fx, ax):
    import static_model as SM
    cols = []
    for c in fx["cols"]:
        c1, c2 = c["c1"], c["c2"]
        cols.append((c, c1, c2, 0.5 * (c1[ax] + c2[ax]), round(0.5 * (c1[1 - ax] + c2[1 - ax]), 3),
                     min(c1[2], c2[2]), max(c1[2], c2[2])))
    env = [tuple(map(tuple, e)) for e in fx["envelope"]]
    sc = SM.wall_wind_pieces(cols, env, ax, 1.0, (("up", 1.0, 1.0), ("down", 1.0, -1.0)),
                             fx["SY"] if ax == 0 else fx["SX"])
    res = SM.envelope_residuals(sc["pieces"], sc["halves"], env, ax)
    tot, by = {}, {}
    for i, (c, c1, c2, face, q, fs, w) in enumerate(sc["pieces"]):
        A = w * abs(c2[2] - c1[2]) + res.get(i, 0.0)
        tot[face] = tot.get(face, 0.0) + A
        by[(c["tag"], face)] = by.get((c["tag"], face), 0.0) + A
    return {k: v / 1e6 for k, v in tot.items()}, {k: v / 1e6 for k, v in by.items()}, sc


def test_R3_3_hall_column_in_one_piece_past_the_lean_to_roof():
    """The reviewer's variant of IN_Ex9: the hall column (12, 30) in one piece 0-8 m, no node at the lean-to roof
    (5 m).  At its mid-height (4 m) it stands behind the lean-to wall, so the hall wall above the lean-to in its strip
    (7.5 x 3 = 22.5 m2) was on no member: -X face 457.5 m2.  Judged band by band it carries that band, and its
    re-entrant share below 5 m (3.75 x 5 = 18.75 m2) as before: 480 m2.  The along-ridge faces stay 288 m2."""
    fx = copy.deepcopy(_fixture("IN_Ex9_wall_wind_geometry.json"))
    c18 = next(c for c in fx["cols"] if c["tag"] == 18)
    fx["cols"] = [c for c in fx["cols"] if c["tag"] not in (18, 19)] + [dict(c18, c2=[12000.0, 30000.0, 8000.0])]
    tot, by, sc = _scan(fx, 0)
    assert tot["up"] == pytest.approx(480.0, abs=1e-6) and tot["down"] == pytest.approx(480.0, abs=1e-6)
    assert by[(18, "up")] == pytest.approx(22.5 + 18.75, abs=1e-6)
    hb = sc["record"]["height_bands"]
    assert len(hb) == 1 and hb[0]["tag"] == 18 and hb[0]["face"] == "up" and hb[0]["area_m2"] == pytest.approx(22.5)
    assert [(b["z_mm"], b["exposure"], b["width_mm"]) for b in hb[0]["bands"]] == [
        ([0.0, 5000.0], "not first", 0.0), ([5000.0, 8000.0], "wall", 7500.0)]
    assert hb[0]["area_at_mid_height_m2"] == 0.0
    tot_y, _, sc_y = _scan(fx, 1)
    assert tot_y["up"] == pytest.approx(288.0, abs=0.01) and tot_y["down"] == pytest.approx(288.0, abs=0.01)
    assert sc_y["record"]["height_bands"] == []


def _lean_to_3m():
    """IN_Ex9 with a 3 m lean-to: lean-to columns 0-3 m, hall columns at x = 12 m (y <= 30 m) split at 3 m."""
    fx = copy.deepcopy(_fixture("IN_Ex9_wall_wind_geometry.json"))
    for c in fx["cols"]:
        if c["c1"][0] == 0.0:
            c["c2"][2] = 3000.0
        elif c["c1"][0] == 12000.0 and c["c1"][1] <= 30000.0:
            if c["c1"][2] == 0.0:
                c["c2"][2] = 3000.0
            else:
                c["c1"][2] = 3000.0
    return fx


def test_R3_3_the_other_way_a_piece_exposed_at_mid_height_but_not_below_the_lean_to():
    """A 3 m lean-to and the hall column (12, 15) in one piece 0-8 m: at its mid-height (4 m) it is the first element
    of its strip, so it took its 7.5 m strip over all 8 m (60 m2), 22.5 m2 of it behind the lean-to wall that the
    lean-to's columns already carry.  Banded: 37.5 m2 (3-8 m).  And the hall column (12, 37.5), one piece 0-8 m, sees
    the step beside it only below 3 m: its re-entrant share (3.75 x 3 = 11.25 m2) reaches the corner column (12, 30)
    0-3 m, which no mid-height judgement gave it (before: 468.75 m2 with the hall column split at 3 m, 491.25 with
    (12, 15) in one piece).  -X face: 480 m2 (30 x 3 + 30 x 5 + 30 x 8)."""
    fx = _lean_to_3m()
    tot0, by0, sc0 = _scan(fx, 0)
    # with nodes at 3 m only (12, 37.5) is banded -- for the step beside it, its own area unchanged
    assert tot0["up"] == pytest.approx(480.0, abs=1e-6) and by0[(18, "up")] == pytest.approx(11.25)
    assert [(b["tag"], b["area_m2"], b["area_at_mid_height_m2"]) for b in sc0["record"]["height_bands"]] == [
        (21, 60.0, 60.0)]
    c10 = next(c for c in fx["cols"] if c["tag"] == 10)
    fx["cols"] = [c for c in fx["cols"] if c["tag"] not in (10, 11)] + [dict(c10, c2=[12000.0, 15000.0, 8000.0])]
    tot, by, sc = _scan(fx, 0)
    assert tot["up"] == pytest.approx(480.0, abs=1e-6) and tot["down"] == pytest.approx(480.0, abs=1e-6)
    hb = {b["tag"]: b for b in sc["record"]["height_bands"]}
    assert hb[10]["area_m2"] == pytest.approx(37.5) and hb[10]["area_at_mid_height_m2"] == pytest.approx(60.0)
    assert by[(10, "up")] == pytest.approx(37.5)
    assert hb[21]["area_m2"] == pytest.approx(60.0) and by[(18, "up")] == pytest.approx(11.25)
    assert any(s["tag"] == 18 and s.get("overlap_mm") == 3000.0 for s in sc["record"]["stepped_facade"])


def test_R3_3_the_fixture_with_its_nodes_is_unchanged():
    """IN_Ex9 as modelled (a node where the lean-to roof meets the hall columns): no piece is banded, 480 / 288 m2."""
    fx = _fixture("IN_Ex9_wall_wind_geometry.json")
    for ax, a in ((0, 480.0), (1, 288.0)):
        tot, _, sc = _scan(fx, ax)
        assert tot["up"] == pytest.approx(a, abs=0.01) and tot["down"] == pytest.approx(a, abs=0.01)
        assert sc["record"]["height_bands"] == []


# ============================================================================================================= G-1
def _chord(eid, L, records):
    import india_is800 as I8
    import sections as S
    S.register_double_angle("2ISA65X65X6", "ISA65X65X6", 8.0)
    m = {"id": "e%d" % eid, "section": "2ISA65X65X6", "grade": "E250", "L_mm": L, "Kz": 0.85, "Ky": 1.0,
         "role": "beam", "LLT_sag_mm": L, "LLT_hog_mm": L, "truss_chord": True}
    z = dict(Mz_i_Nmm=0.0, Mz_j_Nmm=0.0, Mz_mid_Nmm=0.0, My_i_Nmm=0.0, My_j_Nmm=0.0, Vy_N=0.0, Vz_N=0.0)
    return I8.member_check_is800(m, [dict(z, combo=c, P_N=P) for c, P in records])


def test_G1_group_strength_line_is_the_worst_strength_element():
    """IN_Ex21's bottom chord in small: e44 (a long panel next to the knee, a little gravity compression) governs the
    group by its Table 3 ratio (row (i), KL/r over 180) at a strength ratio of a few per cent; e190 (a short panel)
    carries the wind-uplift compression.  The group's strength line, the headline and the Chapter 6 table give e190's
    ratio and combination, the Table 3 line e44's; the group D/C is unchanged."""
    import design_pipeline as DP
    import report_second_wave as RS
    res = {44: _chord(44, 3500.0, [("1.5DL+1.5LL", 5e3), ("0.9DL+1.5W_Y", -20e3)]),
           190: _chord(190, 1546.0, [("1.5DL+1.5LL", -30e3), ("0.9DL+1.5W_Y", 150e3)])}
    r44, r190 = res[44], res[190]
    assert r44["governing_check"] == "IS 800 Table 3 slenderness" and r44["dc"] > r190["dc"]
    assert r190["interaction_dc"] > r44["interaction_dc"] and r190["governing_check"].startswith("IS 800 9.3")
    rows0 = DP.group_table3_row(DP._check_rows(r44), [44, 190], res, 44)
    assert rows0[0]["dc"] == pytest.approx(r44["interaction_dc"])                # before: e44's strength ratio
    rows, wst = DP.group_check_rows(r44, [44, 190], res, 44)                      # what design_india writes
    s = rows[0]
    assert s["dc"] == pytest.approx(r190["interaction_dc"]) and s["element"] == 190 and s["combo"] == "0.9DL+1.5W_Y"
    assert "element e190, combination 0.9DL+1.5W_Y; the largest in the group" in s["name"] and s["governing"] is False
    assert s["clause"] == r190["clause"] and s["ok"] is True
    t3 = [r for r in rows if r["name"].startswith("IS 800 Table 3")]
    assert len(t3) == 1 and t3[0]["dc"] == pytest.approx(r44["dc"]) and "-- governing" in t3[0]["name"]
    assert max(r["dc"] for r in rows) == pytest.approx(r44["dc"])                # the group D/C is unchanged
    assert wst["strength_worst"]["element"] == "e190" and wst["strength_worst"]["combination"] == "0.9DL+1.5W_Y"
    assert wst["strength_worst"]["dc"] == pytest.approx(r190["interaction_dc"], abs=1e-4)
    assert wst["table3_worst"]["element"] == "e44" and wst["table3_worst"]["limit"] == 180
    # what prints it: the headline (and its sentence), the Chapter 6 table, the 7.6.4 lateral scan
    m = {"id": "truss_bottom_chord-2ISA65X65X6", "inputs": {"section": "2ISA65X65X6", "governing_combo": "x"},
         "checks": rows, "DC": r44["dc"]}
    h = RS.headline({"members": [m]})
    assert h["strength"]["dc"] == pytest.approx(round(r190["interaction_dc"], 4)) and h["strength"]["element"] == "e190"
    assert h["strength"]["check"] == "IS 800 9.3 interaction / member resistance"
    assert h["strength"]["combination"] == "0.9DL+1.5W_Y"
    assert "element e190" in RS.headline_sentence(h)
    assert RS.member_cells(m)[0] == RS._f(r190["interaction_dc"])
    assert DP._strength_dc(m) == pytest.approx(r190["interaction_dc"])


def test_G1_group_strength_line_kept_when_the_governing_element_is_the_worst():
    """When the D/C-governing element also has the largest strength ratio, the line is the governing element's own."""
    import design_pipeline as DP
    res = {1: _chord(1, 1546.0, [("1.5DL+1.5LL", 150e3)]), 2: _chord(2, 1546.0, [("1.5DL+1.5LL", 100e3)])}
    rows, wst = DP.group_check_rows(res[1], [1, 2], res, 1)
    assert rows == DP.group_table3_row(DP._check_rows(res[1]), [1, 2], res, 1)
    assert wst["strength_worst"]["element"] == "e1" and "element" not in rows[0]


def test_G1_PEB_station_with_the_worst_strength_names_its_station():
    """A tapered (PEB) element is governed by its D/C over {element, station i, station j}; its strength line takes
    the station with the largest strength ratio, which can be another station than the governing one."""
    import design_pipeline as DP
    res = {7: {"found": True, "dc": 0.9, "interaction_dc": 0.5, "governing_check": "IS 800 Table 3 slenderness",
               "clause": "IS 800:2007 9.3", "station_governs": "element (mid-depth section)",
               "table3_slenderness": {"dc": 0.9, "value": 162.0, "limit": 180, "governing_combo": "1.5DL+1.5LL"},
               "strength_worst": {"where": "station j (WI600X200X8X10)", "section": "WI600X200X8X10",
                                  "interaction_dc": 0.82, "interaction_governing_combo": "1.5DL+1.5WMX+",
                                  "interaction_cite": "IS 800:2007 9.3.2.2", "clause": "IS 800:2007 9.3"}}}
    rows, wst = DP.group_check_rows(res[7], [7], res, 7)
    assert rows[0]["dc"] == pytest.approx(0.82) and "e7, station j (WI600X200X8X10), combination 1.5DL+1.5WMX+" in \
        rows[0]["name"]
    assert wst["strength_worst"]["where"] == "station j (WI600X200X8X10)"
    assert max(r["dc"] for r in rows) == pytest.approx(0.9)


def test_G1_PEB_station_checks_record_the_worst_strength_station():
    """design_pipeline.peb_station_checks on a real element (NPB400 at mid-depth, stations WPB200 / NPB400, 6 m,
    Table 3 governs at the mid-depth section and at station j alike, 0.833): the element's D/C comes from the mid-depth
    check (strength 0.664 there), and its worst strength station is j (0.671, the end moment of 1.5DL+1.5LL taken as
    uniform) -- the group line names that station."""
    import design_pipeline as DP
    import static_model as SM
    f = {k: i for i, k in enumerate(SM.REC_FIELDS)}

    def rec(N, Mi, Mj):
        r = [0.0] * len(SM.REC_FIELDS)
        r[f["N"]], r[f["Mmaj"]], r[f["Mmaj_i"]], r[f["Mmaj_j"]] = N, max(abs(Mi), abs(Mj)), Mi, Mj
        r[f["V"]] = r[f["Vmaj"]] = 1e3
        return r
    recs = {"1.5DL+1.5LL": rec(-200e3, 20e6, -60e6), "1.5DL+1.5WMX+": rec(-50e3, 10e6, -100e6)}
    mem = {"id": "e5", "section": "NPB400X180X57.38", "grade": "E250", "role": "column", "L_mm": 6000.0, "Kz": 1.0,
           "Ky": 1.0, "LLT_sag_mm": 1500.0, "LLT_hog_mm": 1500.0}
    el = DP.member_checks_is800({}, {"member": mem, "kind": "col", "records": recs})
    res = DP.peb_station_checks({}, mem, "col", recs, el, ("WPB200X200X61.3", "NPB400X180X57.38"))
    assert res["station_governs"] == "element (mid-depth section)"
    assert res["governing_check"] == "IS 800 Table 3 slenderness"
    sw = res["strength_worst"]
    assert sw["where"] == "station j (NPB400X180X57.38)" and sw["interaction_governing_combo"] == "1.5DL+1.5LL"
    assert sw["interaction_dc"] == pytest.approx(max(s["interaction_dc"] for s in res["stations"]))
    assert sw["interaction_dc"] > res["interaction_dc"]
    rows, wst = DP.group_check_rows(res, [5], {5: res}, 5)
    assert rows[0]["dc"] == pytest.approx(sw["interaction_dc"]) and "e5, station j (NPB400X180X57.38)" in rows[0]["name"]
    assert wst["strength_worst"]["where"] == "station j (NPB400X180X57.38)"
    assert max(r["dc"] for r in rows) == pytest.approx(res["dc"])
