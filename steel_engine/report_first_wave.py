"""report_first_wave.py -- report sections added by the 2026-10 first-wave review fixes (items 1-8).

* crane_runway_section  -- item 2: crane data, wheel loads and IS 875-2 6.3 allowances, the gantry girder checks
  (pkg['gantry_girder']), the crane bracket at the column face (conn-crane-bracket) and the crane sway / rail spread.
* pv_check_section      -- item 3: rooftop PV check outputs (design/pv_*.csv|json|md written by the job's pv_check.py).
* takeoff_section       -- item 4: steel take-off in kg and kg/m2 for every job (PEB jobs keep their PEB take-off).
* premium_note          -- item 4: why a ductile (IS 18168 route B) PEB is heavier than a typical vendor quote.
* imposed_reduction_section -- item 1 (HR side): the IS 875-2 3.2.1 column imposed-load reduction actually applied.
* dead_load_rows        -- item 5: collateral and rooftop PV shown as their own rows with the 0.9 DL rule.
* occupancy_text, wind_base_shear -- item 7 presentation helpers.
"""
from __future__ import annotations

import csv
import html
import json
import os

import engine3d as E


def _e(x):
    return html.escape(str(x))


def _f(v, d=1, dash="—"):
    try:
        return ("{:,.%df}" % d).format(float(v))
    except (TypeError, ValueError):
        return dash if v is None else _e(v)


def _tab(head, rows):
    h = "".join("<th>%s</th>" % c for c in head)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows)
    return "<table class='t'><tr>%s</tr>%s</table>" % (h, b)


def _ok(v):
    return "—" if v is None else ("OK" if v else "<b>NG</b>")


# ------------------------------------------------------------------------------------------------ occupancy
def occupancy_text(cfg):
    o = cfg.get("occupancy")
    if not isinstance(o, dict):
        return _e(o or "—")
    parts = []
    if o.get("use"):
        parts.append(_e(o["use"]))
    if o.get("area_m2"):
        parts.append("%s m² of floor" % _f(o["area_m2"], 0))
    if o.get("persons"):
        parts.append("%s persons" % _f(o["persons"], 0))
    note = str(o.get("note") or "")
    for tok in ("owner ruling ", "brief ruling ", "(D8)", ", D8", " D8"):
        note = note.replace(tok, "" if tok.startswith(("(", ",", " ")) else "")
    if note:
        parts.append("basis: " + _e(note.strip(" ;,")))
    return "; ".join(parts) or "—"


# ------------------------------------------------------------------------------------------------ dead loads
def dead_load_rows(cfg):
    """Rows for the gravity table: permanent roof dead load, collateral, PV and the rule that applies to them."""
    rows = []
    col, pv = float(cfg.get("D_roof_collateral") or 0.0), float(cfg.get("D_roof_pv") or 0.0)
    if col:
        rows.append(["Collateral (services hung from the roof)", _f(col, 3), "kN/m² of plan"])
    if pv:
        rows.append(["Rooftop solar PV (modules, rails, clamps)", _f(pv, 3), "kN/m² of plan"])
    if col or pv:
        rows.append(["Rule for collateral and PV", "dead-load factor where they add to the effect; omitted from "
                     "the 0.9 DL rows (uplift, overturning); included in the seismic weight", "IS 800 Table 4"])
    return rows


# ------------------------------------------------------------------------------------------------ wind V_B
def wind_base_shear(cfg):
    """{'X': kN, 'Y': kN} characteristic wind base shear: wind_summary VB_x/VB_y when recorded, else the sum of the
    unfactored wind storey forces W_X / W_Y in the load plan."""
    plan = cfg.get("load_plan") or {}
    ws = plan.get("wind_summary") or {}
    out = {}
    for d in ("X", "Y"):
        v = ws.get("VB_%s_kN" % d.lower())
        if v is None:
            sf = (plan.get("story_forces") or {}).get("W_%s" % d)
            if isinstance(sf, dict) and sf:
                tot = 0.0
                for lv, f in sf.items():
                    if isinstance(f, dict):
                        tot += abs(float(f.get("fx" if d == "X" else "fy", 0.0) or 0.0))
                    elif isinstance(f, (list, tuple)) and f:
                        tot += abs(float(f[0] if d == "X" else (f[1] if len(f) > 1 else 0.0)))
                    elif isinstance(f, (int, float)):
                        tot += abs(float(f))
                if tot:
                    try:
                        import india_loads as IL
                        sc = IL._story_force_scale(plan)
                    except Exception:
                        sc = 1.0
                    v = tot * sc / 1000.0
        out[d] = v
    return out


# ------------------------------------------------------------------------------------------------ 3.2.1
def imposed_reduction_section(cfg):
    if not cfg.get("column_imposed_load_reduction"):
        return ""
    import static_model as SM
    NF = len(cfg["heights"])
    rows = []
    for k in range(1, NF + 1):
        n = NF - k + 1
        rows.append(["%d (between levels %d and %d)" % (k, k - 1, k), n, "%d %%" % round(100 * SM.imposed_load_reduction_321(n))])
    return ("<h3>Imposed-load reduction on columns (IS 875-2 3.2.1)</h3><p>The total distributed imposed load on the "
            "floors carried by a column is reduced by the number of floors carried (the roof counts as a floor). The "
            "reduction is applied to the column axial force in the gravity and wind combinations only, never with "
            "earthquake (IS 875-5 8.1), and not to beams, partitions or storage. %s</p>" % _e(SM.IS875_2_321_CITE)
            + _tab(["column storey", "floors carried", "reduction"], rows))


# ------------------------------------------------------------------------------------------------ crane runway
def crane_runway_section(cfg, pkg):
    cr = cfg.get("crane") or {}
    g = (pkg or {}).get("gantry_girder")
    if not cr and not g:
        return ""
    out = ["<h3>Crane runway: crane loads, gantry girder and brackets</h3>"]
    try:
        import india_loads as IL
        R = IL.crane_reactions(cr)
    except Exception as ex:
        R, err = None, ex
    rows = [["capacity / crab / bridge (kN)", "%s / %s / %s" % (_f(cr.get("capacity_kN"), 0), _f(cr.get("crab_kN"), 0),
                                                              _f(cr.get("bridge_kN"), 0))],
            ["crane span / hook approach (m)", "%s / %s" % (_f((cr.get("span_mm") or 0) / 1e3, 2),
                                                           _f((cr.get("hook_approach_mm") or 0) / 1e3, 2))],
            ["wheel base / gantry span (m)", "%s / %s" % (_f((cr.get("wheel_base_mm") or 0) / 1e3, 2),
                                                         _f((cr.get("gantry_span_mm") or 0) / 1e3, 2))],
            ["class / operation", "%s / %s" % (_e(cr.get("class")), _e(cr.get("operation") or cr.get("type") or "—"))]]
    if R:
        rows += [["max / min static rail reaction (kN)", "%s / %s" % (_f(R["Rmax_N"] / 1e3), _f(R["Rmin_N"] / 1e3))],
                 ["max static wheel load (kN)", _f(R["wheel_max_N"] / 1e3)],
                 ["vertical impact: gantry girder / columns", "%d %% / %d %%" % (round(100 * R["impact_girder"]),
                                                                              round(100 * R["impact_column"]))],
                 ["lateral surge on one rail (kN)", "%s (%d %% of crab + lifted load)" % (_f(R["surge_rail_N"] / 1e3),
                                                                                       round(100 * R["surge_pct"]))],
                 ["longitudinal traction on one rail (kN)", "%s (5 %% of the static wheel loads)"
                  % _f(R["traction_rail_N"] / 1e3)],
                 ["basis", _e(R.get("cite") or "IS 875 (Part 2):1987 6.3")]]
    out.append(_tab(["crane", "value"], rows))
    if isinstance(g, dict):
        dm = g.get("demands") or {}
        fac = g.get("factored") or {}
        out.append("<h4>Gantry girder %s (%s, fy %s MPa)</h4>" % (_e(g.get("section")), _e(g.get("grade") or ""),
                                                                 _f(g.get("fy_MPa"), 0)))
        out.append(_tab(["demand", "value"], [
            ["wheel load / with impact (kN)", "%s / %s" % (_f((dm.get("wheel_load_N") or 0) / 1e3),
                                                           _f((dm.get("wheel_load_with_impact_N") or 0) / 1e3))],
            ["static / vertical design moment (kN·m)", "%s / %s" % (_f((dm.get("M_static_Nmm") or 0) / 1e6),
                                                                    _f((dm.get("M_vertical_Nmm") or 0) / 1e6))],
            ["vertical shear (kN)", _f((dm.get("V_vertical_N") or 0) / 1e3)],
            ["surge moment on the top flange (kN·m)", _f((dm.get("M_surge_Nmm") or 0) / 1e6, 2)],
            ["factored Mz / M surge / V (kN·m, kN·m, kN)", "%s / %s / %s" % (
                _f((fac.get("Mz_Nmm") or 0) / 1e6), _f((fac.get("M_surge_Nmm") or 0) / 1e6, 2),
                _f((fac.get("V_N") or 0) / 1e3))],
            ["LTB length (mm)", _f(g.get("LLT_mm"), 0)],
            ["deflection limits", "%s; lateral %s mm (relative between rails %s mm)" % (
                _e(dm.get("defl_limit_basis") or ""), _f(dm.get("lateral_limit_mm"), 1),
                _f(dm.get("lateral_relative_rails_limit_mm"), 0))]]))
        def _vl(c, key):
            # web bearing / buckling rows carry forces in N: print kN
            v = c.get(key)
            if isinstance(v, (int, float)) and ("web bearing" in str(c.get("name")) or "web buckling" in str(c.get("name"))):
                return _f(v / 1e3, 1) + " kN"
            return _f(v, 3)
        crow = [[_e(c.get("name")), _vl(c, "value"), _vl(c, "limit"), _f(c.get("dc"), 3), _ok(c.get("ok")),
                 _e(c.get("clause") or "")] for c in (g.get("checks") or [])]
        out.append(_tab(["gantry girder check", "value", "limit", "D/C", "status", "clause"], crow))
    br = next((c for c in (pkg or {}).get("connections") or [] if c.get("id") == "conn-crane-bracket"), None)
    if br:
        out.append("<h4>Crane bracket at the column face (%s)</h4><p>%s</p>" % (_e(br.get("section")),
                                                                              _e(br.get("design_basis"))))
        out.append(_tab(["bracket check", "value", "limit", "D/C", "status", "basis"],
                        [[_e(c.get("name")), _f(c.get("value"), 1), _f(c.get("limit"), 1), _f(c.get("dc"), 3),
                          _ok(c.get("ok")), _e(c.get("cite") or "")] for c in br.get("checks") or []]))
    cs = (pkg or {}).get("crane_sway")
    if isinstance(cs, dict):
        rs = cs.get("rail_spread") or {}
        out.append(_tab(["crane serviceability", "value (mm)", "limit (mm)", "ratio", "basis"], [
            ["frame sway at rail level", _f(cs.get("sway_mm"), 2), _f(cs.get("limit_mm"), 1), _f(cs.get("ratio"), 3),
             _e(cs.get("cite") or "")]] + ([["rail spread (gauge change)", _f(rs.get("mm"), 2), _f(rs.get("limit_mm"), 1),
                                             _f(rs.get("ratio"), 3), "IS 800 Table 6 relative displacement between rails"]]
                                           if rs else [])))
    return "".join(out)


# ------------------------------------------------------------------------------------------------ PV check
def _csv(path):
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def pv_check_section(cfg, root):
    d = os.path.join(root, "design")
    cap_p = os.path.join(d, "pv_capacity.json")
    if not os.path.exists(cap_p):
        return ""
    out = ["<h2>Rooftop solar PV check: the answer</h2>"]
    try:
        cap = json.load(open(cap_p))
    except Exception:
        cap = {}
    pv = (cfg.get("load_plan") or {}).get("pv_array") or {}
    summ = [["PV load checked", "%s kN/m² over the roof plan" % _f(cfg.get("D_roof_pv") or pv.get("solar_pv_kNm2"), 2)],
            ["capacity of the roof as built", "<b>%s kN/m²</b> (bisection to %s kN/m²)" % (
                _f(cap.get("capacity_kNm2"), 2), _f(cap.get("resolution_kNm2"), 2))],
            ["first failure at", "%s kN/m²" % _f(cap.get("first_failure_kNm2"), 2)],
            ["limiting check", _e("%s: %s" % (cap.get("limiting_item"), cap.get("limiting_check")))]]
    for key, lab in (("capacity_H150_kNm2", "capacity with the dado detailed to move freely (eave sway H/150)"),
                     ("capacity_strength_kNm2", "capacity on strength alone (sway and dynamic-wind trigger aside)")):
        if cap.get(key) is not None:
            summ.append([lab, "%s kN/m²" % _f(cap[key], 2)])
    out.append(_tab(["result", "value"], summ))
    sens = os.path.join(d, "pv_sensitivity_static_wind.json")
    if os.path.exists(sens):
        try:
            sj = json.load(open(sens))
            out.append("<p><b>Why the capacity is low:</b> %s</p>" % _e(sj.get("conclusion") or ""))
        except Exception:
            pass
    ba = _csv(os.path.join(d, "pv_before_after.csv"))
    if ba:
        rows = sorted(ba, key=lambda r: -float(r.get("DC_with_PV") or 0) if (r.get("DC_with_PV") or "").replace(".", "", 1).isdigit() else 0)
        rows = [r for r in rows if str(r.get("change", "0")) not in ("0", "0.0")][:25]
        out.append("<h3>Before and after: the checks the PV load changes (largest first)</h3>")
        out.append(_tab(["item", "D/C as designed", "D/C with PV", "change", "over 1.0", "check"],
                        [[_e(r.get("item")), _e(r.get("DC_IN_Ex1") or r.get("DC_before") or ""),
                          _e(r.get("DC_with_PV")), _e(r.get("change")),
                          "<b>yes</b>" if str(r.get("over_1")).lower() == "true" else "no",
                          _e(r.get("governing_check_with_PV") or "")] for r in rows]))
    st = cap.get("strengthening") or []
    if st:
        out.append("<h3>Strengthening options to carry the array</h3>")
        out.append(_tab(["option", "what changes", "added steel", "result"],
                        [[_e(s.get("option")), _e(s.get("what")), _e(s.get("added_steel") or ""),
                          _e(s.get("result") or "")] for s in st]))
    rc = _csv(os.path.join(d, "pv_reactions_change.csv"))
    def _fl(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    chg = [r for r in rc or [] if any(abs(_fl(v)) > 0.005 for k, v in r.items() if k.endswith("_change"))]
    if chg:
        out.append("<h3>Change in the support reactions (unfactored, per column line and load case; only the rows "
                   "the PV changes)</h3>")
        out.append(_tab(["line", "case", "Fz with PV (kN)", "ΔFz (kN)", "ΔFx (kN)", "ΔFy (kN)", "ΔMx (kN·m)",
                         "ΔMy (kN·m)"],
                        [[_e(r.get("line")), _e(r.get("case")), _e(r.get("Fz_kN_PV")), _e(r.get("Fz_kN_change")),
                          _e(r.get("Fx_kN_change")), _e(r.get("Fy_kN_change")), _e(r.get("Mx_kNm_change")),
                          _e(r.get("My_kNm_change"))] for r in chg[:60]]))
    note = os.path.join(d, "pv_installer_note.md")
    if os.path.exists(note):
        out.append("<h3>Note to the PV installer</h3>" + _md_lite(open(note, encoding="utf-8").read()))
    return "".join(out)


def _md_lite(md):
    """The installer note (plain markdown: '#' title, paragraphs, '- ' bullets, **bold**) as HTML."""
    import re as _re
    html_, ul = [], False
    for block in md.strip().split("\n"):
        ln = block.rstrip()
        if ln.startswith("- "):
            if not ul:
                html_.append("<ul>")
                ul = True
            html_.append("<li>%s</li>" % _bold(_e(ln[2:]), _re))
            continue
        if ul:
            html_.append("</ul>")
            ul = False
        if not ln:
            continue
        if ln.startswith("#"):
            html_.append("<p><b>%s</b></p>" % _e(ln.lstrip("# ")))
        else:
            html_.append("<p>%s</p>" % _bold(_e(ln), _re))
    if ul:
        html_.append("</ul>")
    return "".join(html_)


def _bold(t, _re):
    return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)


# ------------------------------------------------------------------------------------------------ take-off
def takeoff_section(cfg, pkg, root=None):
    """Steel take-off of the analysis members for a non-PEB job: kg by member role and kg/m2 of floor area (also
    written to design/takeoff.json when the job folder is given, for the example index)."""
    if (pkg or {}).get("peb"):
        return ""
    import openseespy.opensees as ops
    try:
        info = E.build(cfg, "Linear")
    except Exception as ex:
        return "<p class='note'>[take-off unavailable: %s]</p>" % _e(ex)
    kg = {}
    for (t, kind, sec, n1, n2) in info["ele"]:
        try:
            c1, c2 = ops.nodeCoord(n1), ops.nodeCoord(n2)
            L = sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5
            A = E.Ipack(sec)[0]
        except Exception:
            continue
        grp = {"col": "columns", "beam": "beams (incl. roof members)", "brace": "braces"}.get(kind, kind)
        kg[grp] = kg.get(grp, 0.0) + A * L * 7.85e-6
    extra = 0.0
    for s_ in cfg.get("secondary_members") or []:
        if s_.get("mass_kg"):
            kg["declared secondary"] = kg.get("declared secondary", 0.0) + float(s_["mass_kg"])
    br = (cfg.get("crane") or {}).get("bracket") or {}
    if br.get("mass_kg"):
        kg["crane brackets"] = kg.get("crane brackets", 0.0) + float(br["mass_kg"])
    NF = len(cfg["heights"])
    area = sum(E.floor_area_mm2(cfg, k) for k in range(1, NF + 1)) / 1e6
    tot = sum(kg.values()) + extra
    if root:
        try:
            import json as _json
            import os as _os
            _json.dump({"kg": {k: round(v, 1) for k, v in kg.items()}, "total_kg": round(tot, 1),
                        "floor_area_m2": round(area, 1), "kg_per_m2": round(tot / area, 2) if area else None,
                        "basis": "modelled members + declared secondary members and crane brackets; connections, "
                                 "deck and unmodelled secondary beams not included"},
                       open(_os.path.join(root, "design", "takeoff.json"), "w"), indent=1)
        except Exception:
            pass
    rows = [[k, _f(v, 0), _f(v / area, 1) if area else "—"] for k, v in sorted(kg.items())]
    rows.append(["<b>TOTAL (modelled members)</b>", "<b>%s</b>" % _f(tot, 0), "<b>%s</b>" % (_f(tot / area, 1) if area else "—")])
    return ("<h3>Steel take-off (analysis members)</h3><p>Mass of the members in the analysis model from their section "
            "areas and lengths (7,850 kg/m³), per square metre of total floor area (%s m² over %d level(s)). Not "
            "included: secondary / filler beams that are not modelled, purlins and girts unless declared, deck, "
            "connections, base plates and stiffeners (allow about 8–12 %% for connections in a braced or moment "
            "frame).</p>" % (_f(area, 0), NF) + _tab(["group", "kg", "kg/m² of floor"], rows))


# ------------------------------------------------------------------------------------------------ premium note
def premium_note(cfg, pkg):
    peb = (pkg or {}).get("peb") or {}
    tn = peb.get("tonnage") or {}
    if not tn or not cfg.get("apply_is18168"):
        return ""
    k = tn.get("kg_per_m2") or {}
    return ("<h3>Why this shed is heavier than a typical vendor quote</h3><p>This design is %s kg/m² (primary %s, "
            "bracing %s, purlins and girts %s, connections %s). Vendor quotes for sheds of this kind are often lighter. "
            "The difference comes from design rules this report applies on purpose, not from the analysis:</p><ul>"
            "<li>IS 18168:2023 ductile detailing (route B, adopted for Zones III–V): compact webs (Table 2 d/tw) instead "
            "of 5–8 mm slender webs, knee and apex joints for 1.2 M<sub>p</sub> of the section at the joint face "
            "(ruling D-T7) and splices for 1.8 times the required strength (6.5);</li>"
            "<li>IS 800 Table 6 H/240 sway for a brick dado, which forces fixed bases and their base plates and anchors; "
            "many tenders use H/150 for metal cladding;</li>"
            "<li>base shear keys for 1.2 times the column shear capacity (IS 800 12.12 reading), compression bracing "
            "instead of rods, and purlins limited to the IS 811 range at F<sub>y</sub> 240 MPa;</li>"
            "<li>the IS 875-2 roof imposed load of 0.75 kN/m² on the whole roof, and collateral and PV kept off the "
            "uplift cases.</li></ul><p>The Steltic PEB lever study re-sizes this shed for each of these choices "
            "in turn and shows the steel each one costs.</p>"
            % (_f(k.get("total"), 1), _f(k.get("primary"), 1), _f(k.get("bracing"), 1), _f(k.get("secondary"), 1),
               _f(k.get("connections"), 1)))
