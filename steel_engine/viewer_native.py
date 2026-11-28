"""Attach published native results to analytical geometry without running a design."""

import csv
from collections import Counter
import json
import math
from pathlib import Path
import re


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def read_json(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def _converted(row, aliases):
    for name, factor in aliases:
        value = number(row.get(name))
        if value is not None:
            return value * factor
    return None


def member_forces(row, si):
    """Native schedule envelopes. Keep compression and tension as separate magnitudes."""
    if si:
        return {
            "Pc": _converted(row, (("P_comp_kN", 1), ("P_comp_N", .001))),
            "Pt": _converted(row, (("P_tens_kN", 1), ("P_tens_N", .001))),
            "Mx": _converted(row, (("M_major_kNm", 1), ("Mz_kNm", 1), ("Mx_kNm", 1),
                                   ("Mz_Nmm", 1e-6), ("Mx_Nmm", 1e-6))),
            "My": _converted(row, (("M_minor_kNm", 1), ("My_kNm", 1), ("My_Nmm", 1e-6))),
            "V": _converted(row, (("V_kN", 1), ("V_N", .001))),
        }
    return {
        "Pc": _converted(row, (("P_comp_kip", 1),)),
        "Pt": _converted(row, (("P_tens_kip", 1),)),
        "Mx": _converted(row, (("M_major_kipft", 1), ("Mx_kipft", 1), ("Mz_kipft", 1))),
        "My": _converted(row, (("M_minor_kipft", 1), ("My_kipft", 1))),
        "V": _converted(row, (("V_kip", 1),)),
    }


def _schedule(root):
    path = root / "design/member_schedule.csv"
    if not path.is_file():
        return {}
    rows = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not (row.get("ele_tag") or "").strip():
                continue
            tag = int(row["ele_tag"])
            if tag in rows:
                raise ValueError(f"Duplicate native schedule element {tag}")
            rows[tag] = row
    return rows


def _strength_groups(package):
    groups = {}
    if not re.search(r"\bIS\s*800\b", str(package.get("code", "")), re.I):
        return groups
    for member in package.get("members") or []:
        inputs = member.get("inputs") or {}
        key = (inputs.get("role"), inputs.get("section"))
        result = member.get("strength_worst") or {}
        ratio = number(result.get("dc"))
        if not all(key) or ratio is None or ratio < 0:
            continue
        if key in groups:
            # A role/section that has several design groups cannot identify an occurrence.
            groups[key] = None
            continue
        element = re.fullmatch(r"[eE]?(\d+)", str(result.get("element", "")).strip())
        groups[key] = {"id": member.get("id") or "-".join(key), "dc": ratio,
                       "element": int(element[1]) if element else None,
                       "combination": result.get("combination"), "clause": result.get("clause")}
    return groups


def _element_results(package):
    """The package retains the detailed check of one element per group, which may
    differ from its strength governor when Table 3 or a tapered station controls."""
    results = {}
    if not re.search(r"\bIS\s*800\b", str(package.get("code", "")), re.I):
        return results
    for group in package.get("members") or []:
        inputs = group.get("inputs") or {}
        result = group.get("governing_element_result") or {}
        tag = re.fullmatch(r"[eE]?(\d+)", str(result.get("id", "")).strip())
        if not tag or result.get("found") is not True or not inputs.get("role") or not inputs.get("section"):
            continue
        strength = result.get("strength_worst") or result
        ratio = number(strength.get("interaction_dc"))
        key = (int(tag[1]), inputs["role"], inputs["section"])
        if key in results:
            results[key] = None
            continue
        results[key] = {"dc": ratio if ratio is not None and ratio >= 0 else None,
                        "combination": strength.get("interaction_governing_combo"),
                        "clause": strength.get("interaction_cite") or strength.get("clause"),
                        "station": strength.get("where"),
                        "overall_dc": number(result.get("dc")), "governing_check": result.get("governing_check")}
    return results


_FIX = re.compile(r"^\s*ops\.fix\(\s*(\d+)\s*,\s*([01](?:\s*,\s*[01]){5})\s*\)\s*(?:#.*)?$")


def saved_restraints(root):
    """Read literal native replay commands as data. Never import or execute a saved job."""
    source = root / "model_opensees.py"
    masks = {}
    if source.is_file():
        with source.open(encoding="utf-8-sig") as f:
            for line in f:
                match = _FIX.match(line)
                if match:
                    tag = int(match[1])
                    values = [int(x) for x in match[2].split(",")]
                    masks[tag] = [int(a or b) for a, b in zip(masks.get(tag, [0] * 6), values)]
    return masks


def _supports(data, masks):
    # Bottom nodes are only candidates. Elevated physical translation restraints also
    # qualify. Rotational stabilizers on axial members and auxiliary masters do not.
    support_tags = set(map(int, data.get("fixed") or []))
    support_tags.update(t for t, m in masks.items() if any(m[:3]) and str(t) in data["nodes"])
    supports = []
    for tag in sorted(support_tags):
        if str(tag) not in data["nodes"]:
            continue
        mask = masks.get(tag)
        if mask is None:
            kind = "unknown"
        elif mask == [1, 1, 1, 1, 1, 1]:
            kind = "fixed"
        elif mask == [1, 1, 1, 0, 0, 0]:
            kind = "pinned"
        elif any(mask):
            kind = "partial"
        else:
            continue
        supports.append({"tag": tag, "kind": kind, "dofs": mask})
    data["supports"] = supports
    data["fixed"] = [s["tag"] for s in supports]
    counts = Counter(s["kind"] for s in supports)
    detail = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    data["meta"]["support_label"] = f"Supports ({detail})" if counts else "Supports unavailable"


def enrich(data, root, si, masks=None):
    root = Path(root)
    rows = _schedule(root)
    package = read_json(root / "design/calc_package.json")
    groups = _strength_groups(package)
    checked = _element_results(package)
    seen = set()
    for element in data["elements"]:
        tag = int(element["tag"])
        if tag in seen:
            raise ValueError(f"Duplicate analytical viewer element {tag}")
        seen.add(tag)
        row = rows.get(tag, {})
        section = (row.get("section") or "").strip()
        if section and section != element["sec"]:
            raise ValueError(f"Viewer element {tag} section does not match its native schedule")
        length = number(row.get("length_mm" if si else "length_in"))
        if length is not None and abs(length - element["L"]) > .11:
            raise ValueError(f"Viewer element {tag} length does not match its native schedule")
        element.update(f=member_forces(row, si), combo=row.get("governing_combo") or None,
                       role=row.get("role") or None, util=None, util_group=None, util_scope=None)
        element["element_result"] = checked.get((tag, element["role"], section))
        group = groups.get((element["role"], section))
        if group:
            element.update(util=group["dc"], util_group=group["id"],
                           util_scope="element" if group["element"] == tag else "group")
    if rows and not seen.intersection(rows):
        raise ValueError("Native schedule and analytical geometry have no matching element tags")
    represented = {e["util_group"] for e in data["elements"] if e["util_group"]}
    data["strength_groups"] = {
        g["id"]: g for g in groups.values() if g and g["id"] in represented
    }
    _supports(data, saved_restraints(root) if masks is None else masks)
    meta = data["meta"]
    meta["units"] = {"length": "mm" if si else "in", "force": "kN" if si else "kip",
                     "moment": "kN·m" if si else "kip·ft"}
    meta["revision"] = 2
    meta["demand_src"] = "IS 800 strength by role and section. Shading shows the group maximum. Grey indicates unavailable."
    meta["caveat"] = ("Analytical member centrelines and schematic floor panels. Forces are per-element schedule "
                      "envelopes. The IS 800 strength ratio is the group maximum, located on the named controlling "
                      "element. See the design report for slenderness, deflection, connections and overall status. "
                      "North is +Y. Drag to orbit, scroll to zoom, right-drag to pan and click for details.")
    stats = [s for s in meta.get("stats", []) if s[0] in ("Nodes / elements", "Periods T1-T3", "Fixed-ended beams")]
    known = sum(any(v is not None for v in el["f"].values()) for el in data["elements"])
    stats.append(["Members with native demands", f"{known} of {len(data['elements'])}"])
    if represented:
        maximum = max(v["dc"] for v in data["strength_groups"].values())
        stats.append(["Max native group strength D/C", f"{maximum:.4f}"])
    for key, name in (("wind", "Wind"), ("seis", "ESM" if si else "Seismic")):
        layer = (data.get("loads") or {}).get(key) or {}
        directions = []
        for axis in ("X", "Y"):
            values = layer.get(axis) or []
            if values and all(number(v) is not None for v in values):
                directions.append(f"{axis} {sum(values):.1f}")
        if directions:
            stats.append([name + " story-force sum", " / ".join(directions) + " " + meta["units"]["force"]])
    meta["stats"] = stats
    return data
