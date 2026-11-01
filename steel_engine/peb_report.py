"""peb_report.py -- PEB (2026-10) section of report.html: the stepped tapered members, station checks, restraints,
joints and splices, flange braces, frame stability, tonnage, the secondary members designed with IS 801, and the
deliverables (reactions, BOM, anchor bolt plan, STAAD export)."""
from __future__ import annotations

import html
import os

import sections as S

OWNER_RULINGS = [
    ("D-T1", "LTB of a tapered member segment by segment between restraints, with the section at the critical "
             "station; C1 from the moment gradient (C1 = 1.0 used: conservative); member buckling in-plane with the "
             "member's smallest section over its length"),
    ("D-T2", "IS 18168:2023 adopted voluntarily for Zone III-V portals (route B): E350 allowed, Table 2 limits, Ry"),
    ("D-T3", "doubly symmetric welded sections only"),
    ("D-T4", "OCBF / SCBF braces KL/r <= 120 / 160 and tension share 30-70 % (IS 800 12.7.2 / 12.8.2): no tension-only "
             "rods in the seismic bracing; angles or CHS designed for compression"),
    ("D-T5", "Z purlins and girts designed with the CFS engine's IS 801 / IS 811 checks"),
    ("D-T6", "IS 800 12.4.2 complete-penetration welds for the connection welds; flange-to-web welds are fillets "
             "(IS 800 10.5)"),
    ("D-T7", "knee and apex joints designed for 1.2 Mp of the section at the joint face"),
]


# MSME (2026-10): the angle-truss shed (knee-braced truss portals, rolled columns) -- the rulings that apply to it
TRUSS_RULINGS = [
    ("D-T4", "OCBF braces KL/r <= 120 and tension share 30-70 % (IS 800 12.7.2): no tension-only rods in the seismic "
             "bracing; the wall braces are CHS designed for compression (single angles cannot meet KL/r <= 120 over "
             "the wall diagonals)"),
    ("D-T5", "Z purlins and girts designed with the CFS engine's IS 801 / IS 811 checks"),
    ("D-T6", "IS 800 12.4.2 complete-penetration welds for the connection welds of the frames (the knee gussets and "
             "the truss seat on the column)"),
    ("D-T10", "knee-braced truss portal (IS 800 12.10.2.1): the truss is pinned on the column cap and reaches the "
              "column only through the couple of the knee brace and the heel seat, so the maximum moment the beam can "
              "deliver to the joint is the knee brace's design strength times its lever arm about the heel; the knee "
              "connections are designed for 1.2 times that moment (each knee-brace connection for 1.2 times the knee "
              "brace's design strength), the heel seat for the matching horizontal force with the 12.10.2.4 shear; "
              "the truss joints use fully tensioned HSFG bolts (12.4.1) and the welds to the column are "
              "complete-penetration welds (12.4.2)"),
]


def is_truss_shed(cfg, pkg=None):
    """MSME (2026-10): a job with angle roof trusses (declared truss connections)."""
    return bool((cfg or {}).get("truss_connections"))


DT9_OPEN = ("D-T9 (open)", "IS 18168:2023 6.5 splices: placed at least 3 db from the column face and designed for 1.8 "
             "times the required strength (both applied). Its third sentence asks each flange splice plate to develop "
             "1.2 Ry fy Af; an end-plate splice has no flange splice plate, so this is applied to flange-plate splices "
             "only. If it is read as applying to end-plate splices too, the rafter end-plate splices need more bolts "
             "at each flange. The reading is not settled and is listed as an open item.")


def rulings_applied(cfg):
    """First wave item 6: list only the rulings that apply to this building, and disclose D-T9 where IS 18168 is
    applied."""
    cfg = cfg or {}
    if is_truss_shed(cfg):
        return [list(r) for r in TRUSS_RULINGS]
    is18 = bool(cfg.get("apply_is18168"))
    out = []
    for k, v in OWNER_RULINGS:
        if k == "D-T2" and not is18:
            continue
        out.append([k, v])
    if is18:
        out.append(list(DT9_OPEN))
    return out


def _ln(path):
    """A deliverable as a link relative to report.html (the job folder), so it opens next to the report."""
    if not path:
        return ""
    return "<a href='%s' download>%s</a>" % (html.escape(str(path), quote=True), html.escape(str(path)))


def _e(x):
    return html.escape(str(x))


def _tab(head, rows):
    h = "".join("<th>%s</th>" % _e(c) for c in head)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % (c if isinstance(c, str) and c.startswith("<") else _e(c))
                                       for c in r) for r in rows)
    return "<table class='t'><tr>%s</tr>%s</table>" % (h, b)


def _f(v, d=1):
    try:
        return ("%." + str(d) + "f") % float(v)
    except (TypeError, ValueError):
        return "\u2014" if v is None else str(v)       # plain dash: _tab escapes text, so no HTML entity here


TRUSS_ROLE_NAMES = {"truss_top_chord": "top chord", "truss_bottom_chord": "bottom chord", "truss_vertical": "vertical",
                    "truss_diagonal": "diagonal", "truss_knee_brace": "knee brace"}


def _truss_head(cfg, pkg):
    """MSME (2026-10): the angle-truss section head -- the truss members, their end connections and the knees."""
    out = ["<h2>Angle roof trusses and knee-braced portals</h2>",
           "<p>Pratt angle trusses: double-angle chords continuous through the panel points on the gussets (IS 800 "
           "7.5.3 / 7.2.4: axial force with the secondary bending of the continuous chord, 9.3), single-angle webs and "
           "knee braces pin-ended (axial force only: 7.5.1.2 single angle loaded through one leg, Table 12 with two "
           "or more bolts and a hinged gusset; 6.2 / 6.3.3 / 6.3.4 / 6.4.1 at the bolted end connections; Table 3 "
           "slenderness). The purlins sit at the top-chord panel points and bring the roof load and the roof wind to "
           "the truss there. The truss seat on each column cap is pinned; a knee brace from each column to the first "
           "bottom-chord panel point makes the column and the truss a portal frame (ordinary moment frame, IS 800 "
           "12.10). Design rulings applied (Steltic India defaults; the design engineer can change each one):</p>",
           _tab(["Steltic design ruling", "as applied"], rulings_applied(cfg))]
    rows = []
    for m in (pkg.get("members") or []):
        inp = m.get("inputs") or {}
        role = inp.get("role")
        if role not in TRUSS_ROLE_NAMES:
            continue
        rows.append([TRUSS_ROLE_NAMES[role], inp.get("section"), inp.get("n_elements"),
                     _f((inp.get("P_comp_N") or 0) / 1e3, 1), _f((inp.get("P_tens_N") or 0) / 1e3, 1),
                     _f(m.get("DC"), 3), str(m.get("governing_check") or "")[:60]])
    if rows:
        out.append("<h3>Truss members (one row per member group)</h3>")
        out.append(_tab(["member", "section", "elements", "max compression (kN)", "max tension (kN)", "D/C",
                         "governing check"], rows))
    crow = []
    for c in (pkg.get("connections") or []):
        cid = str(c.get("id") or "")
        if not cid.startswith("conn-truss_"):
            continue
        role = cid[len("conn-"):].split("-", 1)[0]
        bg = c.get("bolt_group") or {}
        st = c.get("stitches") or {}
        crow.append([TRUSS_ROLE_NAMES.get(role, role), c.get("section"),
                     _f(((c.get("demand") or {}).get("axial_N") or 0) / 1e3, 1),
                     _f((bg.get("capacity_N") or 0) / 1e3, 1), _f(c.get("DC"), 3),
                     ("%d at %.0f mm" % (st["n_intermediate"], st["spacing_mm"])) if st else "-",
                     str(c.get("governing_check") or "")[:60]])
    if crow:
        out.append("<h3>Truss member end connections (bolts in shear and bearing, IS 800 10.3; spacing and edge "
                   "distances 10.2; back-to-back interconnection 7.8)</h3>")
        out.append(_tab(["member", "section", "axial (kN)", "bolt group (kN)", "D/C", "packed connections",
                         "governing check"], crow))
    s12 = ((pkg.get("capacity_design") or {}).get("section12") or {}).get("checks") or []
    krow = []
    for c in s12:
        if str(c.get("id") or "").startswith(("12.10.2.1_knee", "12.10.2.4_heel")):
            kn = c.get("knee") or {}
            krow.append([c.get("member"), "knee brace connection" if "knee" in c["id"] else "heel seat",
                         _f((kn.get("N_d_N") or 0) / 1e3, 1), _f(kn.get("lever_arm_mm"), 0),
                         _f((kn.get("M_del_Nmm") or 0) / 1e6, 1), _f((c.get("value") or 0) / 1e3, 1),
                         _f((c.get("limit") or 0) / 1e3, 1), _f(c.get("dc"), 3)])
    if krow:
        out.append("<h3>Knees (IS 800 12.10.2.1 / 12.10.2.4, Steltic design ruling D-T10: knee-braced truss portal, "
                   "the knee designed for 1.2 times the moment the knee brace can deliver)</h3>")
        out.append(_tab(["knee", "connection", "knee brace N_d (kN)", "lever arm (mm)", "M_del (kN-m)",
                         "demand (kN)", "capacity (kN)", "D/C"], krow[:60]))
    return out


def section(cfg, pkg, root):
    peb = (pkg or {}).get("peb")
    if not peb:
        return ""
    if is_truss_shed(cfg, pkg):
        return _section_tail(cfg, pkg, root, peb, _truss_head(cfg, pkg), truss=True)
    return _section_tail(cfg, pkg, root, peb, None)


def _section_tail(cfg, pkg, root, peb, head, truss=False):
    if head is not None:
        out = list(head)
    else:
        out = _peb_head(cfg, pkg, peb)
    return _common(cfg, pkg, root, peb, out, truss=truss)


def _peb_head(cfg, pkg, peb):
    out = ["<h2>PEB &mdash; web-tapered welded portal frames (stepped model)</h2>",
           "<p>Every web-tapered member is modelled as prismatic welded-I segments (depth at each segment's "
           "mid-length); every segment end (station) is checked with the exact local section (IS 800 Table 2 welded "
           "rows, 3.7.2(d) effective section of a slender web, 8.2.2 LTB between restraints, 8.4.2 shear buckling, "
           "9.3 interaction, 7.1.2 compression). Design rulings applied (Steltic India defaults for PEB; the design "
           "engineer can change each one):</p>",
           _tab(["Steltic design ruling", "as applied"], rulings_applied(cfg))]
    # members
    rows = []
    for mid, m in sorted((peb.get("members") or {}).items()):
        lab = m.get("section")
        try:
            import peb_build as PB
            p = PB.parse(lab)
            plates = ("flanges %g x %g, web %g" % (p[3], p[4], p[5])) if p[0] == "tapered" else \
                (("flanges %g x %g, web %g" % (p[2], p[3], p[4])) if p[0] == "welded" else "rolled / tube")
            d0, d1 = (p[1], p[2]) if p[0] == "tapered" else ((p[1], p[1]) if p[0] == "welded" else ("", ""))
            kg = PB.mass_kg(lab, m.get("L_mm") or 0.0)
        except Exception:
            plates, d0, d1, kg = "", "", "", None
        rows.append([mid, m.get("kind"), lab, plates, d0, d1, _f((m.get("L_mm") or 0) / 1000.0, 2), _f(kg, 0),
                     len(m.get("elements") or [])])
    out.append("<h3>Tapered / welded members (one row per member; a flange change is a new member at a splice)</h3>")
    out.append(_tab(["member", "kind", "designation", "plates (mm)", "start depth", "end depth", "length (m)",
                     "mass (kg)", "segments"], rows[:400]))
    # stations
    st = peb.get("stations") or {}
    srows = []
    for t, lst in sorted(st.items(), key=lambda kv: int(kv[0])):
        gov = max(lst, key=lambda r: (r.get("dc") or 0))
        srows.append(["e%s" % t] + ["%s %s" % (r.get("section"), _f(r.get("dc"), 3)) for r in lst] +
                     [gov.get("where"), _f(gov.get("dc"), 3), str(gov.get("governing_check") or "")[:60]])
    if srows:
        out.append("<h3>Station checks (Steltic design ruling D-T1: tapered members checked segment by segment between "
                   "restraints): element at mid-depth, station i, station j</h3>")
        out.append(_tab(["element", "element", "station i", "station j", "governs", "D/C", "check"], srows[:300]))
    return out


def _common(cfg, pkg, root, peb, out, truss=False):
    # restraints
    fb = cfg.get("flange_braces") or {}
    if fb:
        out.append("<h3>Restraints (IS 800 8.3.2; flange braces as declared)</h3>")
        rrows = [] if truss else [
            ["rafter (plan m from each eave)", ", ".join(_f(x / 1000.0, 2) for x in (fb.get("rafter") or {}).get("purlins_mm") or []),
             ", ".join(_f(x / 1000.0, 2) for x in (fb.get("rafter") or {}).get("fly_braces_mm") or [])]]
        rrows.append(["column (m above the base)", ", ".join(_f(x / 1000.0, 2) for x in (fb.get("column") or {}).get("girts_mm") or []),
                      ", ".join(_f(x / 1000.0, 2) for x in (fb.get("column") or {}).get("fly_braces_mm") or [])])
        out.append(_tab(["member", "outer flange (purlins / girts)", "inner flange (fly braces)"], rrows))
    # joints, splices, flange braces, stability
    crow = []
    for c in (pkg.get("connections") or []):
        cid = str(c.get("id") or "")
        if cid.startswith(("conn-peb-", "peb-")) or "beam-to-column" in str(c.get("type")):
            crow.append([cid, c.get("type"), c.get("section"), _f(c.get("DC"), 3), str(c.get("governing_check") or "")[:70]])
    if crow:
        out.append("<h3>%s</h3>" % ("Column flange braces, frame stability" if truss else
                                    "Knees, apex joints, splices, flange braces, frame stability"))
        out.append(_tab(["record", "type", "section", "D/C", "governing check"], crow))
    fs = peb.get("frame_stability") or {}
    if fs:
        out.append("<p><b>Frame stability (IS 800 4.6.2(b)):</b> %s. X: lambda_cr = %s; Y: lambda_cr = %s.</p>" % (
            _e(fs.get("method")), _f((fs.get("X") or {}).get("lambda_cr"), 2), _f((fs.get("Y") or {}).get("lambda_cr"), 2)))
    # secondary
    sec = [s_ for s_ in (pkg.get("secondary_members") or []) if s_.get("source") or s_.get("kind")]
    if sec:
        out.append("<h3>Secondary members</h3>")
        out.append(_tab(["member", "kind", "section", "D/C", "mass (kg)", "design"], [
            [s_.get("id"), s_.get("kind"), s_.get("section"), _f(s_.get("DC"), 3), _f(s_.get("mass_kg"), 0),
             s_.get("source") or s_.get("check") or "IS 800"] for s_ in sec]))
    # tonnage
    tn = peb.get("tonnage") or {}
    if tn:
        kg, kgm2 = tn.get("kg") or {}, tn.get("kg_per_m2") or {}
        out.append("<h3>Steel take-off</h3>")
        out.append(_tab(["group", "kg", "kg/m2 of plan"], [[k, _f(v, 0), _f(kgm2.get(k), 2)] for k, v in kg.items()]
                        + [["TOTAL", _f(tn.get("total_kg"), 0), _f(kgm2.get("total"), 2)]]))
        out.append("<p>Plan area %s m2. %s</p>" % (_f(tn.get("plan_area_m2"), 0), _e(tn.get("basis"))))
        # MSME (2026-10): a sourced typical range for comparable buildings (cfg['tonnage_benchmark'] = {lo_kg_m2,
        # hi_kg_m2, basis, source}), printed next to this building's total
        bm = cfg.get("tonnage_benchmark") or {}
        if bm.get("lo_kg_m2") is not None and bm.get("hi_kg_m2") is not None and bm.get("source"):
            tot = kgm2.get("total")
            pos = ("" if tot is None else " This building: %s kg/m2 (%s the range)." % (
                _f(tot, 1), "within" if bm["lo_kg_m2"] <= tot <= bm["hi_kg_m2"] else
                "below" if tot < bm["lo_kg_m2"] else "above"))
            out.append("<p>Typical steel for comparable buildings: %s to %s kg/m2 of plan, %s (%s).%s</p>" % (
                _f(bm["lo_kg_m2"], 1), _f(bm["hi_kg_m2"], 1), _e(bm.get("basis") or ""), _e(bm["source"]), pos))
    # outputs
    po = peb.get("outputs") or {}
    if po:
        li = []
        for k, v in po.items():
            if isinstance(v, dict) and k == "staad":
                txt = ("%s primary load cases and %s load combinations (every engine case: dead, collateral + PV, "
                       "imposed, crane, member wind, storey forces with accidental torsion, vertical earthquake, "
                       "notional)" % (v.get("n_primary_cases"), v.get("n_combinations")))
                if v.get("rsa_combinations_as_static"):
                    txt += ("; %s combinations used response-spectrum forces in Steltic and carry the equivalent "
                            "static storey forces in the file" % v["rsa_combinations_as_static"])
                if v.get("missing_terms") or v.get("unmapped_loads") or v.get("error"):
                    txt += "; <b>incomplete</b>: %s" % _e(v.get("error") or "%s missing terms, %s unmapped loads"
                                                      % (v.get("missing_terms"), v.get("unmapped_loads")))
                li.append("<li><b>STAAD.Pro input</b>: %s &mdash; %s</li>" % (_ln(v.get("file")), txt))
            elif isinstance(v, dict):
                li.append("<li><b>%s</b>: %s %s</li>" % (_e(str(k).replace("_", " ")), _ln(v.get("file")),
                                                          _e(v.get("basis") or v.get("note") or "")))
        out.append("<h3>Deliverables</h3><ul>%s</ul>" % "".join(li))
        svg = os.path.join(root, "design", "anchor_bolt_plan.svg")
        if os.path.exists(svg):
            out.append("<h4>Anchor bolt plan</h4><div style='max-width:100%;overflow:auto'>" + open(svg).read() + "</div>")
    if peb.get("errors"):
        out.append("<p class='note'><b>%s post-processing errors:</b> %s</p>" % ("Frame" if truss else "PEB",
                                                                               _e("; ".join(peb["errors"]))))
    return "".join(out)
