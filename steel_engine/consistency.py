"""
consistency.py -- numerical SELF-CONSISTENCY check for a finished design.

Loads <root>/<name>/design/calc_package.json (or a passed-in dict) and flags INTERNAL
inconsistencies before the report is finalised -- the class of bug where two scripts compute the
same quantity differently and the two are never reconciled (e.g. a 1/4" plate at D/C 1.00 in one
script vs a 9/16" plate at D/C 0.77 in another, both left in the package).

For every member AND connection it checks:
  * completeness -- a limit state, a D/C and a cited clause exist (top-level OR inside a `checks`
                    list -- connections legitimately carry these per limit-state);
  * bound        -- no D/C (anywhere) exceeds 1.0;
  * governing    -- the headline D/C equals the MAX of the per-limit-state check D/Cs (this is what
                    catches a headline 0.77 sitting on top of a check that is really 1.00);
  * recompute    -- where a demand and a capacity are both recoverable (numeric fields, or an
                    "Ru=.. -> phiRn=.." style demand string), D/C == demand / capacity to tolerance;
  * one-value    -- a labelled+unit quantity (plate thickness, D/C, ...) that appears more than once
                    in the entry's text must carry ONE value; conflicting numbers are flagged.

check(name) prints a PASS/FAIL summary and returns the list of issue strings ([] == consistent).
Never raises -- a malformed package is itself reported as an issue.
"""
import os, json, re

TOL = 0.04   # 4% relative tolerance on recomputed ratios


def _here_repo():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root (engine/..)


def _num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        m = re.search(r"-?\d+(?:\.\d+)?", x.replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _dc_num(x):
    """Strict D/C reader. Accepts a number, or a string that STARTS with a number ('0.93',
    '0.93 (governs)'). A qualitative status like 'OK (a=.625b_f ...)', 'PASS', 'N/A' returns None
    (a pass/status, NOT a ratio) -- so dimensional/geometry checks are never mis-read as a D/C."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        m = re.match(r"\s*(-?\d*\.?\d+)", x)   # anchored at the START, not search-anywhere
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def _close(a, b, tol=TOL):
    if a is None or b is None:
        return True
    if abs(a) < 1e-9 and abs(b) < 1e-9:
        return True
    return abs(a - b) / max(abs(a), abs(b), 1e-9) <= tol


def _find(d, *subs):
    """First numeric value in dict d whose key contains any of the substrings (case-insensitive)."""
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if any(s in str(k).lower() for s in subs):
            n = _num(v)
            if n is not None:
                return n
    return None


def _demand_capacity_from_string(s):
    """Parse a demand string like 'Ru=788 kip; phiRn=601 (web) -> 1023 kip (with 9/16" doubler)'
    into (demand, capacity). demand = the Ru/required value; capacity = the FINAL (largest, post-
    reinforcement) phiRn / value after an arrow. Returns (dem, cap) or (None, None)."""
    if not isinstance(s, str):
        return None, None
    low = s.lower()
    dem = None
    m = re.search(r"(?:ru|required|demand|mu|pu|vu)\s*[=:]?\s*(-?\d+(?:\.\d+)?)", low)
    if m:
        dem = float(m.group(1))
    cap = None
    # prefer a value after an arrow (final, reinforced capacity), else after phiRn/phi Rn
    arrow = re.findall(r"(?:->|→)\s*(-?\d+(?:\.\d+)?)", low)
    if arrow:
        cap = float(arrow[-1])
    else:
        m = re.search(r"(?:phirn|φrn|phi\s*rn|capacity)\s*[=:]?\s*(-?\d+(?:\.\d+)?)", low)
        if m:
            cap = float(m.group(1))
    return dem, cap


_LABEL_NUM = re.compile(r"([A-Za-z][A-Za-z _/\.-]{1,26}?)\s*[=:]?\s*(-?\d+(?:/\d+)?(?:\.\d+)?)\s*"
                        r"(in\.?|inch|ksi|kips?|k-?ft|k-?in|mm)\b", re.I)


def _gather_text(obj, acc):
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _gather_text(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _gather_text(v, acc)


def _frac(tok):
    if "/" in tok:
        try:
            a, b = tok.split("/"); return float(a) / float(b)
        except Exception:
            return None
    return _num(tok)


def _one_value_issues(kind, cid, entry):
    texts = []
    _gather_text(entry, texts)
    seen = {}
    for t in texts:
        for m in _LABEL_NUM.finditer(t):
            label = re.sub(r"\s+", " ", m.group(1).strip().lower())
            label = re.sub(r"^(the|a|an|use|using|with|of|for|one|each)\s+", "", label)
            if len(label) < 3:
                continue
            unit = m.group(3).lower().replace(".", "").rstrip("s")
            val = _frac(m.group(2))
            if val is None:
                continue
            key = (label, unit)
            seen.setdefault(key, [])
            if all(abs(val - v) / max(abs(val), abs(v), 1e-9) > 0.02 for v in seen[key]):
                seen[key].append(val)
    out = []
    for (label, unit), vals in seen.items():
        if len(vals) > 1:
            out.append(f"[{kind} {cid}] quantity '{label}' ({unit}) appears as "
                       f"{', '.join(str(v) for v in vals)} -- one value only; reconcile")
    return out


def _resize_hint(sec):
    """Next-heavier section in the same W-depth family (hardening #6): a concrete fix for a
    D/C > 1.0 member so a weak agent iterates instead of shipping NG."""
    try:
        import re as _re, csv as _csv, os as _os
        m = _re.match(r"(W\d+)X(\d+(?:\.\d+)?)", str(sec or "").upper())
        if not m:
            return ""
        fam, wt = m.group(1), float(m.group(2))
        path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "aisc_shapes.csv")
        wts = sorted(float(r["AISC_Manual_Label"].upper().split("X")[1])
                     for r in _csv.DictReader(open(path))
                     if r["AISC_Manual_Label"].upper().startswith(fam + "X"))
        nxt = [w for w in wts if w > wt + 0.1]
        return (" -> try %sX%g (next size up, same depth family)" % (fam, int(nxt[0]) if float(nxt[0]).is_integer() else nxt[0])) if nxt else \
               (" -> %s is the heaviest %s: use a BUILT-UP section and FLAG it" % (sec, fam))
    except Exception:
        return ""


def _entry_issues(kind, entry):
    out = []
    cid = entry.get("id", "?")
    checks = entry.get("checks") if isinstance(entry.get("checks"), list) else []

    # collect per-limit-state D/Cs (recomputing from numeric demand/capacity where available)
    check_dcs = []
    for c in checks:
        if not isinstance(c, dict):
            continue
        cls = c.get("limit_state", c.get("name", "check"))
        cdc = _dc_num(c.get("DC"))
        dem = _find(c, "demand", "ru", "required", "mu", "pu", "vu", "_kip", "_kft")
        cap = _find(c, "capacity", "phirn", "phi", "available", "design_strength")
        if dem is not None and cap not in (None, 0.0):
            rec = dem / cap
            if cdc is not None and not _close(rec, cdc):
                out.append(f"[{kind} {cid}] check '{cls}': D/C {cdc:.3f} != demand/capacity "
                           f"{dem:.3g}/{cap:.3g} = {rec:.3f} -- reconcile")
            elif cdc is None:
                cdc = rec
        if cdc is not None:
            check_dcs.append((cls, cdc))

    top_dc = _dc_num(entry.get("DC"))
    ls_present = bool(entry.get("limit_state")) or any(
        isinstance(c, dict) and c.get("limit_state") for c in checks)
    all_dcs = ([top_dc] if top_dc is not None else []) + [d for _, d in check_dcs]

    if not ls_present:
        out.append(f"[{kind} {cid}] no limit_state given (top-level or in a check)")
    if not entry.get("cited") and not any(isinstance(c, dict) and (c.get("cited") or c.get("clause") or c.get("cite"))
                                          for c in checks):
        out.append(f"[{kind} {cid}] no cited code clause")
    if not all_dcs:
        out.append(f"[{kind} {cid}] no D/C reported (top-level or in a check)")
    else:
        worst = max(all_dcs)
        if worst > 1.0 + 1e-9:
            if entry.get("waived"):
                pass   # explicitly waived with an engineering justification (completion-gate convention) --
                       # e.g. an EXISTING member in a retrofit/addition job carried as a retrofit-scope item
            else:
                _sec_ = (entry.get("inputs") or {}).get("section") or entry.get("section")
                out.append(f"[{kind} {cid}] worst D/C = {worst:.3f} > 1.0 (NG -- resize/redesign)"
                           + _resize_hint(_sec_))
        if top_dc is not None and check_dcs:
            wcls, wd = max(check_dcs, key=lambda t: t[1])
            if not _close(wd, top_dc):
                out.append(f"[{kind} {cid}] headline D/C {top_dc:.3f} != worst limit-state D/C "
                           f"{wd:.3f} ('{wcls}') -- the two were never reconciled")

    # recompute from a free-text demand string (Ru=.. ; phiRn=.. -> CAP)
    dem, cap = _demand_capacity_from_string(entry.get("demand"))
    if dem is not None and cap not in (None, 0.0) and all_dcs:
        rec = dem / cap
        if not _close(rec, max(all_dcs)):
            out.append(f"[{kind} {cid}] demand/capacity {dem:.3g}/{cap:.3g} = {rec:.3f} "
                       f"!= reported D/C {max(all_dcs):.3f} -- reconcile")

    out += _one_value_issues(kind, cid, entry)
    return out


def _completeness_issues(pkg):
    """Reserved for commonly-omitted member CATEGORIES. The old infill/filler-beam heuristic
    was removed: secondary filler beams are needed only when the deck cannot span girder-to-
    girder, which the engineer decides per project, not a blanket requirement."""
    return []


def _isnum(x):
    try:
        float(x); return True
    except Exception:
        return False


def _load_cfg(root, name):
    """Best-effort load of the building cfg dict from <root>/cfg.py so geometry/units can be sanity-checked."""
    p = os.path.join(root, "cfg.py")
    if not os.path.exists(p):
        return None
    try:
        # Compile the SOURCE directly (not via importlib) so a stale cached .pyc on a coarse-mtime jobs
        # mount can never shadow the just-edited cfg.py -- the class of bug where an edit looks ignored. (P13)
        import types as _types
        src = open(p, encoding="utf-8").read()
        m = _types.ModuleType("cfg_chk_" + name); m.__file__ = p
        exec(compile(src, p, "exec"), m.__dict__)
        return getattr(m, "cfg", None)
    except Exception:
        return None



def _geometry_issues(cfg):
    """Units/geometry sanity for story heights and bay spacing.

    USA / kip-in: heights are inches (flag feet-as-inches and >60 ft).
    India SI / N-mm: heights are millimetres (flag metres-left-unscaled and absurd tall).
    """
    out = []
    if not isinstance(cfg, dict):
        return out
    H = [float(h) for h in (cfg.get("heights") or []) if _isnum(h)]
    _dex = set(int(k) for k in (cfg.get("drift_exempt_stories") or {}))
    _si = False
    try:
        from india_units import is_si
        _si = bool(is_si(cfg))
    except Exception:
        u = str(cfg.get("units") or "").lower()
        _si = u in ("n-mm", "n-mm-s", "n-mm-sec", "si", "metric", "mm", "india_si", "india_metric")
        if cfg.get("metric") or cfg.get("si_native"):
            _si = True
        if str(cfg.get("jurisdiction") or "").lower() in ("india", "in", "bis", "is"):
            # Heuristic: mm storeys are thousands
            if H and float(H[0]) >= 500:
                _si = True
    if _si:
        small = [h for i, h in enumerate(H, start=1) if h < 1800 and i not in _dex]
        if small:
            out.append(
                "story heights look like METRES, not millimetres (%s) -- SI engine uses MILLIMETRES: "
                "a 3.6 m story is 3600, not 3.6. Call india_units.apply_si_geometry(cfg) / "
                "apply_metric_geometry(cfg)." % ", ".join("%g" % h for h in small[:10])
            )
        tall = [h for h in H if h > 20000]  # > 20 m storey — absurd
        if tall:
            out.append(
                "story height(s) over 20 m (%s mm) -- confirm SI millimetre units."
                % ", ".join("%g" % h for h in tall[:10])
            )
        for key, lab in (("SX", "X-bay"), ("SY", "Y-bay")):
            v = cfg.get(key)
            if _isnum(v) and 0 < float(v) < 1500:
                out.append(
                    "%s spacing %s=%g mm is implausibly small -- SI engine uses MILLIMETRES "
                    "(a 6 m bay is 6000)." % (lab, key, float(v))
                )
        return out
    # ---- kip-in / inch path (USA scaffolding retained for twin cfgs) ----
    small = [h for i, h in enumerate(H, start=1) if h < 72 and i not in _dex]
    if small:
        out.append(
            "story heights look like FEET, not inches (%s) -- the engine uses INCHES: a 13 ft story is 156, "
            "not 13. Multiply every height by 12 and re-run design_and_report."
            % ", ".join("%g" % h for h in small[:10])
        )
    tall = [h for h in H if h > 720]
    if tall:
        out.append(
            "story height(s) over 60 ft (%s in) -- confirm the units are inches."
            % ", ".join("%g" % h for h in tall[:10])
        )
    for key, lab in (("SX", "X-bay"), ("SY", "Y-bay")):
        v = cfg.get(key)
        if _isnum(v) and 0 < float(v) < 60:
            out.append(
                "%s spacing %s=%g in is implausibly small -- the engine uses INCHES (a 20 ft bay is 240)."
                % (lab, key, float(v))
            )
    return out




def _design_basis_issues(cfg, name=None, pkg=None):
    """R1/R2/R8/R12/R14/R16 design-basis gates (SDC-aware so SDC B/C is not over-flagged)."""
    out=[]
    if not isinstance(cfg,dict): return out
    s=cfg.get("seis") or {}
    SDS=float(s.get("SDS",0) or 0); Ie=float(s.get("Ie",1.0) or 1.0); R=s.get("R")
    sdc_high = SDS>=0.50                       # proxy for SDC D/E/F (RC I-III); ELF permitted in B/C
    if not cfg.get("system"):
        out.append("declare cfg['system'] = the EXACT SFRS from the brief (e.g. 'SPSW','EBF','SMF','dual SMF+SCBF') -- "
                   "the report otherwise INFERS it from R, which is ambiguous (R=8 is EBF/BRBF/dual)")
    try:
        import engine3d as _E
        cfgr=_E.CFG.get(name) if name else None
        pir=_E.plan_irregularities(cfgr or cfg)
    except Exception:
        pir={"reentrant":False,"setback":False,"nonparallel":False}
    if not any(pir.values()) and isinstance(pkg,dict):
        # live screen needs the BUILT footprint; fall back to the flags the pipeline recorded
        _sp=(pkg.get("framework_screen") or {}).get("plan") or {}
        if any(_sp.get(k) for k in ("reentrant","setback","nonparallel")):
            pir={k: bool(_sp.get(k)) for k in ("reentrant","setback","nonparallel")}
    # IS 1893 7.6/7.7.1: ESM only for regular buildings < 15 m in Zone II; every other building
    # needs linear dynamic analysis (scaled RSA forces in the demands).  Enforced by
    # india_issues() below and by india_seismic_gates.design_status (WP0.2 / WP1.3).
    # S2: India / SI jobs use IS 1893 0.004 h — strip USA Table 12.12-1 / 0.025h scaffold.
    _india = False
    try:
        from engine3d import _india_job as _ij
        _india = _ij(cfg)
    except Exception:
        u = str(cfg.get("units") or "").lower()
        j = str(cfg.get("jurisdiction") or "").lower()
        _india = u in ("n-mm", "n-mm-sec", "si", "metric") or j in ("india", "in", "bis", "is")
    if _india:
        dl = float(cfg.get("drift_limit", 0.004) or 0.004)
        if dl > 0.00401 and not cfg.get("drift_limit_rag_cite"):
            out.append(
                "India drift_limit=%.4f exceeds IS 1893 cl.7.11.1.1 default 0.004 — set "
                "cfg['drift_limit_rag_cite'] if a RAG-justified special limit applies "
                "(e.g. 0.002 soft-storey), else use 0.004" % dl
            )
    else:
        dl=float(cfg.get("drift_limit",0.020) or 0.020)
        _mfrho=(" (for a moment-frame-only SFRS in SDC D-F the allowable is further divided by rho, "
                "12.12.1.1 -- the engine drift gates apply this)")
        # ASCE 7-22 16.1.2: Chapter 16 analysis relaxes 12.12.1 for RC I-III (never IV).
        _relief_on=False
        try:
            from preflight import relief_findings as _rf, relief_active as _ra
            for _sev,_msg in _rf(cfg):
                if _sev=="ERROR": out.append("16.1.2 drift relief: "+_msg)
            _relief_on=_ra(cfg)
        except Exception:
            pass
        if Ie>=1.5 and dl>0.0101:
            out.append("Risk Category IV (Ie=%.2f): allowable story drift is 0.010 h_sx (Table 12.12-1) -- set cfg['drift_limit']=0.010"%Ie+_mfrho)
        elif Ie>=1.25 and dl>0.0151 and not _relief_on:
            out.append("Risk Category III (Ie=%.2f): allowable story drift is 0.015 h_sx (Table 12.12-1) -- set cfg['drift_limit']=0.015"%Ie+_mfrho)
    if R is not None and float(R)<=3.0:
        # complete-gap wave1 / IN_Ex3: do not always-on "CONFIRM wind or seismic" when the
        # package already computed wind_vs_seismic (wind ≫ EQ documented). Still note R≤3
        # detailing scope once, without the open CONFIRM action item.
        _wvs = None
        if isinstance(pkg, dict):
            _cd = pkg.get("capacity_design") or {}
            _chk = _cd.get("checks") if isinstance(_cd, dict) else {}
            if isinstance(_chk, dict):
                _wvs = _chk.get("wind_vs_seismic") or _cd.get("wind_vs_seismic")
            if _wvs is None and isinstance(_cd, dict):
                _wvs = _cd.get("wind_vs_seismic")
        _gov_done = False
        if isinstance(_wvs, dict):
            # accept computed ratios / governing flags
            if _wvs.get("found") is True or _wvs.get("computed") is True:
                _gov_done = True
            if _wvs.get("governs") or _wvs.get("governing"):
                _gov_done = True
            if _wvs.get("VB_wind_kN") is not None and _wvs.get("VB_seismic_kN") is not None:
                _gov_done = True
            if _wvs.get("ratio_X") is not None or _wvs.get("ratio_wind_over_seis") is not None:
                _gov_done = True
        if _gov_done:
            # IN_Ex3: wind≫EQ already proven in package — do not emit standing R=3 FAIL reminder.
            pass
        else:
            out.append("R=%.2f is a 'not specifically detailed for seismic' system -- AISC 341 does NOT apply (no SCWB / "
                       "capacity design); design members & connections to IS 800 only, and CONFIRM whether wind or seismic governs each direction"%float(R))
    H=[float(h) for h in (cfg.get("heights") or []) if _isnum(h)]
    if len(H)>=2 and sdc_high:
        hr=max(max(H[k]/H[k-1],H[k-1]/H[k]) for k in range(1,len(H)))
        _screened = isinstance(pkg,dict) and (
            isinstance((pkg.get("framework_screen") or {}).get("soft_story"), dict)
            or "classification" in str((pkg.get("capacity_design") or {}).get("vertical_irregularity","")))
        if hr>=1.3 and not _screened:
            out.append("story-height ratio %.2f suggests a SOFT/WEAK story -- COMPUTE the story stiffness AND strength "
                       "ratios and classify (7-22 Vert 1a/1b stiffness, 4a/4b strength); extreme soft story (1b) and "
                       "weak stories (4a/4b) are PROHIBITED in SDC E/F only (12.3.3.1)"%hr)
        elif hr>=1.3 and _screened:
            _ss=(pkg.get("framework_screen") or {}).get("soft_story") or {}
            try:
                from preflight import sdc_of_cfg as _sdcf; _sdc_ef=_sdcf(cfg) in ("E","F")
            except Exception:
                _sdc_ef=float(s.get("S1",0) or 0)>=0.75
            if "EXTREME" in str(_ss.get("classification","")) and _sdc_ef:
                out.append("framework screen classifies an EXTREME soft story (Type 1b) -- PROHIBITED in SDC E/F "
                           "(12.3.3.1): stiffen the story or document why the classification does not govern")
    _dia = str(cfg.get("diaphragm","rigid")).lower()
    if _dia in ("flexible","semi-rigid") and isinstance(pkg,dict):
        _blob2=_cd_blob(pkg)+" "+json.dumps(pkg).lower()
        if "tributary" not in _blob2:
            out.append("cfg['diaphragm']='%s' declared but calc_package never distributes lateral force by "
                       "TRIBUTARY AREA -- for a flexible diaphragm the braced-line shears, deck shear (plf), "
                       "chords and collectors must be designed from the tributary model (IS 875/1893 12.3.1)"%_dia)
    _dex = cfg.get("drift_exempt_stories") or {}
    if _dex and isinstance(pkg,dict):
        _blob3=json.dumps(pkg).lower()
        if not any(w in _blob3 for w in ("step","split-level","inter-diaphragm","offset")):
            out.append("drift_exempt_stories declared (%s) but calc_package has no step/split-level transfer "
                       "detail -- the exempted inter-diaphragm racking must be a DESIGNED detail (shear "
                       "transfer + the shared columns checked across the offset)"%sorted(_dex))
    if (pir.get("reentrant") or pir.get("setback")) and isinstance(pkg,dict):
        conns=pkg.get("connections") or []
        has_coll=any(isinstance(c,dict) and "collector" in (str(c.get("id",""))+str(c.get("type",""))).lower() for c in conns)
        if not has_coll:
            out.append("re-entrant/setback present but NO collector in calc_package -- collectors are a REQUIRED deliverable "
                       "(design with Omega_0 on the re-entrant/transfer lines, 12.3.3.5/12.10.2.1), not 'delegated to the drawings'")
    return out


_SYS_REQUIRED = {
    "spsw": [("VBE stiffness Ic>=0.00307 t h^4/L (COMPUTED)", ["0.00307","vbe","ic_","ic "]),
             ("web-plate tension field / 1.1RyFy expected strength", ["tension","plate","ryfy","1.1ry"])],
    "ebf":  [("shear link e<=1.6Mp/Vp + rotation 0.08 rad", ["link","1.6","0.08"]),
             ("brace/beam-outside-link capacity from 1.25RyVn", ["1.25","expected","ry"])],
    "brbf": [("adjusted brace strengths (beta*omega*RyFy)", ["adjusted","omega","beta"])],
    "scbf": [("brace expected strength RyFyAg / 1.1RyPn", ["expected","ryfy","1.1ry","brace"])],
    "smf":  [("SCWB (strong-column-weak-beam) ratio", ["scwb","strong column","e3.4"]),
             ("panel-zone shear / doubler", ["panel","doubler"])],
    "dual": [("SMF independently resists >=25% of V at every level", ["25","independent","resist"])],
}

def _cd_blob(pkg):
    """All text in capacity_design -- dict KEYS + string values + numbers -- so a computed check stored with
    descriptive keys (Ic_provided: 1350) is detected, not just free-text notes."""
    cd=pkg.get("capacity_design") if isinstance(pkg,dict) else None
    parts=[]
    def walk(o):
        if isinstance(o,dict):
            for k,v in o.items(): parts.append(str(k)); walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
        else: parts.append(str(o))
    walk(cd if cd is not None else {})
    return " ".join(parts).lower()

def _is_numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _gather_uncomputed_text(obj, acc):
    """Like _gather_text, but a record that carries a numeric value / limit / dc IS a computed check: its
    clause / cite formula strings (e.g. '(V/Vdb)^2+(T/Tdb)^2 <= 1') are the requirement it evaluated, not an
    unevaluated symbolic requirement, so they are skipped (WP6-fix: false positives on computed base / anchor rows)."""
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        computed = _is_numeric(obj.get("dc")) or (_is_numeric(obj.get("value")) and "limit" in obj)
        for k, v in obj.items():
            if computed and isinstance(v, str):
                continue
            _gather_uncomputed_text(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _gather_uncomputed_text(v, acc)


def _named_not_computed_issues(pkg):
    out=[]; cd=pkg.get("capacity_design") if isinstance(pkg,dict) else None
    if cd is None: return out
    txt=[]; _gather_uncomputed_text(cd,txt)
    for t in txt:
        if not isinstance(t,str) or not re.search(r">=|<=|≥|≤",t): continue
        bare=set(v.lower() for v in re.findall(r"(?<![A-Za-z0-9])[A-Za-z](?![A-Za-z0-9])", t))  # single-letter symbols (t,h,L,e,...)
        if len(bare) >= 2:   # a symbolic formula with >=2 unresolved variables -> not numerically evaluated
            out.append("[capacity_design] '%s' is a symbolic REQUIREMENT, not a COMPUTED check -- substitute the section's numbers and give value vs limit + D/C"%t.strip()[:80])
    return out

def _system_checks_issues(cfg, pkg):
    out=[]; sysname=str(cfg.get("system") or "").lower()
    if not sysname or not isinstance(pkg,dict): return out
    blob=_cd_blob(pkg)
    for key,reqs in _SYS_REQUIRED.items():
        if key in sysname:
            for label,kws in reqs:
                if not any(kw in blob for kw in kws):
                    out.append("system '%s' requires check: %s -- not found in capacity_design (add it, computed)"%(cfg.get("system"),label))
    return out

def _height_limit_issues(cfg):
    out=[]; s=cfg.get("seis") or {}
    H=[float(h) for h in (cfg.get("heights") or []) if _isnum(h)]
    if not H: return out
    hn=sum(H)/12.0; R=s.get("R"); SDS=float(s.get("SDS",0) or 0); sysname=str(cfg.get("system") or "").lower()
    if SDS<0.5: return out
    limit=None
    if "smf" in sysname or "dual" in sysname: limit=None
    elif "ocbf" in sysname or (R and abs(float(R)-3.25)<0.5): limit=35.0
    elif "scbf" in sysname or (R and abs(float(R)-6)<0.6): limit=160.0
    elif "ebf" in sysname or "brbf" in sysname or (R and abs(float(R)-8)<0.4): limit=160.0
    elif "spsw" in sysname or (R and abs(float(R)-7)<0.4): limit=160.0
    if limit and hn>limit+0.5:
        out.append("structural height h_n=%.0f ft exceeds the Table 12.2-1 limit (~%.0f ft) for this system in SDC D+/E -- FLAG and resolve (dual system / exception) or re-select the system"%(hn,limit))
    return out

def _transfer_issues(cfg, name, pkg):
    out=[]
    try:
        import engine3d as _E
        pir=_E.plan_irregularities(_E.CFG.get(name) or cfg)
    except Exception:
        return out
    if pir.get("setback") and isinstance(pkg,dict):
        txt=[]; _gather_text([pkg.get("capacity_design"), pkg.get("connections")],txt)
        blob=" ".join(t for t in txt if isinstance(t,str)).lower()
        if "transfer" not in blob and "backstay" not in blob:
            out.append("footprint SETBACK detected -- design the TRANSFER/backstay diaphragm chords/collectors and supporting members for Omega_0 (7-22 12.3.3.4, discontinuous-element support) and report the backstay force")
    return out

def _nonparallel_issues(cfg, pkg):
    out=[]
    if cfg.get("skew") and isinstance(pkg,dict):
        if "biaxial" not in _cd_blob(pkg):
            out.append("nonparallel/skewed frame -- resolve stiffness into BOTH principal directions and apply BIAXIAL SCWB/interaction at the skewed columns (not evident in capacity_design)")
    return out



def _consultancy_issues(cfg, pkg):
    """Tier A/B real-world guards (EDGE_CASE_SWEEP): each WARN clears when the package addresses
    the topic, so they are reconcilable by DOING the check, not by boilerplate."""
    out = []
    if not isinstance(cfg, dict) or not isinstance(pkg, dict):
        return out
    blob = json.dumps(pkg).lower()
    arch = (str(cfg.get("arch", "")) + " " + str(cfg.get("system", ""))).lower()
    mem = pkg.get("members") or []
    # A3 ponding: long-span flat roof beams and no ponding statement
    def _len_m(m):
        inp = (m.get("inputs") or {}) if isinstance(m, dict) else {}
        if inp.get("length_mm") is not None:
            return float(inp.get("length_mm") or 0) / 1000.0
        return float(inp.get("length_in") or 0) * 0.0254
    roof_long = any(isinstance(m, dict) and (m.get("inputs") or {}).get("role") == "roof"
                    and _len_m(m) >= 12.0 for m in mem)
    if roof_long and "ponding" not in blob:
        out.append("long-span (>= 12 m) roof framing and NO ponding evaluation in calc_package -- "
                   "check ponding / impounded rain (roof slope + secondary drainage head; IS 875 (Part 4) "
                   "for snow-water) and record it")
    # A6 footfall vibration: long floor spans or vibration-sensitive occupancy
    floor_long = any(isinstance(m, dict) and (m.get("inputs") or {}).get("role") == "floor"
                     and _len_m(m) >= 12.0 for m in mem)
    sens = any(k in arch for k in ("lab", "laborator", "hospital", "gym", "assembly", "vibration"))
    if (floor_long or sens) and "vibration" not in blob:
        out.append("footfall VIBRATION serviceability not addressed (long floor spans and/or "
                   "vibration-sensitive occupancy) -- IS 800:2007 5.6.4 / Annex (floor vibration) screen: "
                   "fundamental frequency and acceleration vs occupancy, recorded in the package")
    # A1 composite floors: the cfg declares a composite floor system -> the package must carry the
    # Ch. I essentials (studs + camber + the unshored wet-concrete stage), OR an explicit scope
    # statement (bare-steel lower bound / composite excluded / delegated). Content-clearable.
    fs = (str(cfg.get("floor_system", "")).lower() + " " + arch + " "
          + str(cfg.get("notes", "")).lower())   # notes too: agents park the brief's composite line there
    if "composite" in fs:
        need = [("stud", "stud strength/schedule (I8.2a)"),
                ("camber", "camber decision (even 'no camber', with the wet deflection shown)"),
                (("wet", "unshored", "construction stage"), "unshored wet-concrete stage check")]
        missing = []
        for keys, what in need:
            keys = (keys,) if isinstance(keys, str) else keys
            if not any(k in blob for k in keys):
                missing.append(what)
        stubs_ok = False
        cd = pkg.get("composite_design") if isinstance(pkg, dict) else None
        if isinstance(cd, dict):
            ws = cd.get("chI_worksheet") or {}
            slots = ws.get("slots") if isinstance(ws, dict) else None
            if isinstance(slots, list) and slots and all(s.get("found") is False for s in slots):
                stubs_ok = True  # H6: honest found:false stubs — do not invent
        scoped = stubs_ok or ("composite" in blob and any(k in blob for k in
                  ("lower bound", "lower-bound model", "scope", "excluded", "not relied", "delegated")))
        if missing and not scoped:
            out.append("COMPOSITE floor system declared and the package lacks: " + "; ".join(missing) +
                       " -- composite beams in India fall under IS 11384 (not in the corpus -> found:false): "
                       "record the scope (bare-steel design per IS 800 8.2 + construction stage, or delegated)")
    # A8 seismic joint / pounding: multi-wing keywords and no joint decision
    if any(k in arch for k in ("twin", "two tower", "wings", "wing ")) and \
            not any(k in blob for k in ("seismic joint", "pounding", "joint width", "no seismic joint")):
        out.append("multi-wing/tower configuration and NO seismic-joint decision recorded -- either "
                   "size the joint per IS 1893 7.11.3 (R x (D1 + D2), or (R1 D1 + R2 D2)/2 at equal floor "
                   "levels, Amd 1) or record why the wings are intentionally connected")
    # B6 snow drift at steps/parapets
    stepish = any(k in arch for k in ("step", "setback", "parapet", "penthouse", "tier", "wedding"))
    if float(cfg.get("snow", 0) or 0) > 0 and stepish and "drift" not in blob.replace("drift_", ""):
        out.append("snow present with roof steps/parapets/setbacks and no DRIFT surcharge in the "
                   "package (IS 875 (Part 4) drift / unbalanced cases) -- add it to the step-adjacent members")
    # B8 delegated-design register
    if any(k in blob for k in ("joist", "sji", " deck", "brb", "stair", "curtain wall")) and \
            "delegat" not in blob:
        out.append("delegated-design components referenced (joists/deck/BRBs/stairs/cladding) but no "
                   "'delegated_design' register in capacity_design -- list each delegated item, the "
                   "design criteria handed off, and the interface forces")
    return out


# =====================================================================================
# WP0.3 -- India extensions (FAIL rules).  All return lists of issue strings.
# =====================================================================================
GREP_RULES = (
    (re.compile(r"cap\w*\s*=\s*max\(.*(\*\s*1\.(15|25)|1\.(15|25)\s*\*)"), "capacity computed from its own demand (cap = max(.. * 1.15/1.25))"),
    (re.compile(r"DC['\"\]]*\s*[:=]\s*0\.8\b"), "literal D/C constant 0.8 in a job script"),
    (re.compile(r"DC['\"\]]*\s*[:=]\s*0\.9\b"), "literal D/C constant 0.9 in a job script"),
    (re.compile(r"seeded\s+D/C", re.I), "'seeded D/C' in a job script"),
    (re.compile(r"governing\s*=\s*[\"']seismic[\"']"), "governing='seismic' forced in a job script"),
    (re.compile(r"\.pass\"?\]?\s*=\s*True|\"pass\"\s*:\s*True\s*,\s*#\s*force", re.I), "forced pass flag"),
)


def script_grep_issues(job_dir):
    """Grep the job's python scripts for capacity-from-demand / seeded-D/C patterns."""
    out = []
    if not job_dir or not os.path.isdir(job_dir):
        return out
    for dp, dn, fn in os.walk(job_dir):
        if os.path.basename(dp) in ("rag", "figs", "__pycache__"):
            continue
        for f in fn:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            try:
                lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
            except Exception:
                continue
            for i, ln in enumerate(lines, 1):
                for rx, why in GREP_RULES:
                    if rx.search(ln):
                        out.append("%s:%d %s" % (os.path.relpath(p, job_dir), i, why))
    return out


def bak_issues(job_dir):
    out = []
    d = os.path.join(job_dir or "", "design")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if ".bak" in f or f.endswith("bak"):
                out.append("stale backup design/%s shipped -- delete it" % f)
    for f in ("pipeline_error.txt",):
        if job_dir and os.path.exists(os.path.join(job_dir, f)):
            out.append("%s shipped with the package -- delete it (stale failed run)" % f)
    return out


def report_residue_issues(job_dir):
    p = os.path.join(job_dir or "", "report.html")
    if not os.path.exists(p):
        return []
    try:
        from india_contract_residue import residue_hits
        h = residue_hits(open(p, encoding="utf-8", errors="replace").read())
    except Exception as ex:
        return ["report residue scan failed: %s" % ex]
    return ["report.html US-residue: %d hit(s), e.g. %r" % (len(h), h[:3])] if h else []


_NUM = re.compile(r"(?<![\w.])\d+\.\d+(?![\d.])|(?<==)\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?(?=\s*(?:m/s|kN|kPa|mm|percent|%))")


def _rag_texts(job_dir):
    out = []
    d = os.path.join(job_dir or "", "rag")
    if not os.path.isdir(d):
        return out
    for dp, dn, fn in os.walk(d):
        for f in fn:
            p = os.path.join(dp, f)
            try:
                raw = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            q = None
            try:
                js = json.loads(raw)
                q = js.get("query") if isinstance(js, dict) else None
                txt = []
                _gather_text(js, txt)
                raw = " ".join(t for t in txt if isinstance(t, str))
            except Exception:
                pass
            out.append((os.path.relpath(p, job_dir), q, re.sub(r"\s+", " ", raw).lower()))
    return out


def rag_evidence_issues(plan, job_dir):
    """found:true retrieval entries must have a stored hit in rag/ containing the cited text:
    either {hit_file, quote} with the quote in that file, or a stored hit for the same query whose
    text contains every number quoted in the cite."""
    out = []
    ret = (plan or {}).get("retrieval") if isinstance(plan, dict) else None
    if not isinstance(ret, list):
        return out
    texts = _rag_texts(job_dir)
    for i, h in enumerate(ret):
        if not isinstance(h, dict) or h.get("found") is not True:
            continue
        cite = str(h.get("cite") or "")
        ok = False
        hf, quote = h.get("hit_file"), h.get("quote")
        if hf and quote:
            qn = re.sub(r"\s+", " ", str(quote)).lower()
            ok = any(rel.endswith(str(hf)) and qn in t for rel, _q, t in texts)
        else:
            nums = [n.strip() for n in _NUM.findall(cite)]
            for rel, q, t in texts:
                if q is not None and str(q).strip().lower() != str(h.get("query") or "").strip().lower():
                    continue
                if nums and all(n in t for n in nums):
                    ok = True
                    break
        if not ok:
            out.append("load_plan.retrieval[%d] (%s) is found:true but no stored rag/ hit contains the cited "
                       "text/values -- persist the hit (hit_file + quote) or set found:false" % (i, h.get("query")))
    return out


_COMPONENT_REQUIRES = (
    (re.compile(r"crane|gantry|runway", re.I), lambda c, comps: bool(c.get("crane") or c.get("cranes"))),
    (re.compile(r"\bbrb|brb_core|buckling[_ -]?restrained", re.I), lambda c, comps: "nobasis:brbf" in comps),   # WP6-fix: not every 'buckling' key (gusset 12.8.3.4) is a BRB
    (re.compile(r"\blink\b|link_", re.I), lambda c, comps: "sbf_eccentric" in comps),
    (re.compile(r"web_plate|spsw|plate_shear", re.I), lambda c, comps: "nobasis:spsw" in comps),
    (re.compile(r"scwb|panel_zone|smf_", re.I), lambda c, comps: "steel_smrf" in comps),
)


def absent_component_issues(cfg, pkg):
    """capacity_design / connection keys for components that the model does not contain."""
    out = []
    if not isinstance(cfg, dict) or not isinstance(pkg, dict):
        return out
    try:
        from india_seismic_gates import parse_systems, system_text
        comps = parse_systems(system_text(cfg), imf_as_smrf=bool(cfg.get("imf_as_smrf")))
    except Exception:
        comps = []
    keys = []
    cd = pkg.get("capacity_design") or {}
    if isinstance(cd, dict):
        keys += list((cd.get("checks") or {}).keys()) if isinstance(cd.get("checks"), dict) else []
        keys += [k for k in cd.keys() if k not in ("checks", "note", "cite", "status", "system", "R")]
    keys += [str(c.get("id") or "") for c in (pkg.get("connections") or []) if isinstance(c, dict)]
    for k in keys:
        for rx, pred in _COMPONENT_REQUIRES:
            if rx.search(k) and not pred(cfg, comps):
                out.append("package carries '%s' for a component absent from the model/system" % k)
    return out


def literal_dc_issues(pkg):
    """D/C exactly 0.80 / 0.90 / 1.000 without derived capacity fields, or a capacity that is an
    exact multiple of its own demand."""
    out = []
    if not isinstance(pkg, dict):
        return out
    for kind in ("members", "connections"):
        for e in (pkg.get(kind) or []):
            if not isinstance(e, dict):
                continue
            ch = e.get("checks")
            recs = [e]
            if isinstance(ch, list):
                recs += [c for c in ch if isinstance(c, dict)]
            elif isinstance(ch, dict):
                recs += [v for v in ch.values() if isinstance(v, dict)]
            for c in recs:
                dc = c.get("DC", c.get("dc"))
                if isinstance(dc, bool) or not isinstance(dc, (int, float)):
                    continue
                if any(abs(float(dc) - k) < 1e-9 for k in (0.8, 0.9, 1.0)):
                    derived = any(c.get(k) is not None for k in ("value", "demand", "demand_N")) and \
                        any(c.get(k) is not None for k in ("limit", "capacity", "capacity_N")) and \
                        (c.get("inputs") or c.get("geometry") or c.get("derivation") or c.get("clause"))
                    if not derived:
                        out.append("%s '%s': literal D/C %.3f without a capacity derived from geometry + clause"
                                   % (kind[:-1], e.get("id"), float(dc)))
    return out


def zero_demand_issues(pkg):
    out = []
    for m in (pkg or {}).get("members") or []:
        if not isinstance(m, dict):
            continue
        inp = m.get("inputs") or {}
        vals = [inp.get(k) for k in ("P_comp_N", "P_tens_N", "Mz_Nmm", "My_Nmm", "V_N")]
        if all(isinstance(v, (int, float)) for v in vals) and all(abs(float(v)) < 1e-6 for v in vals):
            out.append("member '%s' has zero demand in every combination -- load path missing (WP2.7)" % m.get("id"))
    for t in (pkg or {}).get("zero_demand_elements") or []:
        out.append("element %s has zero demand in every combination (load not distributed)" % t)
    return out


def _india_design_basis_issues(cfg, pkg):
    """India replacement for _design_basis_issues (no ASCE Table 12.12-1 / AISC 341 / 12.3.3.5 text)."""
    out = []
    if not isinstance(cfg, dict):
        return out
    if not cfg.get("system"):
        out.append("declare cfg['system'] = the IS 1893 Table 9 system (e.g. 'SCBF', 'SMRF')")
    dl = cfg.get("drift_limit")
    if dl not in (None, "") and float(dl) > 0.004 + 1e-9:
        out.append("drift_limit=%.4f exceeds IS 1893 7.11.1.1 (0.004 h) -- not permitted" % float(dl))
    _dia = str(cfg.get("diaphragm", "rigid")).lower()
    if _dia in ("flexible", "semi-rigid") and isinstance(pkg, dict):
        blob = json.dumps(pkg).lower()
        if "tributary" not in blob and "semi_rigid" not in blob and "semi-rigid" not in blob:
            out.append("cfg['diaphragm']='%s' but no tributary / semi-rigid diaphragm distribution is recorded "
                       "(IS 1893 7.6.4)" % _dia)
    _dex = cfg.get("drift_exempt_stories") or {}
    if _dex and isinstance(pkg, dict):
        blob3 = json.dumps(pkg).lower()
        if not any(w in blob3 for w in ("step", "split-level", "inter-diaphragm", "offset")):
            out.append("drift_exempt_stories declared (%s) but no step/split-level transfer detail is designed"
                       % sorted(_dex))
    try:
        import engine3d as _E
        pir = _E.plan_irregularities(cfg)
    except Exception:
        pir = {}
    if (pir.get("reentrant") or pir.get("setback")) and isinstance(pkg, dict):
        conns = pkg.get("connections") or []
        coll = [c for c in conns if isinstance(c, dict) and "collector" in (str(c.get("id", "")) + str(c.get("type", ""))).lower()]
        if not coll and not (pkg.get("collectors") or []):
            out.append("re-entrant/setback plan but no collector / chord design in calc_package (IS 1893 7.6.4; WP2.6)")
    return out


def india_issues(cfg, pkg, job_dir):
    """All WP0.3 India FAIL rules."""
    out = []
    try:
        import india_seismic_gates as G
        out += G._R_system_agreement(cfg or {}, pkg)
        out += [m for s, m in G.system_zone_findings(cfg or {}) if s == "ERROR"] if cfg else []
    except Exception as ex:
        out.append("seismic gates unavailable: %s" % ex)
    out += zero_demand_issues(pkg)
    out += absent_component_issues(cfg, pkg)
    out += literal_dc_issues(pkg)
    out += script_grep_issues(job_dir)
    out += bak_issues(job_dir)
    out += report_residue_issues(job_dir)
    plan = (cfg or {}).get("load_plan") if isinstance(cfg, dict) else None
    if plan is None and isinstance(pkg, dict):
        plan = pkg.get("load_plan")
    if plan is None and job_dir and os.path.exists(os.path.join(job_dir, "load_plan.json")):
        try:
            plan = json.load(open(os.path.join(job_dir, "load_plan.json")))
        except Exception:
            plan = None
    out += rag_evidence_issues(plan, job_dir)
    return out


def _is_india(cfg):
    try:
        from engine3d import _india_job
        return bool(_india_job(cfg or {}))
    except Exception:
        return str((cfg or {}).get("jurisdiction") or "").lower() in ("india", "in", "is", "bis")


def check(name, root=None, pkg=None, verbose=True):
    """Run the self-consistency check. Returns a list of issue strings ([] == consistent)."""
    issues = []
    if pkg is None:
        if root is None:
            base = os.environ.get("STEEL_BUILDER_JOBS") or _here_repo()
            root = os.path.join(base, name)
        path = os.path.join(root, "design", "calc_package.json")
        if not os.path.exists(path):
            issues.append(f"calc_package.json not found at {path} -- run design_and_report first")
            if verbose:
                _print(name, issues)
            return issues
        try:
            pkg = json.load(open(path, encoding="utf-8"))
        except Exception as ex:
            issues.append(f"calc_package.json is not valid JSON: {ex}")
            if verbose:
                _print(name, issues)
            return issues

    members = pkg.get("members") or []
    conns = pkg.get("connections") or []
    if not isinstance(conns, list) or len(conns) == 0:
        issues.append("connections list is empty -- connections are a REQUIRED deliverable "
                      "(design them in place; demands-and-basis alone is incomplete)")
    for m in members:
        if isinstance(m, dict):
            issues += _entry_issues("member", m)
    for c in conns:
        if isinstance(c, dict):
            issues += _entry_issues("connection", c)

    _root = root if root else os.path.join(os.environ.get("STEEL_BUILDER_JOBS") or _here_repo(), name)
    if not os.path.exists(os.path.join(_root, "cfg.py")):
        issues.append("jobs/%s/cfg.py not found -- write the building's cfg (including any custom_build) to cfg.py "
                      "FIRST and keep it; the saved OpenSees model must be reproducible and editable for later studies." % name)
    _dcfg = _load_cfg(_root, name)
    if _dcfg is None:
        try:
            import engine3d as _E
            _dcfg = _E.CFG.get(name)
        except Exception:
            _dcfg = None
    issues += _geometry_issues(_dcfg)                       # units/geometry sanity (story heights in ft, etc.)
    if _is_india(_dcfg) or (isinstance(pkg, dict) and pkg.get("unit_system") == "N-mm"):
        # India path: the USA ASCE/AISC generators (Table 12.2-1 heights, AISC 341 R<=3 text,
        # 12.12.3 joints, AISC DG11 ...) are not applied (WP1.13); WP0.3 rules instead.
        issues += _india_design_basis_issues(_dcfg, pkg)
        issues += _named_not_computed_issues(pkg)
        issues += _consultancy_issues(_dcfg, pkg)
        issues += india_issues(_dcfg, pkg, _root)
    else:
        issues += _design_basis_issues(_dcfg, name, pkg)        # R1/R2/R8/R12/R14/R16
        issues += _height_limit_issues(_dcfg)                   # R19 system height limit
        issues += _transfer_issues(_dcfg, name, pkg)            # R7/R15 transfer/backstay
        issues += _nonparallel_issues(_dcfg, pkg)               # R10 skewed frame
        issues += _consultancy_issues(_dcfg, pkg)               # Tier A/B real-world guards
        issues += _named_not_computed_issues(pkg)               # R9 named-not-computed
        issues += _system_checks_issues(_dcfg, pkg)             # R9 per-system required checks
    issues += _completeness_issues(pkg)
    if verbose:
        _print(name, issues)
    return issues


def _print(name, issues):
    print("[consistency] %s: %d issue(s)" % (name, len(issues)))
    for i in issues:
        print("   -", i)
    print("RESULT:", "PASS (self-consistent)" if not issues else "FAIL (%d to reconcile)" % len(issues))


if __name__ == "__main__":
    import sys
    for nm in (sys.argv[1:] or ["B02"]):
        check(nm)
