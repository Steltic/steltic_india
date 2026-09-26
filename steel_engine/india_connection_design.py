"""HR-INTEGRATE wiring: the agent's DECLARED connection / base geometry (cfg['connections']) -> IS 800 checks.

cfg['connections'] = {
  'brace_end':    {<brace section> | 'default': {weld_type ('cjp'|'fillet'), bolt_type ('HSFG'|...), welds{size_mm|
                   cjp:{t_mm}, length_mm, fu_MPa|fy_MPa, n_sides, site}, bolts{n_bolts, d_mm, grade, t_mm,
                   fu_plate_MPa, e_mm, p_mm, d0_mm, lj_mm?, n_e? (10.4.3 effective interfaces, default 1), Kh? (10.4.3
                   hole factor, default 1.0), mu_f? (Table 20)}, gusset{t_mm, fy_MPa, fu_MPa, w_start_mm, L_conn_mm,
                   L_unbraced_mm, K, Avg_mm2, Avn_mm2, Atg_mm2, Atn_mm2}, An_mm2 (brace net area at the slot),
                   moment_capacity_Nmm?, system_max_force_N?, bolts_and_welds_share (bool), slip_surface?}},
  'beam_column':  {<beam section> | 'default': {type 'end_plate' {bolt rows...} | 'welded_cover_plate' {...},
                   shear: {fin plate / web bolts ...}, weld_type, bolt_type, continuity_plates, doubler_t_mm, cite}},
  'beam_shear':   {<beam section> | 'default': fin_plate_shear_checks inputs (gravity beams)},
  'column_base':  {<column section> | 'default': base_plate_design geometry (B_mm, L_mm, t_plate_mm, fy_plate_MPa,
                   fck_MPa, anchors{n_total, n_tension, d_mm, grade, f_mm, pitch_mm, edge_mm, n_per_row},
                   Ec_MPa? (default IS 456 5000 sqrt fck), embedment{capacity_N, cite}?, fixed (bool), Hc_mm?)},
  'column_splice': {<upper column section> | 'default': column_splice_checks 'splice' dict | {'none': True, note}},
}
Capacities are computed here from that geometry with india_connections (never from the demand).  Missing geometry
-> ok None (blocks COMPLETE).  Units N, mm, MPa.
"""
from __future__ import annotations

import math

import india_connections as C
import india_is800 as I8

SRC = "steel_engine/india_connection_design.py"


def spec_for(cfg, kind, section, role=None):
    specs = ((cfg or {}).get("connections") or {}).get(kind) or {}
    if not isinstance(specs, dict):
        return None
    for key in ((role, section), "%s:%s" % (role, section), section, role, "default"):
        if key in specs and isinstance(specs[key], dict):
            return dict(specs[key])
    return None


def _props(sec, member=None):
    import sections as S
    if str(sec).upper().startswith(("CHS", "NB")) and member:
        return S.props(sec, grade=member.get("grade"), process=member.get("process"))
    return S.props(sec)


def _fy(member, p):
    m = I8.material_for_section(p, member.get("grade"), process=member.get("process"))
    return m.get("fy_MPa"), m.get("fu_MPa")


# ------------------------------------------------------------------------------------------ braces
def brace_end_connection(cfg, member):
    """model_data 'connections' entry (kind brace_end) for one brace member from cfg['connections']['brace_end'];
    the weld capacity input is normalised so india_is800_s12.brace_connection_checks can call
    fillet_weld_capacity_is800_N / cjp_weld_capacity_N."""
    sp = spec_for(cfg, "brace_end", member["section"], "brace")
    if not sp:
        return None
    conn = {"id": "conn-%s" % member["id"], "member_id": member["id"], "kind": "brace_end"}
    conn.update({k: v for k, v in sp.items() if k not in ("welds",)})
    w = sp.get("welds")
    if w:
        w = dict(w)
        if w.get("cjp") or str(sp.get("weld_type") or "").lower() in ("cjp", "complete_penetration"):
            cj = dict(w.get("cjp") or {})
            conn["welds_cjp"] = {"t_mm": cj.get("t_mm") or w.get("t_mm"), "length_mm": w.get("length_mm"),
                                 "fy_MPa": cj.get("fy_MPa") or w.get("fy_MPa"), "n_sides": w.get("n_sides", 1),
                                 "site": w.get("site", False)}
        else:
            conn["welds"] = {k: v for k, v in w.items() if k in ("size_mm", "length_mm", "fu_MPa", "n_sides", "angle_deg",
                                                                 "site", "lj_mm", "throat_mm")}
    return conn


# ------------------------------------------------------------------------------------------ beam-column joints
def beam_column_connection(cfg, beam_member, p_beam, fy_beam, *, col_props=None):
    """joint['connection'] for the S12 SMF/OMF joint checks: moment capacity (end plate 10.3.5/10.4.7 or cover-plated
    CJP 8.2.1.2/10.5.7.1.2) and shear capacity (fin/web bolts + plate + weld), from declared geometry."""
    sp = spec_for(cfg, "beam_column", beam_member["section"], "beam")
    if not sp:
        return None
    typ = str(sp.get("type") or "").lower()
    out = {"type": typ, "weld_type": sp.get("weld_type"), "bolt_type": sp.get("bolt_type"), "cite": sp.get("cite"),
           "source": SRC}
    if typ == "end_plate":
        ep = dict(sp.get("end_plate") or {})
        r = C.end_plate_moment_capacity(**ep)
        out["moment"] = r
        out["moment_capacity_Nmm"] = r.get("capacity_Nmm")
        out["bolt_type"] = out["bolt_type"] or ep.get("bolt_type", "HSFG")
        out["cite"] = out["cite"] or r.get("cite")
    elif typ in ("welded_cover_plate", "cover_plate"):
        cp = dict(sp.get("cover_plate") or {})
        r = C.cover_plate_moment_capacity(Zp_beam_mm3=p_beam["Zx"], fy_beam_MPa=fy_beam, d_beam_mm=p_beam["d"], **cp)
        out["moment"] = r
        out["moment_capacity_Nmm"] = r.get("capacity_Nmm")
        out["weld_type"] = out["weld_type"] or "cjp"
        out["cite"] = out["cite"] or r.get("cite")
    elif typ in ("welded", "cjp"):
        # direct CJP flange welds: the connection develops the beam section at the face (Zp fy/gamma_m0)
        out["moment_capacity_Nmm"] = p_beam["Zx"] * fy_beam / C.GAMMA_M0
        out["weld_type"] = out["weld_type"] or "cjp"
        out["cite"] = out["cite"] or "IS 800:2007 10.5.7.1.2 (CJP = parent metal): Zp fy/gamma_m0 at the column face"
    sh = sp.get("shear")
    if sh:
        out["shear"] = C.fin_plate_shear_checks(V_N=float(sh.pop("V_N", 0.0) or 0.0), **sh) if "V_N" in sh else None
        out["shear_spec"] = sh
        if out["shear"] is None:
            # capacity only (demand applied at the joint): evaluate with a unit demand, keep the capacity
            r = C.fin_plate_shear_checks(V_N=1.0, **sh)
            out["shear_capacity_N"] = r.get("capacity_N")
            out["shear_detail"] = r
    for k in ("continuity_plates", "continuity_plate_t_mm", "doubler_t_mm", "max_deliverable_moment_Nmm", "rbs"):
        if k in sp:
            out[k] = sp[k]
    return out


def beam_shear_connection_checks(cfg, beam_member, V_N, *, sfrs=False):
    """Simple beam-end (shear) connection of a gravity beam under its governing shear."""
    sp = spec_for(cfg, "beam_shear", beam_member["section"], "beam")
    if not sp:
        return None
    keys = ("t_plate_mm", "h_plate_mm", "fy_plate_MPa", "fu_plate_MPa", "bolts", "weld", "block_shear_areas", "cjp")
    sp = {k: v for k, v in sp.items() if k in keys}
    r = C.fin_plate_shear_checks(V_N=float(V_N), **sp)
    return r


# ------------------------------------------------------------------------------------------ column bases / splices
def base_entry(cfg, col_member, load_cases):
    """model_data 'bases' entry with the declared base geometry and the per-combination (P, M, V) of the column."""
    # keyed by 'lateral_col:<section>' / 'gravity_col:<section>' (role group) before the bare section (WP6: one rolled
    # section can serve both an SFRS column with a fixed base and a gravity column with a pinned base)
    sp = spec_for(cfg, "column_base", col_member["section"], col_member.get("role_group") or "column")
    if not sp:
        return None
    b = {"id": "base-%s" % col_member["id"], "column_member_id": col_member["id"], "fixed": bool(sp.get("fixed", True)),
         "axis": sp.get("axis", "z"), "load_cases": load_cases}
    for k, v in sp.items():
        if k not in ("fixed", "axis"):
            b[k] = v
    return b


def is_seismic_combo(label, tags=None):
    """A combination that carries the earthquake load (IS 800 Table 4 EL rows, 12.2.3, IS 18168 5.5): the only cases
    the 12.12.1 / IS 18168 9.3 capacity moment is paired with (H08)."""
    t = set(tags or [])
    return bool(t & {"is800_12_2_3", "is18168_5_5"}) or ("EQ" in str(label or "") and not str(label).startswith("SLS"))


def base_load_cases(records, *, kind="col", major_plane_is_frame=True, tags_of=None):
    """(P, Mz, My, V) per combination for the base of a column from its per-combination records (N tension +;
    Mmaj_i / Mmin_i are the moments at the i end = base end for columns built bottom-up).  H08: the major and minor
    moments are kept separately (the base is checked about both axes); M_Nmm = |Mz| (major axis); V_N is the
    resultant of the two shears; 'seismic' marks the combinations with EL (12.2.3 / 5.5 / Table 4 EL)."""
    import static_model as SM
    out = []
    for lab, r in (records or {}).items():
        r = list(r) + [0.0] * (len(SM.REC_FIELDS) - len(r))
        d = dict(zip(SM.REC_FIELDS, r))
        Mz, My = abs(d["Mmaj_i"]), abs(d["Mmin_i"])
        V = math.hypot(d["Vmaj"], d["Vmin"])
        out.append({"combo": lab, "P_N": -d["N"], "M_Nmm": Mz, "Mz_Nmm": Mz, "My_Nmm": My, "V_N": V,
                    "V_maj_N": abs(d["Vmaj"]), "V_min_N": abs(d["Vmin"]),
                    "seismic": is_seismic_combo(lab, (tags_of or {}).get(lab))})
    return out


def column_splice(cfg, col_member, p, fy, records, *, sfrs, tags_of=None, seismic_cfg=None, tie_force_N=None,
                  Hc_mm=None, Zx_lower_mm3=None):
    """Column splice of the upper-column group: every (combination, element) record is one concurrent case
    (P, Mz, My) (H10); cases tagged 12.2.3 / IS 18168 5.5 carry family '5.5'.  seismic_cfg = the Section 12 cfg
    (zone, occupancy, apply_is18168) for the IS 18168 7.5 / 12.2.4.6 / 12.3.4.7 rules of SFRS columns."""
    sp = spec_for(cfg, "column_splice", col_member["section"], col_member.get("role_group") or "column")
    if not sp:
        return None
    if sp.get("none"):
        return {"found": True, "none": True, "note": sp.get("note") or "no splice in this column length",
                "checks": {"no_splice": {"value": None, "limit": None, "dc": None, "ok": True, "gate": True,
                                         "clause": "IS 800:2007 12.5.2 (not applicable: no splice)",
                                         "cite": "column continuous over this length (declared)"}}}
    import static_model as SM
    cases = []
    for lab, r in (records or {}).items():
        d = dict(zip(SM.REC_FIELDS, list(r) + [0.0] * (len(SM.REC_FIELDS) - len(r))))
        base = str(lab).split("@")[0]
        tg = set((tags_of or {}).get(base) or [])
        fam = "5.5" if (tg & {"is18168_5_5", "is800_12_2_3"} or "[col]" in base) else "table4"
        cases.append({"combo": lab, "P_N": -d["N"], "Mz_Nmm": abs(d["Mmaj"]), "My_Nmm": abs(d["Mmin"]),
                      "V_N": max(abs(d["Vmaj"]), abs(d["Vmin"])), "family": fam})
    P = max([abs(c["P_N"]) for c in cases] + [0.0])
    M = max([c["Mz_Nmm"] for c in cases] + [0.0])
    a18 = None
    if sfrs and seismic_cfg is not None:
        import india_is800_s12 as S12
        st = S12.is18168_status(cfg.get("system"), seismic_cfg)
        comps = S12.system_components(cfg.get("system"))
        sys18 = "EBF" if "EBF" in comps else ("SCBF" if "SCBF" in comps else ("SMRF" if "SMF" in comps else None))
        ry, _ = S12._ry(col_member, p)
        a18 = {"applies": bool(st.get("applies")) and sys18 is not None, "system": sys18, "Ry": ry}
    return C.column_splice_checks(sfrs=sfrs, Af_mm2=p["bf"] * p["tf"], fy_MPa=fy, P_N=P, M_Nmm=M, Zx_mm3=p["Zx"],
                                  A_mm2=p["A"], d_mm=p["d"], splice=sp, cases=cases, bf_mm=p["bf"], tf_mm=p["tf"],
                                  tw_mm=p["tw"], is18168=a18, tie_force_N=tie_force_N, Hc_mm=Hc_mm,
                                  Zx_lower_mm3=Zx_lower_mm3)


# ------------------------------------------------------------------------------------------ HSFG slip (10.4.3)
def hsfg_slip_checks(bolts, bolt_type, V_service_N, V_ultimate_N=None, *, slip_surface=None, mu_f=None,
                     slip_at_ultimate=False):
    """IS 800 10.4.3: Vsf <= Vdsf = mu_f ne Kh F0 / gamma_mf, gamma_mf 1.10 at service (1.25 when slip is designed
    at ultimate).  12.4.1 makes SFRS bolts HSFG; the service check uses the SLS combination force."""
    if not bolts or not bolt_type or "hsfg" not in str(bolt_type).lower() and "friction" not in str(bolt_type).lower():
        return None
    b = dict(bolts)
    n = int(b.get("n_bolts") or 0)
    if not n:
        return None
    out = {}
    one = C.hsfg_slip_capacity(b["d_mm"], b.get("grade", "8.8"), mu_f=mu_f, surface=slip_surface,
                               n_e=b.get("n_e", 1), Kh=b.get("Kh", 1.0), gamma_mf=C.GAMMA_MF_SERVICE, lj_mm=b.get("lj_mm"))
    if one.get("found"):
        out["slip_service_10_4_3"] = C._check(abs(float(V_service_N)), n * one["Vdsf_N"], clause="IS 800:2007 10.4.3",
                                              cite="service-load slip: n x mu_f ne Kh F0/1.10 (Table 20 mu_f)",
                                              mu_f=one["mu_f"], gamma_mf=1.10, n_bolts=n)
        if slip_at_ultimate and V_ultimate_N is not None:
            u = C.hsfg_slip_capacity(b["d_mm"], b.get("grade", "8.8"), mu_f=mu_f, surface=slip_surface,
                                     n_e=b.get("n_e", 1), Kh=b.get("Kh", 1.0), gamma_mf=C.GAMMA_MF_ULTIMATE,
                                     lj_mm=b.get("lj_mm"))
            out["slip_ultimate_10_4_3"] = C._check(abs(float(V_ultimate_N)), n * u["Vdsf_N"], clause="IS 800:2007 10.4.3",
                                                   cite="slip at ultimate load: gamma_mf 1.25", gamma_mf=1.25)
    else:
        out["slip_service_10_4_3"] = C._check(None, None, clause="IS 800:2007 10.4.3", cite="slip resistance", ok=None,
                                              reason="mu_f (Table 20 surface) missing: %s" % one.get("required_inputs"))
    return out


# ------------------------------------------------------------------------------------------ composite (WP2.9)
def construction_stage_elements(cfg, beam_elems):
    """H40 (HR-C-05, HR-D-06, NEW): the unshored wet-concrete check per floor-beam ELEMENT (role 'floor' only -- not
    keyed by section, so a section used as floor-X and roof-Y is not skipped), per direction (with cfg['deck_span'] a
    beam parallel to the deck span carries no wet deck), with the tributary of the bays actually present (nb = 1 on
    an edge beam: half a bay) and the element's own grade (grade_by_section).
    beam_elems = [{tag, section, role, dir 'X'|'Y', L_mm, nb (bays present beside the beam, 0-2), grade}].
    Returns the worst {DC, ...} or None."""
    cs = cfg.get("construction_stage") or {}
    ds = str(cfg.get("deck_span") or "").upper()
    worst = None
    cache = {}
    for e in beam_elems or []:
        if e.get("role") != "floor":
            continue
        d = str(e.get("dir") or "").upper()
        if ds in ("X", "Y") and d == ds:
            continue                                    # parallel to the deck span: no wet-deck load
        S_across = float(cfg["SY"] if ds == "Y" else cfg["SX"]) if ds in ("X", "Y") else min(float(cfg["SX"]), float(cfg["SY"]))
        nb = max(min(int(e.get("nb") if e.get("nb") is not None else 2), 2), 1)
        trib = float(cs.get("trib_mm") or nb * S_across / 2.0)
        L = float(e["L_mm"])
        grade = e.get("grade") or cfg.get("steel_grade")
        LLT = float(cs.get("LLT_mm") or L)
        key = (e["section"], grade, round(L, 1), round(trib, 1), LLT)
        if key not in cache:
            w = (1.5 * float(cs["D_wet_kNm2"]) + 1.5 * float(cs.get("L_const_kNm2") or 0.0)) * trib / 1000.0
            M = w * L * L / 8.0
            res = I8.member_check_is800({"id": "wet-e%s" % e.get("tag"), "section": e["section"], "grade": grade,
                                         "role": "beam", "L_mm": L, "LLT_sag_mm": LLT},
                                        [{"combo": "1.5Dwet+1.5Lconst", "P_N": 0.0, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0,
                                          "Mz_mid_Nmm": M, "Vy_N": w * L / 2.0}])
            cache[key] = (res, M)
        res, M = cache[key]
        if res.get("dc") is not None and (worst is None or res["dc"] > worst["DC"]):
            worst = {"DC": res["dc"], "section": e["section"], "element": e.get("tag"), "dir": d, "nb": nb,
                     "trib_mm": trib, "grade": grade, "M_Nmm": M, "combo": "1.5Dwet+1.5Lconst", "LLT_mm": LLT,
                     "capacity": res.get("capacities", {}).get("Mdz_section"),
                     "basis": "per element and direction; tributary nb x bay/2 (edge beam: half a bay); "
                              "element grade (H40)"}
    return worst


def composite_design_record(cfg, pkg_members, beam_dirs=None, beam_elems=None):
    """WP2.9: IS 11384 is not in the corpus -> found:false slots; scope 'bare_steel' is satisfied by the IS 800 8.2 /
    9.3 member checks already in the package plus a construction-stage (unshored wet concrete) check of the floor
    beams with the compression flange unrestrained until the deck is fixed (cfg['construction_stage']).
    beam_dirs = {section: {'X','Y'}} (WP6-fix): with cfg['deck_span'] declared, a beam group parallel to the deck span
    carries no wet-deck load and is not wet-stage checked; the others take the full bay width (conservative)."""
    rec = I8.composite_is11384_worksheet_stubs(cfg)
    scope = str(cfg.get("composite_scope") or "").lower()
    if scope not in ("bare_steel", "bare-steel"):
        return rec
    for s in rec["slots"]:
        if s["component"] == "bare_steel_8_2":
            fl = [m for m in pkg_members if m["inputs"].get("role") in ("floor", "roof")]
            ok = bool(fl) and all(isinstance(m.get("DC"), (int, float)) for m in fl)
            s.update(found=ok, DC=max([m["DC"] for m in fl if isinstance(m.get("DC"), (int, float))] or [None]),
                     cited="IS 800:2007 8.2.1.2 / 8.2.2 / 9.3 via member_check_is800 (members[])",
                     note="bare-steel scope: every floor/roof beam checked in members[] (no composite action relied on)")
        if s["component"] == "construction_stage":
            cs = cfg.get("construction_stage")
            if not cs:
                s["note"] = ("construction stage not declared: cfg['construction_stage'] = {D_wet_kNm2, L_const_kNm2, "
                             "LLT_mm (compression-flange restraint before the deck is fixed)}")
                continue
            worst = None
            ds = str(cfg.get("deck_span") or "").upper()
            if beam_elems is not None:
                worst = construction_stage_elements(cfg, beam_elems)
            for m in ([] if beam_elems is not None else pkg_members):
                if m["inputs"].get("role") != "floor":
                    continue
                sec = m["inputs"]["section"]
                dirs = (beam_dirs or {}).get(sec)
                if ds in ("X", "Y") and dirs and set(dirs) <= {ds}:
                    continue                                    # parallel to the deck span: no wet-deck load
                L = float(m["inputs"]["length_mm"])
                if ds in ("X", "Y") and dirs:
                    trib = float(cs.get("trib_mm") or (cfg["SY"] if ds == "Y" else cfg["SX"]))   # one-way: the bay across
                else:
                    trib = float(cs.get("trib_mm") or min(cfg["SX"], cfg["SY"]))
                w = (1.5 * float(cs["D_wet_kNm2"]) + 1.5 * float(cs.get("L_const_kNm2") or 0.0)) * trib / 1000.0
                M = w * L * L / 8.0
                res = I8.member_check_is800({"id": "wet-" + sec, "section": sec, "grade": cfg.get("steel_grade"),
                                             "role": "beam", "L_mm": L, "LLT_sag_mm": float(cs.get("LLT_mm") or L)},
                                            [{"combo": "1.5Dwet+1.5Lconst", "P_N": 0.0, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0,
                                              "Mz_mid_Nmm": M, "Vy_N": w * L / 2.0}])
                if res.get("dc") is not None and (worst is None or res["dc"] > worst["DC"]):
                    worst = {"DC": res["dc"], "section": sec, "M_Nmm": M, "combo": "1.5Dwet+1.5Lconst",
                             "LLT_mm": float(cs.get("LLT_mm") or L), "capacity": res.get("capacities", {}).get("Mdz_section")}
            if worst:
                s.update(found=True, DC=worst["DC"], capacity={"Md_Nmm": (worst["capacity"] or {}).get("Md_Nmm")},
                         cited="IS 800:2007 8.2.2 (unrestrained compression flange, LLT = %.0f mm)" % worst["LLT_mm"],
                         detail=worst, value=worst["M_Nmm"], limit=(worst["M_Nmm"] / worst["DC"]) if worst["DC"] else None)
        if s["component"] in ("is11384_composite_strength", "is11384_shear_connectors"):
            s["note"] += "; bare-steel scope: composite action not relied on (not required)"
            s["not_required"] = True
    live = [s for s in rec["slots"] if not s.get("not_required")]
    rec["blocks_complete"] = not all(s.get("found") for s in live)
    rec["scope"] = "bare_steel"
    return rec
