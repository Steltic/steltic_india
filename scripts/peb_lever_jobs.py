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
  secondary      the CFS secondary script, its constants, the gold purlin / girt dicts, the non-permanent dead loads
                 (collateral, PV, kN/m2) and the purlin span
  brace          the brace constant (resized by the rod switch only)
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
                      "gold": {"purlin": {"section": "LZ230X75X20X2", "spacing_mm": 1500.0, "sag_rods": 1},
                               "girt": {"section": "LZ230X75X20X2", "spacing_mm": 1800.0, "sag_rods": 2}},
                      "nonpermanent": {"collateral": 0.15}, "span_mm": 7500.0},
        "brace": {"const": "BRACE"},
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
                      "gold": {"purlin": {"section": "LZ250X75X20X3.15", "spacing_mm": 1250.0, "sag_rods": 3},
                               "girt": {"section": "LZ250X75X20X3.15", "spacing_mm": 1500.0, "sag_rods": 3}},
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
                      "gold": {"purlin": {"section": "LZ250X75X20X2.3", "spacing_mm": 1500.0, "sag_rods": 2},
                               "girt": {"section": "LZ250X75X20X2.3", "spacing_mm": 1800.0, "sag_rods": 2}},
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
                      "gold": {"purlin": {"section": "LZ250X75X20X2.55", "spacing_mm": 1500.0, "sag_rods": 3},
                               "girt": {"section": "LZ250X75X20X2.55", "spacing_mm": 1500.0, "sag_rods": 2}},
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
                  "gold": {"purlin": {"section": "LZ230X75X20X2", "spacing_mm": 1500.0, "sag_rods": 1},
                           "girt": {"section": "LZ230X75X20X2", "spacing_mm": 1800.0, "sag_rods": 2}},
                  "nonpermanent": {"collateral": 0.15}, "span_mm": 7500.0},
    "brace": {"const": "BRACE"},
}
