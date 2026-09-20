#!/usr/bin/env python3
"""IN_Ex1 — 5-storey office SCBF New Delhi. Live India RAG → load_plan → pipeline."""
from __future__ import annotations
import copy, json, math, os, sys, traceback
from pathlib import Path

JOB = Path(__file__).resolve().parent
NAME = "IN_Ex1_SCBF_5levels_Delhi"
REPO = next(p for p in JOB.parents if (p / "steel_engine").is_dir())
sys.path.insert(0, str(REPO / "steel_engine"))
os.chdir(REPO)
os.environ.setdefault("STEEL_BUILDER_JOBS", os.environ.get("STELTIC_TEST_JOBS", str(REPO / "jobs")))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import india_units as IU
import engine3d as E
import example_build as EB
import pipeline
import consistency
import india_is800 as I8
import sections as S

# ---------------------------------------------------------------------------
# Geometry (metres → N-mm via apply_si_geometry)
# ---------------------------------------------------------------------------
H_STOREY_M = 3.6
N_STOREYS = 5
NX, NY = 5, 4          # bays
BAY_M = 6.0
H_M = H_STOREY_M * N_STOREYS  # 18 m

# ---------------------------------------------------------------------------
# LIVE RAG-backed load numbers (see rag/ + retrieval[] below)
# ---------------------------------------------------------------------------
# IS 875 Part 2 Table 1 — office rooms UDL 2.5 kN/m² (retrieved)
L_FLOOR = 2.5
# IS 875 Part 2 Table 2 — flat roof, access not provided (maintenance only): 0.75 kN/m²
L_ROOF = 0.75
# Brief cladding 0.5 kN/m²; IS 875 Part 1 plaster 13 mm on concrete 0.25 kN/m² (retrieved)
CLAD = 0.5
# Dead load assembly — RAG-backed IS 875 Part 1:2026 Table 1 unit weights +
# project thicknesses for composite metal-deck office (documented in gravity_summary).
# RCC with 1% steel: 22.75–24.20 kN/m³ → use mid 23.5 kN/m³ (retrieved).
# Floor: 100 mm avg concrete fill @ 23.5 = 2.35; plaster ceiling 13 mm = 0.25;
# mortar screed 10 mm = 0.21; clay floor tiles ~0.15 (0.10–0.20) → 2.96 ≈ 3.0 kN/m².
# Roof: 100 mm fill 2.35 + screed 0.21 + plaster soffit 0.25 → 2.81 ≈ 2.8 kN/m².
# Services/MEP ~0.2–0.5 not tabulated in Part 1 → NOT added (honest gap).
D_FLOOR = 3.0   # kN/m² RAG assembly (was 3.5 ASSUMED)
D_ROOF = 2.8    # kN/m² RAG assembly (was 3.0 ASSUMED)

# IS 875 Part 3 Annex A — Delhi Vb = 47 m/s
VB_WIND = 47.0
# Table 1 — k1 risk coefficient: general buildings, 50 yr, Vb=47 → k1=1.0 (retrieved)
K1 = 1.0
# Terrain Category 3 (Delhi urban office — buildings/structures up to 10 m) §6.3.2.1
# Table 2 k2 at z=18 m: Cat 3 interpolate 15 m→0.97, 20 m→1.01 → k2=0.994
K2 = 0.994
# k3 = 1.0 for flat site (6.3.3.1 slope < 3°) — retrieved
K3 = 1.0
# k4 = 1.0 (Delhi inland — not cyclonic east-coast / Gujarat per §6.3.4)
K4 = 1.0
# Table 5 walls rectangular clad: h/w~0.6–0.75 (½ < h/w ≤ 3/2), l/w~1–1.25
# → Cpe windward A ≈ +0.7, leeward B ≈ −0.5 (first readable Table 5 rows; OCR noisy but signs/magnitudes consistent)
CPE_W = 0.7
CPE_L = -0.5
# §7.3.2.1 Cpi = ±0.2 (openings ≤5%); cancels for overall building shear (opposite walls)
CPI = 0.2
# §7.2.1 Kd = 0.9 for buildings; Ka Table 4 OCR garbled → use Ka=1.0 (conservative upper bound)
KD = 0.9
KA = 0.923  # IS 875 P3 Table 4 RAG: A=6×3.6=21.6 m² → interp 0.923 (was 1.0 OCR conservative)
KC = 1.0  # external-only net wall force
WIND_FORCES_AVAILABLE = True

# IS 1893 Annex E — Delhi Zone IV, Z = 0.24
Z = 0.24
# Table 8 / 6.4.2 — I = 1.0 for "the rest" / all other buildings (ordinary office)
I_IMP = 1.0
# Table 9 — Buildings with special braced frame (SBF) having concentric braces: R = 4.5
R = 4.5
# §7.6.2(c) All other buildings (SCBF ≠ bare MRF): Ta = 0.09 h / √d
# Plan: Lx=30 m (5×6), Ly=24 m (4×6); use direction-specific Ta, governing ELF uses max Ta
# (both <0.55 s → Sa/g=2.5 identical; report both)
DX_M = NX * BAY_M  # 30
DY_M = NY * BAY_M  # 24
Ta_x = 0.09 * H_M / (DX_M ** 0.5)
Ta_y = 0.09 * H_M / (DY_M ** 0.5)
Ta = max(Ta_x, Ta_y)  # governing for single Ah (Y: shorter base → longer Ta)
# Medium / stiff soil (brief) — Soil Type II; Sa/g for T≤0.55s: 2.5; T>0.55: 1.36/T (§6.4.2)
if Ta <= 0.55:
    Sa_g = 2.5
else:
    Sa_g = 1.36 / Ta
# 6.4.2 Ah = (Z/2) * (Sa/g) / (R/I)  = (Z/2)*(I/R)*(Sa/g)
Ah = (Z / 2.0) * (I_IMP / R) * Sa_g
# Table 7 Zone IV minimum ρ = 1.6% → Ah_min = 0.016
Ah = max(Ah, 0.016)

# Drift limit 7.11.1.1 — 0.004 h (india_seismic CLAUSES + RAG)
DRIFT_LIMIT = 0.004

# IS 2062 Table 3 — E250 Quality A: fy = 250 MPa (t ≤ 16 mm)
FY = 250.0
FU = 410.0

# IS 800 Table 4 (retrieved factors)
# DL+LL+CL → 1.5, 1.5
# DL+WL/EL → 1.5 (0.9), 1.5
# DL+LL+CL+WL/EL → 1.2, 1.2, … (EL taken as 1.2 when leading; accompanying WL 0.6 noted)

def perimeter_scbf_braces(k, NX, NY):
    """Perimeter SCBF both directions — every perimeter bay, every storey."""
    out = []
    for i in range(NX):
        out.append(("X", i, 0))
        out.append(("X", i, NY))
    for j in range(NY):
        out.append(("Y", 0, j))
        out.append(("Y", NX, j))
    return out


def col_sec(i, j, k, perim):
    # k is 1-based storey of column top
    if k <= 2:
        return "WPB300X300X100.85" if perim else "WPB300X300X88.34"
    if k <= 4:
        return "WPB300X300X88.34" if perim else "WPB300X300X69.8"
    return "HB300" if perim else "MB300"


def beam_sec(i, j, k, dirn):
    if k == N_STOREYS:
        return "NPB400X180X57.38"
    return "NPB450X190X67.16"


def col_strong(i, j, NX, NY):
    # Perimeter frames: strong axis in frame plane
    if i in (0, NX) and j not in (0, NY):
        return "Y"   # N-S frames on east/west
    if j in (0, NY) and i not in (0, NX):
        return "X"   # E-W frames on south/north
    # corners: assign to drift-critical (both) — use X
    if i in (0, NX) or j in (0, NY):
        return "X" if j in (0, NY) else "Y"
    return "Y"


def releases(i, j, k, dirn):
    # Interior gravity framing pinned; perimeter beams continuous into braced frames
    perim_x = (j in (0, NY))  # beam on N/S face
    perim_y = (i in (0, NX))
    if dirn == "X":
        if perim_x:
            return ("none", "none")  # rigid in braced frame line
        return ("both", "none")      # pinned gravity
    else:
        if perim_y:
            return ("none", "none")
        return ("both", "none")


def estimate_seismic_weights():
    """Floor seismic weights in kN (DL + partition allowance + clad + 25% LL office)."""
    area = (NX * BAY_M) * (NY * BAY_M)  # 720 m²
    perim = 2 * (NX * BAY_M + NY * BAY_M)  # 108 m
    # IS 1893 7.3.6 partitions ≥ 0.5 kN/m² on floors (not roof)
    W = []
    for k in range(1, N_STOREYS + 1):
        roof = k == N_STOREYS
        d = D_ROOF if roof else D_FLOOR
        if not roof:
            d += 0.5  # partitions
        # LL seismic fraction: office LL=2.5 ≤ 3 → typically 25% (Table 10 not fully retrieved;
        # 7.3 imposed-load participation — using 25% with note)
        ll_seis = 0.0 if roof else 0.25 * L_FLOOR
        # cladding tributary: full storey on floors, half at roof (matches engine)
        th = H_STOREY_M if not roof else H_STOREY_M / 2.0
        w_clad = CLAD * perim * th
        w = (d + ll_seis) * area + w_clad
        W.append(w)
    return W


def story_forces_kN(VB_kN, W):
    """Qi = Wi hi² / Σ Wj hj² * VB  (IS 1893 7.6.3)."""
    hs = [H_STOREY_M * k for k in range(1, N_STOREYS + 1)]
    denom = sum(W[i] * hs[i] ** 2 for i in range(N_STOREYS))
    Qi = [VB_kN * (W[i] * hs[i] ** 2) / denom for i in range(N_STOREYS)]
    return hs, Qi


def kN_to_N_lateral_X(Qi):
    """Story map 1..n → (fx, fy, mz) in Newtons."""
    return {str(k): [Qi[k - 1] * 1000.0, 0.0, 0.0] for k in range(1, N_STOREYS + 1)}


def kN_to_N_lateral_Y(Qi):
    return {str(k): [0.0, Qi[k - 1] * 1000.0, 0.0] for k in range(1, N_STOREYS + 1)}


def wind_story_forces_kN():
    """IS 875 Part 3 — net wall pressure story forces (kN) for X and Y.
    Vz=Vb·k1·k2·k3·k4; pz=0.6 Vz²; pd=Kd·Ka·Kc·pz ≥ 0.7 pz;
    net Cp = Cpe_w − Cpe_l (Cpi cancels for overall shear).
    Story force = net_Cp · pd · B · h_trib.
    """
    Vz = VB_WIND * K1 * K2 * K3 * K4
    pz = 0.6 * Vz * Vz          # N/m²
    pd = max(KD * KA * KC * pz, 0.70 * pz)  # N/m²
    net_Cp = CPE_W - CPE_L      # 0.7 - (-0.5) = 1.2
    # projected widths: wind // X hits Ly face; wind // Y hits Lx face
    Bx, By = DY_M, DX_M         # 24 m, 30 m
    Qi_x, Qi_y = [], []
    for k in range(1, N_STOREYS + 1):
        roof = k == N_STOREYS
        h_trib = H_STOREY_M / 2.0 if roof else H_STOREY_M
        # N → kN: /1000
        Qi_x.append(net_Cp * pd * Bx * h_trib / 1000.0)
        Qi_y.append(net_Cp * pd * By * h_trib / 1000.0)
    return {
        "Vz": Vz, "pz_Npm2": pz, "pd_Npm2": pd, "net_Cp": net_Cp,
        "Qi_x_kN": Qi_x, "Qi_y_kN": Qi_y,
        "VB_x_kN": sum(Qi_x), "VB_y_kN": sum(Qi_y),
    }


def build_retrieval():
    return [
        {"stem": "IS_875_Part_1_2026", "query": "Cement Concrete Reinforced unit weight Table 1 1 percent steel",
         "found": True,
         "cite": "IS 875 (Part 1):2026 Table 1 Sl No. 24 — Cement Concrete, Reinforced with 1% steel: 22.75–24.20 kN/m³ (use mid 23.5)",
         "collection": "engineering_standards_IS875_P1"},
        {"stem": "IS_875_Part_1_2026", "query": "cement plaster screed floor tiles finishes unit weight",
         "found": True,
         "cite": "IS 875 (Part 1):2026 Table 1 — plaster on concrete 13 mm 0.25 kN/m²; mortar screeding 10 mm 0.21 kN/m²; clay floor tiles 0.10–0.20 kN/m²",
         "collection": "engineering_standards_IS875_P1"},
        {"stem": "IS_875_Part_2_1987", "query": "office rooms imposed floor load Table 1",
         "found": True, "cite": "IS 875 (Part 2):1987 Table 1 — Office rooms and OPD rooms UDL 2.5 kN/m²",
         "collection": "engineering_standards_IS875_P2"},
        {"stem": "IS_875_Part_2_1987", "query": "imposed loads on roofs Table 2 access not provided",
         "found": True, "cite": "IS 875 (Part 2):1987 Table 2 — flat roof, access not provided except maintenance: 0.75 kN/m²",
         "collection": "engineering_standards_IS875_P2"},
        {"stem": "IS_875_Part_3_2015", "query": "basic wind speed Delhi Annex A",
         "found": True, "cite": "IS 875 (Part 3):2015 Annex A (Clause 6.2) — Delhi Vb = 47 m/s",
         "collection": "engineering_standards_IS875_P3"},
        {"stem": "IS_875_Part_3_2015", "query": "design wind speed Vz = Vb k1 k2 k3 k4",
         "found": True, "cite": "IS 875 (Part 3):2015 §6.3 — Vz = Vb·k1·k2·k3·k4; §6.3.3.1 k3=1.0 for slope≤3°",
         "collection": "engineering_standards_IS875_P3"},
        {"stem": "IS_875_Part_3_2015", "query": "Table 1 Risk Coefficient k1 general buildings 50 years",
         "found": True,
         "cite": "IS 875 (Part 3):2015 Table 1 — All general buildings, 50 yr design life, Vb=47: k1=1.0",
         "collection": "engineering_standards_IS875_P3"},
        {"stem": "IS_875_Part_3_2015", "query": "Table 2 Terrain and Height Multiplier k2 Category 3",
         "found": True,
         "cite": "IS 875 (Part 3):2015 Table 2 — Terrain Cat 3: k2(15 m)=0.97, k2(20 m)=1.01 → k2(18 m)=0.994",
         "collection": "engineering_standards_IS875_P3"},
        {"stem": "IS_875_Part_3_2015", "query": "Table 5 external pressure coefficients walls rectangular + Cpi 7.3.2",
         "found": True,
         "cite": "IS 875 (Part 3):2015 Table 5 (Clause 7.3.3.1) Cpe walls ≈ +0.7 / −0.5 for ½<h/w≤3/2; §7.3.2.1 Cpi=±0.2; §7.2 pz=0.6Vz², pd=Kd Ka Kc pz, Kd=0.9 (§7.2.1)",
         "collection": "engineering_standards_IS875_P3",
         "note": "Table 5 Cpe +0.7/−0.5 (first readable rows; OCR noisy). Ka Table 4 RAG found:true → A=21.6 m² → Ka=0.923"},
        {"stem": "IS_875_Part_4_1987", "query": "snow Delhi",
         "found": False, "cite": None, "collection": "engineering_standards_IS875_P4",
         "note": "Snow N/A for Delhi office — not applied"},
        {"stem": "IS_875_Part_5_1987", "query": "special loads",
         "found": False, "cite": None, "collection": "engineering_standards_IS875_P5"},
        {"stem": "IS_1893_Part_1_2016", "query": "Delhi seismic zone factor Z Annex E",
         "found": True, "cite": "IS 1893 (Part 1):2016 Annex E — Delhi Zone IV, Z = 0.24",
         "collection": "engineering_standards_IS1893"},
        {"stem": "IS_1893_Part_1_2016", "query": "response reduction factor R concentric braced SBF Table 9",
         "found": True, "cite": "IS 1893 (Part 1):2016 Table 9 — Buildings with special braced frame (SBF) having concentric braces: R = 4.5",
         "collection": "engineering_standards_IS1893"},
        {"stem": "IS_1893_Part_1_2016", "query": "importance factor I Table 8 / 6.4.2",
         "found": True, "cite": "IS 1893 (Part 1):2016 §6.4.2 / Table 8 — I = 1.0 for the rest / all other buildings",
         "collection": "engineering_standards_IS1893"},
        {"stem": "IS_1893_Part_1_2016", "query": "design horizontal seismic coefficient Ah 6.4.2 spectrum medium soil",
         "found": True, "cite": "IS 1893 (Part 1):2016 §6.4.2 Ah=(Z/2)·(I/R)·(Sa/g); medium soil Sa/g=2.5 (T≤0.55), 1.36/T (0.55<T≤4)",
         "collection": "engineering_standards_IS1893"},
        {"stem": "IS_1893_Part_1_2016", "query": "Ta all other buildings 7.6.2(c) 0.09h/sqrt(d)",
         "found": True,
         "cite": "IS 1893 (Part 1):2016 §7.6.2(c) All other buildings: Ta=0.09h/√d; §7.6.3 Qi=Wi hi²/ΣWj hj²·VB; VB=Ah W (§7.6.1)",
         "collection": "engineering_standards_IS1893",
         "note": "SCBF is not bare MRF → use 7.6.2(c) not 7.6.2(a) steel MRF 0.085h^0.75"},
        {"stem": "IS_1893_Part_1_2016", "query": "storey drift limit 7.11.1.1",
         "found": True, "cite": "IS 1893 (Part 1):2016 §7.11.1.1 — storey drift ≤ 0.004 × storey height under design VB (γ=1.0)",
         "collection": "engineering_standards_IS1893"},
        {"stem": "IS_800_2007", "query": "Table 4 partial safety factors for loads",
         "found": True, "cite": "IS 800:2007 Table 4 — DL+LL+CL: 1.5/1.5/1.05; DL+LL+CL+WL/EL: 1.2/1.2/1.05/0.6; DL+WL/EL: 1.5(0.9)/1.5",
         "collection": "engineering_standards_IS800"},
        {"stem": "IS_800_2007", "query": "Section 12.8 Special Concentrically Braced Frames SCBF",
         "found": True,
         "cite": "IS 800:2007 §12.8 SCBF (Zone IV OK); §12.7.3.1/12.8 brace connections: min(1.2 fy Ag, 12.2.3 combo force, max transferable); columns plastic §12.8.4",
         "collection": "engineering_standards_IS800"},
        {"stem": "IS_2062_Part_1_2025", "query": "E250 yield stress Table 3",
         "found": True, "cite": "IS 2062 (Part 1):2025 Table 3 — E250 Qual. A: ReH 250 MPa (t≤16), Rm min 410 MPa",
         "collection": "engineering_standards_IS2062"},
    ]



def build_cfg():
    W = estimate_seismic_weights()
    Wtot = sum(W)
    VB = Ah * Wtot  # kN
    hs, Qi = story_forces_kN(VB, W)
    latX = kN_to_N_lateral_X(Qi)
    latY = kN_to_N_lateral_Y(Qi)

    wind = wind_story_forces_kN()
    windX = kN_to_N_lateral_X(wind["Qi_x_kN"])
    windY = kN_to_N_lateral_Y(wind["Qi_y_kN"])

    retrieval = build_retrieval()
    load_plan = {
        "jurisdiction": "india",
        "partial_factors_cite": "IS 800:2007 Table 4 (retrieved)",
        "retrieval": retrieval,
        "seismic_summary": {
            "code": "IS 1893 (Part 1):2016",
            "site": "New Delhi",
            "zone": "IV",
            "Z": Z,
            "I": I_IMP,
            "R": R,
            "system": "SCBF / SBF concentric braces",
            "soil": "medium / stiff (Type II)",
            "Ta_s": round(Ta, 4),
            "Ta_x_s": round(Ta_x, 4),
            "Ta_y_s": round(Ta_y, 4),
            "Ta_formula": "0.09 h/√d (§7.6.2(c) all other buildings; SCBF ≠ bare MRF)",
            "d_x_m": DX_M,
            "d_y_m": DY_M,
            "Sa_g": round(Sa_g, 4),
            "Ah": round(Ah, 5),
            "W_kN": round(Wtot, 1),
            "W_by_floor_kN": [round(w, 1) for w in W],
            "VB_kN": round(VB, 2),
            "Qi_kN": [round(q, 2) for q in Qi],
            "hi_m": hs,
            "drift_limit_ratio": DRIFT_LIMIT,
            "cite": "Annex E Z; Table 9 R; §6.4.2 Ah; §7.6.2(c) Ta; §7.6.1–7.6.3; §7.11.1.1",
            "Cs": round(Ah, 5),
            "V": round(VB * 1000.0, 1),
            "Tu": round(Ta, 4),
            "Ta": round(Ta, 4),
            "k": 2.0,
            "W": round(Wtot * 1000.0, 1),
            "Fx": {str(k): round(Qi[k-1] * 1000.0, 1) for k in range(1, N_STOREYS+1)},
        },
        "wind_summary": {
            "code": "IS 875 (Part 3):2015",
            "Vb_mps": VB_WIND,
            "terrain_category": 3,
            "k1": K1,
            "k2": K2,
            "k3": K3,
            "k4": K4,
            "Vz_mps": round(wind["Vz"], 3),
            "pz_kNm2": round(wind["pz_Npm2"] / 1000.0, 4),
            "pd_kNm2": round(wind["pd_Npm2"] / 1000.0, 4),
            "Kd": KD, "Ka": KA, "Ka_found": True, "Ka_cite": "IS 875 (Part 3):2015 Table 4 RAG found:true A=21.6 m2 -> Ka=0.923", "Kc": KC,
            "Cpe_windward": CPE_W, "Cpe_leeward": CPE_L,
            "net_Cp": wind["net_Cp"],
            "Cpi": CPI,
            "VB_x_kN": round(wind["VB_x_kN"], 2),
            "VB_y_kN": round(wind["VB_y_kN"], 2),
            "Qi_x_kN": [round(q, 2) for q in wind["Qi_x_kN"]],
            "Qi_y_kN": [round(q, 2) for q in wind["Qi_y_kN"]],
            "cite": "Annex A Vb; Table 1 k1; Table 2 k2 Cat3; §6.3.3.1 k3; §6.3.4 k4; §7.2 pd; Table 5 Cpe; §7.3.2.1 Cpi",
            "note": "Ka=0.923 from IS 875 P3 Table 4 (RAG found; frame A=21.6 m²); Table 5 Cpe OCR noisy but +0.7/−0.5 used",
        },
        "gravity_summary": {
            "L_floor_kNm2": L_FLOOR,
            "L_roof_kNm2": L_ROOF,
            "D_floor_kNm2": D_FLOOR,
            "D_roof_kNm2": D_ROOF,
            "D_note": (
                "RAG assembly IS 875 Part 1:2026 Table 1: RCC 1% steel mid 23.5 kN/m³ × 100 mm fill "
                "+ plaster 0.25 + screed 0.21 + tiles ~0.15 → floor 3.0; roof 2.8 (no MEP — not tabulated). "
                "Fill thickness is project assumption for composite deck."
            ),
            "clad_kNm2": CLAD,
            "cite_LL": "IS 875 Part 2 Table 1 / Table 2",
            "cite_DL": "IS 875 Part 1:2026 Table 1 Sl 21/24/31 finishes + RCC",
        },
        "story_forces": {
            "EQ_X": latX,
            "EQ_Y": latY,
            "W_X": windX,
            "W_Y": windY,
        },
        "combinations": [
            {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 1.5,
             "lateral": {}, "cite": "IS 800:2007 Table 4 — DL+LL+CL"},
            {"label": "1.5DL+1.5EQ_X", "fD": 1.5, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "EQ_X", "cite": "IS 800:2007 Table 4 — DL+EL"},
            {"label": "1.5DL+1.5EQ_Y", "fD": 1.5, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "EQ_Y", "cite": "IS 800:2007 Table 4 — DL+EL"},
            {"label": "1.2DL+1.2LL+1.2EQ_X", "fD": 1.2, "fL": 1.2, "fLr": 0.0,
             "lateral_ref": "EQ_X", "cite": "IS 800:2007 Table 4 — DL+LL+EL"},
            {"label": "1.2DL+1.2LL+1.2EQ_Y", "fD": 1.2, "fL": 1.2, "fLr": 0.0,
             "lateral_ref": "EQ_Y", "cite": "IS 800:2007 Table 4 — DL+LL+EL"},
            {"label": "0.9DL+1.5EQ_X", "fD": 0.9, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "EQ_X", "cite": "IS 800:2007 Table 4 — DL+EL with 0.9 DL"},
            {"label": "0.9DL+1.5EQ_Y", "fD": 0.9, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "EQ_Y", "cite": "IS 800:2007 Table 4 — DL+EL with 0.9 DL"},
            {"label": "1.5DL+1.5W_X", "fD": 1.5, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "W_X", "cite": "IS 800:2007 Table 4 — DL+WL"},
            {"label": "1.5DL+1.5W_Y", "fD": 1.5, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "W_Y", "cite": "IS 800:2007 Table 4 — DL+WL"},
            {"label": "1.2DL+1.2LL+1.2W_X", "fD": 1.2, "fL": 1.2, "fLr": 0.0,
             "lateral_ref": "W_X", "cite": "IS 800:2007 Table 4 — DL+LL+WL"},
            {"label": "1.2DL+1.2LL+1.2W_Y", "fD": 1.2, "fL": 1.2, "fLr": 0.0,
             "lateral_ref": "W_Y", "cite": "IS 800:2007 Table 4 — DL+LL+WL"},
            {"label": "0.9DL+1.5W_X", "fD": 0.9, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "W_X", "cite": "IS 800:2007 Table 4 — DL+WL with 0.9 DL"},
            {"label": "0.9DL+1.5W_Y", "fD": 0.9, "fL": 0.0, "fLr": 0.0,
             "lateral_ref": "W_Y", "cite": "IS 800:2007 Table 4 — DL+WL with 0.9 DL"},
        ],
        "notes": (
            "Units: engine N-mm (SI-native steltic_india). Lateral story forces in Newtons. "
            "Wind laterals applied (k1/k2/Cpe retrieved; Ka=1.0 conservative). "
            "SDL from Part 1 RCC+finishes assembly; MEP not tabulated. "
            "Ta per §7.6.2(c) all-other-buildings."
        ),
    }

    cfg = {
        "name": NAME,
        "system": "SCBF",
        "arch": "SCBF",
        "governing": "seismic",
        "jurisdiction": "india",
        "units": "m",
        "metric": True,
        "si_native": True,
        "NX": NX, "NY": NY,
        "bay_x": BAY_M, "bay_y": BAY_M,
        "heights": [H_STOREY_M] * N_STOREYS,
        "D_floor": D_FLOOR,
        "D_roof": D_ROOF,
        "L_floor": L_FLOOR,
        "Lr": L_ROOF,
        "clad": CLAD,
        "snow": 0.0,
        "Fy": FY,
        "Fu": FU,
        "E": 200000.0,
        "base": "fixed",
        "diaphragm": "rigid",
        "floor_system": "one-way composite",
        "model": {"bases": "fixed", "joints": "mixed", "gravity": "framed"},
        "col": "WPB300X300X88.34",
        "beam": "NPB450X190X67.16",
        "brace": "CHS168.3X8",
        "braces": perimeter_scbf_braces,
        "col_sec": col_sec,
        "beam_sec": beam_sec,
        "col_strong": col_strong,
        "releases": releases,
        "custom_build": EB.example_build,
        "seis": {
            "Z": Z, "I": I_IMP, "R": R,
            "Ah": Ah, "Ta": Ta, "Sa_g": Sa_g,
            "VB_kN": VB, "zone": "IV", "soil": "medium",
        },
        "drift_limit": DRIFT_LIMIT,
        "load_plan": load_plan,
        "analyses": ["ELF"],
        "notes": (
            "IN_Ex1 5-storey office perimeter SCBF, New Delhi. "
            "Interior gravity beams pinned; perimeter beams rigid; fixed bases. "
            "Composite metal deck modelled one-way; composite Ch.I scoped in calc package. "
            "Ta=0.09h/√d; wind laterals on."
        ),
    }
    IU.apply_si_geometry(cfg)
    IU.apply_metric_pressures(cfg)
    if cfg.get("SX", 0) < 100:
        cfg["SX"] = float(cfg.get("bay_x", BAY_M)) * 1000.0
        cfg["SY"] = float(cfg.get("bay_y", BAY_M)) * 1000.0
    IU.activate_si()
    import sections as _S
    import engine3d as _E
    _E.activate_si_units()
    for br in ("CHS168.3X8", "CHS168.3X10", "CHS219.1X8", "CHS193.7X8"):
        try:
            _E.HSS[br] = float(_S.props(br)["A"])
        except Exception:
            pass
    cfg["seis"] = {
        "Z": Z, "I": I_IMP, "R": R,
        "Ah": Ah, "Ta": Ta, "Sa_g": Sa_g,
        "VB_kN": VB, "zone": "IV", "soil": "medium",
        "Ie": I_IMP,
        "Cd": R,
        "SDS": round(2 * Ah, 3),
        "SD1": round(Ah, 3),
        "Om0": 2.0,
        "Ct": 0.09, "x": 0.5, "Cu": 1.0,  # shim reflecting 0.09h/√d form
    }
    return cfg, {
        "W_kN": W, "VB_kN": VB, "Qi_kN": Qi, "Ta": Ta, "Ta_x": Ta_x, "Ta_y": Ta_y,
        "Ah": Ah, "Sa_g": Sa_g, "wind": wind,
    }



def main():
    cfg, seis = build_cfg()
    # persist cfg (without callables for JSON; keep .py with callables)
    cfg_path = JOB / "cfg.py"
    # Write a loadable cfg.py
    with open(cfg_path, "w") as f:
        f.write("# Auto-built IN_Ex1 cfg — see build_and_run.py\n")
        f.write("import sys, os\n")
        f.write("sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'steel_engine'))\n")
        f.write("from build_and_run import build_cfg\n")
        f.write("cfg, _seis = build_cfg()\n")

    (JOB / "load_plan.json").write_text(json.dumps(cfg["load_plan"], indent=2))
    (JOB / "seismic_calc.json").write_text(json.dumps({
        "Ta_s": seis["Ta"], "Ta_x_s": seis["Ta_x"], "Ta_y_s": seis["Ta_y"],
        "Ta_formula": "0.09 h/sqrt(d) 7.6.2(c)",
        "Sa_g": seis["Sa_g"], "Ah": seis["Ah"],
        "VB_kN": seis["VB_kN"], "W_kN": seis["W_kN"], "Qi_kN": seis["Qi_kN"],
        "Z": Z, "I": I_IMP, "R": R,
        "wind_VB_x_kN": seis["wind"]["VB_x_kN"],
        "wind_VB_y_kN": seis["wind"]["VB_y_kN"],
    }, indent=2))

    # RAG summary counts
    ret = cfg["load_plan"]["retrieval"]
    by_stem = {}
    for h in ret:
        s = h["stem"]
        by_stem.setdefault(s, {"found_true": 0, "found_false": 0, "queries": []})
        if h.get("found"):
            by_stem[s]["found_true"] += 1
        else:
            by_stem[s]["found_false"] += 1
        by_stem[s]["queries"].append(h.get("query"))
    rag_summary = {
        "total_queries": len(ret),
        "found_true": sum(1 for h in ret if h.get("found")),
        "found_false": sum(1 for h in ret if not h.get("found")),
        "by_stem": by_stem,
        "found_false_list": [h for h in ret if not h.get("found")],
    }
    (JOB / "rag_summary.json").write_text(json.dumps(rag_summary, indent=2))

    print("=== Seismic ===")
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in {
        "Ta": seis["Ta"], "Sa_g": seis["Sa_g"], "Ah": seis["Ah"],
        "VB_kN": seis["VB_kN"], "Qi_kN": [round(q, 2) for q in seis["Qi_kN"]],
    }.items()}, indent=2))
    print("units after convert:", cfg.get("units"), "heights[0]=", cfg["heights"][0], "SX=", cfg["SX"])

    print("\n=== pipeline.design_and_report ===")
    try:
        res = pipeline.design_and_report(NAME, cfg)
        print("RESULT keys:", sorted(res.keys()))
        print("model_valid:", res.get("model_valid"))
        print("demands_written:", res.get("demands_written"))
        print("report:", res.get("report_html") or res.get("report"))
        print("root:", res.get("root"))
        (JOB / "pipeline_result.json").write_text(json.dumps(
            {k: (str(v) if not isinstance(v, (int, float, bool, str, list, dict, type(None))) else v)
             for k, v in res.items() if k != "preflight"}, indent=2, default=str))
    except Exception as ex:
        print("PIPELINE ERROR:", ex)
        traceback.print_exc()
        (JOB / "pipeline_error.txt").write_text(traceback.format_exc())
        return 1



    # --- complete-gap wave1 post-fill (χ Pd, §12, base plates) + report rebuild ---
    try:
        import wave1_fill
        gov_dc, gov_id = wave1_fill.apply(JOB / "design" / "calc_package.json")
        print(f"wave1 fill: governing DC={gov_dc} @ {gov_id}")
        import report as report_mod
        report_mod.build_report(NAME)
        print("report rebuilt after wave1 fill")
    except Exception as ex:
        print("wave1 fill/report error:", ex)
        traceback.print_exc()

    try:
        flags = consistency.check(NAME)
        (JOB / "consistency_result.json").write_text(json.dumps(flags, indent=2, default=str))
        print("consistency flags:", flags)
    except Exception as ex:
        print("consistency error:", ex)
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    sys.exit(main())
