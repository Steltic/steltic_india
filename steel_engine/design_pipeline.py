"""
design_pipeline.py  --  India (IS/BIS) load combinations + per-member DEMAND envelope. NO capacities.

Load combinations and lateral story forces come from cfg['load_plan'], which the agent MUST fill
after LIVE RAG queries to IS 875 Parts 1–5 and IS 1893 Part 1:2016 (see india_loads.py).
This module does **not** embed ASCE 7-22 or permanent IS load formulas — retrieval is mandatory
every job, same pattern as design RAG for IS 800.

It writes the demand package (member_schedule.csv, member_demands.md, calc_package.json,
connection_demands.csv, design_report.md).

It does **NOT** compute any IS 800 member capacity or D/C — there is no coded capacity anywhere
in this repo. The design agent must query the IS 800 / IS 808 / IS 816 / IS 4000 RAG, derive each
governing limit-state equation itself, compute the capacity and D/C, cite the clause, and fill
them into calc_package.json.

Run:  python design_pipeline.py <building>
"""
import os, sys, math, csv, json
import openseespy.opensees as ops
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
import engine3d as E
import sections as S
from design_post import run_case   # analysis/demand extraction only (no capacities)
import india_loads as IL

# ---------- build the combination set from RAG-backed load_plan (India) ----------
def combos(cfg):
    """Return LRFD/partial-factor cases from cfg['load_plan'] only.

    USA steltic hardcodes ASCE 7-22 §2.3 combos + elf()/wind_forces() here.
    steltic_india refuses that path: the agent retrieves IS 875 / IS 1893 / IS 800
    Table 4 factors LIVE and writes them into cfg['load_plan'].
    """
    return IL.cases_from_load_plan(cfg)




def _section12_component_stubs(role="brace"):
    """H5: IS 800 §12 gusset/bolt/weld D/C worksheet slots (structure only).

    Brace capacity-design *demand* is already written on the connection. These stubs
    give the agent empty slots so a RAG miss does not become invented sizes/capacities.
    found:false until the agent fills from IS 800 / IS 816 / IS 4000 retrieval.

    complete-gap wave1: slots list required_inputs and accept fill via
    india_is800.fill_connection_component_dc when RAG+cfg provide fy/Ag/demand + capacity.
    """
    try:
        import india_is800 as I8
        req = I8.CONN_COMPONENT_REQUIRED
    except Exception:
        req = {
            "gusset": ["demand_N", "capacity_N", "cited"],
            "bolts": ["demand_N", "capacity_N", "cited"],
            "welds": ["demand_N", "capacity_N", "cited"],
        }
    def _slot(component, note):
        return {
            "component": component,
            "limit_state": None,
            "cited": None,
            "capacity": {},
            "size": None,
            "DC": None,
            "found": False,
            "required_inputs": list(req.get(component, ["demand_N", "capacity_N", "cited"])),
            "note": note,
        }
    return {
        "status": "stubs",
        "cite": "IS 800:2007 §12 (seismic connections) / §10; IS 816 welds; IS 4000 HSFG",
        "policy": (
            "Fill from LIVE RAG only. Do not invent bolt grade/diameter, weld size, or "
            "gusset thickness when retrieval misses — leave found:false. "
            "When fy/Ag (or demand_N) and a RAG capacity_N are both available, use "
            "india_is800.fill_connection_component_dc to write D/C — still no invented capacities."
        ),
        "fill_helper": "india_is800.fill_connection_component_dc",
        "slots": [
            _slot("gusset",
                  "Gusset plate: thickness/Fy/Whitmore/block shear — RAG IS 800; found:false until sized."),
            _slot("bolts",
                  "Bolt group: n, diameter, grade, shear/bearing/slip — RAG IS 800 §10 / IS 4000; found:false until sized."),
            _slot("welds",
                  "Weld(s): size/length/electrode — RAG IS 816 / IS 800; found:false until sized."),
        ],
    }


def _section12_smf_worksheets():
    """complete-gap wave1: SMF SCWB + panel-zone worksheets (compute when data available)."""
    try:
        import india_is800 as I8
        return I8.section12_smf_worksheets_stub()
    except Exception as ex:
        return {
            "status": "stubs_error",
            "error": str(ex),
            "SCWB": {"found": False, "required_inputs": ["column_Mp", "beam_Mp"]},
            "panel_zone": {"found": False, "required_inputs": ["column geometry", "V_design"]},
        }


def _composite_chI_worksheet_stubs():
    """H6: IS 800 Ch. I composite floor worksheet slots (structure only).

    Parallel to §12 stubs: give empty found:false slots so agents do not invent
    stud schedules, camber, or wet-stage D/C when IS 800 Ch. I retrieval misses
    or composite is out of scope. Fill from LIVE RAG or record an explicit scope
    statement — never invent numbers.
    """
    def _slot(component, note):
        return {
            "component": component,
            "limit_state": None,
            "cited": None,
            "capacity": {},
            "size": None,
            "DC": None,
            "found": False,
            "note": note,
        }
    return {
        "status": "stubs",
        "cite": "Composite construction is outside IS 800:2007 (IS 11384 not in the corpus) -- see COMPOSITE_INDIA.md",
        "policy": (
            "Fill from LIVE IS 800 Ch. I RAG only, or record an explicit composite scope "
            "statement (bare-steel lower bound / excluded / delegated). Do not invent stud "
            "count, camber, or wet-stage D/C when retrieval misses — leave found:false."
        ),
        "qfm_scope": "H6 — composite Ch.I not auto-designed; stubs prevent invention",
        "slots": [
            _slot("b_eff",
                  "Effective width b_eff — RAG IS 800 Ch. I; found:false until retrieved."),
            _slot("studs",
                  "Shear connectors: n, diameter, Qn/Rd — RAG IS 800 Ch. I; found:false until sized."),
            _slot("partial_composite",
                  "Degree of shear connection / partial composite % — RAG; found:false until set."),
            _slot("camber",
                  "Camber decision (even 'none') with wet deflection shown — found:false until decided."),
            _slot("wet_stage",
                  "Unshored wet-concrete / construction-stage check — found:false until checked."),
            _slot("I_LB_deflection",
                  "Service deflection on lower-bound I — RAG; found:false until checked."),
        ],
    }


# ---------- DEMAND envelope (analysis only; NO IS 800 capacities) ----------
def design(name, outdir=None):
    """Run India load_plan combinations through P-Delta and write the per-member DEMAND
    envelope + connection demands. NO capacities / D-C are computed -- the design agent derives
    every IS 800 check from the RAG and fills them into calc_package.json."""
    cfg = E.CFG[name]
    base = os.path.dirname(os.path.abspath(__file__))
    outdir = outdir or os.path.join(base, "buildings", name, "design")
    os.makedirs(outdir, exist_ok=True)
    if E._india_job(cfg):
        return design_india(name, cfg, outdir)
    cases = combos(cfg)
    try:
        from india_units import is_si, display_scale, demand_field_names
        _SI = is_si(cfg)
        _SC = display_scale(cfg)
        _FN = demand_field_names(cfg)
    except Exception:
        _SI = str(cfg.get("units") or "").upper().startswith("N-MM")
        _SC = {"si": _SI, "force_div": 1000.0 if _SI else 1.0, "moment_div": 1e6 if _SI else 12.0,
               "E_default": 200000.0 if _SI else 29000.0, "Fy_default": 250.0 if _SI else 50.0}
        _FN = None

    info0 = E.build(cfg, "PDelta")
    reg = {t: (kind, sec, n1, n2) for (t, kind, sec, n1, n2) in info0["ele"]}
    length = {t: math.dist(ops.nodeCoord(n1), ops.nodeCoord(n2)) for t, (k, s, n1, n2) in reg.items()}

    prop = {}
    def P(sec):
        if sec not in prop:
            try: prop[sec] = S.props(sec, SEC=E.SEC)
            except Exception: prop[sec] = None
        return prop[sec]

    # ---- DEMANDS from the SINGLE distributed static model (gravity-correct column axial / base
    #      reactions; one-way vs two-way girder moment per cfg["floor_system"]). Two-key DISK cache:
    #      gravity solved ONCE (size-invariant when the gravity path is determinate / pinned joints),
    #      seismic keyed on the LATERAL members' sections so it is reused while only gravity members
    #      change. Keyed by frozenset of corner nodes -> mapped onto the dynamic-model element tags. ----
    import static_model as SM
    brace_lines = set(); 
    for (t, kind, sec, n1, n2) in info0["ele"]:
        if kind == "brace":
            for nd in (n1, n2): brace_lines.add(((nd % 100000)//100, nd % 100))
    moment_lines = {((nd % 100000)//100, nd % 100) for nd in info0.get("moment_nodes", set())}
    lat_lines = brace_lines | moment_lines
    def _is_lat(t):
        k, sec, n1, n2 = reg[t]
        return True if k == "brace" else (((n1 % 100000)//100, n1 % 100) in lat_lines)
    sec_sig = repr(sorted(reg[t][1] for t in reg))                            # full schedule (indeterminate gravity)
    lat_sig = repr(sorted(reg[t][1] for t in reg if _is_lat(t)))             # lateral-system sections (seismic key)
    determinate = str((cfg.get("model") or {}).get("joints", "")).lower() == "pinned"
    senv, _kinds = SM.demand_envelope(cfg, cases, nseg=int(cfg.get("demand_nseg", 6)),
                                      floor_system=cfg.get("floor_system", "one-way"),
                                      determinate=determinate, sec_sig=sec_sig, lat_sig=lat_sig,
                                      cache_dir=outdir)
    env = {t: dict(comp=0.0, tens=0.0, Mz=0.0, My=0.0, V=0.0, combo="") for t in reg}
    score = {t: -1.0 for t in reg}
    for t in reg:
        se = senv.get(frozenset((reg[t][2], reg[t][3])))
        if se:
            env[t] = dict(comp=se["comp"], tens=se["tens"], Mz=se["Mz"], My=se["My"], V=se["V"], combo=se["combo"])
        score[t] = (max(env[t]["comp"], env[t]["tens"]) if reg[t][0] in ("col", "brace") else env[t]["Mz"])

    # ---- member_schedule.csv (every element: DEMANDS only; SI headers when N-mm) ----
    _mdiv = _SC["moment_div"]
    with open(os.path.join(outdir, "member_schedule.csv"), "w", newline="") as f:
        w = csv.writer(f)
        if _SI:
            w.writerow(["ele_tag", "member", "section", "length_mm", "P_comp_N", "P_tens_N",
                        "Mx_kNm", "My_kNm", "V_N", "governing_combo", "unit_system"])
            for t in sorted(reg):
                kind, sec, n1, n2 = reg[t]; e = env[t]
                w.writerow([t, kind, sec, round(length[t], 1), round(e["comp"], 1), round(e["tens"], 1),
                            round(e["Mz"]/_mdiv, 3), round(e["My"]/_mdiv, 3), round(e["V"], 1),
                            e["combo"], "N-mm"])
        else:
            w.writerow(["ele_tag", "member", "section", "length_in", "P_comp_kip", "P_tens_kip",
                        "Mx_kipft", "My_kipft", "V_kip", "governing_combo"])
            for t in sorted(reg):
                kind, sec, n1, n2 = reg[t]; e = env[t]
                w.writerow([t, kind, sec, round(length[t], 1), round(e["comp"], 1), round(e["tens"], 1),
                            round(e["Mz"]/12, 1), round(e["My"]/12, 1), round(e["V"], 1), e["combo"]])

    # ---- member_demands.md (summary by type; capacities are the AGENT's job) ----
    # group by (kind, section, ROLE), with the group demand = max of EVERY component over ALL members
    # in the group (not one max-moment representative) so axial-governed members are not understated,
    # and auto-tag a role so the report places members without the agent re-deriving it (P3).
    braced = E.is_braced(cfg); NFlev = len(cfg["heights"])
    brace_lines = set()
    for (t, kind, sec, n1, n2) in info0["ele"]:
        if kind == "brace":
            for nd in (n1, n2): brace_lines.add(((nd % 100000) // 100, nd % 100))
    # B3: a column is LATERAL if a brace OR a rigid (moment) beam frames into it; otherwise GRAVITY.
    # moment_nodes (from the build) carries the nodes a non-released beam connects to, so perimeter
    # moment-frame columns auto-tag lateral_col and interior gravity columns auto-tag gravity_col -- the
    # agent no longer has to relabel interiors by hand.
    moment_lines = {((nd % 100000) // 100, nd % 100) for nd in info0.get("moment_nodes", set())}
    lateral_lines = brace_lines | moment_lines
    def _role(kind, n1, n2):
        if kind == "brace": return "brace"
        if kind == "beam":  return "roof" if (n1 // 100000) >= NFlev else "floor"
        ij = ((n1 % 100000) // 100, n1 % 100)                  # column line (i,j)
        return "lateral_col" if ij in lateral_lines else "gravity_col"
    role_of = {t: _role(reg[t][0], reg[t][2], reg[t][3]) for t in reg}
    by = {}
    for t in reg:
        kind, sec, n1, n2 = reg[t]; by.setdefault((kind, sec, role_of[t]), []).append(t)
    genv = {}
    for key, tags in by.items():
        gg = dict(comp=0.0, tens=0.0, Mz=0.0, My=0.0, V=0.0)
        for t in tags:
            e = env[t]
            for kk in ("comp", "tens", "Mz", "My", "V"): gg[kk] = max(gg[kk], e[kk])
        tg = max(tags, key=lambda t: score[t])
        gg["combo"] = env[tg]["combo"]; gg["L"] = max(length[t] for t in tags); genv[key] = gg
    with open(os.path.join(outdir, "member_demands.md"), "w") as f:
        f.write("# %s - member DEMAND envelope (IS 800 partial factors via load_plan, second-order P-Delta)\n\n" % name)
        f.write("Load combinations: %d (from cfg['load_plan'] after IS 875/1893 RAG; "
                "Omega0 [col]%s). Each run as a factored P-Delta case; demands enveloped per element.\n\n"
                % (len(cases), ", wind" if cfg.get("wind") else ""))
        f.write("> **Capacities and D/C are NOT computed here.** The framework provides demands only; "
                "the design agent derives each IS 800:2007 limit-state capacity (section classification, "
                "compression/tension/flexure/shear/interaction per IS 800) and IS 800 §12 seismic "
                "capacity-design checks from the RAG, computes D/C, cites the clause, and "
                "records them in calc_package.json.\n\n")
        if _SI:
            f.write("Unit system: **N-mm-sec** (display: P/V in N, Mx/My in kN·m). Stress checks use **MPa**.\n\n")
            f.write("| member type | section | n | governing combo | P_comp (N) | P_tens (N) | Mx (kN·m) | My (kN·m) | V (N) |\n")
        else:
            f.write("| member type | section | n | governing combo | P_comp | P_tens | Mx(k-ft) | My | V |\n")
        f.write("|---|---|---:|---|---:|---:|---:|---:|---:|\n")
        for key, tags in sorted(by.items()):
            kind, sec, role = key; g = genv[key]
            if _SI:
                f.write("| %s | %s | %d | %s | %.0f | %.0f | %.2f | %.2f | %.0f |\n"
                        % (role, sec, len(tags), g["combo"], g["comp"], g["tens"],
                           g["Mz"]/_mdiv, g["My"]/_mdiv, g["V"]))
            else:
                f.write("| %s | %s | %d | %s | %.0f | %.0f | %.0f | %.0f | %.0f |\n"
                        % (role, sec, len(tags), g["combo"], g["comp"], g["tens"], g["Mz"]/12, g["My"]/12, g["V"]))

    # ---- calc_package.json (DEMANDS only; agent adds limit_state / cited / capacity / DC) ----
    pkg = {"building": name, "code": "IS 800:2007 LSD",
           "unit_system": "N-mm" if _SI else "kip-in",
           "stress_unit": "MPa" if _SI else "ksi",
           "note": "Framework provides DEMANDS only. The agent must derive every capacity and D/C "
                   "from the IS 800 RAG and add 'limit_state', 'cited', 'capacity', and 'DC' to "
                   "each member and connection. India SI: forces N, moments N·mm (display kN·m), "
                   "stress MPa.", "members": [], "connections": []}
    _Edef = float(_SC.get("E_default", 200000.0 if _SI else 29000.0))
    _Fydef = float(_SC.get("Fy_default", 250.0 if _SI else 50.0))
    for key, tags in sorted(by.items()):
        kind, sec, role = key; g = genv[key]; L = g["L"]
        if _SI:
            inp = {"kind": kind, "role": role, "section": sec, "length_mm": round(L, 1)}
        else:
            inp = {"kind": kind, "role": role, "section": sec, "length_in": round(L, 1)}
        p = P(sec)
        if kind == "brace":
            inp.update(A=(E.HSS.get(sec) if hasattr(E, "HSS") else None), r=S.brace_r(sec))
        elif p:
            # Lp ≈ 0.095·ry·E/Fy (AISC F2 twin) — SI uses MPa; not an IS capacity (agent RAG).
            Lb_eff = min(L, 0.095*p["ry"]*_Edef/_Fydef) if kind == "beam" else L
            lb_key = "Lb_mm" if _SI else "Lb_in"
            inp.update(**{lb_key: round(Lb_eff, 1)}, A=p["A"], Ix=p["Ix"], Iy=p["Iy"], J=p["J"], Zx=p["Zx"],
                       Zy=round(p["Zy"], 1), Sx=round(p["Sx"], 1), Sy=round(p["Sy"], 1),
                       rx=round(p["rx"], 3), ry=round(p["ry"], 3),
                       Aw=round(p["Aw"], 2) if p.get("Aw") else None,
                       ho=round(p["ho"], 2) if p.get("ho") else None,
                       rts=round(p["rts"], 3) if p.get("rts") else None)
        if _SI:
            inp.update(P_comp_N=round(g["comp"], 2), P_tens_N=round(g["tens"], 2),
                       Mz_Nmm=round(g["Mz"], 1), My_Nmm=round(g["My"], 1), V_N=round(g["V"], 2),
                       governing_combo=g["combo"])       # WP1.12: no *_kip aliases holding N / N-mm
        else:
            inp.update(P_comp_kip=round(g["comp"], 2), P_tens_kip=round(g["tens"], 2),
                       Mz_kipin=round(g["Mz"], 1), My_kipin=round(g["My"], 1), V_kip=round(g["V"], 2),
                       governing_combo=g["combo"])
        pkg["members"].append({"id": "%s-%s" % (role, sec), "inputs": inp,
                               "limit_state": None, "cited": None, "capacity": {}, "DC": None})
    # ---- connections[] : DEMANDS only (agent fills capacity/D-C from IS 800 RAG) ----
    for key, tags in sorted(by.items()):
        kind, sec, role = key; e = genv[key]
        if kind == "beam":
            ctype = "beam-to-column (shear; + moment if MF)"
            if _SI:
                dem = {"V_N": round(e["V"], 1), "M_kNm": round(e["Mz"]/_mdiv, 3)}
            else:
                dem = {"V_kip": round(e["V"], 1), "M_kipft": round(e["Mz"]/12, 1)}
            basis = "IS 800 / IS 816 / IS 4000 connections; MF detailing per IS 800 (agent/RAG)"
        elif kind == "brace":
            ctype = "brace-to-gusset"
            if _SI:
                dem = {"axial_N": round(max(e["comp"], e["tens"]), 1)}
            else:
                dem = {"axial_kip": round(max(e["comp"], e["tens"]), 1)}
            basis = "IS 800 / IS 816 / IS 4000 connection; seismic capacity design per IS 800 §12 + IS 1893 (agent/RAG)"
        else:
            ctype = "column splice / base plate"
            if _SI:
                dem = {"P_N": round(e["comp"], 1), "M_kNm": round(e["Mz"]/_mdiv, 3)}
            else:
                dem = {"P_kip": round(e["comp"], 1), "M_kipft": round(e["Mz"]/12, 1)}
            basis = "IS 800 base plate / splice; foundation anchorage per applicable IS (agent/RAG)"
        entry = {"id": "conn-%s-%s" % (role, sec), "type": ctype, "section": sec,
                "demand": dem, "design_basis": basis,
                "limit_state": None, "cited": None, "capacity": {}, "DC": None}
        if kind == "brace":
            # H5: §12 worksheet stubs (gusset/bolt/weld) — CD demand already on dem when agent adds it
            entry["section12_worksheet"] = _section12_component_stubs("brace")
            entry["component_checks"] = {
                s["component"]: {
                    "limit_state": None, "cited": None, "capacity": {}, "DC": None,
                    "found": False, "note": s["note"],
                    "required_inputs": s.get("required_inputs"),
                }
                for s in entry["section12_worksheet"]["slots"]
            }
        elif kind == "col" or "base" in ctype.lower() or "column" in ctype.lower():
            # complete-gap wave1 / IN_Ex3: base-plate / weld component worksheets
            # wave4: pass cfg-supplied plate/anchor geometry + RAG formula inputs
            try:
                import india_is800 as I8
                _geom = (
                    (cfg.get("base_plate_geometry") if isinstance(cfg, dict) else None)
                    or (cfg.get("column_base_geometry") if isinstance(cfg, dict) else None)
                    or (cfg.get("splice_geometry") if isinstance(cfg, dict) else None)
                    or {}
                )
                _rag_base = {}
                if isinstance(cfg, dict):
                    _rm = cfg.get("connection_rag_capacities") or {}
                    if isinstance(_rm, dict):
                        _rag_base = (_rm.get("base") or _rm.get("col") or _rm.get("default") or {})
                bp = I8.base_plate_worksheet(
                    P_N=(dem.get("P_N") if isinstance(dem, dict) else None),
                    M_Nmm=((dem.get("M_kNm") or 0) * 1e6 if isinstance(dem, dict) and dem.get("M_kNm") else None),
                    cfg=cfg if isinstance(cfg, dict) else None,
                    geometry=_geom if isinstance(_geom, dict) else None,
                    capacity_bearing_N=(_rag_base.get("bearing", {}) or {}).get("capacity_N")
                        if isinstance(_rag_base.get("bearing"), dict)
                        else (_rag_base.get("bearing") if isinstance(_rag_base.get("bearing"), (int, float)) else None),
                    capacity_anchor_N=(_rag_base.get("anchors", {}) or {}).get("capacity_N")
                        if isinstance(_rag_base.get("anchors"), dict)
                        else (_rag_base.get("anchors") if isinstance(_rag_base.get("anchors"), (int, float)) else None),
                    bearing_stress_MPa=(
                        (_rag_base.get("bearing") or {}).get("bearing_stress_MPa")
                        if isinstance(_rag_base.get("bearing"), dict) else None
                    ),
                    bearing_factor=(
                        (_rag_base.get("bearing") or {}).get("bearing_factor")
                        if isinstance(_rag_base.get("bearing"), dict) else None
                    ),
                    capacity_one_anchor_N=(
                        (_rag_base.get("anchors") or {}).get("capacity_one_N")
                        if isinstance(_rag_base.get("anchors"), dict) else None
                    ),
                    cited=(_rag_base.get("cite") if isinstance(_rag_base, dict) else None),
                )
                # Optional splice/base Pn from same geometry + RAG
                try:
                    pn = I8.column_base_or_splice_Pn_capacity_N(
                        demand_P_N=(dem.get("P_N") if isinstance(dem, dict) else None),
                        cfg=cfg if isinstance(cfg, dict) else None,
                        geometry=_geom if isinstance(_geom, dict) else None,
                        capacity_bearing_N=(
                            (_rag_base.get("bearing") or {}).get("capacity_N")
                            if isinstance(_rag_base.get("bearing"), dict) else None
                        ),
                        capacity_anchor_N=(
                            (_rag_base.get("anchors") or {}).get("capacity_N")
                            if isinstance(_rag_base.get("anchors"), dict) else None
                        ),
                        bearing_stress_MPa=(
                            (_rag_base.get("bearing") or {}).get("bearing_stress_MPa")
                            if isinstance(_rag_base.get("bearing"), dict) else None
                        ),
                        bearing_factor=(
                            (_rag_base.get("bearing") or {}).get("bearing_factor")
                            if isinstance(_rag_base.get("bearing"), dict) else None
                        ),
                        capacity_one_anchor_N=(
                            (_rag_base.get("anchors") or {}).get("capacity_one_N")
                            if isinstance(_rag_base.get("anchors"), dict) else None
                        ),
                        cite=(_rag_base.get("cite") if isinstance(_rag_base, dict) else None),
                    )
                    entry["column_base_or_splice_Pn"] = pn
                except Exception as _pne:
                    entry["column_base_or_splice_Pn"] = {"found": False, "error": str(_pne)}
                entry["base_plate_worksheet"] = bp
                entry["component_checks"] = {
                    s["component"]: {
                        "limit_state": s.get("limit_state"), "cited": s.get("cited"),
                        "capacity": s.get("capacity") or {}, "DC": s.get("DC"),
                        "found": s.get("found"), "note": s.get("note"),
                        "required_inputs": s.get("required_inputs"),
                        "demand_N": s.get("demand_N"),
                    }
                    for s in bp.get("slots") or []
                }
            except Exception as _bpe:
                entry["base_plate_worksheet"] = {"status": "stubs_error", "error": str(_bpe)}
        # complete-gap wave2: apply LIVE RAG capacities when cfg supplies them
        _rag_map = (cfg.get("connection_rag_capacities") or {})
        _rag_for = None
        if isinstance(_rag_map, dict):
            _rag_for = (_rag_map.get(role) or _rag_map.get(kind)
                        or _rag_map.get("brace" if kind == "brace" else None)
                        or _rag_map.get("base" if kind == "col" else None)
                        or _rag_map.get("default"))
        if _rag_for:
            try:
                import india_is800 as _I8rag
                entry["rag_capacities"] = _rag_for
                entry = _I8rag.apply_rag_capacities_to_connection(entry, rag_capacities=_rag_for)
            except Exception as _rage:
                entry["rag_capacities_error"] = str(_rage)
        pkg["connections"].append(entry)
    # WP2.6: the ASCE diaphragm-force collector stub was removed.  India collectors / chords come
    # from the diaphragm load path (india_diaphragm.collector_demands, applied in design_india).
    _cp = os.path.join(outdir, "calc_package.json")
    try:                                            # never silently destroy the agent's filled package
        if os.path.exists(_cp):
            _old = json.load(open(_cp))
            _filled = any(m.get("limit_state") or m.get("DC") is not None for m in _old.get("members", [])) \
                   or any(c.get("DC") is not None or c.get("checks") for c in _old.get("connections", []))
            if _filled:
                import shutil as _sh; _sh.copy(_cp, _cp + ".filled.bak")
                print("[design] WARNING: existing calc_package.json had agent capacities -> backed up to "
                      "calc_package.json.filled.bak before overwriting with fresh demands. Do NOT re-run "
                      "design_and_report to make a report; re-render with report.build_report "
                      "(which preserves your capacities).")
    except Exception:
        pass
    # H6: seed India composite Ch.I worksheet stubs when composite is declared
    # so agents do not invent stud/camber designs (parallel to §12 stubs).
    try:
        _blob = (str(cfg.get("floor_system", "")).lower() + " "
                 + str(cfg.get("notes", "")).lower() + " "
                 + str(cfg.get("arch", "")).lower())
        if "composite" in _blob or cfg.get("composite"):
            pkg["composite_design"] = {
                "status": "stubs",
                "chI_worksheet": _composite_chI_worksheet_stubs(),
                "note": (
                    "H6: composite Ch.I not auto-designed. Fill slots from IS 800 Ch. I RAG "
                    "or record explicit scope (bare-steel lower bound / excluded / delegated). "
                    "Do not invent stud/camber/wet-stage numbers."
                ),
            }
    except Exception as _ce:
        pkg.setdefault("composite_design", {"status": "stubs_error", "error": str(_ce)})


    # complete-gap wave1: seed SMF SCWB / panel-zone worksheets when system is SMF/MRF
    try:
        _sys = (str(cfg.get("system", "")) + " " + str(cfg.get("arch", ""))).lower()
        if any(k in _sys for k in ("smf", "smrf", "moment frame", "mrf")):
            pkg.setdefault("capacity_design", {})
            if not isinstance(pkg["capacity_design"], dict):
                pkg["capacity_design"] = {}
            _ws = _section12_smf_worksheets()
            pkg["capacity_design"].setdefault("system", cfg.get("system") or cfg.get("arch") or "SMF")
            pkg["capacity_design"].setdefault("cite", "IS 800:2007 §12.11 Special Moment Frames")
            pkg["capacity_design"].setdefault("status", "worksheets_seeded")
            checks = pkg["capacity_design"].setdefault("checks", {})
            if "SCWB" not in checks or checks["SCWB"].get("found") is not True:
                checks["SCWB"] = _ws.get("SCWB") or {"found": False}
            if "panel_zone" not in checks or checks["panel_zone"].get("found") is not True:
                checks["panel_zone"] = _ws.get("panel_zone") or {"found": False}
            pkg["capacity_design"]["smf_worksheets"] = _ws
            pkg["capacity_design"].setdefault(
                "note",
                "SCWB/panel-zone worksheets seeded; call india_is800.scwb_ratio / "
                "panel_zone_check when member strengths / joint geometry available. "
                "found:false only when inputs missing — not an always-stub.",
            )
    except Exception as _s12e:
        pkg.setdefault("capacity_design", {"status": "smf_worksheet_error", "error": str(_s12e)})

    json.dump(pkg, open(_cp, "w"), indent=1)

    # ---- connection_demands.csv (demands + the limit-state checklist the agent sizes) ----
    with open(os.path.join(outdir, "connection_demands.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["connection", "member_tag", "type",
                    ("demand_N_or_kNm" if _SI else "demand_kip_or_kipft"), "note"])
        for t in sorted(reg):
            kind, sec, n1, n2 = reg[t]; e = env[t]
            if kind == "beam":
                if _SI:
                    dems = "V=%.1f N, M=%.3f kN·m" % (e["V"], e["Mz"]/_mdiv)
                else:
                    dems = "V=%.1f kip, M=%.1f kip-ft" % (e["V"], e["Mz"]/12)
                w.writerow(["beam-end @ %s/%s" % (n1, n2), t, "shear (+moment if MF)", dems,
                            "size per IS 800 / IS 816 / IS 4000 (agent derives bolt/weld/plate from RAG)"])
            elif kind == "brace":
                if _SI:
                    dems = "P=%.1f N" % max(e["comp"], e["tens"])
                else:
                    dems = "P=%.1f kip" % max(e["comp"], e["tens"])
                w.writerow(["brace @ %s/%s" % (n1, n2), t, "axial", dems,
                            "gusset/weld per IS 800 / IS 816 / IS 4000; seismic capacity-design per IS 800/1893 (agent)"])
        _l, _fd, _fl, _flr, _lat, _co = cases[1]; res, info = run_case(cfg, _fd, _fl, _flr, _lat); ops.reactions()
        for (i, j) in info["present"][0]:
            R = [ops.nodeReaction(E.ntag(i, j, 0), d) for d in (1, 2, 3, 4, 5, 6)]
            if _SI:
                dems = "P=%.1f N, Vx=%.1f, Vy=%.1f, M=%.3f kN·m" % (
                    R[2], R[0], R[1], max(abs(R[3]), abs(R[4]))/_mdiv)
            else:
                dems = "P=%.1f kip, Vx=%.1f, Vy=%.1f, M=%.1f kip-ft" % (
                    R[2], R[0], R[1], max(abs(R[3]), abs(R[4]))/12)
            w.writerow(["column base @ grid(%s,%s)" % (i, j), E.ntag(i, j, 0), "base plate/anchorage",
                        dems, "base plate/anchor rods per IS 800 (agent/RAG)"])

    # ---- optional opsvis figures ----
    figs = []
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        import opsvis as opsv
        E.build(cfg, "Linear")
        opsv.plot_model(node_labels=0, element_labels=0); plt.savefig(os.path.join(outdir, "fig_model.png"), dpi=140); plt.close()
        _l, _fd, _fl, _flr, _lat, _co = cases[1]; run_case(cfg, _fd, _fl, _flr, _lat)
        opsv.plot_defo(sfac=30); plt.savefig(os.path.join(outdir, "fig_deformed.png"), dpi=140); plt.close()
        figs = ["fig_model.png", "fig_deformed.png"]
    except Exception as ex:
        with open(os.path.join(outdir, "figures_note.txt"), "w") as f:
            f.write("opsvis/matplotlib not available here; reviewer figures come from plot_model.py.\n(%s)\n" % ex)

    # ---- design_report.md ----
    with open(os.path.join(outdir, "design_report.md"), "w") as f:
        f.write("# %s - demand summary\n\n" % name)
        f.write("Archetype: %s; %d storeys; system %s; R=%s, Ie=%s.\n\n"
                % (cfg["arch"], len(cfg["heights"]), "CBF/dual" if cfg.get("braces") else "moment frame",
                   cfg["seis"]["R"], cfg["seis"]["Ie"]))
        f.write("- Load combinations run: **%d** (IS partial-factor combos from load_plan, P-Delta each).\n" % len(cases))
        f.write("- Members enveloped: **%d** elements.\n" % len(reg))
        f.write("- **Capacities / D-C: derived by the agent from the IS 800 RAG** (not computed by the framework).\n\n")
        f.write("Files: member_schedule.csv (per-element demands), member_demands.md (summary by type), "
                "connection_demands.csv (+ checklist), calc_package.json (demands; agent fills capacities).\n")
    print("[%s] %d combos, %d members -> DEMAND envelope written (capacities = agent/RAG)" % (name, len(cases), len(reg)))
    print("  output: %s" % outdir)
    return {"members": len(reg), "combos": len(cases), "outdir": outdir}   # B8: truthy -> pipeline.demands_written is True


# --- HR polish Wave D: re-export H6/H7 residual status ------------------------
try:
    from india_is800 import h6_h7_residual_status  # noqa: F401
except Exception:  # pragma: no cover
    def h6_h7_residual_status(cfg=None, pkg=None):
        return {"blocking": False, "status": "unavailable", "H6": {"found": False}, "H7": {"found": False}}



# =====================================================================================
# India design path (WP1.1-1.3, WP1.6-1.9, WP2.1, WP2.6/2.7 hooks).  Demands in N / N-mm;
# member capacities from HR-MEMBERS' india_is800.member_check_is800 (concurrent forces per
# combination); Section 12 from india_is800_s12.section12_checks; the COMPLETE decision is
# india_seismic_gates.design_status only.
# =====================================================================================
_ROLE_TO_I8 = {"col": "column", "beam": "beam", "brace": "brace"}


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not callable(v) and not str(k).startswith("_rsa")}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (int, float, str, bool)) or o is None:
        return o
    try:
        import numpy as _np
        if isinstance(o, _np.ndarray):
            return o.tolist()
        if isinstance(o, _np.generic):
            return o.item()
    except Exception:
        pass
    return None


def cfg_snapshot(cfg):
    """JSON-serialisable cfg (callables dropped) for the app-side COMPLETE gate (agent.py)."""
    return _jsonable({k: v for k, v in cfg.items() if not callable(v) and k not in ("custom_build",)})


def _sha256(path):
    import hashlib
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


def provenance_record(job_dir):
    """Hashes of the job's scripts + cfg (0.2: the package must match the shipped script)."""
    files = {}
    if job_dir and os.path.isdir(job_dir):
        for f in sorted(os.listdir(job_dir)):
            if f.endswith(".py") or f in ("load_plan.json",):
                h = _sha256(os.path.join(job_dir, f))
                if h:
                    files[f] = h
    return {"files": files, "note": "sha256 of the job's cfg/fill scripts at package time"}


def _member_input_record(cfg, t, kind, sec, n1, n2, length, role):
    grade = cfg.get("brace_grade") if kind == "brace" else cfg.get("steel_grade")
    m = {"id": "e%d" % t, "tag": t, "section": sec, "grade": grade, "role": _ROLE_TO_I8.get(kind, kind),
         "L_mm": length, "node_i": n1, "node_j": n2}
    if kind == "brace":
        m["process"] = cfg.get("brace_process")
    K = cfg.get("K_factors") or {}
    kk = K.get(role) or K.get(kind) or {}
    if kk:
        m["Kz"], m["Ky"] = kk.get("Kz"), kk.get("Ky")
    if kind == "beam":
        for key in ("LLT_sag_mm", "LLT_hog_mm"):        # a number, or {role: mm} per member group
            v = cfg.get(key)
            m[key] = (v.get(role) if isinstance(v, dict) else v)
    if kind == "col":
        m["sway"] = bool(cfg.get("sway_frame"))
    return m


def _top_records(recs, k=12):
    """The governing combinations of one member (largest |N|, |Mmaj|, |Mmin|, |V|) -- concurrent tuples."""
    if len(recs) <= k:
        return recs
    keep = set()
    for idx in range(4):
        keep |= set(sorted(recs, key=lambda l: -abs(recs[l][idx]))[: max(3, k // 4)])
    comp = sorted(recs, key=lambda l: recs[l][0])[:3]        # most compressive
    keep |= set(comp)
    return {l: recs[l] for l in keep}


def member_checks_is800(cfg, elem):
    """Call HR-MEMBERS' member_check_is800 (guarded).  elem = {member, kind, records}."""
    try:
        import india_is800 as I8
        f = I8.member_check_is800
    except (ImportError, AttributeError) as ex:
        return {"found": False, "ok": None, "dc": None,
                "reason": "india_is800.member_check_is800 unavailable (HR-MEMBERS integration pending): %s" % ex}
    import static_model as SM
    cf = SM.combo_forces_for_member_check(_top_records(elem["records"]), elem["kind"])
    try:
        return f(elem["member"], cf, cfg=cfg)
    except Exception as ex:
        return {"found": False, "ok": None, "dc": None, "reason": "member_check_is800 failed: %s" % ex}


def _check_rows(res):
    """member_check_is800 result -> {value, limit, dc, ok, clause, cite, source} check records."""
    rows = []
    src = "india_is800.member_check_is800"
    if res.get("found") and res.get("dc") is not None:
        rows.append({"name": "IS 800 9.3 interaction / member resistance (governing combination %s)"
                             % res.get("governing_combo"), "value": float(res["dc"]), "limit": 1.0,
                     "dc": float(res["dc"]), "ok": bool(res["dc"] <= 1.0), "clause": res.get("clause"),
                     "cite": res.get("cite") or res.get("clause"), "source": src})
    else:
        rows.append({"name": "IS 800 member check", "value": None, "limit": None, "dc": None, "ok": None,
                     "found": False, "clause": "IS 800:2007 7-9", "cite": res.get("reason"), "source": src})
    t3 = res.get("table3_slenderness")
    if isinstance(t3, dict):
        rows.append({"name": "IS 800 Table 3 slenderness KL/r", "value": t3.get("value"), "limit": t3.get("limit"),
                     "dc": t3.get("dc"), "ok": t3.get("ok"), "clause": t3.get("clause"), "cite": t3.get("cite"),
                     "source": src})
    return rows


def section12_model_data(cfg, reg, length, role_of, env, per_case_tags, cases, info0):
    """model_data for HR-MEMBERS' india_is800_s12.section12_checks (see its module docstring)."""
    import static_model as SM
    members, forces = [], {}
    fam = {}
    for c in cases:
        m = getattr(c, "meta", {}) or {}
        fam[c[0]] = "12.2.3" if "is800_12_2_3" in (m.get("tags") or []) else ("service" if m.get("service") else "table4")
    for t, (kind, sec, n1, n2) in reg.items():
        mid = "e%d" % t
        rec = _member_input_record(cfg, t, kind, sec, n1, n2, length[t], role_of[t])
        rec["sfrs"] = role_of[t] in ("brace", "lateral_col") or (kind == "beam" and t in per_case_tags.get("lateral_beams", set()))
        try:
            c1, c2 = ops.nodeCoord(n1), ops.nodeCoord(n2)
            dx, dy, dz = c2[0] - c1[0], c2[1] - c1[1], c2[2] - c1[2]
            Lh = math.hypot(dx, dy); L3 = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            if kind in ("brace", "beam"):
                rec["frame_dir"] = "X" if abs(dx) >= abs(dy) else "Y"
            if kind == "brace":
                rec["cos_h"] = Lh / L3
                # brace line = (frame direction, grid line perpendicular coordinate)
                rec["line"] = "%s@%.0f" % (rec["frame_dir"], c1[1] if rec["frame_dir"] == "X" else c1[0])
            if kind == "col":
                rec["major_axis_plane"] = (info0.get("col_dir") or {}).get(t)
        except Exception:
            pass
        members.append(rec)
        recs = per_case_tags["records"].get(t) or {}
        fl = SM.combo_forces_for_member_check(recs, kind)
        for f in fl:
            f["family"] = fam.get(f["combo"], "table4")
        forces[mid] = fl
    return {"members": members, "forces": forces,
            "combos_12_2_3_present": any(v == "12.2.3" for v in fam.values())}


def design_india(name, cfg, outdir):
    """India demand + check package (N-mm)."""
    import static_model as SM
    import india_loads as IL
    import india_seismic_gates as G
    from india_units import display_scale
    _SC = display_scale(cfg)
    _mdiv = _SC["moment_div"]
    job_dir = os.path.dirname(os.path.abspath(outdir))
    cases = combos(cfg)
    run = E.india_run_cached(cfg, name)
    rsa_el = None
    if any((getattr(c, "meta", {}) or {}).get("rsa") for c in cases):
        rsa = run.get("rsa") or E.rsa_analysis(cfg)
        run["rsa"] = rsa
        rsa_el = rsa["elements"]
    fs_ = "two-way" if "two" in str(cfg.get("floor_system", "one-way")).lower() else "one-way"
    nseg = int(cfg.get("demand_nseg", 6))
    per_case, kinds, sinfo = SM.solve_cases_si(cfg, cases, nseg, fs_, rsa=rsa_el)
    # WP2.6: collector / chord axial from the diaphragm load path (rigid diaphragm gives beams P = 0)
    coll_added, coll_error = {}, None
    amp1223 = str(cfg.get("collector_basis") or "").lower() in ("is800_12_2_3", "12.2.3")
    try:
        import india_diaphragm as DIA
        _i = E.build(cfg, "PDelta")
        _reg = {t: (kind, sec, n1, n2) for (t, kind, sec, n1, n2) in _i["ele"]}
        coll_added = DIA.add_to_records(per_case, cases, _reg, cfg, amplify_12_2_3=amp1223)
    except Exception as ex:
        coll_error = "%s: %s" % (type(ex).__name__, ex)
    env = SM.envelope_from_records(per_case, kinds, cases)

    info0 = E.build(cfg, "PDelta")
    reg = {t: (kind, sec, n1, n2) for (t, kind, sec, n1, n2) in info0["ele"]}
    length = {t: math.dist(ops.nodeCoord(n1), ops.nodeCoord(n2)) for t, (k, s_, n1, n2) in reg.items()}
    NFlev = len(cfg["heights"])
    brace_lines = set()
    for (t, kind, sec, n1, n2) in info0["ele"]:
        if kind == "brace":
            for nd in (n1, n2):
                brace_lines.add(((nd % 100000) // 100, nd % 100))
    moment_lines = {((nd % 100000) // 100, nd % 100) for nd in info0.get("moment_nodes", set())}
    lateral_lines = brace_lines | moment_lines

    def _role(kind, n1, n2):
        if kind == "brace":
            return "brace"
        if kind == "beam":
            return "roof" if (n1 // 100000) >= NFlev else "floor"
        return "lateral_col" if ((n1 % 100000) // 100, n1 % 100) in lateral_lines else "gravity_col"
    role_of = {t: _role(reg[t][0], reg[t][2], reg[t][3]) for t in reg}
    envt = {t: env.get(frozenset((reg[t][2], reg[t][3])), dict(comp=0.0, tens=0.0, Mz=0.0, My=0.0, V=0.0, combo="",
                                                              records={}, conn={})) for t in reg}
    zero = [t for t in reg if all(abs(x) < 1e-6 for r in (envt[t].get("records") or {}).values() for x in r[:4])]

    # ---- member_schedule.csv + per-element combination forces for HR-MEMBERS ----
    with open(os.path.join(outdir, "member_schedule.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ele_tag", "member", "role", "section", "length_mm", "P_comp_kN", "P_tens_kN",
                    "M_major_kNm", "M_minor_kNm", "V_kN", "governing_combo"])
        for t in sorted(reg):
            kind, sec, n1, n2 = reg[t]; e = envt[t]
            w.writerow([t, kind, role_of[t], sec, round(length[t], 1), round(e["comp"] / 1e3, 2),
                        round(e["tens"] / 1e3, 2), round(e["Mz"] / _mdiv, 3), round(e["My"] / _mdiv, 3),
                        round(e["V"] / 1e3, 2), e["combo"]])
    json.dump({"fields": list(SM.REC_FIELDS), "units": "N, N-mm (Mmaj sagging + for beams)",
               "elements": {str(t): {"kind": reg[t][0], "section": reg[t][1], "role": role_of[t],
                                     "L_mm": round(length[t], 1), "records": envt[t].get("records") or {},
                                     "conn_only_records": envt[t].get("conn") or {}} for t in reg}},
              open(os.path.join(outdir, "member_combo_forces.json"), "w"))

    # ---- IS 800 member checks per element (concurrent forces per combination) ----
    by = {}
    for t in reg:
        by.setdefault((reg[t][0], reg[t][1], role_of[t]), []).append(t)
    pkg = {"building": name, "code": "IS 800:2007 LSD", "unit_system": "N-mm", "stress_unit": "MPa",
           "units": {"force": "N", "length": "mm", "moment": "N-mm", "display": "kN, kN-m, m, mm, MPa"},
           "note": "Demands from the India analysis (IS 800 Table 4 / IS 1893 combinations); member checks "
                   "from india_is800.member_check_is800 per combination with concurrent forces.",
           "members": [], "connections": []}
    elem_results = {}
    for key, tags in sorted(by.items()):
        kind, sec, role = key
        worst = None
        for t in tags:
            recs = {l: r for l, r in (envt[t].get("records") or {}).items()}
            if kind != "col" and not (amp1223 and t in coll_added):
                recs = {l: r for l, r in recs.items() if l not in (envt[t].get("conn") or {})}
            mem = _member_input_record(cfg, t, kind, sec, reg[t][2], reg[t][3], length[t], role)
            res = member_checks_is800(cfg, {"member": mem, "kind": kind, "records": recs})
            elem_results[t] = res
            if worst is None or (res.get("dc") or -1) > (worst[1].get("dc") or -1) or res.get("dc") is None:
                worst = (t, res)
                if res.get("dc") is None:
                    break
        t0, res = worst
        e = envt[t0]
        g = {q: max(envt[t][q] for t in tags) for q in ("comp", "tens", "Mz", "My", "V")}
        inp = {"kind": kind, "role": role, "section": sec, "n_elements": len(tags), "governing_element": t0,
               "length_mm": round(max(length[t] for t in tags), 1),
               "P_comp_N": round(g["comp"], 1), "P_tens_N": round(g["tens"], 1), "Mz_Nmm": round(g["Mz"], 1),
               "My_Nmm": round(g["My"], 1), "V_N": round(g["V"], 1), "governing_combo": e["combo"],
               "combo_forces_file": "design/member_combo_forces.json",
               "grade": _member_input_record(cfg, t0, kind, sec, 0, 0, 0, role).get("grade")}
        rows = _check_rows(res)
        dc = res.get("dc")
        pkg["members"].append({"id": "%s-%s" % (role, sec), "inputs": inp, "checks": rows,
                               "limit_state": "IS 800:2007 7-9 (member_check_is800)", "cited": res.get("clause"),
                               "capacity": res.get("capacities") and {k: (v if not isinstance(v, dict) else
                                                                          {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float, str, bool))})
                                                                      for k, v in res["capacities"].items()},
                               "DC": dc, "governing_element_result": _jsonable({k: v for k, v in res.items() if k != "per_combo"})})

    # ---- connections: demands (incl. 12.2.3 conn_only forces); capacities by HR-MEMBERS ----
    for key, tags in sorted(by.items()):
        kind, sec, role = key
        g = {q: max(envt[t][q] for t in tags) for q in ("comp", "tens", "Mz", "My", "V")}
        conn_max = 0.0
        for t in tags:
            for r in (envt[t].get("conn") or {}).values():
                conn_max = max(conn_max, abs(r[0]))
        if kind == "beam":
            ctype = "beam-to-column"; dem = {"V_N": round(g["V"], 1), "M_Nmm": round(g["Mz"], 1), "P_N": round(max(g["comp"], g["tens"]), 1)}
        elif kind == "brace":
            ctype = "brace-to-gusset"; dem = {"axial_N": round(max(g["comp"], g["tens"]), 1),
                                              "axial_12_2_3_N": round(conn_max, 1)}
        else:
            ctype = "column splice / base"; dem = {"P_N": round(g["comp"], 1), "T_N": round(g["tens"], 1),
                                                   "M_Nmm": round(g["Mz"], 1), "V_N": round(g["V"], 1),
                                                   "P_12_2_3_N": round(conn_max, 1)}
        pkg["connections"].append({"id": "conn-%s-%s" % (role, sec), "type": ctype, "section": sec, "demand": dem,
                                   "design_basis": "IS 800:2007 Section 10 / 7.4 / Section 12 (india_connections)",
                                   "checks": [], "DC": None, "limit_state": None, "cited": None})
    # ---- Section 12 (HR-MEMBERS) ----
    try:
        import india_is800_s12 as S12
        md = section12_model_data(cfg, reg, length, role_of, envt,
                                  {"records": {t: envt[t].get("records") or {} for t in reg}}, cases, info0)
        try:
            nodes = {nd: tuple(ops.nodeCoord(nd)) for nd in ops.getNodeTags()}
            md["joints"] = S12.joints_from_model(nodes, md["members"],
                                                 frame_members={m["id"] for m in md["members"] if m.get("sfrs")})
        except Exception as ex:
            md["joints_error"] = str(ex)
        s12 = S12.section12_checks(cfg.get("system"), md, dict(cfg.get("section12_inputs") or {},
                                   zone=G.zone_of(cfg), I=G.importance_of(cfg),
                                   height_m=G.building_height_m(cfg),
                                   brace_config=cfg.get("brace_config")))
        pkg["capacity_design"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "section12": _jsonable(s12),
                                  "checks": {c.get("id", "c%d" % i) + ("@" + str(c.get("member")) if c.get("member") else ""):
                                             {"value": c.get("value"), "limit": c.get("limit"), "dc": c.get("dc"),
                                              "ok": c.get("ok"), "pass": c.get("ok"), "clause": c.get("clause"),
                                              "cite": c.get("cite"), "found": c.get("ok") is not None}
                                             for i, c in enumerate(s12.get("checks") or [])}}
    except ImportError as ex:
        pkg["capacity_design"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "checks": {},
                                  "error": "india_is800_s12.section12_checks unavailable (HR-MEMBERS): %s" % ex}
    except Exception as ex:
        pkg["capacity_design"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "checks": {},
                                  "error": "section12_checks failed: %s" % ex}

    # ---- seismic analysis record, combinations, drift, irregularity, W ----
    rsa = run.get("rsa")
    sa = {"method": run.get("method"), "esm_permitted": run.get("esm_permitted"),
          "esm_reasons": run.get("esm_reasons"), "rsa_used_in_demands": bool(rsa_el),
          "cite": "IS 1893 7.6 / 7.7.1 / 7.7.3 / 7.7.5"}
    if rsa:
        sa["scale"] = {d: {"VB_rsa_kN": round(rsa[d]["VB_rsa_N"] / 1e3, 2), "VBbar_kN": round(rsa[d]["VBbar_N"] / 1e3, 2),
                           "scale": round(rsa[d]["scale"], 4), "VB_scaled_kN": round(rsa[d]["VB_scaled_N"] / 1e3, 2),
                           "mass_participation": round(rsa[d]["mass_participation"], 4)} for d in ("X", "Y")}
        sa["modes"] = [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in m_.items()} for m_ in rsa["modes"][:15]]
    pkg["seismic_analysis"] = sa
    pkg["load_combinations"] = [_jsonable(dict((getattr(c, "meta", {}) or {}).get("source") or {"label": c[0]},
                                               lateral_kind=(getattr(c, "meta", {}) or {}).get("kind"),
                                               direction=(getattr(c, "meta", {}) or {}).get("direction"),
                                               sign=(getattr(c, "meta", {}) or {}).get("sign"),
                                               fE=(getattr(c, "meta", {}) or {}).get("fLat") if (getattr(c, "meta", {}) or {}).get("kind") == "EQ" else None))
                                for c in cases]
    pkg["drift_table"] = []
    for d, rec in (run.get("drift") or {}).items():
        for i, x in enumerate(rec["drift"]):
            lim = (run.get("drift_limits") or [0.004] * len(rec["drift"]))[i]
            pkg["drift_table"].append({"storey": i + 1, "dir": d, "drift": round(x, 6), "limit": lim,
                                       "value": x, "dc": x / lim if lim else None, "ok": x <= lim,
                                       "clause": "IS 1893 7.11.1.1 (edges, 7.8.2 eccentricity, gamma 1.0)"})
    pkg["irregularity"] = run.get("irregularity") or {"error": "irregularity screens not run"}
    if (pkg["irregularity"].get("reentrant") or {}).get("irregular"):
        pkg["seismic_analysis"]["reentrant_flexible_required"] = True
        pkg["seismic_analysis"]["flexible_diaphragm_run"] = bool(cfg.get("_flexible_diaphragm_run"))
    plan = cfg.get("load_plan") or {}
    ss = plan.get("seismic_summary") or {}
    pkg["seismic_calc"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "Z": ss.get("Z"), "I": G.importance_of(cfg),
                           "zone": G.zone_of(cfg), "W_engine_kN": round(sum(E.floor_w(cfg, k) for k in range(1, NFlev + 1)) / 1e3, 1),
                           "W_design_kN": ss.get("W_kN"),
                           "W_by_floor_engine_kN": [round(E.floor_w(cfg, k) / 1e3, 1) for k in range(1, NFlev + 1)]}
    pkg["load_plan"] = {"seismic_summary": ss, "retrieval": plan.get("retrieval"),
                        "story_forces_units": plan.get("story_forces_units")}
    pkg["zero_demand_elements"] = zero
    pkg["beam_deflection"] = run.get("beam_deflection_rows")
    pkg["gates"] = {k: bool(v) for k, v in (run.get("chk") or {}).items()}
    if cfg.get("crane") or cfg.get("cranes"):
        try:
            gd = IL.gantry_girder_demands(cfg)
            pkg["gantry_girder"] = {"demands": _jsonable(gd), "checks": [], "DC": None,
                                    "section": (IL._crane_def(cfg).get("gantry_section")),
                                    "note": "capacity checks (biaxial + surge, LTB with actual restraint, web "
                                            "bearing/buckling, Section 13 fatigue) by HR-MEMBERS"}
        except Exception as ex:
            pkg["gantry_girder"] = {"error": str(ex), "checks": [], "DC": None}
        pkg["crane_sway"] = _jsonable(run.get("crane_sway"))
    pkg["_coll_added"] = {str(t): round(v, 1) for t, v in coll_added.items()}
    pkg["_coll_error"] = coll_error; pkg["_coll_amp"] = amp1223
    for hook in (_collector_demands, _secondary_member_demands, _deformation_compatibility):
        try:
            hook(cfg, pkg, run, envt, reg)
        except Exception as ex:
            pkg.setdefault("hook_errors", []).append("%s: %s" % (hook.__name__, ex))
    pkg["provenance"] = provenance_record(job_dir)
    json.dump(cfg_snapshot(cfg), open(os.path.join(outdir, "cfg_snapshot.json"), "w"), indent=1, default=str)
    st = G.design_status(cfg, pkg, job_dir=job_dir)
    pkg["design_status"] = {"status": st["status"], "n_reasons": len(st["reasons"]), "reasons": st["reasons"][:200],
                            "authority": st["authority"]}
    json.dump(_jsonable(pkg), open(os.path.join(outdir, "calc_package.json"), "w"), indent=1)

    # ---- member_demands.md / connection_demands.csv / design_report.md ----
    with open(os.path.join(outdir, "member_demands.md"), "w") as f:
        f.write("# %s - member demands and IS 800 checks (N-mm engine, kN / kN-m display)\n\n" % name)
        f.write("Combinations: %d (IS 800 Table 4 / IS 1893 6.3 / IS 800 12.2.3, generated). Analysis: %s.\n\n"
                % (len(cases), run.get("method")))
        f.write("| role | section | n | governing combo | P_comp (kN) | P_tens (kN) | M_maj (kN-m) | M_min (kN-m) | V (kN) | D/C |\n")
        f.write("|---|---|---:|---|---:|---:|---:|---:|---:|---:|\n")
        for m_ in pkg["members"]:
            i_ = m_["inputs"]
            f.write("| %s | %s | %d | %s | %.1f | %.1f | %.1f | %.1f | %.1f | %s |\n"
                    % (i_["role"], i_["section"], i_["n_elements"], i_["governing_combo"], i_["P_comp_N"] / 1e3,
                       i_["P_tens_N"] / 1e3, i_["Mz_Nmm"] / 1e6, i_["My_Nmm"] / 1e6, i_["V_N"] / 1e3,
                       ("%.3f" % m_["DC"]) if isinstance(m_.get("DC"), (int, float)) else "not evaluated"))
    with open(os.path.join(outdir, "connection_demands.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["connection", "type", "demand (N, N-mm)"])
        for c in pkg["connections"]:
            w.writerow([c["id"], c["type"], json.dumps(c["demand"])])
    with open(os.path.join(outdir, "design_report.md"), "w") as f:
        f.write("# %s - demand and check summary\n\nSystem %s (IS 1893 Table 9 R %s); %d storeys; %s analysis.\n\n"
                % (name, cfg.get("system"), G.declared_R(cfg), NFlev, run.get("method")))
        f.write("Status (india_seismic_gates.design_status): **%s** (%d reasons).\n" % (st["status"], len(st["reasons"])))
    print("[%s] %d combinations, %d elements, %s -> demands + IS 800 checks written; status %s"
          % (name, len(cases), len(reg), run.get("method"), st["status"]))
    return {"members": len(reg), "combos": len(cases), "outdir": outdir, "status": st["status"]}


def _collector_demands(cfg, pkg, run, envt, reg):
    """WP2.6: collector / chord rows (india_diaphragm); the forces were already added to the beam
    records before the member checks."""
    from india_diaphragm import collector_demands
    rows = collector_demands(cfg, run, reg)
    pkg["collectors"] = {"rows": rows, "applied_to_member_checks": bool(pkg.get("_coll_added")),
                         "n_beams_with_axial": len(pkg.get("_coll_added") or {}),
                         "basis_12_2_3": pkg.get("_coll_amp"), "error": pkg.get("_coll_error"),
                         "cite": "india_diaphragm (equilibrium of the analysed model); IS 800 9.3"}
    for k in ("_coll_added", "_coll_error", "_coll_amp"):
        pkg.pop(k, None)


def _secondary_member_demands(cfg, pkg, run, envt, reg):
    """WP2.7 secondary members (joists / purlins / girts) -- simple-span demands per combination."""
    sec = cfg.get("secondary_members") or []
    if not sec:
        return
    out = []
    for s_ in sec:
        out.append(secondary_member_demand(cfg, s_))
    pkg["secondary_members"] = out


def secondary_member_demand(cfg, s_):
    """{id, section, span_mm, spacing_mm, level ('floor'|'roof'), wind_uplift_kNm2?} -> demands for the
    IS 800 check (sagging LTB restrained by the deck, hogging / uplift needs fly-brace spacing)."""
    D = float(cfg.get("D_roof" if s_.get("level") == "roof" else "D_floor") or 0.0)
    Lp = float(cfg.get("Lr") or 0.0) if s_.get("level") == "roof" else float(cfg.get("L_floor") or 0.0)
    sp = float(s_["spacing_mm"]); L = float(s_["span_mm"])
    rows = []
    for lab, fD, fL, fW in (("1.5DL+1.5LL", 1.5, 1.5, 0.0), ("0.9DL+1.5WL(uplift)", 0.9, 0.0, 1.5)):
        up = float(s_.get("wind_uplift_kNm2") or 0.0)
        wv = (fD * D + fL * Lp - fW * up) * sp / 1000.0          # N/mm (+ down)
        rows.append({"combo": lab, "w_N_per_mm": round(wv, 3), "M_Nmm": round(wv * L * L / 8.0, 1),
                     "V_N": round(abs(wv) * L / 2.0, 1), "sign": "sagging" if wv >= 0 else "hogging"})
    return {"id": s_.get("id"), "section": s_.get("section"), "span_mm": L, "spacing_mm": sp,
            "demands": rows, "check": "india_is800.member_check_is800 with LLT_sag = deck restraint, "
                                      "LLT_hog = fly-brace spacing (IS 800 8.2.2)"}


def _deformation_compatibility(cfg, pkg, run, envt, reg):
    """IS 1893 7.11.2 (Zones III-V): members that are not part of the SFRS must keep their vertical
    load capacity under storey deformations equal to R x the 7.11.1 storey displacements.  The ESM
    story forces x R (gamma 1.0, 1.0 DL + 1.0 LL, P-Delta) impose R x Delta on the whole model; the
    gravity columns are then checked with india_is800.member_check_is800.  Also 7.11.3 separation."""
    import static_model as SM
    import india_loads as IL
    import india_seismic_gates as G
    z = G.zone_of(cfg)
    out = {"clause": "IS 1893 7.11.2", "zone": z, "checks": []}
    if z not in ("III", "IV", "V"):
        out["note"] = "Zone %s: 7.11.2 applies in Zones III-V only" % z
        pkg["deformation_compatibility"] = out
        return
    R = G.declared_R(cfg)
    plan = cfg.get("load_plan") or {}
    cases = []
    for d in ("X", "Y"):
        raw = (plan.get("story_forces") or {}).get("EQ_" + d)
        if not raw:
            continue
        c = {"label": "7.11.2 1.0DL+1.0LL+R.EQ_%s" % d, "fD": 1.0, "fL": 1.0, "fLr": 1.0, "fE": float(R),
             "lateral_ref": "EQ_" + d}
        cases.append(IL.case_from_combination(c, plan))
    per_case, kinds, _ = SM.solve_cases_si(cfg, cases, int(cfg.get("demand_nseg", 6)),
                                           "two-way" if "two" in str(cfg.get("floor_system")) else "one-way")
    env = SM.envelope_from_records(per_case, kinds, cases)
    info0 = E.build(cfg, "Linear")
    lat_lines = set()
    for (t, kind, sec, n1, n2) in info0["ele"]:
        if kind == "brace":
            for nd in (n1, n2):
                lat_lines.add(((nd % 100000) // 100, nd % 100))
    lat_lines |= {((nd % 100000) // 100, nd % 100) for nd in info0.get("moment_nodes", set())}
    worst = None
    for t, (kind, sec, n1, n2) in reg.items():
        if kind != "col" or ((n1 % 100000) // 100, n1 % 100) in lat_lines:
            continue
        e = env.get(frozenset((n1, n2)))
        if not e:
            continue
        length = math.dist(ops.nodeCoord(n1), ops.nodeCoord(n2))
        mem = _member_input_record(cfg, t, kind, sec, n1, n2, length, "gravity_col")
        res = member_checks_is800(cfg, {"member": mem, "kind": kind, "records": e.get("records") or {}})
        rec = {"element": t, "section": sec, "value": res.get("dc"), "limit": 1.0, "dc": res.get("dc"),
               "ok": (res.get("dc") <= 1.0) if isinstance(res.get("dc"), (int, float)) else None,
               "clause": "IS 1893 7.11.2 + IS 800 9.3", "cite": "R x storey displacement imposed (R = %s)" % R,
               "source": "design_pipeline._deformation_compatibility", "reason": res.get("reason")}
        if worst is None or (rec["dc"] or 9e9 if rec["dc"] is None else rec["dc"]) > (worst["dc"] or -1):
            worst = rec
    if worst:
        out["checks"].append(worst)
    sep = cfg.get("adjacent_units") or []
    if sep:
        import india_seismic as IS
        dr = run.get("drift") or {}
        for u in sep:
            d = u.get("direction", "X")
            D1 = max((dr.get(d) or {}).get("disp_max") or [0.0])
            r_ = IS.separation_required(float(R), D1, float(u.get("R2", R)), float(u.get("delta2_mm", 0.0)),
                                        bool(u.get("same_floor_levels")))
            gap = u.get("gap_mm")
            out.setdefault("separation", []).append({"unit": u.get("id"), "value": r_["required_mm"], "limit": gap,
                                                     "dc": (r_["required_mm"] / gap) if gap else None,
                                                     "ok": (gap is not None and r_["required_mm"] <= gap),
                                                     "clause": "IS 1893 7.11.3", "cite": r_["cite"]})
    pkg["deformation_compatibility"] = out
