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
        return "&mdash;" if v is None else str(v)


def section(cfg, pkg, root):
    peb = (pkg or {}).get("peb")
    if not peb:
        return ""
    out = ["<h2>PEB &mdash; web-tapered welded portal frames (stepped model)</h2>",
           "<p>Every web-tapered member is modelled as prismatic welded-I segments (depth at each segment's "
           "mid-length); every segment end (station) is checked with the exact local section (IS 800 Table 2 welded "
           "rows, 3.7.2(d) effective section of a slender web, 8.2.2 LTB between restraints, 8.4.2 shear buckling, "
           "9.3 interaction, 7.1.2 compression). Owner rulings applied:</p>",
           _tab(["ruling", "as applied"], [[k, v] for k, v in OWNER_RULINGS])]
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
        out.append("<h3>Station checks (D-T1): element at mid-depth, station i, station j</h3>")
        out.append(_tab(["element", "element", "station i", "station j", "governs", "D/C", "check"], srows[:300]))
    # restraints
    fb = cfg.get("flange_braces") or {}
    if fb:
        out.append("<h3>Restraints (IS 800 8.3.2; cfg['flange_braces'])</h3>")
        out.append(_tab(["member", "outer flange (purlins / girts)", "inner flange (fly braces)"], [
            ["rafter (plan m from each eave)", ", ".join(_f(x / 1000.0, 2) for x in (fb.get("rafter") or {}).get("purlins_mm") or []),
             ", ".join(_f(x / 1000.0, 2) for x in (fb.get("rafter") or {}).get("fly_braces_mm") or [])],
            ["column (m above the base)", ", ".join(_f(x / 1000.0, 2) for x in (fb.get("column") or {}).get("girts_mm") or []),
             ", ".join(_f(x / 1000.0, 2) for x in (fb.get("column") or {}).get("fly_braces_mm") or [])]]))
    # joints, splices, flange braces, stability
    crow = []
    for c in (pkg.get("connections") or []):
        cid = str(c.get("id") or "")
        if cid.startswith(("conn-peb-", "peb-")) or "beam-to-column" in str(c.get("type")):
            crow.append([cid, c.get("type"), c.get("section"), _f(c.get("DC"), 3), str(c.get("governing_check") or "")[:70]])
    if crow:
        out.append("<h3>Knees, apex joints, splices, flange braces, frame stability</h3>")
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
             s_.get("source") or s_.get("check") or "IS 800 (secondary_members)"] for s_ in sec]))
    # tonnage
    tn = peb.get("tonnage") or {}
    if tn:
        kg, kgm2 = tn.get("kg") or {}, tn.get("kg_per_m2") or {}
        out.append("<h3>Steel take-off</h3>")
        out.append(_tab(["group", "kg", "kg/m2 of plan"], [[k, _f(v, 0), _f(kgm2.get(k), 2)] for k, v in kg.items()]
                        + [["TOTAL", _f(tn.get("total_kg"), 0), _f(kgm2.get("total"), 2)]]))
        out.append("<p>Plan area %s m2. %s</p>" % (_f(tn.get("plan_area_m2"), 0), _e(tn.get("basis"))))
    # outputs
    po = peb.get("outputs") or {}
    if po:
        li = []
        for k, v in po.items():
            if isinstance(v, dict):
                li.append("<li><b>%s</b>: %s %s</li>" % (_e(k), _e(v.get("file")), _e(v.get("basis") or v.get("note") or "")))
        out.append("<h3>Deliverables</h3><ul>%s</ul>" % "".join(li))
        svg = os.path.join(root, "design", "anchor_bolt_plan.svg")
        if os.path.exists(svg):
            out.append("<h4>Anchor bolt plan</h4><div style='max-width:100%;overflow:auto'>" + open(svg).read() + "</div>")
    if peb.get("errors"):
        out.append("<p class='note'><b>PEB post-processing errors:</b> %s</p>" % _e("; ".join(peb["errors"])))
    return "".join(out)
