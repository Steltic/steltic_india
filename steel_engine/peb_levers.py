"""peb_levers.py -- PEB-LEVERS (2026-10 variations study): the switches of cfg['peb_rules'].

The PEB golds (IN_Ex1 ... IN_Ex4) are designed code-strict with the owner rulings of the PEB release
(docs/PEB_LIMITATIONS.md).  Each ruling, and each common Indian PEB practice that differs from it, is a switch here,
so that a design engineer can see what each reading costs or saves in steel on one shed.  Every switch defaults to the
gold ruling: a cfg without 'peb_rules' (or with the defaults) runs exactly as before.

    cfg['peb_rules'] = {
        'joint_demand':   '1.2Mp' (D-T7, default) | 'deliverable',
        'deliverable_factor': 1.2 (default) | 1.0,
        'ltb_c1':         'unity' (D-T1, default) | 'gradient',
        'sway_limit':     'H240_brittle_dado' (default) | 'H150_with_dado_check' | 'H150_no_dado_check',
        'dado_height_mm': 3000.0 (needed by 'H150_with_dado_check'),
        'base_shear_key': '1.2Vd' (ruling O1, default) | 'analysis',
        'bracing':        'compression' (D-T4, default) | 'tension_rods',
        'purlins':        'IS811_Fy240' (default) | 'thin_G350',
        'collateral_in_uplift': False (default) | True,
    }

What each switch does (and what the code says), in plain terms:

* joint_demand 'deliverable' -- IS 800:2007 12.10.2.1 (corpus transcription, IS_800_2007 p.95): "Rigid moment
  connections should be designed to withstand a moment of at least 1.2 times of either the full plastic moment of the
  connected beam or the maximum moment that can be delivered by the beam to the joint due to the induced weakness at
  the ends of the beam, whichever is less."  The study takes the deliverable moment as the largest factored moment at
  the joint over all strength combinations, the IS 800 12.2.3 amplified-seismic rows (1.2DL + 0.5LL +- 2.5EL,
  0.9DL +- 2.5EL) included.  Read with the clause's "1.2 times of either ... whichever is less", the demand is
  min(1.2 Mp, 1.2 M_deliverable) (deliverable_factor 1.2, the default); deliverable_factor 1.0 gives
  min(1.2 Mp, M_deliverable).  Applies to ordinary moment frames only (route A, IS 800 12.10): an SMRF joint (IS 800
  12.11.2.1, 1.2 Mp with no deliverable option) and an IS 18168 joint (8.4, 1.1 Ry fy Zpb) are left unchanged.
  Used at the PEB knees (peb_checks.knee_records), the apex (peb_checks.splice_records) and the Section 12 12.10.2.1
  row (india_is800_s12 'max_deliverable_moment_Nmm').
* ltb_c1 'gradient' -- the moment-gradient C1 the PEB scope proposed (docs/PEB_TAPERED_SCOPE.md 5.2,
  india_is800.c1_from_end_moments, IS 800 Table 42 K = 1.0) instead of C1 = 1.0 (D-T1), per combination and per sign
  of moment, over the restrained length that the D-T1 LTB check uses (purlins / girts / fly braces).  The end moments
  of that length are read from the stepped elements of the tapered members (linear between element ends); where the
  restrained length runs into an element of a prismatic member (one long element, transverse load inside) or the
  moment inside the length exceeds both end values, C1 stays 1.0 (conservative).
* sway_limit -- IS 800:2007 Table 6 (corpus): column, no cranes: elastic cladding Height/150, masonry / brittle
  cladding Height/240.  'H150_with_dado_check' treats the metal wall cladding above the dado as elastic (eave sway <=
  H/150) and checks the brick dado where it is: the column displacement at the dado top <= dado height / 240.
  'H150_no_dado_check' (market practice bundle only) drops the dado check: NOT compliant where a brick dado is tied
  to the columns.
* base_shear_key 'analysis' -- ruling O1 reads IS 800 12.12.2 literally (shear keys for 1.2 Vd of the column on every
  SFRS base).  'analysis' designs the base shear transfer for the largest factored base shear of the analysis over
  all strength combinations, the 12.2.3 rows included.  The study marks it as a reading of 12.12.2 that the O1 ruling
  rejected (not compliant with the owner ruling; see the study notes).
* bracing 'tension_rods' -- round-bar X-bracing designed in tension only (the compression diagonal ignored).  IS 800
  12.1 applies Section 12 to all zones and 12.7.2.1 limits OCBF brace slenderness to 120 (12.7.2.3: tension braces
  resist 30 to 70 percent of the lateral load): a rod brace meets neither.  The switch is accepted only on a Zone II
  OCBF and is marked NOT compliant with IS 800 Section 12 (market practice); elsewhere it is refused.
* purlins 'thin_G350' -- generic thin lipped zeds (IS 277 grade 350 coil, Fy 350 MPa, inside IS 801:1975 Table 2's
  36 kgf/mm2 row) instead of IS 811 zeds at Fy 240 MPa.  Used by the secondary design (peb_autosize.design_secondary),
  not by the frame engine.
* collateral_in_uplift True -- the collateral and rooftop PV loads (cfg 'D_roof_collateral', 'D_roof_pv', kN/m2 on plan,
  not included in 'D_roof') also count in the 0.9DL rows: they are folded into D_roof (fold_collateral).  False (the
  default) leaves them to the engine, which applies them with the dead-load factor except in the 0.9DL rows.

Brief-level variants (not engine switches; peb_autosize / scripts/peb_lever_study.py re-run the job's cfg.py):
'seismic_route' ('as_briefed' | 'OMRF_R3') and the 'market_practice' bundle; their code status is from
seismic_route_status() and MARKET_PRACTICE below.
"""
from __future__ import annotations

import math

SRC = "steel_engine/peb_levers.py"

DEFAULTS = {
    "joint_demand": "1.2Mp",
    "deliverable_factor": 1.2,
    "ltb_c1": "unity",
    "sway_limit": "H240_brittle_dado",
    "dado_height_mm": None,
    "base_shear_key": "1.2Vd",
    "bracing": "compression",
    "purlins": "IS811_Fy240",
    "collateral_in_uplift": False,
    "purlin_free_flange": "sag_rods",
}
ALLOWED = {
    "joint_demand": ("1.2Mp", "deliverable"),
    "ltb_c1": ("unity", "gradient"),
    "sway_limit": ("H240_brittle_dado", "H150_with_dado_check", "H150_no_dado_check"),
    "base_shear_key": ("1.2Vd", "analysis"),
    "bracing": ("compression", "tension_rods"),
    "purlins": ("IS811_Fy240", "thin_G350"),
    "collateral_in_uplift": (False, True),
    "purlin_free_flange": ("sag_rods", "sheeting_braced"),
}
# status of each non-default value (the study labels its rows with these)
STATUS = {
    ("joint_demand", "deliverable"): ("compliant", "IS 800:2007 12.10.2.1 (OMF): the lesser of 1.2 Mp and the moment "
                                                   "the beam can deliver to the joint"),
    ("ltb_c1", "gradient"): ("compliant", "IS 800:2007 8.2.2.1 / Annex E Table 42 C1 for end moments (K = 1.0); the "
                                          "tapered-member basis proposed in docs/PEB_TAPERED_SCOPE.md 5.2"),
    ("sway_limit", "H150_with_dado_check"): ("compliant", "IS 800:2007 Table 6: elastic cladding H/150 at the eave; "
                                                          "masonry H/240 applied to the dado over its own height"),
    ("sway_limit", "H150_no_dado_check"): ("not compliant", "IS 800:2007 Table 6 masonry / brittle cladding H/240 "
                                                            "ignored where a brick dado is tied to the columns"),
    ("base_shear_key", "analysis"): ("reading rejected by ruling O1", "IS 800:2007 12.12.2 read as the analysis base "
                                                                     "shear (owner ruling O1 reads 1.2 Vd literally)"),
    ("bracing", "tension_rods"): ("not compliant", "IS 800:2007 12.1 (all zones), 12.7.2.1 (KL/r <= 120) and 12.7.2.3 "
                                                   "(tension braces 30-70 %) are not met by rod X-bracing"),
    ("purlins", "thin_G350"): ("compliant", "IS 801:1975 Table 2 36 kgf/mm2 row (Fy 350 MPa), IS 801 5.2 section "
                                            "properties by conventional methods (generic thin zeds)"),
    ("collateral_in_uplift", True): ("conservative", "collateral / PV also resist uplift in the 0.9DL rows (the "
                                                     "pre-2026-10 treatment)"),
    ("purlin_free_flange", "sheeting_braced"): ("not compliant", "the purlin's free flange taken as braced by the "
                                                                 "sheeting under uplift (IS 801 6.3 needs the "
                                                                 "unbraced length of the compression flange)"),
}

# market practice bundle (clearly NOT compliant): what many Indian PEB vendors assume
MARKET_PRACTICE = {
    "Lr_kNm2": 0.57,
    "Lr_note": "MBMA roof live load 12 psf = 0.57 kN/m2 (foreign vendor practice, not an IS value); IS 875 (Part 2) "
               "Table 2 gives 0.75 kN/m2 for a roof with access for maintenance only",
    "R": 3.0,
    "R_note": "ordinary frames (OMRF R 3, OCBF R 4 per IS 1893 Table 9) in any zone; IS 1893 (Part 1):2016 Table 9 "
              "Note 1 (Amd 2) does not allow them in Zones III-V; IS 800 12.10.1.1 / 12.7.1.1 not in Zones IV-V",
    "rules": {"sway_limit": "H150_no_dado_check", "purlin_free_flange": "sheeting_braced"},
    "status": "NOT COMPLIANT (market practice)",
}


class LeverError(ValueError):
    pass


def rules(cfg) -> dict:
    """cfg['peb_rules'] merged over DEFAULTS and validated (LeverError on an unknown key or value)."""
    pr = (cfg or {}).get("peb_rules") or {}
    if not isinstance(pr, dict):
        raise LeverError("cfg['peb_rules'] must be a dict (got %r)" % type(pr).__name__)
    out = dict(DEFAULTS)
    for k, v in pr.items():
        if k.startswith("_"):
            out[k] = v                        # private keys (e.g. '_dump_element_inputs' for peb_autosize)
            continue
        if k not in DEFAULTS:
            raise LeverError("cfg['peb_rules'][%r]: unknown switch (known: %s)" % (k, ", ".join(sorted(DEFAULTS))))
        if k in ALLOWED and v not in ALLOWED[k]:
            raise LeverError("cfg['peb_rules'][%r] = %r: allowed %s" % (k, v, list(ALLOWED[k])))
        out[k] = v
    if out["deliverable_factor"] not in (1.0, 1.2):
        raise LeverError("cfg['peb_rules']['deliverable_factor'] must be 1.2 (12.10.2.1 '1.2 times of either') or 1.0")
    if out["sway_limit"] == "H150_with_dado_check" and not out.get("dado_height_mm"):
        raise LeverError("cfg['peb_rules']['sway_limit'] = 'H150_with_dado_check' needs 'dado_height_mm' (the brick "
                         "dado height above the base)")
    return out


def rule(cfg, key):
    return rules(cfg)[key]


def is_default(cfg) -> bool:
    r = rules(cfg)
    return all(r[k] == v for k, v in DEFAULTS.items())


def describe(cfg) -> list:
    """[(switch, value, status, basis)] for the report / the study table; defaults are the gold rulings."""
    r = rules(cfg)
    out = []
    for k, v0 in DEFAULTS.items():
        v = r[k]
        if k in ("deliverable_factor", "dado_height_mm"):
            continue
        if v == v0:
            out.append((k, v, "default (gold ruling)", ""))
        else:
            st, basis = STATUS.get((k, v), ("", ""))
            out.append((k, v, st, basis))
    return out


# ------------------------------------------------------------------------------------------- brief-level variants
def seismic_route_status(zone, I=1.0):
    """Code status of an ordinary moment frame (OMRF, R 3) with ordinary braced frames (OCBF, R 4), no IS 18168, in
    the given seismic zone: (permitted, label, note)."""
    z = str(zone or "").upper().replace("ZONE", "").strip()
    I = float(I or 1.0)
    if z == "II":
        return (True, "permitted", "Zone II: IS 800:2007 12.10.1.1 / 12.7.1.1 and IS 1893 (Part 1):2016 Table 9 Note 1 "
                                   "allow ordinary moment and braced frames")
    if z == "III" and I <= 1.0:
        return (True, "conflict: permitted by IS 800 12.10.1.1, not by IS 1893 Table 9 Note 1",
                "Zone III, I <= 1.0: IS 800:2007 12.10.1.1 / 12.7.1.1 exclude OMF / OCBF only in Zones IV-V and in "
                "Zone III for I > 1.0, but IS 1893 (Part 1):2016 Table 9 Note 1 (Amd 2) says 'Structures in Seismic "
                "Zones III, IV and V shall be designed to be ductile. Hence, this system is not allowed in these "
                "seismic zones' -- the design engineer must decide which governs")
    if z == "III":
        return (False, "not compliant", "Zone III with I > 1.0: IS 800:2007 12.10.1.1 / 12.7.1.1 and IS 1893 Table 9 "
                                        "Note 1 both exclude ordinary frames")
    return (False, "market practice, not compliant",
            "Zone %s: IS 800:2007 12.10.1.1 / 12.7.1.1 ('shall not be used in seismic zones IV and V') and IS 1893 "
            "(Part 1):2016 Table 9 Note 1 exclude ordinary frames" % (z or "?"))


# ------------------------------------------------------------------------------------------- collateral / PV
def fold_collateral(cfg):
    """collateral_in_uplift True: D_roof_collateral and D_roof_pv (kN/m2 on plan, outside D_roof by the engine
    contract) are folded into D_roof (and D_floor where it mirrors D_roof) so that they act in every dead-load row,
    the 0.9DL rows included.  Returns (cfg, note); cfg is changed in place only when the switch is on."""
    r = rules(cfg)
    if not r["collateral_in_uplift"]:
        return cfg, None
    c = float(cfg.get("D_roof_collateral") or 0.0)
    pv = float(cfg.get("D_roof_pv") or 0.0)
    if c == 0.0 and pv == 0.0:
        return cfg, ("collateral_in_uplift: the job declares no D_roof_collateral / D_roof_pv (they are inside D_roof "
                     "and already act in the 0.9DL rows)")
    mirror = abs(float(cfg.get("D_floor") or 0.0) - float(cfg.get("D_roof") or 0.0)) < 1e-12
    cfg["D_roof"] = round(float(cfg.get("D_roof") or 0.0) + c + pv, 6)
    if mirror:
        cfg["D_floor"] = cfg["D_roof"]
    cfg["D_roof_collateral"], cfg["D_roof_pv"] = 0.0, 0.0
    return cfg, ("collateral_in_uplift: collateral %.3f + PV %.3f kN/m2 folded into D_roof = %.3f kN/m2 (they also "
                 "resist uplift in the 0.9DL rows)" % (c, pv, cfg["D_roof"]))


# ------------------------------------------------------------------------------------------- joint demand
def _frame_system(cfg, system=None):
    import india_is800_s12 as S12
    for s in ((cfg or {}).get("system_y"), system, (cfg or {}).get("system")):
        n = S12.normalize_system(s) if s else None
        if n:
            return n
    return None


def deliverable_applies(cfg, is18=False, system=None):
    """(applies, note): the 'deliverable' joint demand applies to ordinary moment frames (route A) only."""
    r = rules(cfg)
    if r["joint_demand"] != "deliverable":
        return False, None
    if is18:
        return False, ("joint_demand 'deliverable' not applied: IS 18168:2023 8.4 joint (route B, 1.1 Ry fy Zpb) -- "
                       "unchanged")
    sysn = _frame_system(cfg, system)
    if sysn != "OMF":
        return False, ("joint_demand 'deliverable' not applied: %s joint (IS 800 12.11.2.1 1.2 Mp, no deliverable "
                       "option) -- unchanged" % (sysn or "non-OMF"))
    return True, None


def joint_demand(cfg, Mp_Nmm, M_deliv_Nmm, *, is18=False, system=None, fac_default=1.2):
    """(M_conn, basis, applied) at a moment-frame joint: fac_default x Mp (D-T7) or, under 'deliverable',
    min(1.2 Mp, f x M_deliverable)."""
    ok, note = deliverable_applies(cfg, is18, system)
    if not ok:
        return fac_default * Mp_Nmm, note, False
    f = float(rules(cfg)["deliverable_factor"])
    Md = f * abs(float(M_deliv_Nmm or 0.0))
    M = min(1.2 * Mp_Nmm, Md)
    basis = ("PEB-LEVERS joint_demand 'deliverable': IS 800:2007 12.10.2.1 -- min(1.2 Mp = %.0f kN-m, %.1f x the largest "
             "factored joint moment %.0f kN-m (all strength combinations incl. 12.2.3)) = %.0f kN-m"
             % (1.2 * Mp_Nmm / 1e6, f, abs(float(M_deliv_Nmm or 0.0)) / 1e6, M / 1e6))
    return M, basis, True


# ------------------------------------------------------------------------------------------- C1 (moment gradient)
def _restraint_sets_rafter(cfg, ln):
    """(purlin coords, fly coords) in plan coordinates of a rafter line, as peb_build.overrides builds them."""
    fb = (cfg or {}).get("flange_braces") or {}
    rb = fb.get("rafter") or {}
    lo, hi, ridge = ln["lo"], ln["hi"], ln["ridge"]

    def coords(lst):
        out_ = set()
        for d in lst:
            for a in (lo + float(d), hi - float(d)):
                if lo - 1 <= a <= hi + 1:
                    out_.add(a)
        out_ |= {lo, hi, ridge}
        out_ |= {a for a, nd in zip(ln["a_mm"], ln["nodes"]) if nd in ln["supports"]}
        return sorted(out_)
    return coords(rb.get("purlins_mm") or []), coords(rb.get("fly_braces_mm") or [])


def _interval(pts, a0, a1):
    """The largest restraint interval [p0, p1] that overlaps [a0, a1] (peb_build._gaps / overrides.gap)."""
    best = None
    for p0, p1 in zip(pts, pts[1:]):
        if p1 > a0 + 1e-6 and p0 < a1 - 1e-6:
            if best is None or (p1 - p0) > (best[1] - best[0]) + 1e-9:
                best = (p0, p1)
    return best


def _c1_segment(chain, recs_of, combo, p0, p1, short):
    """C1 over the restrained length [p0, p1] of an ordered chain [(t, a0, a1)] for one combination, or 1.0."""
    import india_is800 as I8
    vals = []                                           # (position, moment) at element ends inside / bounding
    m_at = {}
    for t, a0, a1 in chain:
        if a1 <= p0 - 1e-6 or a0 >= p1 + 1e-6:
            continue
        if not short.get(t):
            return 1.0, "restrained length runs into a prismatic element"
        r = list(recs_of(t).get(combo) or []) + [0.0] * 13
        Mi, Mj = float(r[4]), float(r[5])
        for p in (p0, p1):
            if a0 - 1e-6 <= p <= a1 + 1e-6 and p not in m_at:
                f = (p - a0) / (a1 - a0) if a1 > a0 else 0.0
                m_at[p] = Mi + (Mj - Mi) * f
        if p0 + 1e-6 < a0 < p1 - 1e-6:
            vals.append(Mi)
        if p0 + 1e-6 < a1 < p1 - 1e-6:
            vals.append(Mj)
    if p0 not in m_at or p1 not in m_at:
        return 1.0, "restrained length not covered by the chain"
    Ma, Mb = m_at[p0], m_at[p1]
    big, small = (Ma, Mb) if abs(Ma) >= abs(Mb) else (Mb, Ma)
    if abs(big) < 1.0:                                   # < 1 N-mm: no moment
        return 1.0, "no end moment"
    if any(abs(v) > abs(big) * 1.001 for v in vals):
        return 1.0, "moment inside the restrained length exceeds both end values"
    psi = small / big
    return float(I8.c1_from_end_moments(psi)), "psi %.3f" % psi


def c1_gradient_map(cfg, peb, envt):
    """{element tag: {combo: {'sagging': C1, 'hogging': C1}}} for the stepped elements of PEB column / rafter
    chains (ltb_c1 'gradient').  Elements not in the map keep the D-T1 C1 = 1.0."""
    if rules(cfg)["ltb_c1"] != "gradient" or not peb:
        return {}
    els, mems, chains = peb.get("elements") or {}, peb.get("members") or {}, peb.get("chains") or {}
    fb = (cfg or {}).get("flange_braces") or {}
    short = {}
    for t, e in els.items():
        short[t] = e.get("sec_i") != e.get("sec_j")      # a stepped segment of a tapered member
    recs_of = lambda t: (envt.get(t) or {}).get("records") or {}
    out = {}
    # columns: one chain each; positions = height above the base
    for cid, ch in chains.items():
        if ch.get("kind") != "column":
            continue
        tl = []
        for mid in ch.get("members") or []:
            for t in (mems.get(mid) or {}).get("elements") or []:
                e = els[t]
                tl.append((t, float(e["pos_mm"][0]), float(e["pos_mm"][1])))
        tl.sort(key=lambda x: x[1])
        H = float(ch.get("L_mm") or 0.0)
        cb = ch.get("restraints") if ch.get("restraints") is not None else (fb.get("column") or {})
        g = sorted(set([0.0, H] + [float(x) for x in cb.get("girts_mm") or [] if 0.0 <= float(x) <= H]))
        f = sorted(set([0.0, H] + [float(x) for x in cb.get("fly_braces_mm") or [] if 0.0 <= float(x) <= H]))
        for t, a0, a1 in tl:
            if not short.get(t):
                continue
            ig, iff = _interval(g, a0, a1), _interval(f, a0, a1)
            seg = ig if (ig and (not iff or (ig[1] - ig[0]) >= (iff[1] - iff[0]))) else iff
            if not seg:
                continue
            per = {}
            for combo in recs_of(t):
                c, _n = _c1_segment(tl, recs_of, combo, seg[0], seg[1], short)
                per[combo] = {"sagging": c, "hogging": c}
            out[t] = per
    # rafters: one rafter line (both slopes) each; positions = plan coordinate along the span
    for key, ln in (peb.get("rafter_lines") or {}).items():
        tl = []
        for t, e in els.items():
            m = mems.get(e["member"]) or {}
            if m.get("kind") != "rafter" or (m.get("plane"), m.get("line")) != tuple(key):
                continue
            a0, a1 = sorted(float(x) for x in e["pos_mm"])
            tl.append((t, a0, a1))
        tl.sort(key=lambda x: x[1])
        pur, fly = _restraint_sets_rafter(cfg, ln)
        for t, a0, a1 in tl:
            if not short.get(t):
                continue
            sg, hg = _interval(pur, a0, a1), _interval(fly, a0, a1)
            per = {}
            for combo in recs_of(t):
                cs = _c1_segment(tl, recs_of, combo, sg[0], sg[1], short)[0] if sg else 1.0
                ch_ = _c1_segment(tl, recs_of, combo, hg[0], hg[1], short)[0] if hg else 1.0
                per[combo] = {"sagging": cs, "hogging": ch_}
            out[t] = per
    return out


# ------------------------------------------------------------------------------------------- sway (Table 6)
def sway_key(cfg, key):
    """The IS 800 Table 6 row for the column sway under the switch: 'H150_*' turns the brittle (masonry) column row
    into the elastic-cladding row; any other row (crane frames, other buildings) is unchanged.  Returns (key, note)."""
    r = rules(cfg)
    if r["sway_limit"] == "H240_brittle_dado" or key != "column_no_crane_brittle":
        return key, None
    if r["sway_limit"] == "H150_with_dado_check":
        return "column_no_crane_elastic", ("PEB-LEVERS sway_limit 'H150_with_dado_check': eave sway H/150 (metal "
                                           "cladding above the dado, IS 800 Table 6 elastic cladding); the dado is "
                                           "checked over its own height at H/240 (masonry)")
    return "column_no_crane_elastic", ("PEB-LEVERS sway_limit 'H150_no_dado_check' (market practice, NOT compliant): "
                                       "eave sway H/150 and no check of the brick dado")


def dado_check_on(cfg):
    r = rules(cfg)
    return r["sway_limit"] == "H150_with_dado_check" and bool((cfg or {}).get("cladding_brittle"))


def _hermite(z0, u0, s0, z1, u1, s1, z):
    """Cubic Hermite interpolation of a beam deflection between two nodes (displacement u, slope s)."""
    L = z1 - z0
    if L <= 0:
        return u0
    x = (z - z0) / L
    h00 = 2 * x ** 3 - 3 * x ** 2 + 1
    h10 = x ** 3 - 2 * x ** 2 + x
    h01 = -2 * x ** 3 + 3 * x ** 2
    h11 = x ** 3 - x ** 2
    return h00 * u0 + h10 * L * s0 + h01 * u1 + h11 * L * s1


def dado_drift(cfg, info, d, ntag):
    """Largest column displacement in direction d ('X' / 'Y') at the dado top over the columns of the ground storey,
    from the current OpenSees state (a serviceability solve), by Hermite interpolation between the column's station
    nodes (peb_build chains) with the nodal slopes.  Returns (u_max_mm, h_dado_mm, where)."""
    import openseespy.opensees as ops
    try:
        import peb_build as PB
        chains = PB.snapshot()["chains"] if PB.active() else {}
    except Exception:
        chains = {}
    h = float(rules(cfg)["dado_height_mm"])
    di = 1 if d == "X" else 2
    best = (0.0, None)
    by_line = {tuple(ch["line"]): ch for ch in chains.values() if ch.get("kind") == "column"}
    for (i, j) in sorted(info["present"][0]):
        if (i, j) not in info["present"].get(1, set()):
            continue
        ch = by_line.get((i, j))
        if ch:
            nodes, zs = ch["nodes"], ch["s_mm"]
        else:
            nodes = [ntag(i, j, 0), ntag(i, j, 1)]
            zs = [0.0, math.dist(ops.nodeCoord(nodes[0]), ops.nodeCoord(nodes[1]))]
        if h >= zs[-1]:
            continue
        k = max(n for n in range(len(zs) - 1) if zs[n] <= h + 1e-9)
        n0, n1 = nodes[k], nodes[k + 1]
        # slope du/dz: u_x' = +theta_y (dof 5), u_y' = -theta_x (dof 4) for a vertical member
        sl = (lambda n: ops.nodeDisp(n, 5)) if d == "X" else (lambda n: -ops.nodeDisp(n, 4))
        u = _hermite(zs[k], ops.nodeDisp(n0, di), sl(n0), zs[k + 1], ops.nodeDisp(n1, di), sl(n1), h)
        u -= ops.nodeDisp(nodes[0], di)                  # relative to the base (0 at a fixed / pinned support)
        if abs(u) > best[0]:
            best = (abs(u), (i, j))
    return best[0], h, best[1]


# ------------------------------------------------------------------------------------------- base shear
def base_shear_note(cfg):
    if rules(cfg)["base_shear_key"] != "analysis":
        return None
    return ("PEB-LEVERS base_shear_key 'analysis': base shear = the largest factored base shear of the case (all "
            "strength combinations incl. 12.2.3); the 1.2 Vd of ruling O1 is not added")


# ------------------------------------------------------------------------------------------- tension rods
ROD_FY, ROD_FU = 250.0, 410.0          # IS 2062 E250 round bar (assumption: rod grade declared by the job)
ROD_SIZES_MM = (16, 20, 24, 30, 36)     # threaded rods with an IS 4000 Table 2 stress area in india_connections


def rods_allowed(cfg):
    """(allowed, note) for bracing 'tension_rods': Zone II OCBF only; marked NOT compliant with IS 800 Section 12."""
    r = rules(cfg)
    if r["bracing"] != "tension_rods":
        return False, None
    import india_is800_s12 as S12
    zone = str(((cfg or {}).get("seis") or {}).get("zone") or "").upper()
    sx = S12.normalize_system((cfg or {}).get("system_x")) if (cfg or {}).get("system_x") else None
    if zone != "II" or sx != "OCBF":
        raise LeverError("bracing 'tension_rods' is accepted on a Zone II OCBF only (zone %s, longitudinal system %s)"
                         % (zone or "?", sx or "?"))
    return True, ("PEB-LEVERS bracing 'tension_rods' (market practice, NOT compliant with IS 800:2007 Section 12: 12.1 "
                  "applies to all zones; 12.7.2.1 KL/r <= 120 and 12.7.2.3 30-70 %% tension share are not met)")


def rod_area_mm2(d_mm):
    return math.pi * float(d_mm) ** 2 / 4.0


def rod_label(d_mm):
    return "ROD%d" % int(d_mm)


def is_rod(sec):
    s = str(sec or "").upper().replace(" ", "")
    return s.startswith("ROD") and s[3:].isdigit()


def rod_diameter(sec):
    return float(str(sec).upper().replace(" ", "")[3:])


def register_rod(label, fy=ROD_FY, fu=ROD_FU):
    """Register a tension-rod X-bracing diagonal 'ROD<d>' for the ANALYSIS model: each diagonal of the X pair is a
    half-area bar (a solid round of diameter d / sqrt 2), so that the pair with both diagonals active has the lateral
    stiffness of the single tension rod that really acts; the rod force is then 2 |N| of the model bar
    (rod_member_result).  The take-off doubles the model mass back (peb_checks.tonnage).  Properties are those of a
    solid round (section_type 'CHS' with t = D/2) so that the Section 12 brace rows can be evaluated -- they FAIL for
    a rod (KL/r, compression), which is the non-compliance the study reports."""
    import sections as S
    d = rod_diameter(label)
    De = d / math.sqrt(2.0)
    A = math.pi * De ** 2 / 4.0
    I = math.pi * De ** 4 / 64.0
    r = De / 4.0
    p = {"_units": "mm", "section_type": "CHS", "Type": "ROD", "source": "PEB-LEVERS tension rod M%d (half-area X-pair "
         "model of a round bar, IS 2062 E250 assumption)" % d, "A": A, "Ix": I, "Iy": I, "d": De, "bf": De, "tw": De / 2.0,
         "tf": De / 2.0, "rx": r, "ry": r, "r_min": r, "Sx": I / (De / 2.0), "Zx": De ** 3 / 6.0, "Sy": I / (De / 2.0),
         "Zy": De ** 3 / 6.0, "J": 2.0 * I, "Cw": 0.0, "Aw": 2.0 * A / math.pi, "ho": None,
         "Mass_kg_m": 2.0 * A * 7850.0 / 1e6, "grade": "E250 (rod)", "fy_MPa": fy, "fu_MPa": fu,
         "buckling_class": "c", "material_found": True, "rod_d_mm": d, "rod_model": "half_area_pair"}
    S.CUSTOM[S.normalize_label(label)] = p
    return p


def rod_member_result(mem, recs):
    """member_check_is800-shaped result for a tension-only rod brace: T = 2 |N| over every combination (the X pair is
    two half-area bars in the model; the real tension diagonal carries the panel force alone)."""
    import static_model as SM
    d = rod_diameter(mem["section"])
    best = None
    per = []
    for lab, r in (recs or {}).items():
        r = list(r) + [0.0] * (len(SM.REC_FIELDS) - len(r))
        T = 2.0 * abs(float(r[0]))
        c = rod_tension_check(d, T)
        per.append({"combo": lab, "T_N": T, "dc": c["dc"], "ok": c["ok"]})
        if best is None or c["dc"] > best[1]["dc"]:
            best = (lab, c)
    if best is None:
        return {"found": False, "ok": None, "dc": None, "reason": "no combination forces"}
    lab, c = best
    return {"id": mem.get("id"), "section": mem["section"], "role": mem.get("role"), "found": True, "dc": c["dc"],
            "ok": c["ok"], "value": c["dc"], "limit": 1.0, "governing_check": "tension rod (IS 800 6.2 / 6.3)",
            "governing_combo": lab, "clause": c["clause"],
            "cite": "PEB-LEVERS bracing 'tension_rods': T = 2 |N| of the half-area model bar = %.1f kN (%s); %s" % (
                c["T_N"] / 1e3, lab, c["cite"]),
            "capacities": {"tension": {"Td_N": c["Td_N"], "Tdg_N": c["Tdg_N"], "Tdn_N": c["Tdn_N"]}},
            "per_combo": per, "flags": ["tension-only rod: compression not resisted (market practice; NOT compliant "
                                        "with IS 800 12.7.2.1 / 12.7.2.3)"]}


def rod_tension_check(d_mm, T_N, *, fy=ROD_FY, fu=ROD_FU, gamma_m0=1.10, gamma_m1=1.25):
    """Round bar in tension: gross yielding of the shank 6.2 (Ag fy / gamma_m0) and rupture at the thread 6.3
    (0.9 An fu / gamma_m1, An = the IS 4000 Table 2 tensile stress area, as IS 800 10.3.5 takes it for threads)."""
    import india_connections as C
    Ag = rod_area_mm2(d_mm)
    An = (C.IS4000_STRESS_AREA_MM2.get(int(d_mm)) or (None, None))[1]
    if An is None:
        raise LeverError("rod M%s: no IS 4000 Table 2 stress area in india_connections (sizes %s)"
                         % (d_mm, sorted(C.IS4000_STRESS_AREA_MM2)))
    Tdg = Ag * fy / gamma_m0
    Tdn = 0.9 * An * fu / gamma_m1
    Td = min(Tdg, Tdn)
    return {"d_mm": d_mm, "Ag_mm2": Ag, "An_mm2": An, "Tdg_N": Tdg, "Tdn_N": Tdn, "Td_N": Td, "T_N": T_N,
            "dc": abs(T_N) / Td if Td else None, "ok": abs(T_N) <= Td,
            "clause": "IS 800:2007 6.2 / 6.3; 10.3.5 (tensile stress area at the thread, IS 4000 Table 2)",
            "cite": "Td = min(Ag fy/1.10 = %.0f kN, 0.9 An fu/1.25 = %.0f kN), An %.0f mm2; rod fy %.0f / fu %.0f MPa "
                    "(IS 2062 E250 round bar, assumption)" % (Tdg / 1e3, Tdn / 1e3, An, fy, fu)}
