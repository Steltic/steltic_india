"""peb_lever_jobs.py -- PEB-LEVERS (2026-10): the auto-sizer job specs of the four PEB golds (IN_Ex1 ... IN_Ex4) and
the template an engineer copies for their own PEB job.

A job spec tells steel_engine/peb_autosize.py which module-level constants of the job's cfg.py it may resize and how:

  members        {CONST: {'group': 'column' | 'rafter', 'sfrs': True}}  -- welded / tapered section labels (WI / TI)
                 the sizer may change (plates: depths at the ends, flange width and thickness, web thickness)
  links          [['A.D1', 'B.D0'], ...] dimensions kept equal (knee depth of column and rafter, matching depths at an
                 end-plate splice)
  fixed          ['A.D0', ...] dimensions not changed
  fab            fabrication limits: D_min / D_max, bf_min / bf_max (mm), tw_min (the briefs: 4 mm)
  knee_column    the column constant whose top section is the knee column face
  splice_faces   {rafter_splice spec key: [CONST, f]} the section cfg.py builds each end plate from (f = 0 / 1 end)
  base_consts    the column constants whose base section sets the 1.2 Vd shear-key demand
  frame_line     a typical main frame line (sway / lambda_cr predictor); base 'pinned' | 'fixed'
  dado_height_mm brick dado height (the 'H150_with_dado_check' switch)
  seismic        zone, I, the R constants {CONST: 'x' | 'y'} and the frame route ('OMRF' / 'SMRF_IS18168')
  Lr_const       the roof imposed-load constant (market-practice bundle)
  secondary      the CFS secondary script and its constants (the purlin / girt dicts are read from the script),
                 the non-permanent dead loads (collateral, PV, kN/m2) and the purlin span
  brace          the brace constant (resized by the rod switch only)
"""

# second wave: the solar-ready variant of IN_Ex1 uses the wind basis of the IN_Ex5 PV check -- with the PV mass the
# first transverse mode drops below 1.0 Hz and IS 875 (Part 3):2015 9.1 (b) asks for the 10.2 gust-factor along-wind
# load; IN_Ex5's cfg.py applies it (walls of the across-ridge cases and the Y storey force scaled to the 10.2 force).
# The same block is appended to a copy of the IN_Ex1 job for the variant (evidence: IN_Ex5's retrieval_evidence.json,
# a superset of IN_Ex1's).  Names are IN_Ex1's module-level constants.
SOLAR_GUST_APPEND = r"""

# ==================================================================================================================
# PEB-LEVERS solar-ready variant (second wave): IS 875-3 9.1 (b) with the PV mass, as in IN_Ex5's cfg.py.  When the
# first transverse mode is below 1.0 Hz the along-wind frame load is the larger of the 10.2 gust-factor force and the
# static 7.2 force (walls of the across-ridge member cases and the Y storey force); otherwise the static wind stands.
# ==================================================================================================================
if SOLAR_PV > 0.0:
    _lp = cfg["load_plan"]
    _lp["retrieval"] = list(_lp["retrieval"]) + [_ev(k) for k in ("dyn_9_1", "dyn_10_1", "gust_10_2", "beta_T36",
                                                                  "hourly_6_4", "turb_6_5", "across_10_3_scope")]
    _T, _w2, _eX, _eY, _Mt = E.modal(cfg, 3)
    _iy = max(range(len(_T)), key=lambda n: _eY[n]); _ix = max(range(len(_T)), key=lambda n: _eX[n])
    FA_Y, FA_X = 1.0 / _T[_iy], 1.0 / _T[_ix]
    CF_Y = CPE_W0["A"] - CPE_W0["B"]
    BETA = 0.020
    if FA_Y < 1.0:
        AW_Y = WT.along_wind_story_forces([H_EAVE / 1000.0], L_M, CF_Y, FA_Y, TERRAIN, VB, K1, K3, K4, BETA)
        GUST_RATIO = max(1.0, AW_Y["VB_N"] / (F_Y * 1000.0))
        for p_ in _lp["member_wind"]:
            if p_["direction"] == "across_ridge" and GUST_RATIO > 1.0:
                p_["wall_windward_kNm2"] += (GUST_RATIO - 1.0) * CPE_W0["A"] * PD
                p_["wall_leeward_kNm2"] += (GUST_RATIO - 1.0) * CPE_W0["B"] * PD
                p_["gust_factor_basis"] = "walls x %.3f to the IS 875-3 10.2 force (G %.3f, f %.3f Hz)" % (
                    GUST_RATIO, AW_Y["gust"]["G"], FA_Y)
        _lp["story_forces"]["W_Y"] = {"1": [0.0, F_Y * GUST_RATIO * 1000.0, 0.0]}
        _lp["wind_summary"]["gust_factor"] = {
            "G": round(AW_Y["gust"]["G"], 4), "G_y": round(AW_Y["gust"]["G"], 4), "fa_hz": round(FA_Y, 4),
            "fa_y_hz": round(FA_Y, 4), "fa_x_hz": round(FA_X, 4), "beta": BETA,
            "beta_basis": "IS 875-3 Table 36 ii) bolted steel structures 0.020 (as IN_Ex5)",
            "Cf": {"Y": CF_Y}, "Cf_basis": "Table 5 net wall coefficient A - B (as the static 7.2 force)",
            "terrain": TERRAIN, "h_m": H_EAVE / 1000.0, "b_m": L_M,
            "VB_y_kN": round(AW_Y["VB_N"] / 1000.0, 1), "VB_y_static_kN": round(F_Y, 1),
            "applied_W_Y_kN": round(F_Y * GUST_RATIO, 1), "gust_ratio": round(GUST_RATIO, 4),
            "components_y": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in AW_Y["gust"].items()},
            "x_direction": "first X mode %.2f Hz (static 7.2 only when >= 1.0 Hz)" % FA_X,
            "trigger": "PV mass: f1 = %.2f Hz < 1.0 Hz (9.1 (b))" % FA_Y,
            "cite": "IS 875 (Part 3):2015 9.1 (b); 10.1; 10.2; 6.4; 6.5; Table 36 ii)"}
        _lp["wind_summary"]["across_wind"] = {"eor": {
            "value": 0.0,
            "source": "EOR (as IN_Ex5): no across-wind response -- IS 875-3 10.3 covers tall enclosed buildings and "
                      "towers; this is a 10 m low-rise shed",
            "cite": "IS 875 (Part 3):2015 10.3 (scope), 10.4; VERIFY (EOR)"}}
"""

JOB_SPECS = {
    "IN_Ex1_PEB_factory_shed_tapered_Bengaluru": {
        "job": "IN_Ex1_PEB_factory_shed_tapered_Bengaluru",
        "members": {"COL_T": {"group": "column"}, "RAF_T": {"group": "rafter"}, "RAF_P": {"group": "rafter"},
                    "G_RAF": {"group": "rafter", "sfrs": False}, "G_COL": {"group": "column", "sfrs": False},
                    "W_COL": {"group": "column", "sfrs": False}},
        "links": [["COL_T.D1", "RAF_T.D0"], ["RAF_T.D1", "RAF_P.D"]],
        "fab": {"D_min": 200.0, "D_max": 1500.0, "bf_min": 120.0, "bf_max": 400.0, "tw_min": 4.0},
        "knee_column": "COL_T",
        "splice_faces": {"apex": ["RAF_P", 1.0], "rafter_splice": ["RAF_P", 0.0]},
        "base_consts": ["COL_T", "G_COL"],
        "frame_line": 5, "base": "pinned", "dado_height_mm": 3000.0,
        "seismic": {"zone": "II", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "OMRF"},
        "Lr_const": "LR",
        "secondary": {"script": "secondary/secondary_is801.py",
                      "consts": {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"},
                      "nonpermanent": {"collateral": 0.15}, "span_mm": 7500.0},
        "brace": {"const": "BRACE"},
        "solar": {"pv_kNm2": 0.15, "evidence_job": "IN_Ex5_PEB_rooftop_solar_check_Bengaluru",
                  "cfg_append": SOLAR_GUST_APPEND},
    },
    "IN_Ex2_PEB_GradeA_warehouse_multispan_Bhiwandi": {
        "job": "IN_Ex2_PEB_GradeA_warehouse_multispan_Bhiwandi",
        "members": {"COL": {"group": "column"}, "RAF_K": {"group": "rafter"}, "RAF_B": {"group": "rafter"},
                    "RAF_S": {"group": "rafter"}, "CAN_T": {"group": "rafter", "sfrs": False},
                    "G_RAF": {"group": "rafter", "sfrs": False}, "G_COL": {"group": "column", "sfrs": False},
                    "W_COL": {"group": "column", "sfrs": False}},
        "links": [["RAF_K.D1", "RAF_B.D", "RAF_S.D"]],
        "fab": {"D_min": 200.0, "D_max": 1500.0, "bf_min": 120.0, "bf_max": 400.0, "tw_min": 4.0},
        "knee_column": "COL",
        "splice_faces": {"rafter_splice": ["RAF_B", 0.0], "canopy_root": ["CAN_T", 0.0]},
        "base_consts": ["COL"],
        "frame_line": 6, "base": "fixed", "dado_height_mm": 3000.0,
        "seismic": {"zone": "III", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "SMRF_IS18168"},
        "Lr_const": "LR",
        "secondary": {"script": "secondary/secondary_is801.py",
                      "consts": {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"},
                      "nonpermanent": {"collateral": 0.25, "pv": 0.15}, "span_mm": 9000.0},
        "brace": {"const": "BRACE"},
    },
    "IN_Ex3_PEB_crane_shed_10t_Nagpur": {
        "job": "IN_Ex3_PEB_crane_shed_10t_Nagpur",
        "members": {"COL": {"group": "column"}, "RAF_T": {"group": "rafter"}, "RAF_P": {"group": "rafter"},
                    "G_RAF": {"group": "rafter", "sfrs": False}, "G_COL": {"group": "column", "sfrs": False},
                    "W_COL": {"group": "column", "sfrs": False}},
        "links": [["RAF_T.D1", "RAF_P.D"]],
        "fab": {"D_min": 200.0, "D_max": 1500.0, "bf_min": 120.0, "bf_max": 400.0, "tw_min": 4.0},
        "knee_column": "COL",
        "splice_faces": {"apex": ["RAF_P", 1.0], "rafter_splice": ["RAF_P", 0.0]},
        "base_consts": ["COL"],
        "frame_line": 4, "base": "fixed", "dado_height_mm": None,
        "seismic": {"zone": "II", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "OMRF"},
        "Lr_const": "LR",
        "secondary": {"script": "secondary/secondary_is801.py",
                      "consts": {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"},
                      "nonpermanent": {"collateral": 0.10}, "span_mm": 7500.0},
        "brace": {"const": "BRACE"},
    },
    "IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR": {
        "job": "IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR",
        "members": {"COL_T": {"group": "column"}, "RAF_K": {"group": "rafter"}, "RAF_B": {"group": "rafter"},
                    "G_RAF": {"group": "rafter", "sfrs": False}, "G_COL": {"group": "column", "sfrs": False},
                    "W_COL": {"group": "column", "sfrs": False}},
        "links": [["RAF_K.D1", "RAF_B.D"]],
        "fab": {"D_min": 200.0, "D_max": 1500.0, "bf_min": 120.0, "bf_max": 400.0, "tw_min": 4.0},
        "knee_column": "COL_T",
        "splice_faces": {"apex": ["RAF_B", 1.0], "rafter_splice": ["RAF_B", 0.0]},
        "base_consts": ["COL_T"],
        "frame_line": 6, "base": "fixed", "dado_height_mm": 3000.0,
        "seismic": {"zone": "IV", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "SMRF_IS18168"},
        "Lr_const": "LR",
        "secondary": {"script": "secondary/secondary_is801.py",
                      "consts": {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"},
                      "nonpermanent": {"collateral": 0.20}, "span_mm": 7500.0},
        "brace": {"const": "BRACE"},
    },
}

# the template an engineer copies for their own PEB job (fill the names of their cfg.py constants)
TEMPLATE = {
    "job": "<job folder name>",
    "members": {"COL_T": {"group": "column"}, "RAF_T": {"group": "rafter"}, "RAF_P": {"group": "rafter"}},
    "links": [["COL_T.D1", "RAF_T.D0"], ["RAF_T.D1", "RAF_P.D"]],
    "fab": {"D_min": 200.0, "D_max": 1500.0, "bf_min": 120.0, "bf_max": 400.0, "tw_min": 4.0},
    "knee_column": "COL_T",
    "splice_faces": {"apex": ["RAF_P", 1.0], "rafter_splice": ["RAF_P", 0.0]},
    "base_consts": ["COL_T"],
    "frame_line": 1, "base": "pinned", "dado_height_mm": 3000.0,
    "seismic": {"zone": "II", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "OMRF"},
    "Lr_const": "LR",
    "secondary": {"script": "secondary/secondary_is801.py", "consts": {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"},
                  "nonpermanent": {"collateral": 0.15}, "span_mm": 7500.0},
    "brace": {"const": "BRACE"},
}
