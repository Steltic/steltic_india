"""viewer3d.py -- interactive 3D structural viewer (three.js), opened from the report's
"View model" button (standalone tab; no iframe embed).

  standalone_html(cfg, name, root) -> full-page viewer HTML string
  report_section(cfg, name, root)  -> writes <root>/viewer_3d.html and returns the orange
                                      "View model" button linking to it (new tab).

The rendered frame uses the native OpenSees geometry, modes and releases. Displayed member
forces and strength results come from the saved schedule and IS 800 calculation package.
Publish an existing run with JOB --output STAGING/viewer_3d.html.
"""
import html as _html
import hashlib
import json
import math
import os
from itertools import accumulate
from pathlib import Path
import re
import tempfile

if __package__:
    from . import viewer_native as native
else:
    import viewer_native as native

_DIR = os.path.dirname(os.path.abspath(__file__))
ORANGE = "#ff8a3d"   # matches frontend/styles.css accent


def _viewer_si(cfg):
    """True when cfg is SI-native N-mm (India). Falls back to india_units.is_si."""
    try:
        import india_units as _IU
        return bool(_IU.is_si(cfg))
    except Exception:
        pass
    if not cfg:
        return False
    if cfg.get("force_kip_in"):
        return False
    if cfg.get("metric") or cfg.get("si_native"):
        return True
    u = str(cfg.get("units") or "").lower()
    return u in ("n-mm", "n-mm-s", "n-mm-sec", "si", "metric", "mm", "india_si", "india_metric")



def _model_used(root):
    """LLM model recorded by the run harness: '_model=<x>' in execution_log.md."""
    try:
        txt = open(os.path.join(root, "execution_log.md"), encoding="utf-8",
                   errors="replace").read(4000)
        m = re.search(r"_model=([^\s|]+)", txt)
        return m.group(1) if m else None
    except Exception:
        return None


# --------------------------------------------------------------- loads
def _static_gravity(cfg, coords):
    """Illustrative two-way pressure ribbons, excluding point loads and alternate deck paths."""
    import engine3d as E, static_model as SM
    m = SM.build_static(cfg)
    NF = m["NF"]; SX, SY = cfg["SX"], cfg["SY"]
    heights = cfg["heights"]; clad = cfg.get("clad", 0.0)
    extra = cfg.get("extra_mass_floors", {})
    D, L = [], []
    totD = totL = 0.0
    for b in m["beams"]:
        i, j, k, dirn, Ln = b["i"], b["j"], b["k"], b["dir"], b["L"]
        if not (1 <= k <= NF):
            continue
        n1 = E.ntag(i, j, k)
        n2 = E.ntag(i + 1, j, k) if dirn == "X" else E.ntag(i, j + 1, k)
        c1, c2 = coords.get(n1), coords.get(n2)
        if c1 is None or c2 is None:
            continue
        roof = (k == NF)
        pD = (cfg["D_roof"] if roof else cfg["D_floor"]) + extra.get(k, 0.0)
        pL = float(cfg.get("Lr") or 0.0) if roof else cfg["L_floor"]
        nb = SM._bays_adjacent(m["present"].get(k, set()), i, j, dirn)
        other = SY if dirn == "X" else SX
        wcap = other / 2.0
        si = _viewer_si(cfg)
        if si:                                  # N/mm from kN/m2 x mm / 1000 (WP2.10)
            th = heights[k - 1] / 2.0 if roof else heights[k - 1]
            wclad = clad * th / 1000.0 if (clad and nb == 1) else 0.0
        else:
            th = heights[k - 1] / 12.0; th = th / 2.0 if roof else th
            wclad = clad * th / 12000.0 if (clad and nb == 1) else 0.0
        nseg = len(b["segs"])
        wD, wL = [], []
        for s in range(nseg):
            smid = Ln * (s + 0.5) / nseg
            width_in = min(smid, Ln - smid, wcap)
            base = (nb * width_in / 1000.0) if si else (nb * (width_in / 12.0) / 12000.0)
            wD.append(round(pD * base + wclad, 6))
            wL.append(round(pL * base, 6))
            totD += wD[-1] * Ln / nseg; totL += wL[-1] * Ln / nseg
        seg = [round(c1[0], 1), round(c1[1], 1), round(c1[2], 1),
               round(c2[0], 1), round(c2[1], 1), round(c2[2], 1)]
        if any(wD):
            D.append(seg + [wD])
        if any(wL):
            L.append(seg + [wL])
    force_scale = 1000 if _viewer_si(cfg) else 1
    return {"D": {"beams": D, "total": round(totD / force_scale, 3)},
            "L": {"beams": L, "total": round(totL / force_scale, 3)}}


def _gravity_levels(engine, cfg, present, coords, si):
    # Same unfactored floor totals and grid-node distribution as engine3d.static_lateral.
    scale = 1000.0 if si else 1.0
    result = {key: {"pts": [], "total": 0.0} for key in ("DLdyn", "LLdyn")}
    for k in range(1, len(cfg["heights"]) + 1):
        pts = sorted(present.get(k) or present.get(str(k)) or ())
        if not pts:
            continue
        dead = engine.floor_dead(cfg, k) / scale
        imposed = (engine.floor_live(cfg, k) + engine.floor_roofLrS(cfg, k)) / scale
        for key, magnitude in (("DLdyn", dead), ("LLdyn", imposed)):
            layer = result[key]
            layer["total"] += magnitude
            for i, j in pts:
                xyz = coords.get(engine.ntag(i, j, k))
                if xyz is not None:
                    layer["pts"].append([*xyz[:3], round(magnitude / len(pts), 6)])
    for layer in result.values():
        layer["total"] = round(layer["total"], 3)
    return result


def _india_lateral(loads, plan, heights):
    forces = plan.get("story_forces") or {}
    if not forces or not heights:
        # Original SI viewers recorded ESM X only. Leave Y explicitly unavailable.
        if loads.get("seis") and "F" in loads["seis"]:
            old = loads["seis"]
            loads["seis"] = {"z": old["z"], "X": old["F"]}
        return
    loads.pop("wind", None)
    loads.pop("seis", None)
    unit = str(plan.get("story_forces_units") or "N").lower()
    if unit not in ("n", "kn"):
        return
    scale = 1000.0 if unit == "n" else 1.0
    for key, name in (("wind", "W"), ("seis", "EQ")):
        layer = {"z": heights}
        for i, axis in enumerate(("X", "Y")):
            rows = forces.get(f"{name}_{axis}")
            if not isinstance(rows, dict):
                continue
            values = []
            for k in range(1, len(heights) + 1):
                row = rows.get(str(k), rows.get(k))
                component = row[i] if isinstance(row, (list, tuple)) and len(row) > i else None
                value = native.number(component)
                values.append(round(value / scale, 4) if value is not None else None)
            if any(value is not None for value in values):
                layer[axis] = values
        if len(layer) > 1:
            loads[key] = layer
    loads["seismic_label"] = "IS 1893 characteristic ESM story forces"


def _loads(cfg, info, coords, T1):
    import engine3d as E
    out = {}
    NF = len(cfg["heights"]); z = E.zlevels(cfg)
    present = info.get("present") or {}
    si = _viewer_si(cfg)
    out.update(_gravity_levels(E, cfg, present, coords, si))
    out["force_unit"] = "kN" if si else "kip"
    if si:
        _india_lateral(out, cfg.get("load_plan") or {}, z[1:])
    else:
        # ---- wind story forces (both directions)
        try:
            FX = E.wind_forces(cfg, "X"); FY = E.wind_forces(cfg, "Y")
            out["wind"] = {"z": [z[k] for k in range(1, NF + 1)],
                           "X": [round(FX[k], 1) for k in range(1, NF + 1)],
                           "Y": [round(FY[k], 1) for k in range(1, NF + 1)]}
        except Exception:
            pass
        # ---- ELF seismic story forces
        try:
            Cs, V, Tu, Ta, kk, Fk, Wt = E.elf(cfg, T1)
            out["seis"] = {"z": [z[k] for k in range(1, NF + 1)],
                           "F": [round(Fk[k], 1) for k in range(1, NF + 1)],
                           "V": round(V, 1), "Cs": round(Cs, 4)}
        except Exception:
            pass
    # Build the pressure sketch last because build_static replaces the OpenSees domain.
    try:
        out["stat"] = _static_gravity(cfg, coords)
    except Exception:
        out["stat"] = None
    return out


# --------------------------------------------------------------- data build
def _viewer_data(cfg, name, root):
    import engine3d as E
    ms = E.mode_shapes(cfg, 6)
    info = E.build(cfg, "Linear")           # fresh build: beam_rel / col_dir / present snapshots
    beam_rel = info.get("beam_rel") or {}
    col_dir = info.get("col_dir") or {}
    moment_nodes = info.get("moment_nodes") or set()
    coords = {t: tuple(c[:3]) for t, c in ms["coords"].items()}
    nmodes = min(6, ms.get("nmodes", len(ms["T"])))
    kindmap = {"col": "column", "beam": "beam", "brace": "brace", "column": "column",
               "truss": "brace"}                  # MSME (2026-10): pin-ended truss members draw as axial members

    used = set()
    elements = []
    # Save actual support fixities before the static-load sketch rebuilds the OpenSees domain.
    try:
        masks = {}
        for tag in E.ops.getFixedNodes():
            restrained = set(E.ops.getFixedDOFs(tag))
            masks[tag] = [int(i in restrained) for i in range(1, 7)]
    except (AttributeError, RuntimeError):
        masks = None
    for (tag, kind, sec, n1, n2) in ms["ele"]:
        if n1 not in coords or n2 not in coords:
            continue
        used.update((n1, n2))
        x1, y1, z1 = coords[n1]; x2, y2, z2 = coords[n2]
        L = math.dist((x1, y1, z1), (x2, y2, z2))
        rec = {"tag": tag, "type": kindmap.get(kind, "beam"), "sec": sec,
               "n": [n1, n2], "L": round(L, 1), "util": None, "combo": None, "f": {}}
        if rec["type"] == "beam":
            rel = beam_rel.get(tag)
            if rel:
                rec["fe"] = 1 if rel[0] == "none" else 0
                rec["rel"] = {"none": "fixed-fixed", "both": "pinned-pinned",
                              "I": "pinned-fixed", "J": "fixed-pinned"}.get(rel[0], rel[0])
            else:                                     # fallback: node-level moment snapshot
                rec["fe"] = 1 if (n1 in moment_nodes and n2 in moment_nodes) else 0
        elif rec["type"] == "column":
            wd = col_dir.get(tag)
            if wd in ("X", "Y"):
                rec["wd"] = wd
        elements.append(rec)

    zs = sorted({round(coords[t][2], 1) for t in used})
    levels = list(zs)
    fixed = [t for t in used if abs(coords[t][2] - levels[0]) < 1e-6]

    # mode shapes; patch rigid-diaphragm slaves from their master
    masters = [t for t in coords if t not in used]
    modes = []
    for m in range(nmodes):
        shape = {t: list(ms["ev"][t][m][:3]) for t in used}
        for mt in masters:
            evm = ms["ev"].get(mt)
            if not evm or len(evm[m]) < 6:
                continue
            xm, ym, zm = coords[mt]
            vx, vy, rz = evm[m][0], evm[m][1], evm[m][5]
            for t in used:
                x, y, zc = coords[t]
                if abs(zc - zm) < 1e-6 and abs(shape[t][0]) + abs(shape[t][1]) < 1e-12:
                    shape[t][0] = vx - rz * (y - ym)
                    shape[t][1] = vy + rz * (x - xm)
        mx = max(max(abs(c) for c in s) for s in shape.values()) or 1.0
        modes.append({"T": round(ms["T"][m], 4),
                      "shape": {str(t): [round(c / mx, 4) for c in s] for t, s in shape.items()}})

    # slabs: one translucent quad per grid bay whose 4 corners have nodes
    slabs = []
    for z in levels[1:]:
        pts = {(round(coords[t][0], 1), round(coords[t][1], 1)) for t in used
               if abs(coords[t][2] - z) < 1e-6}
        xs = sorted({p[0] for p in pts}); ys = sorted({p[1] for p in pts})
        for a in range(len(xs) - 1):
            for b in range(len(ys) - 1):
                if all(p in pts for p in [(xs[a], ys[b]), (xs[a + 1], ys[b]),
                                          (xs[a], ys[b + 1]), (xs[a + 1], ys[b + 1])]):
                    slabs.append([xs[a], xs[a + 1], ys[b], ys[b + 1], z])

    loads = _loads(cfg, info, coords, ms["T"][0])

    model_used = _model_used(root)
    stats = [["Nodes / elements", f"{len(used)} / {len(elements)}"],
             ["Periods T1-T3", " / ".join("%.3f" % t for t in ms["T"][:3]) + " s"],
             ["Fixed-ended beams", str(sum(bool(e.get("fe")) for e in elements))]]

    data = {
        "meta": {
            "title": "%s — %s" % (name, cfg.get("arch", "")),
            "subtitle": "%d nodes · %d elements · T₁=%.3f s · units: %s" %
                        (len(used), len(elements), ms["T"][0],
                         ("N, mm (N-mm-sec)" if _viewer_si(cfg) else "kip, in")),
            "model_line": ("designed with model: %s" % model_used) if model_used else "",
            "levels": levels, "stats": stats,
        },
        "nodes": {str(t): [round(c, 1) for c in coords[t]] for t in used},
        "fixed": fixed, "elements": elements, "modes": modes, "slabs": slabs,
        "loads": loads,
    }
    return native.enrich(data, root, _viewer_si(cfg), masks)


# --------------------------------------------------------------- html assembly
def standalone_html(cfg, name, root=None):
    root = root or os.getcwd()
    data = _viewer_data(cfg, name, root)
    return _render(data, name)


def _render(data, name):
    directory = Path(_DIR)
    template = (directory / "viewer3d_template.html").read_text(encoding="utf-8")
    three = (directory / "vendor/three.min.js").read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    return (template.replace("__THREE__", three).replace("__TITLE__", _html.escape(str(name)))
            .replace("__DATA__", payload))


def _saved_geometry(source):
    contents = source.read_text(encoding="utf-8-sig")
    marker = re.search(r"^\s*const\s+DATA\s*=\s*", contents, re.MULTILINE)
    if not marker:
        raise ValueError(f"Missing native viewer geometry in {source.name}")
    data, _ = json.JSONDecoder().raw_decode(contents, marker.end())
    if not data.get("nodes") or not data.get("elements") or not isinstance(data.get("meta"), dict):
        raise ValueError(f"Incomplete geometry in {source.name}")
    return data


def _saved_gravity(data, cfg, package):
    """Use the native load arithmetic when installed. No cfg or replay program is executed."""
    loads = data.setdefault("loads", {})
    old_points = (loads.get("DLdyn") or {}).get("pts", [])
    loads.pop("DLdyn", None)
    loads.pop("LLdyn", None)
    if cfg.get("present") and cfg.get("heights"):
        try:
            import engine3d as engine
        except ImportError:
            engine = None
        if engine is not None:
            previous = engine.unit_system()
            try:
                engine.activate_si_units()
                # JSON object keys are strings. The solver accepts integers for these schedules.
                cfg = dict(cfg)
                for key in ("D_by_level", "L_by_level", "extra_mass_floors", "roof_regions"):
                    if isinstance(cfg.get(key), dict):
                        cfg[key] = {int(k): v for k, v in cfg[key].items()}
                coords = {int(tag): xyz for tag, xyz in data["nodes"].items()}
                loads.update(_gravity_levels(engine, cfg, cfg["present"], coords, True))
                return
            except (KeyError, TypeError, ValueError):
                # Older snapshots can omit the footprint or rely on executable project callbacks.
                pass
            finally:
                if previous == "kip-in":
                    engine.activate_kip_in_units()
    # The historical DL layer stored effective seismic weight in N. No native imposed-load
    # totals can be recovered from the obsolete psf overlay without the project footprint.
    weight = native.number((package.get("seismic_calc") or {}).get("W_engine_kN"))
    if weight is not None and old_points:
        loads["weight"] = {"pts": [[*pt[:3], round(pt[3] / 1000, 6)] for pt in old_points],
                           "total": weight}


def rebuild_saved(job, output, source_viewer=None):
    """Create a derived standalone website viewer outside the immutable native job tree."""
    root = Path(job).resolve(strict=True)
    source = Path(source_viewer or root / "viewer_3d.html").resolve(strict=True)
    target = Path(output).resolve()
    if target == source or target.is_relative_to(root) or target.suffix.lower() not in (".html", ".htm"):
        raise ValueError("Choose a separate staging HTML file outside the native job directory")
    data = _saved_geometry(source)
    cfg = native.read_json(root / "design/cfg_snapshot.json")
    package = native.read_json(root / "design/calc_package.json")
    system = str(package.get("unit_system") or cfg.get("units") or "").lower()
    subtitle = str(data["meta"].get("subtitle") or "").lower()
    if system in ("n-mm", "n-mm-s", "n-mm-sec", "si", "metric"):
        si = True
    elif system in ("kip-in", "kip-in-sec"):
        si = False
    elif "n-mm" in subtitle or "kip, in" in subtitle:
        si = "n-mm" in subtitle
    else:
        raise ValueError("Saved job does not declare the analytical geometry length unit")
    if si and data["meta"].get("revision") != 2:
        _saved_gravity(data, cfg, package)
        loads = data["loads"]
        for layer in (loads.get("stat") or {}).values():
            if isinstance(layer, dict) and native.number(layer.get("total")) is not None:
                layer["total"] = round(float(layer["total"]) / 1000, 3)
        plan = cfg.get("load_plan") or {}
        if not plan.get("story_forces"):
            plan = native.read_json(root / "load_plan.json") or package.get("load_plan") or {}
        heights = cfg.get("heights") or []
        _india_lateral(loads, plan, list(accumulate(heights)))
        loads["force_unit"] = "kN"
    native.enrich(data, root, si)
    bindings = {}
    for path in (source, root / "model_opensees.py", root / "design/member_schedule.csv",
                 root / "design/calc_package.json", root / "design/cfg_snapshot.json", root / "load_plan.json"):
        if path.is_file():
            key = "geometry_viewer" if path == source else path.relative_to(root).as_posix()
            with path.open("rb") as f:
                digest = hashlib.sha256()
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
                bindings[key] = digest.hexdigest()
    data["meta"]["source_sha256"] = bindings
    target.parent.mkdir(parents=True, exist_ok=True)
    result = _render(data, data["meta"].get("title") or root.name)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as f:
        temp = Path(f.name)
    try:
        temp.write_bytes(result.encode("utf-8"))
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def report_section(cfg, name, root):
    """Write <root>/viewer_3d.html and return an orange 'View model' button (opens a new tab)."""
    doc = standalone_html(cfg, name, root)
    with open(os.path.join(root, "viewer_3d.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return ("<p><a href='viewer_3d.html' target='_blank' rel='noopener' style=\""
            "display:inline-block;background:%s;color:#fff;font-weight:600;"
            "padding:9px 22px;border-radius:8px;text-decoration:none\">"
            "View model</a> <span class='note' style='margin-left:8px'>interactive 3D viewer "
            "(analytical geometry, mode shapes, loads and native strength groups) &mdash; opens in a new tab</span></p>"
            % ORANGE)



if __name__ == "__main__":
    import argparse
    if __package__:
        import sys
        sys.path.insert(0, _DIR)  # Existing engine modules import their siblings by top-level name.
    parser = argparse.ArgumentParser(description="Rebuild a standalone viewer from an existing native job.")
    parser.add_argument("job", help="saved job containing viewer_3d.html and design/")
    parser.add_argument("--output", required=True, help="publication HTML outside the saved job")
    args = parser.parse_args()
    print(rebuild_saved(args.job, args.output))
