"""IS 18168:2023 precedence (HR-INTEGRATE): numbers read from the licensed PDF (pdf p. 3, 7, 10, 11, 14, 15, 21)
and the stricter-governs rule against IS 800:2007 Section 12."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steel_engine"))

import india_is18168 as I18  # noqa: E402
import india_is800_s12 as S12
import india_combos as IC


def test_constants_from_pdf():
    assert I18.OMEGA == {"SCBF": 2.5, "EBF": 2.5, "SMRF": 3.0}                      # 5.5 (pdf p. 7)
    assert I18.gamma_LL(3.0) == 0.25 and I18.gamma_LL(4.0) == 0.50                   # 5.5
    assert I18.RY == {"E250": 1.4, "E275": 1.4, "E300": 1.3, "E350": 1.2}            # Table 1
    assert I18.COLUMN_KLR_LIMIT == 75 and I18.BRACE_KLR_LIMIT == 160                  # 7.2 / 10.2
    assert I18.SCWB_MIN == 1.4 and I18.LINK_ROTATION_LIMIT == 0.08                    # 8.2 / 12.3.3.1
    assert I18.LINK_LENGTH_FACTOR == 1.6 and I18.SH == {"I": 1.25, "box": 1.4}        # 11.3 / 12.3.2.2


def test_applicability_zones():
    assert I18.applies("SCBF", "IV")["mandatory"] is True
    assert I18.applies("SMF", "III")["applies"] is True
    assert I18.applies("SCBF", "II")["applies"] is False                              # 1.2 optional in Zone II
    assert I18.applies("SCBF", "II", opt_in=True)["applies"] is True
    assert I18.applies("OCBF", "IV")["applies"] is False                              # 1.3 not covered


def test_zone_v_and_smrf_height_gate():
    assert I18.system_gate("SCBF", "V")["ok"] is False                                # 1.3: EBF only in Zone V
    assert I18.system_gate("EBF", "V")["ok"] is True
    assert I18.system_gate("SMRF", "IV", 31.5)["ok"] is False                         # 9 x 3.5 m = 31.5 m > 15 m
    assert I18.system_gate("SMRF", "IV", 12.0)["ok"] is True
    assert I18.system_gate("SMRF", "III", 31.5)["ok"] is True                         # limit only in IV / V
    assert I18.system_gate("SMRF", "IV")["ok"] is None                                # height missing -> blocks


def test_stricter_governs_helper():
    assert I18.stricter(1.2, 1.4, kind="min") == 1.4                                  # SCWB
    assert I18.stricter(180, 75, kind="max") == 75                                    # column KL/r
    assert I18.stricter(160, 160, kind="max") == 160


def test_combos_smrf_zone_iv_get_omega_3_rows():
    plan = {"story_forces": {"EQ_X": {"1": [1000.0, 0, 0]}, "EQ_Y": {"1": [0, 1000.0, 0]}},
            "seismic_summary": {"zone": "IV", "Z": 0.24, "R": 5.0, "I": 1.2, "system": "SMF"}}
    cfg = {"system": "SMF", "seis": {"R": 5.0, "zone": "IV"}, "heights": [3500.0], "SX": 7500.0, "SY": 7500.0,
           "NX": 1, "NY": 1, "load_plan": plan, "notional_loads": False}
    combos = IC.expand_combinations(plan, cfg, method="ESM")
    om = [c for c in combos if c.get("fE") is not None and abs(abs(c["fE"]) - 3.0) < 1e-9]
    assert om and all("is18168_5_5" in c["tags"] and "col_only" in c["tags"] for c in om)
    assert {c["fD"] for c in om} == {1.2, 0.9}
    assert any("1.2DL+0.5LL+3EQ_X" in c["label"] for c in om)
    # the IS 800 12.2.3 rows (2.5) are still present
    assert any(abs(abs(c.get("fE") or 0) - 2.5) < 1e-9 and "is800_12_2_3" in c["tags"] for c in combos)
    assert not IC.validate_combinations(combos, cfg, plan)
    # SCBF Zone IV: Omega 2.5 = 12.2.3 -> the 12.2.3 rows carry both cites and sfrs_beam
    cfg2 = dict(cfg, system="SCBF")
    plan2 = dict(plan, seismic_summary=dict(plan["seismic_summary"], system="SCBF", R=4.5))
    c2 = IC.expand_combinations(plan2, cfg2, method="ESM")
    r = [c for c in c2 if "is800_12_2_3" in c["tags"]]
    assert r and all("is18168_5_5" in c["tags"] and "sfrs_beam" in c["tags"] for c in r)
    assert "IS 18168:2023 5.5" in r[0]["cite"]
    assert not any(abs(abs(c.get("fE") or 0) - 3.0) < 1e-9 for c in c2)


def test_scwb_is18168_1p4_with_ry_and_roof_exemption():
    md = {"members": [
        {"id": "c1", "role": "column", "section": "WPB400X400X191.11", "grade": "E250 B0", "L_mm": 3500.0,
         "node_i": 1, "node_j": 2, "major_axis_plane": "X"},
        {"id": "c2", "role": "column", "section": "WPB400X400X191.11", "grade": "E250 B0", "L_mm": 3500.0,
         "node_i": 2, "node_j": 3, "major_axis_plane": "X"},
        {"id": "b1", "role": "beam", "section": "NPB550X210X92.08", "grade": "E250 B0", "L_mm": 7500.0}],
        "forces": {"c1": [{"combo": "x", "P_N": 1.0e6}], "c2": [{"combo": "x", "P_N": 0.5e6}]}}
    joint = {"id": "J2-X", "frame_dir": "X", "columns": [{"member_id": "c1", "position": "below"},
                                                          {"member_id": "c2", "position": "above"}],
             "beams": [{"member_id": "b1"}]}
    r800 = S12.scwb_joint(joint, md)
    r18 = S12.scwb_joint_is18168(joint, md, {"zone": "IV"})
    assert r18["limit"] == 1.4 and r800["limit"] == 1.2
    assert r18["value"] < r800["value"]            # 1.1 Ry (1.54) on the beams and (1 - Pu/Pd) on the columns
    assert all(t["Ry"] == 1.4 for t in r18["beams"])
    roof = dict(joint, columns=[{"member_id": "c1", "position": "below"}])
    assert S12.scwb_joint_is18168(roof, md, {"zone": "IV"})["ok"] is True   # 8.2.1 roof exemption


def test_column_klr_75_and_brace_klr_strict():
    col = {"id": "c1", "role": "column", "section": "MB300", "grade": "E250 B0", "L_mm": 6000.0, "sfrs": True}
    md = {"members": [col], "forces": {"c1": [{"combo": "x", "P_N": 1.0e5}]}, "combos_12_2_3_present": True,
          "combos_is18168_5_5_present": True}
    r = S12.section12_checks("SCBF", md, {"zone": "IV", "brace_config": "X"})
    ids = {c["id"]: c for c in r["checks"]}
    assert ids["is18168_7_2_column_KL_r"]["limit"] == 75 and ids["is18168_7_2_column_KL_r"]["ok"] is False   # 6000/28.4 > 75
    assert ids["is18168_5_5_combinations"]["ok"] is True
    r2 = S12.section12_checks("SCBF", md, {"zone": "II", "brace_config": "X"})
    assert "is18168_7_2_column_KL_r" not in {c["id"] for c in r2["checks"]}


def test_zone_v_scbf_blocked_live():
    r = S12.section12_checks("SCBF", {"members": [], "combos_12_2_3_present": True}, {"zone": "V", "brace_config": "X"})
    g = next(c for c in r["checks"] if c["id"] == "is18168_1_3_system")
    assert g["ok"] is False and r["blocks_complete"]
