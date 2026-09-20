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


def _composite_chI_worksheet_stubs(cfg=None):
    """WP2.9: composite floors are IS 11384 (not in the corpus) -> india_is800.composite_is11384_worksheet_stubs."""
    import india_is800 as I8
    return I8.composite_is11384_worksheet_stubs(cfg)


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
            inp.update(A=S.brace_area(sec), r=S.brace_r(sec))       # IS 808 / IS 1161 DB (never E.HSS)
        elif p:
            # the unbraced length is the physical element length; LTB restraint (LLT) is a declared input
            lb_key = "Lb_mm" if _SI else "Lb_in"
            inp.update(**{lb_key: round(L, 1)}, A=p["A"], Ix=p["Ix"], Iy=p["Iy"], J=p["J"], Zx=p["Zx"],
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
            import india_is800 as _I8c
            pkg["composite_design"] = {
                "status": "stubs",
                "chI_worksheet": _I8c.composite_is11384_worksheet_stubs(cfg),
                "note": (
                    "WP2.9: composite beams are IS 11384 (not in the corpus -> found:false). Record the scope "
                    "(bare-steel per IS 800 8.2 + construction stage, or delegated) -- see COMPOSITE_INDIA.md."
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
    generated = {"model_opensees.py", "model_static.py", "cfg_snapshot.json"}     # written by the pipeline itself
    if job_dir and os.path.isdir(job_dir):
        for f in sorted(os.listdir(job_dir)):
            if (f.endswith(".py") or f in ("load_plan.json",)) and f not in generated:
                h = _sha256(os.path.join(job_dir, f))
                if h:
                    files[f] = h
    return {"files": files, "note": "sha256 of the job's cfg/fill scripts + load_plan.json at package time "
                                    "(engine-generated model files excluded)"}


def _member_input_record(cfg, t, kind, sec, n1, n2, length, role):
    grade = cfg.get("brace_grade") if kind == "brace" else cfg.get("steel_grade")
    grade = (cfg.get("grade_by_section") or {}).get(sec) or grade      # per-section IS 2062 grade (e.g. E350 columns)
    m = {"id": "e%d" % t, "tag": t, "section": sec, "grade": grade, "role": _ROLE_TO_I8.get(kind, kind),
         "role_group": role, "L_mm": length, "node_i": n1, "node_j": n2}
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


def sfrs_beam_tags(reg, info0):
    """Beams that are part of the lateral system: moment-frame beams (both ends rigid) and braced-bay beams
    (a brace frames into the bay at the beam's level)."""
    rel = info0.get("beam_rel") or {}
    bays = set()
    col_nodes = set()
    for t, (kind, sec, n1, n2) in reg.items():
        if kind == "col":
            col_nodes |= {n1, n2}
        if kind == "brace":
            l1 = ((n1 % 100000) // 100, n1 % 100); l2 = ((n2 % 100000) // 100, n2 % 100)
            for k in (n1 // 100000, n2 // 100000):
                bays.add((frozenset((l1, l2)), k))
    out = set()
    for t, (kind, sec, n1, n2) in reg.items():
        if kind != "beam":
            continue
        l1 = ((n1 % 100000) // 100, n1 % 100); l2 = ((n2 % 100000) // 100, n2 % 100)
        if (frozenset((l1, l2)), n1 // 100000) in bays:
            out.add(t)
        elif rel.get(t) and rel[t][0] == "none" and n1 in info0.get("moment_nodes", set()) and n2 in info0.get("moment_nodes", set()):
            out.add(t)
        elif rel.get(t) and rel[t][0] in ("I", "J"):
            # one end pinned, the other rigid (e.g. the corner bay of a perimeter moment frame whose corner column
            # belongs to the orthogonal frame): a moment-frame beam at its rigid end only (WP6-fix)
            rigid = n2 if rel[t][0] == "I" else n1
            # the rigid end must be at a COLUMN node: a girder made of two elements continuous over a hanging mid
            # node (no column) is a gravity member, not a moment-frame beam (WP6-fix, Ex11 gym 17 m girder)
            if rigid in info0.get("moment_nodes", set()) and rigid in col_nodes:
                out.add(t)
    return out


def section12_model_data(cfg, reg, length, role_of, env, per_case_tags, cases, info0, run=None):
    """model_data for india_is800_s12.section12_checks (see its module docstring): members with the declared
    connection / base geometry (india_connection_design), per-combination forces tagged by family, joints, bases,
    brace lines, and (EBF, WP6) the links declared by the custom_build (info['links']) with their analysis shear."""
    import static_model as SM
    import india_connection_design as CD
    members, forces = [], {}
    fam, tagof, kindof = {}, {}, {}
    for c in cases:
        m = getattr(c, "meta", {}) or {}
        tg = m.get("tags") or []
        tagof[c[0]] = tg
        kindof[c[0]] = m.get("kind")
        fam[c[0]] = ("12.2.3" if ("is800_12_2_3" in tg or "is18168_5_5" in tg) else
                     ("service" if m.get("service") else "table4"))
    sfrs_beams = per_case_tags.get("lateral_beams") or set()
    NF = len(cfg["heights"])
    for t, (kind, sec, n1, n2) in reg.items():
        mid = "e%d" % t
        rec = _member_input_record(cfg, t, kind, sec, n1, n2, length[t], role_of[t])
        rec["sfrs"] = role_of[t] in ("brace", "lateral_col") or (kind == "beam" and t in sfrs_beams)
        if kind == "beam":
            rec["release_major"] = ((info0.get("beam_rel") or {}).get(t) or ("none", "none"))[0]   # none | I | J | both
        rec["level"] = n1 // 100000 if kind != "col" else n2 // 100000
        rec["roof"] = (kind == "beam" and n1 // 100000 >= NF)
        if kind == "brace":
            sp = CD.spec_for(cfg, "brace_end", sec, "brace") or {}
            if sp.get("An_mm2"):
                rec["An_mm2"] = float(sp["An_mm2"])
        if kind == "col":
            ls = cfg.get("column_lateral_support_both_flanges")
            if ls is not None:
                rec["lateral_support_both_flanges"] = bool(ls)
        if kind == "beam":
            try:
                c1, c2 = ops.nodeCoord(n1), ops.nodeCoord(n2)
                d_ = "X" if abs(c2[0] - c1[0]) >= abs(c2[1] - c1[1]) else "Y"
                dcol = max((S.props(reg[tc][1])["d"] for tc in reg if reg[tc][0] == "col" and reg[tc][3] in (n1, n2)),
                           default=0.0)
                rec["L_clear_mm"] = length[t] - dcol
                bdict = {"k": n1 // 100000, "L": length[t], "dir": d_, "_A": S.props(sec)["A"]}
                rec["V_gravity_N"] = SM.one_way_gravity(cfg, bdict, 1.2, 0.5, 0.5)[1]
                rec["V_gravity_cite"] = "1.2DL + 0.5LL simple-span end shear (12.11.2.2)"
            except Exception:
                pass
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
            f["tags"] = tagof.get(f["combo"], [])
            if kindof.get(f["combo"]) == "EQ" and f["family"] == "table4" and "P_LAT_N" in f:
                f["P_EL_N"] = f["P_LAT_N"]        # EL share of the IS 800 Table 4 EQ combination (IS 18168 12.3.2.2)
        if kind == "brace":
            # signed static EQ cases for the 12.7.2.3 / 12.8.2.4 tension-share test (RSA forces are unsigned)
            ts = SM.combo_forces_for_member_check((per_case_tags.get("ts_records") or {}).get(t) or {}, kind)
            for f in ts:
                f["family"] = "tension_share"
            fl += ts
        forces[mid] = fl
    md = {"members": members, "forces": forces,
          "combos_12_2_3_present": any("is800_12_2_3" in v for v in tagof.values()),
          "combos_is18168_5_5_present": any("is18168_5_5" in v for v in tagof.values())}
    # declared connections / bases (india_connection_design)
    conns, bases = [], []
    for m in members:
        if m["role"] == "brace":
            c = CD.brace_end_connection(cfg, m)
            if c:
                conns.append(c)
        if m["role"] == "column" and (m["node_i"] // 100000) == 0:
            lc = CD.base_load_cases(per_case_tags["records"].get(m["tag"]) or {})
            b = CD.base_entry(cfg, m, lc)
            if b:
                bases.append(b)
    md["connections"], md["bases"] = conns, bases
    # brace lines: the +/- Table 4 DL+EL combination in the line's direction (torsion variant a)
    lines = {}
    for m in members:
        if m["role"] == "brace" and m.get("line"):
            lines.setdefault(m["line"], []).append(m["id"])
    bl = []
    ts_labels = per_case_tags.get("ts_labels") or {}
    for ln, ids in lines.items():
        d = ln[0]
        combos = {sg: lab for sg, lab in (ts_labels.get(d) or {}).items()}
        bl.append({"id": ln, "braces": ids, "combos": combos})
    md["brace_lines"] = bl
    # EBF links (IS 18168:2023 11 / 12.3): declared by the custom_build as info['links'] (WP6)
    md["links"] = ebf_links_model_data(cfg, info0, reg, members, forces, run)
    return md


def ebf_links_model_data(cfg, info0, reg, members, forces, run=None):
    """model_data['links'] for india_is800_s12.ebf_link_checks from the links the custom_build declared:
    info['links'] = [{tag, e_mm, bay_L_mm, brace_tags, column_tags, beam_tags, end_stiffeners,
    intermediate_stiffener_spacing_mm, braced_both_flanges, connected_to_column, continuous_link_beam, dir, storey}].
    Vu_N / Pu_N = the largest link shear / axial force over the IS 800 Table 4 earthquake combinations (12.3.2.1:
    'based on the analysis required by IS 1893'); the link rotation is (L/e) x the inelastic storey drift, the
    inelastic drift being R x the elastic drift under the design lateral force (IS 1893 7.11.2 wording) at that
    storey in the link's direction (the largest edge drift, 7.11.1.1)."""
    import india_seismic_gates as G
    decl = (info0 or {}).get("links") or cfg.get("ebf_links") or []
    if not decl:
        return []
    by_tag = {m["tag"]: m for m in members}
    R = None
    try:
        R = float(G.declared_R(cfg) or 0.0) or None
    except Exception:
        R = None
    dr = (run or {}).get("drift") or {}
    out = []
    for ln in decl:
        t = int(ln["tag"])
        m = by_tag.get(t)
        if not m:
            continue
        fl = [f for f in forces.get(m["id"], []) if f.get("family") == "table4" and f.get("P_EL_N") is not None]
        Vu = max((abs(f.get("Vy_N") or 0.0) for f in fl), default=None)
        Pu = max((abs(f.get("P_N") or 0.0) for f in fl), default=0.0)
        rec = {"id": "link-%s" % m["id"], "member_id": m["id"], "tag": t, "section": m["section"], "grade": m.get("grade"),
               "e_mm": ln.get("e_mm"), "bay_L_mm": ln.get("bay_L_mm"), "Vu_N": Vu, "Pu_N": Pu,
               "Vu_basis": "max |V| over the IS 800 Table 4 EQ combinations (RSA scaled per 7.7.3.1)",
               "brace_ids": ["e%d" % x for x in (ln.get("brace_tags") or [])],
               "column_ids": ["e%d" % x for x in (ln.get("column_tags") or [])],
               "beam_ids": ["e%d" % x for x in (ln.get("beam_tags") or [])],
               "end_stiffeners": ln.get("end_stiffeners"),
               "intermediate_stiffener_spacing_mm": ln.get("intermediate_stiffener_spacing_mm"),
               "braced_both_flanges": ln.get("braced_both_flanges"),
               "connected_to_column": ln.get("connected_to_column"),
               "continuous_link_beam": ln.get("continuous_link_beam"), "doubler": ln.get("doubler"),
               "dir": ln.get("dir"), "storey": ln.get("storey")}
        d, k = ln.get("dir"), ln.get("storey")
        if ln.get("rotation_rad") is not None:
            rec["rotation_rad"] = ln["rotation_rad"]
        elif R and d in dr and k and 1 <= int(k) <= len(dr[d]["drift"]):
            el = float(dr[d]["drift"][int(k) - 1])
            rec["drift_ratio_inelastic"] = R * el
            rec["drift_basis"] = ("R x elastic storey drift under the design lateral force (IS 1893 7.11.2; edge drift "
                                  "with 7.8.2 eccentricity, 7.11.1.1): %.1f x %.5f" % (R, el))
        out.append(rec)
    return out


def design_india(name, cfg, outdir):
    """India demand + check package (N-mm)."""
    import static_model as SM
    import india_loads as IL
    import india_seismic_gates as G
    import india_connections as C_
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
    sfrs_beams = sfrs_beam_tags(reg, info0)
    tagof = {c[0]: ((getattr(c, "meta", {}) or {}).get("tags") or []) for c in cases}
    # serviceability cases (IS 800 10.4.3 service-load slip of HSFG connections): {label: {fset: rec}}
    try:
        per_sls, _k2, _i2 = SM.solve_cases_si(cfg, cases, nseg, fs_, rsa=rsa_el, service=True)
    except Exception as ex:
        per_sls = {"_error": str(ex)}
    sls_rec = {}
    for lab, res in per_sls.items():
        if lab.startswith("_"):
            continue
        for fs, rec in res.items():
            sls_rec.setdefault(fs, {})[lab] = [round(float(x), 1) for x in rec]

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
                # 12.2.3 forces are for columns / connections; IS 18168 5.5 adds beams of SCBF/EBF and braces of EBF
                keep = (lambda l: ("sfrs_beam" in tagof.get(l, []) and kind == "beam" and t in sfrs_beams) or
                        ("sfrs_brace" in tagof.get(l, []) and kind == "brace"))
                recs = {l: r for l, r in recs.items() if l not in (envt[t].get("conn") or {}) or keep(l)}
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

    # ---- Section 12 (india_is800_s12) with the declared connections / bases / joints ----
    import india_connection_design as CD
    ts_rec, ts_labels = {}, {}
    if any(reg[t][0] == "brace" for t in reg):
        # signed static +/-EQ_X / +/-EQ_Y (ESM story forces, gamma 1.0, LATERAL LOAD ONLY - no gravity) for the
        # 12.7.2.3 / 12.8.2.4 tension-share test: the clause shares "the total lateral load" between the tension
        # braces, so gravity compression in the braces must not enter the split (WP6-fix, CFS finding).
        try:
            plan_ = cfg.get("load_plan") or {}
            tcs = []
            for d in ("X", "Y"):
                if (plan_.get("story_forces") or {}).get("EQ_" + d):
                    for sg, f in (("+", 1.0), ("-", -1.0)):
                        lab = "TS:%s1.0EQ_%s" % (sg, d)
                        tcs.append(IL.case_from_combination({"label": lab, "fD": 0.0, "fL": 0.0, "fLr": 0.0, "fE": f,
                                                             "lateral_ref": "EQ_" + d, "direction": d}, plan_))
                        ts_labels.setdefault(d, {})[sg] = lab
            per_ts, _kk, _ii = SM.solve_cases_si(cfg, tcs, 2, fs_)
            for lab, res in per_ts.items():
                for t in reg:
                    if reg[t][0] == "brace":
                        r_ = res.get(frozenset((reg[t][2], reg[t][3])))
                        if r_ is not None:
                            ts_rec.setdefault(t, {})[lab] = [float(x) for x in r_]
        except Exception as ex:
            ts_labels = {"_error": str(ex)}
    md = section12_model_data(cfg, reg, length, role_of, envt,
                              {"records": {t: envt[t].get("records") or {} for t in reg}, "lateral_beams": sfrs_beams,
                               "ts_records": ts_rec, "ts_labels": {k: v for k, v in ts_labels.items() if k in ("X", "Y")}},
                              cases, info0, run=run)
    mem_by_id = {m["id"]: m for m in md["members"]}
    s12_cfg = dict(cfg.get("section12_inputs") or {}, zone=G.zone_of(cfg), I=G.importance_of(cfg),
                   height_m=G.building_height_m(cfg), brace_config=cfg.get("brace_config"),
                   apply_is18168=cfg.get("apply_is18168"), eor_weld_exception=cfg.get("eor_weld_exception"),
                   is18168_table2=cfg.get("is18168_table2"))
    joint_conn = {}
    try:
        import india_is800_s12 as S12
        nodes = {nd: tuple(ops.nodeCoord(nd)) for nd in ops.getNodeTags()}
        frame = {m["id"] for m in md["members"] if m.get("sfrs")}
        md["joints"] = S12.joints_from_model(nodes, md["members"], frame_members=frame)
        for j in md["joints"]:
            bm = mem_by_id.get(j["beams"][0]["member_id"]) if j.get("beams") else None
            j["roof"] = bool(bm and bm.get("roof"))
            # the joint's connection record comes from the first beam at the joint that has a declared beam_column
            # spec (an SFRS beam piece next to a gravity beam on the same line, WP6)
            for bb in (j.get("beams") or []):
                bm_ = mem_by_id.get(bb["member_id"])
                if bm_ and CD.spec_for(cfg, "beam_column", bm_["section"], "beam"):
                    bm = bm_
                    break
            if bm:
                pb = S.props(bm["section"])
                fyb = CD._fy(bm, pb)[0]
                cn = CD.beam_column_connection(cfg, bm, pb, fyb)
                if cn:
                    j["connection"] = cn
                    joint_conn[bm["section"]] = cn
                    for k in ("continuity_plates", "continuity_plate_t_mm", "doubler_t_mm"):   # t for the OMF 12.10.2.5 check
                        if k in cn:
                            j[k] = cn[k]
    except Exception as ex:
        md["joints_error"] = str(ex)
    try:
        import india_is800_s12 as S12
        s12 = S12.section12_checks(cfg.get("system"), md, s12_cfg)
        pkg["capacity_design"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "section12": _jsonable(s12),
                                  "checks": {c.get("id", "c%d" % i) + ("@" + str(c.get("member")) if c.get("member") else ""):
                                             {"value": c.get("value"), "limit": c.get("limit"), "dc": c.get("dc"),
                                              "ok": c.get("ok"), "pass": c.get("ok"), "clause": c.get("clause"),
                                              "cite": c.get("cite"), "found": c.get("ok") is not None}
                                             for i, c in enumerate(s12.get("checks") or [])}}
    except ImportError as ex:
        s12 = {"checks": []}
        pkg["capacity_design"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "checks": {},
                                  "error": "india_is800_s12.section12_checks unavailable: %s" % ex}
    except Exception as ex:
        s12 = {"checks": []}
        pkg["capacity_design"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "checks": {},
                                  "error": "section12_checks failed: %s" % ex}
    if cfg.get("delegated_design"):
        # the delegated-design register (consistency B8): items handed off with their criteria and interface forces
        pkg["capacity_design"]["delegated_design"] = _jsonable(cfg["delegated_design"])
    s12_by_member = {}
    for c in s12.get("checks") or []:
        s12_by_member.setdefault(c.get("member"), []).append(c)

    # ---- connections: demands + capacities from the declared geometry (india_connection_design) ----
    def _row(name, c, **extra):
        r = {"name": name, "value": c.get("value"), "limit": c.get("limit"), "dc": c.get("dc"), "ok": c.get("ok"),
             "clause": c.get("clause"), "cite": c.get("cite"), "source": c.get("source", CD.SRC)}
        if c.get("reason"):
            r["reason"] = c["reason"]
        if c.get("ok") is None:
            r["found"] = False
        elif (r["value"] is None and r["limit"] is None) or c.get("gate") is True:
            r["gate"] = True                     # boolean detailing gate (weld type / bolt type / load sharing)
        r.update(extra)
        return r

    def _conn_force_sls(t, kind):
        best = 0.0
        for lab, r in (sls_rec.get(frozenset((reg[t][2], reg[t][3]))) or {}).items():
            best = max(best, abs(r[0]) if kind == "brace" else abs(r[3]))
        return best

    for key, tags in sorted(by.items()):
        kind, sec, role = key
        g = {q: max(envt[t][q] for t in tags) for q in ("comp", "tens", "Mz", "My", "V")}
        conn_max = 0.0
        for t in tags:
            for r in (envt[t].get("conn") or {}).values():
                conn_max = max(conn_max, abs(r[0]))
        checks, notes = [], []
        if kind == "beam":
            ctype = "beam-to-column"
            dem = {"V_N": round(g["V"], 1), "M_Nmm": round(g["Mz"], 1), "P_N": round(max(g["comp"], g["tens"]), 1)}
            sfrs_tags = [t for t in tags if t in sfrs_beams]
            if sfrs_tags and G.section12_system(cfg) and S12.normalize_system(cfg.get("system")) in ("SMF", "OMF"):
                # moment connection: the per-joint 12.11.2 checks (demand 1.2 Mp, shear) live in capacity_design
                ids = {"connection_moment", "connection_shear", "12.4.2_weld_type", "12.4.1_bolt_type"}
                worst = {}
                for t in sfrs_tags:
                    for c in s12_by_member.get("e%d" % t, []):
                        if c["id"] in ids:
                            w = worst.get(c["id"])
                            k_ = (c.get("ok") is None, c.get("dc") if c.get("dc") is not None else -1)
                            if w is None or k_ > w[0]:
                                worst[c["id"]] = (k_, c)
                for cid, (_, c) in worst.items():
                    checks.append(_row("IS 800 12.11.2 %s (joint %s)" % (cid, c.get("member")), c))
                cn = joint_conn.get(sec)
                if cn and cn.get("moment_capacity_Nmm"):
                    dem["M_1p2Mp_Nmm"] = None
                    notes.append("moment capacity %.1f kN-m (%s)" % (cn["moment_capacity_Nmm"] / 1e6, cn.get("type")))
                if not checks:
                    checks.append(_row("IS 800 12.11.2 moment connection", {"ok": None, "clause": "IS 800:2007 12.11.2",
                                                                            "reason": "no joint checks for this beam group"}))
                # a moment-frame beam pinned at one end (corner bay whose corner column belongs to the orthogonal
                # frame): that end is a shear connection under the governing V (WP6-fix)
                rel_ = info0.get("beam_rel") or {}
                if any((rel_.get(t) or ("none",))[0] in ("I", "J") for t in sfrs_tags):
                    r = CD.beam_shear_connection_checks(cfg, {"section": sec, "role": "beam"}, g["V"])
                    if r is None:
                        checks.append(_row("IS 800 10 shear connection (pinned end)", {
                            "ok": None, "clause": "IS 800:2007 10.3 / 8.4.1 / 6.4.1",
                            "reason": "cfg['connections']['beam_shear'] not declared for %s (pinned end of the SMF beam)" % sec}))
                    else:
                        for nm, c in r["checks"].items():
                            checks.append(_row("pinned-end shear connection: %s" % nm, c))
            else:
                # braced-bay / gravity beam: shear connection under the governing V (SFRS braced-bay beams: also the
                # collector axial is carried by the member check; the connection sees V and the 12.2.3 axial)
                Vd = g["V"]
                r = CD.beam_shear_connection_checks(cfg, {"section": sec, "role": "beam"}, Vd)
                if r is None:
                    checks.append(_row("IS 800 10 shear connection", {"ok": None, "clause": "IS 800:2007 10.3 / 8.4.1 / 6.4.1",
                                                                       "reason": "cfg['connections']['beam_shear'] not declared for %s" % sec}))
                else:
                    for nm, c in r["checks"].items():
                        checks.append(_row("beam-end shear connection: %s" % nm, c))
                    sp = CD.spec_for(cfg, "beam_shear", sec, "beam") or {}
                    if sp.get("bolts") and (sfrs_tags or sp.get("bolt_type")):
                        sl = CD.hsfg_slip_checks(sp.get("bolts"), sp.get("bolt_type"),
                                                 max(_conn_force_sls(t, "beam") for t in tags), Vd,
                                                 slip_surface=sp.get("slip_surface"), mu_f=sp.get("mu_f"))
                        for nm, c in (sl or {}).items():
                            checks.append(_row("beam-end bolts %s" % nm, c))
                    if sfrs_tags:
                        checks.append(_row("12.4.2 weld type", dict(C_.cjp_weld_gate(sp.get("weld_type") or ("cjp" if sp.get("cjp") else None),
                                                                             location="beam_column", sfrs=True,
                                                                             eor_exception=cfg.get("eor_weld_exception")))))
                        if sp.get("bolts"):
                            checks.append(_row("12.4.1 bolt type", dict(C_.hsfg_gate(sp.get("bolt_type")))))
        elif kind == "brace":
            ctype = "brace-to-gusset"
            dem = {"axial_N": round(max(g["comp"], g["tens"]), 1), "axial_12_2_3_N": round(conn_max, 1)}
            try:
                m0 = mem_by_id["e%d" % tags[0]]
                cf = S12.brace_connection_force(cfg.get("system"), m0, md, conn=CD.brace_end_connection(cfg, m0), cfg=s12_cfg)
                dem["Pu_capacity_design_N"] = round(cf["demand_N"], 1) if cf.get("found") else None
                dem["Pu_capacity_design_basis"] = cf.get("basis")
            except Exception as ex:
                dem["Pu_capacity_design_N"] = None
                dem["Pu_capacity_design_error"] = str(ex)
            ids = {"brace_conn_bolts", "brace_conn_welds", "brace_conn_block_shear", "brace_conn_net_rupture",
                   "gusset_whitmore_yield", "gusset_out_of_plane_buckling", "brace_conn_1p2Mp", "12.4.2_weld_type",
                   "12.4.1_bolt_type", "12.4.3_no_load_sharing", "brace_conn_fasteners", "brace_connection",
                   "brace_connection_force", "brace_conn_pinned_12.3.4.6"}
            worst = {}
            for t in tags:
                for c in s12_by_member.get("e%d" % t, []):
                    if c["id"] in ids:
                        w = worst.get(c["id"])
                        k_ = (c.get("ok") is None, c.get("dc") if c.get("dc") is not None else -1)
                        if w is None or k_ > w[0]:
                            worst[c["id"]] = (k_, c)
            for cid, (_, c) in worst.items():
                if cid == "brace_connection_force":
                    continue
                checks.append(_row("brace end: %s" % cid, c))
            sp = CD.spec_for(cfg, "brace_end", sec, "brace") or {}
            if sp.get("bolts"):
                sl = CD.hsfg_slip_checks(sp.get("bolts"), sp.get("bolt_type"), max(_conn_force_sls(t, "brace") for t in tags),
                                         dem.get("Pu_capacity_design_N"), slip_surface=sp.get("slip_surface"),
                                         mu_f=sp.get("mu_f"), slip_at_ultimate=bool(sp.get("slip_at_ultimate")))
                for nm, c in (sl or {}).items():
                    checks.append(_row("brace end bolts %s" % nm, c))
            if not checks:
                checks.append(_row("IS 800 12.8.3 / 12.7.3 brace connection", {"ok": None, "clause": "IS 800:2007 12.8.3",
                                                                                "reason": "cfg['connections']['brace_end'] not declared for %s" % sec}))
        else:
            ctype = "column splice / base"
            dem = {"P_N": round(g["comp"], 1), "T_N": round(g["tens"], 1), "M_Nmm": round(g["Mz"], 1),
                   "V_N": round(g["V"], 1), "P_12_2_3_N": round(conn_max, 1)}
            base_tags = [t for t in tags if reg[t][2] // 100000 == 0]
            bchecks = {}
            for t in base_tags:
                for c in s12_by_member.get("base-e%d" % t, []):
                    w = bchecks.get(c["id"])
                    k_ = (c.get("ok") is None, c.get("dc") if c.get("dc") is not None else -1)
                    if w is None or k_ > w[0]:
                        bchecks[c["id"]] = (k_, c)
            for cid, (_, c) in bchecks.items():
                det = c.get("detail") or {}
                for nm, cc in (det.get("checks") or {}).items():
                    if isinstance(cc, dict) and ("limit" in cc or cc.get("ok") is None):
                        checks.append(_row("column base (%s): %s" % (c.get("member"), nm), cc,
                                           governing_combo=c.get("governing_combo")))
                dem["base_demands"] = det.get("demands")
            if base_tags and not bchecks:
                checks.append(_row("IS 800 7.4 / 12.12 column base", {"ok": None, "clause": "IS 800:2007 7.4 / 12.12",
                                                                        "reason": "cfg['connections']['column_base'] not declared for %s" % sec}))
            upper = [t for t in tags if t not in base_tags]
            if upper:
                m0 = mem_by_id["e%d" % upper[0]]
                p0 = S.props(sec); fy0 = CD._fy(m0, p0)[0]
                recs_u = {}
                for t in upper:
                    for l, r in (envt[t].get("records") or {}).items():
                        if l not in recs_u or abs(r[0]) > abs(recs_u[l][0]):
                            recs_u[l] = r
                spl = CD.column_splice(cfg, m0, p0, fy0, recs_u, sfrs=(role == "lateral_col"))
                if spl is None:
                    checks.append(_row("IS 800 12.5.2 column splice", {"ok": None, "clause": "IS 800:2007 12.5.2 / 10",
                                                                        "reason": "cfg['connections']['column_splice'] not declared for %s" % sec}))
                else:
                    for nm, cc in spl["checks"].items():
                        checks.append(_row("column splice: %s" % nm, cc))
        dcs = [c["dc"] for c in checks if isinstance(c.get("dc"), (int, float))]
        pkg["connections"].append({"id": "conn-%s-%s" % (role, sec), "type": ctype, "section": sec, "demand": dem,
                                   "inputs": dict(dem, V_N=dem.get("V_N", dem.get("axial_N"))),
                                   "design_basis": "IS 800:2007 Section 10 / 7.4 / Section 12 (india_connections, "
                                                   "india_connection_design; declared geometry in cfg['connections'])",
                                   "checks": checks, "DC": max(dcs) if dcs else None,
                                   "limit_state": "IS 800:2007 10 / 7.4 / 12", "cited": None, "notes": notes})

    # ---- composite floors (WP2.9) ----
    _blob = (str(cfg.get("floor_system", "")) + " " + str(cfg.get("notes", "")) + " " + str(cfg.get("arch", ""))).lower()
    if "composite" in _blob or cfg.get("composite") or cfg.get("composite_scope"):
        try:
            _bdirs = {}
            for (t_, k_, s_, n1_, n2_) in info0["ele"]:
                if k_ == "beam":
                    c1_, c2_ = ops.nodeCoord(n1_), ops.nodeCoord(n2_)
                    _bdirs.setdefault(s_, set()).add("X" if abs(c2_[0] - c1_[0]) >= abs(c2_[1] - c1_[1]) else "Y")
            pkg["composite_design"] = {"status": "evaluated", "chI_worksheet": CD.composite_design_record(cfg, pkg["members"], beam_dirs=_bdirs),
                                       "note": "WP2.9: IS 11384 not in the corpus; scope per COMPOSITE_INDIA.md"}
            pkg["composite_design"]["blocks_complete"] = pkg["composite_design"]["chI_worksheet"].get("blocks_complete")
        except Exception as ex:
            pkg["composite_design"] = {"status": "error", "error": str(ex), "blocks_complete": True}

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
    # IS 1893 7.6.4 diaphragm classification (rigid: 7.8.2 torsion in the model; flexible: tributary distribution)
    try:
        import india_diaphragm as DIA
        d764 = dict(cfg.get("diaphragm_7_6_4") or {})
        d764.setdefault("declared", str(cfg.get("diaphragm") or "rigid").lower())
        d764.setdefault("plan_aspect_ratio", max(cfg["NX"] * cfg["SX"], cfg["NY"] * cfg["SY"]) /
                        max(min(cfg["NX"] * cfg["SX"], cfg["NY"] * cfg["SY"]), 1.0))
        rec764 = DIA.classify_7_6_4(**d764)
        rec764["model"] = "rigid diaphragm constraint + 7.8.2 eccentricity" if not rec764.get("flexible") else \
            "tributary-width storey-shear distribution to the lateral lines (no diaphragm torsion)"
        if rec764.get("flexible"):
            rec764["line_shears"] = _jsonable(DIA.flexible_diaphragm_line_shears(cfg, "EQ"))
        pkg["diaphragm_7_6_4"] = rec764
    except Exception as ex:
        pkg["diaphragm_7_6_4"] = {"clause": "IS 1893 (Part 1):2016 7.6.4", "ok": None, "error": str(ex)}
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
            pkg["gantry_girder"] = {"demands": _jsonable(gd), "section": (IL._crane_def(cfg).get("gantry_section")),
                                    "note": "IS 800 checks: LTB with the declared restraint, top-flange surge, web "
                                            "bearing / buckling under the wheel, Table 6 deflections, Section 13 fatigue"}
            pkg["gantry_girder"].update(_jsonable(gantry_girder_checks(cfg, gd)))
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
    """WP2.7 secondary members (joists / purlins / girts) -- simple-span demands per combination + the
    IS 800 checks (WP6-fix: the demand-only record blocked COMPLETE for every job that declared them)."""
    sec = cfg.get("secondary_members") or []
    if not sec:
        return
    out = []
    for s_ in sec:
        rec = secondary_member_demand(cfg, s_)
        rec.update(secondary_member_checks(cfg, s_, rec))
        out.append(rec)
    pkg["secondary_members"] = out


def secondary_member_demand(cfg, s_):
    """{id, section, span_mm, spacing_mm, level ('floor'|'roof'), wind_uplift_kNm2?, D_kNm2?, L_kNm2?,
    snow_kNm2?, extra_cases[{label, w_kNm2}]?} -> simple-span demands per combination for the IS 800 check
    (sagging LTB restrained by the deck, hogging / uplift needs the fly-brace / sag-rod spacing)."""
    roof = s_.get("level") == "roof"
    D = float(s_["D_kNm2"]) if s_.get("D_kNm2") is not None else float(cfg.get("D_roof" if roof else "D_floor") or 0.0)
    if s_.get("L_kNm2") is not None:
        Lp = float(s_["L_kNm2"])
    else:
        Lp = float(cfg.get("Lr") or 0.0) if roof else (float(cfg.get("L_floor") or 0.0) +
                                                        float(cfg.get("partition_load_kNm2") or 0.0))
    S_ = float(s_["snow_kNm2"]) if s_.get("snow_kNm2") is not None else (float(cfg.get("snow") or 0.0) if roof else 0.0)
    sp = float(s_["spacing_mm"]); L = float(s_["span_mm"])
    try:
        A_sw = float(S.props(s_["section"])["A"]) if s_.get("section") else 0.0
    except Exception:
        A_sw = 0.0
    from static_model import STEEL_UNIT_WEIGHT_N_PER_MM3 as _SW
    wsw = A_sw * _SW                                              # N/mm self-weight
    up = float(s_.get("wind_uplift_kNm2") or 0.0)
    cases = [("1.5DL+1.5LL", 1.5, 1.5, 0.0, 0.0)]
    if S_ > 0:
        cases.append(("1.5DL+1.5SL", 1.5, 0.0, 1.5, 0.0))
    if up > 0:
        cases.append(("0.9DL+1.5WL(uplift)", 0.9, 0.0, 0.0, 1.5))
    rows = []
    for lab, fD, fL, fS, fW in cases:
        wv = (fD * D + fL * Lp + fS * S_ - fW * up) * sp / 1000.0 + fD * wsw     # N/mm (+ down)
        rows.append({"combo": lab, "w_N_per_mm": round(wv, 3), "M_Nmm": round(wv * L * L / 8.0, 1),
                     "V_N": round(abs(wv) * L / 2.0, 1), "sign": "sagging" if wv >= 0 else "hogging"})
    for ex in (s_.get("extra_cases") or []):                    # e.g. IS 875-4 5.2.4 drift snow on a lean-to
        wv = float(ex["w_kNm2"]) * sp / 1000.0 + float(ex.get("fD", 1.5)) * wsw
        rows.append({"combo": ex["label"], "w_N_per_mm": round(wv, 3), "M_Nmm": round(wv * L * L / 8.0, 1),
                     "V_N": round(abs(wv) * L / 2.0, 1), "sign": "sagging" if wv >= 0 else "hogging",
                     "cite": ex.get("cite")})
    return {"id": s_.get("id"), "section": s_.get("section"), "span_mm": L, "spacing_mm": sp, "level": s_.get("level"),
            "loads_kNm2": {"D": D, "L": Lp, "S": S_, "wind_uplift": up}, "self_weight_N_per_mm": round(wsw, 4),
            "demands": rows, "check": "india_is800.member_check_is800 with LLT_sag = deck restraint, "
                                      "LLT_hog = fly-brace spacing (IS 800 8.2.2)"}


def _sls_deflection_row(cfg, s_, L, w_service_N_per_mm, sec, key_default):
    """IS 800 Table 6 deflection of a simply supported secondary member under the service load."""
    A, Ix, Iy, J = E.Ipack(sec)
    delta = 5.0 * w_service_N_per_mm * L ** 4 / (384.0 * E.E * Ix)
    key = s_.get("deflection_key") or key_default
    div = float(IL.IS800_TABLE6[key])
    lim = L / div
    return {"name": "IS 800 Table 6 deflection (%s, span/%d)" % (key, int(div)), "value": round(delta, 2),
            "limit": round(lim, 2), "dc": delta / lim, "ok": delta <= lim, "clause": "IS 800:2007 5.6.1 / Table 6",
            "cite": IL.IS800_TABLE6_CITE, "source": "design_pipeline._sls_deflection_row (5 w L^4 / 384 E I)"}


def secondary_member_checks(cfg, s_, rec):
    """IS 800 member check of a declared secondary member (purlin / girt / joist / filler beam / lean-to beam)
    from its simple-span demands: 8.2.2 LTB with LLT_sag (deck / sheeting restraint) and LLT_hog (fly braces
    or sag rods), shear 8.4, Table 6 deflection under the service imposed / snow / wind load."""
    sec = s_.get("section")
    if not sec:
        return {"checks": [{"name": "IS 800 member check", "value": None, "limit": None, "dc": None, "ok": None,
                            "found": False, "reason": "secondary member has no section"}], "DC": None}
    L = float(s_["span_mm"])
    mem = {"id": s_.get("id"), "section": sec, "grade": s_.get("grade") or cfg.get("steel_grade"), "role": "beam",
           "L_mm": L, "Kz": 1.0, "Ky": 1.0, "LLT_sag_mm": float(s_.get("LLT_sag_mm") or L),
           "LLT_hog_mm": float(s_.get("LLT_hog_mm") or L), "process": s_.get("process")}
    cf = []
    for r in rec["demands"]:
        M = float(r["M_Nmm"])
        cf.append({"combo": r["combo"], "P_N": 0.0, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0, "Mz_mid_Nmm": M,
                   "My_i_Nmm": 0.0, "My_j_Nmm": 0.0, "Vy_N": float(r["V_N"]), "Vz_N": 0.0})
    try:
        import india_is800 as I8
        res = I8.member_check_is800(mem, cf, cfg=cfg)
    except Exception as ex:
        res = {"found": False, "ok": None, "dc": None, "reason": "member_check_is800 failed: %s" % ex}
    rows = _check_rows(res)
    # service deflection: imposed (or snow) load only, IS 800 Table 6
    sp = float(s_["spacing_mm"])
    lo = rec["loads_kNm2"]
    w_sls = max(lo["L"], lo["S"]) * sp / 1000.0
    for ex in (s_.get("extra_cases") or []):
        if ex.get("service_w_kNm2") is not None:
            w_sls = max(w_sls, float(ex["service_w_kNm2"]) * sp / 1000.0)
    if w_sls > 0:
        key = "purlin_girt_elastic" if s_.get("level") == "roof" else "floor_roof_live_cracking"
        rows.append(_sls_deflection_row(cfg, s_, L, w_sls, sec, key))
    dcs = [c["dc"] for c in rows if isinstance(c.get("dc"), (int, float))]
    return {"checks": rows, "DC": (max(dcs) if dcs and all(isinstance(c.get("dc"), (int, float)) for c in rows) else None),
            "member_result": _jsonable({k: v for k, v in (res or {}).items() if k != "per_combo"}),
            "LLT_sag_mm": mem["LLT_sag_mm"], "LLT_hog_mm": mem["LLT_hog_mm"]}


def gantry_girder_checks(cfg, gd):
    """IS 800 checks of the declared gantry girder (cfg['crane']['gantry_section'], 'gantry_LLT_mm' = spacing of
    the compression-flange lateral restraints, 'gantry_grade'): 8.2.2 LTB on the vertical moment (crane vertical
    load with the 6.3(a) impact + self-weight, IS 800 Table 4 DL+LL+CL factor 1.5), surge on the top flange
    (9.3.1.1 biaxial, surge moment resisted by the top flange alone -> checked against Mdy/2, and the linear sum
    with the LTB moment as the conservative practice bound), 8.4 shear, 8.7.4 web bearing and 8.7.3.1 web
    buckling under the wheel (stiff bearing = rail foot + 2 x flange thickness at 45 deg), Table 6 vertical
    deflection span/750 (static wheel loads, no impact) and 10 mm lateral / span/400.  IS 800 Section 13 fatigue:
    stress range at the bottom flange under the static wheel loads vs the detail category's fatigue strength at
    the EOR-declared cycle count (cfg['crane']['fatigue'] = {detail_category_MPa, cycles, cite})."""
    import india_is800 as I8
    cr = IL._crane_def(cfg)
    sec = cr.get("gantry_section")
    if not sec:
        return {"checks": [{"name": "gantry girder", "value": None, "limit": None, "dc": None, "ok": None, "found": False,
                            "reason": "cfg['crane']['gantry_section'] not declared"}], "DC": None}
    p = S.props(sec)
    grade = cr.get("gantry_grade") or cfg.get("steel_grade")
    mat = I8.material_for_section(p, grade)
    fy = mat.get("fy_MPa")
    L = float(cr["gantry_span_mm"])
    LLT = float(cr.get("gantry_LLT_mm") or L)
    from static_model import STEEL_UNIT_WEIGHT_N_PER_MM3 as _SW
    wsw = float(p["A"]) * _SW + float(cr.get("rail_weight_N_per_mm") or 0.0)
    Msw = wsw * L * L / 8.0; Vsw = wsw * L / 2.0
    fC = 1.5; fD = 1.5                                            # IS 800 Table 4 DL+LL+CL (CL leading): 1.5 / 1.5
    Mz = fD * Msw + fC * gd["M_vertical_Nmm"]
    My = fC * gd["M_surge_Nmm"]
    V = fD * Vsw + fC * gd["V_vertical_N"]
    mem = {"id": "gantry", "section": sec, "grade": grade, "role": "beam", "L_mm": L, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": LLT, "LLT_hog_mm": L}
    cap = cr.get("top_flange_cap") or {}                          # EOR-declared surge system on the top flange
    # (e.g. channel cap / surge girder): {Iy_mm4, Zpy_mm3, cite} -> lateral stiffness and surge capacity of the
    # capped flange replace the bare top flange (Iy/2, Mdy/2)
    cf = [{"combo": "1.5DL+1.5CL(vertical+impact+surge)", "P_N": 0.0, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0, "Mz_mid_Nmm": Mz,
           "My_i_Nmm": 0.0 if cap else 2.0 * My, "My_j_Nmm": 0.0 if cap else 2.0 * My, "Vy_N": V, "Vz_N": 0.0}]
    res = I8.member_check_is800(mem, cf, cfg=cfg)                  # 2 x My: bare top flange alone (Mdy/2)
    rows = _check_rows(res)
    caps = res.get("capacities") or {}
    Mdz_ltb = None
    for pc in res.get("per_combo") or []:
        for c in pc.get("checks") or []:
            if c.get("Mdz_LTB_Nmm"):
                Mdz_ltb = c["Mdz_LTB_Nmm"]
    Mdy = (caps.get("Mdy") or {}).get("Md_Nmm")
    if cap and cap.get("Zpy_mm3"):
        Mdy_top = float(cap["Zpy_mm3"]) * fy / 1.10
        top_note = "capped top flange (%s): Mdy_top = Zpy fy / gamma_m0 = %.1f kN-m" % (cap.get("cite"), Mdy_top / 1e6)
    else:
        Mdy_top = 0.5 * Mdy if Mdy else None
        top_note = "bare top flange alone (Mdy/2)"
    if Mdz_ltb and Mdy_top:
        lin = Mz / Mdz_ltb + My / Mdy_top
        rows.append({"name": "gantry biaxial: Mz/Mdz(LTB, LLT %.0f mm) + M_surge/Mdy_top (%s)" % (LLT, top_note),
                     "value": round(lin, 4), "limit": 1.0, "dc": lin, "ok": lin <= 1.0,
                     "clause": "IS 800:2007 8.2.2 + 9.3.1.1 (linear sum, conservative practice bound)",
                     "cite": "top flange resists the surge alone; LTB moment capacity for the restraint spacing declared",
                     "source": "design_pipeline.gantry_girder_checks"})
    # web bearing (8.7.4) and web buckling (8.7.3.1) under one wheel with impact, factored
    W = fC * gd["wheel_load_with_impact_N"]
    tw, tf, d = float(p["tw"]), float(p["tf"]), float(p["d"])
    b1 = float(cr.get("rail_foot_mm") or 0.0)
    n2 = 2.5 * (tf + float(p.get("R1") or p.get("r1") or 0.0))          # 8.7.4: 1:2.5 dispersion through the flange
    Fw_bearing = (b1 + 2.0 * n2) * tw * fy / 1.10
    rows.append({"name": "gantry web bearing under the wheel (8.7.4, b1 = rail foot %.0f mm)" % b1, "value": round(W, 1),
                 "limit": round(Fw_bearing, 1), "dc": W / Fw_bearing, "ok": W <= Fw_bearing, "clause": "IS 800:2007 8.7.4",
                 "cite": "Fw = (b1 + n2) tw fyw / gamma_m0, n2 = 2.5 (tf + r) each side", "source": "design_pipeline.gantry_girder_checks"})
    # 8.7.3.1 web buckling: strut of width (b1 + n1), n1 = d/2 dispersion at 45 deg, KL = 0.7 d, r = tw/sqrt(12)
    n1 = d / 2.0
    bw = b1 + 2.0 * n1
    KL = 0.7 * d; r_ = tw / math.sqrt(12.0)
    Pd_web = None
    try:
        lam = (KL / r_) / (math.pi * math.sqrt(200000.0 / fy))
        chi = I8.chi_reduction(lam, I8.alpha_for_class("c")["alpha"])["chi"]     # Table 7 class c (7.1.2.2)
        if chi is not None:
            Pd_web = chi * bw * tw * fy / 1.10
    except Exception:
        Pd_web = None
    if Pd_web:
        rows.append({"name": "gantry web buckling under the wheel (8.7.3.1, strut width b1 + d, KL = 0.7 d)", "value": round(W, 1),
                     "limit": round(Pd_web, 1), "dc": W / Pd_web, "ok": W <= Pd_web, "clause": "IS 800:2007 8.7.3.1 / 7.1.2.1",
                     "cite": "web strut of width b1 + 2 x d/2 at 45 deg, buckling class c, KL = 0.7 d",
                     "source": "design_pipeline.gantry_girder_checks"})
    # deflection: static wheel loads (no impact) at the absolute-max moment position, simply supported
    A, Ix, Iy, J = E.Ipack(sec)
    Ws = gd["wheel_load_N"]; c = float(cr["wheel_base_mm"]); n = int(cr.get("wheels_per_side") or 2)
    xs0 = [i * c for i in range(n)]
    dmax = 0.0
    for s_ in range(0, 201):
        off = -xs0[-1] + (L + xs0[-1]) * s_ / 200.0
        pos = [x + off for x in xs0 if 0.0 <= x + off <= L]
        if not pos:
            continue
        # mid-span deflection of a simply supported beam under point loads (Ws at a): P b x (L^2 - b^2 - x^2)/(6 E I L) at x <= a
        dm = 0.0
        for a in pos:
            b = L - a
            x = L / 2.0
            if x <= a:
                dm += Ws * b * x * (L * L - b * b - x * x) / (6.0 * E.E * Ix * L)
            else:
                aa, bb = b, a
                dm += Ws * bb * x * (L * L - bb * bb - x * x) / (6.0 * E.E * Ix * L)
        dmax = max(dmax, dm)
    lim = gd["defl_limit_vertical_mm"]
    rows.append({"name": "gantry vertical deflection (%s)" % gd["defl_limit_basis"], "value": round(dmax, 2), "limit": round(lim, 2),
                 "dc": dmax / lim, "ok": dmax <= lim, "clause": "IS 800:2007 Table 6", "cite": IL.IS800_TABLE6_CITE,
                 "source": "design_pipeline.gantry_girder_checks (static wheel loads, no impact, absolute-max position)"})
    Hs = gd["M_surge_Nmm"] / max(gd["M_static_Nmm"], 1.0) * Ws                # surge per wheel (service)
    Iy_top = float(cap["Iy_mm4"]) if cap.get("Iy_mm4") else Iy / 2.0
    dlat = 0.0
    for a in (L / 2.0 - c / 2.0, L / 2.0 + c / 2.0):
        if 0 <= a <= L:
            b = L - a; x = L / 2.0
            if x <= a:
                dlat += Hs * b * x * (L * L - b * b - x * x) / (6.0 * E.E * Iy_top * L)
            else:
                dlat += Hs * a * x * (L * L - a * a - x * x) / (6.0 * E.E * Iy_top * L)
    rows.append({"name": "gantry lateral deflection under surge (top flange%s, Table 6 span/400 and 10 mm)"
                         % (" + cap" if cap else ""), "value": round(dlat, 2),
                 "limit": round(min(gd["lateral_limit_mm"], gd["lateral_relative_rails_limit_mm"]), 2),
                 "dc": dlat / min(gd["lateral_limit_mm"], gd["lateral_relative_rails_limit_mm"]),
                 "ok": dlat <= min(gd["lateral_limit_mm"], gd["lateral_relative_rails_limit_mm"]), "clause": "IS 800:2007 Table 6",
                 "cite": IL.IS800_TABLE6_CITE + "; lateral stiffness Iy_top = %.3e mm4 (%s)" % (Iy_top, top_note),
                 "source": "design_pipeline.gantry_girder_checks"})
    # Section 13 fatigue: stress range at the bottom flange under the static wheel loads (13.2.2: no impact / partial
    # factors on the load), constant-amplitude, vs the detail category strength at the declared cycle count (13.5.2.1)
    fat = cr.get("fatigue") or {}
    fr = gd["M_static_Nmm"] / float(p["Sx"])
    if fat.get("detail_category_MPa") and fat.get("cycles"):
        ffn = float(fat["detail_category_MPa"]); Nsc = float(fat["cycles"])
        if Nsc <= 5.0e6:
            ff = ffn * (5.0e6 / Nsc) ** (1.0 / 3.0)
        elif Nsc <= 1.0e8:
            ff = ffn * (5.0e6 / Nsc) ** (1.0 / 5.0)
        else:
            ff = ffn * (5.0e6 / 1.0e8) ** (1.0 / 5.0)
        gmft = float(fat.get("gamma_mft") or 1.35)                  # Table 25 fail-safe / non-fail-safe: EOR-declared
        ffd = ff / gmft
        rows.append({"name": "gantry fatigue (IS 800 13.5.2.1, detail category %.0f MPa, %.2e cycles, gamma_mft %.2f)" % (ffn, Nsc, gmft),
                     "value": round(fr, 2), "limit": round(ffd, 2), "dc": fr / ffd, "ok": fr <= ffd,
                     "clause": "IS 800:2007 13.5.2.1 / 13.2.2 / Table 25 / Table 26", "cite": fat.get("cite"),
                     "source": "design_pipeline.gantry_girder_checks (stress range = M_static / Ze at the bottom flange)"})
    else:
        rows.append({"name": "gantry fatigue (IS 800 Section 13)", "value": round(fr, 2), "limit": None, "dc": None, "ok": None,
                     "found": False, "clause": "IS 800:2007 13.5.2.1", "reason": "cfg['crane']['fatigue'] = {detail_category_MPa, "
                     "cycles, gamma_mft, cite} (Table 26 detail category, duty cycles) not declared",
                     "source": "design_pipeline.gantry_girder_checks"})
    dcs = [c["dc"] for c in rows if isinstance(c.get("dc"), (int, float))]
    return {"checks": rows, "DC": (max(dcs) if dcs and all(isinstance(c.get("dc"), (int, float)) for c in rows) else None),
            "factored": {"Mz_Nmm": round(Mz, 1), "M_surge_Nmm": round(My, 1), "V_N": round(V, 1), "wheel_with_impact_N": round(W, 1)},
            "self_weight_N_per_mm": round(wsw, 4), "LLT_mm": LLT, "grade": grade, "fy_MPa": fy,
            "member_result": _jsonable({k: v for k, v in res.items() if k != "per_combo"})}


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
    n_candidates = 0
    for t, (kind, sec, n1, n2) in reg.items():
        if kind != "col" or ((n1 % 100000) // 100, n1 % 100) in lat_lines:
            continue
        n_candidates += 1
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
    if n_candidates == 0:
        # every column line carries a moment-frame beam or a brace: there is no non-SFRS column to check (WP6)
        out["no_non_sfrs_columns"] = True
        out["note"] = ("every column belongs to a lateral-load-resisting line (moment or braced frame); IS 1893 7.11.2 "
                       "has no non-SFRS member to check -- the SFRS members are designed for the 7.11.1 drift")
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
