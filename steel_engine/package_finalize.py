"""package_finalize.py -- shared package-finalize helpers (X06, E11): the STATUS writer that respects the H44 split
(the engine writes STATUS.engine.md; STATUS.md belongs to the package and is only (re)written when absent or itself
engine-generated), the status ranking used to combine several runs (multi-unit jobs, X04), and a small HTML index.

    import package_finalize as PF
    PF.write_status(root, name, "partial", authority, reasons)      # -> {"engine": path, "status_md": path | None}
    PF.worst_status(["complete", "partial"])                         # -> "partial"

Used by pipeline.design_and_report's callers that assemble a package from several engine runs (multi_unit.design_units)
and by the CFS engine's package steps.  Nothing here changes a design status; it only records one.
"""
from __future__ import annotations

import html
import os

# worse = larger.  'example_only' outranks 'partial' (an example is not a design); a unit that did not produce a
# package (blocked by preflight / crashed) counts as 'partial' with its reason.
STATUS_RANK = {"complete": 0, "partial": 1, "example_only": 2}


def worst_status(statuses):
    """The worst of several design statuses (complete < partial < example_only); unknown / None -> partial."""
    worst = "complete"
    for s in statuses:
        s = str(s or "partial").lower()
        if s not in STATUS_RANK:
            s = "partial"
        if STATUS_RANK[s] > STATUS_RANK[worst]:
            worst = s
    return worst


def status_body(name, status, authority, reasons, sections=None):
    """The engine STATUS text (first line = pipeline.ENGINE_STATUS_MARK, second the pre-H44 header form)."""
    import pipeline as P
    body = ("%s\n# %s -- design status: %s\n\nAuthority: %s\n\n" % (P.ENGINE_STATUS_MARK, name, str(status).upper(),
                                                                    authority)
            + "Open reasons (%d):\n" % len(reasons) + "".join("- %s\n" % r for r in reasons))
    for title, lines in (sections or []):
        body += "\n## %s\n\n" % title + "".join("- %s\n" % ln for ln in lines)
    return body


def write_status(root, name, status, authority, reasons, sections=None):
    """Write <root>/STATUS.engine.md always and <root>/STATUS.md only when the engine owns it (H44)."""
    import pipeline as P
    os.makedirs(root, exist_ok=True)
    body = status_body(name, status, authority, reasons, sections)
    eng = os.path.join(root, "STATUS.engine.md")
    with open(eng, "w", encoding="utf-8") as f:
        f.write(body)
    smd = os.path.join(root, "STATUS.md")
    wrote = None
    if P._status_md_engine_owned(smd):
        with open(smd, "w", encoding="utf-8") as f:
            f.write(body)
        wrote = smd
    return {"engine": eng, "status_md": wrote}


def html_index(title, intro, tables):
    """A plain, self-contained HTML index page: tables = [(caption, header[list], rows[list of list]), ...].  Cells
    are escaped unless given as ('html', markup)."""
    def cell(c):
        if isinstance(c, tuple) and len(c) == 2 and c[0] == "html":
            return c[1]
        return html.escape("" if c is None else str(c))
    out = ["<!doctype html><html><head><meta charset='utf-8'><title>%s</title>" % html.escape(title),
           "<style>body{font-family:sans-serif;margin:24px;color:#111;background:#fff}table{border-collapse:collapse;"
           "margin:12px 0}td,th{border:1px solid #999;padding:4px 8px;text-align:left}th{background:#eee}"
           ".ok{color:#060}.bad{color:#a00}</style></head><body>",
           "<h1>%s</h1><p>%s</p>" % (html.escape(title), html.escape(intro))]
    for cap, head, rows in tables:
        out.append("<h2>%s</h2><table><tr>%s</tr>" % (html.escape(cap), "".join("<th>%s</th>" % html.escape(h) for h in head)))
        for r in rows:
            out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % cell(c) for c in r))
        out.append("</table>")
    out.append("</body></html>")
    return "\n".join(out)
