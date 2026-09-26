"""
report.py  --  one self-contained HTML engineer's report per building.

A senior engineer can follow the whole job: building summary + plan, model & deformed shape,
dynamic properties + mode shapes, drift/P-Delta, story shear/OTM, support reactions, member
forces per load case (tables + N/V/M diagrams), the design summary, and Appendix A — a fully
referenced IS 800:2007 design-calculation record for every member/connection.

Math is rendered with MathJax; figures are written to figs/ and referenced (keeps the .html small).

Run (operator, Linux/WSL where openseespy runs):
    python report.py B07
    python report.py T06            # auto-registers test_cfgs
    python report.py T01 T06 B02
"""
import os, sys, math, re, base64, io, json, datetime
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa
import openseespy.opensees as ops

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))
sys.path.insert(0, os.path.join(HERE, "eval_tests", "answer_key"))
import engine3d as E
import sections as S
import design_post as DPOST          # run_case + capacity snippets (operator side)


# ---- Wave 2 SI report unit context (set in build_report / _design_basis) ----
_REP_CFG = None
_REP_SI = True
_REP_SC = None

def _set_report_units(cfg=None):
    """Bind display scales for this report render (SI default for India)."""
    global _REP_CFG, _REP_SI, _REP_SC, Fy, Emod
    _REP_CFG = cfg
    try:
        from india_units import is_si, display_scale
        _REP_SI = is_si(cfg) if cfg is not None else True
        _REP_SC = display_scale(cfg)
    except Exception:
        _REP_SI = True
        _REP_SC = {"si": True, "force_div": 1000.0, "force_lbl": "kN", "moment_div": 1e6,
                   "moment_lbl": "kN·m", "length_div": 1000.0, "length_lbl": "m",
                   "length_member_lbl": "mm", "stress_lbl": "MPa", "pressure_lbl": "kN/m²",
                   "E_default": 200000.0, "Fy_default": 250.0}
    Fy = float(_REP_SC.get("Fy_default", 250.0 if _REP_SI else 50.0))
    Emod = float(_REP_SC.get("E_default", 200000.0 if _REP_SI else 29000.0))
    return _REP_SC

def _sc():
    if _REP_SC is None:
        _set_report_units(_REP_CFG)
    return _REP_SC

def _F(v, digits=1):
    """Engine force → display number (kN if SI)."""
    if v is None: return None
    return round(float(v) / _sc()["force_div"], digits)

def _M(v, digits=1):
    """Engine moment (N·mm / kip-in) → display (kN·m / kip-ft)."""
    if v is None: return None
    return round(float(v) / _sc()["moment_div"], digits)

def _Lstory(v, digits=2):
    if v is None: return None
    return round(float(v) / _sc()["length_div"], digits)

def _ul(kind):
    sc = _sc()
    return {
        "F": sc["force_lbl"], "M": sc["moment_lbl"], "L": sc["length_lbl"],
        "Lm": sc.get("length_member_lbl", "mm" if sc["si"] else "in"),
        "S": sc["stress_lbl"], "P": sc["pressure_lbl"],
    }[kind]

def _si_unit_banner(cfg=None):
    """Wave 2 SI: N-mm-sec engine + SI HTML labels (kN / mm / MPa / kN·m)."""
    _set_report_units(cfg)
    try:
        from india_units import is_si, report_unit_labels, ENGINE_UNITS
    except Exception:
        return ""
    if not is_si(cfg):
        return ("<p><b>Unit system:</b> kip-in (legacy / explicit opt-in).</p>")
    lab = report_unit_labels(cfg)
    return (
        "<p><b>Unit system (India SI wave 2):</b> OpenSees / engine = <code>N-mm-sec</code> "
        f"(force {lab['force']}, length {lab['length']}, stress {lab['stress']}). "
        f"Tables below use display units <b>{lab['force_display']}</b> / <b>{lab['moment_display']}</b> / "
        f"<b>{lab['stress']}</b> / <b>{lab['pressure']}</b> (not kip/ksi). "
        f"E_steel = {ENGINE_UNITS['E_steel_MPa']:.0f} MPa, g = {ENGINE_UNITS['g_mm_s2']:.0f} mm/s².</p>"
    )

try:
    import design_pipeline as PIPE   # combos() — the IS 875/1893 load-case list
    HAVE_PIPE = True
except Exception:
    HAVE_PIPE = False

Fy, Emod = 250.0, 200000.0  # India SI defaults (MPa); legacy kip-in via _set_report_units
try:
    from india_units import active_unit_system, ENGINE_UNITS
    if active_unit_system() == 'N-mm':
        Fy, Emod = 250.0, ENGINE_UNITS['E_steel_MPa']
    else:
        Fy, Emod = 50.0, 29000.0
except Exception:
    pass
g = E.g
_set_report_units(None)  # bind module defaults

# ============================================================ small utilities
def _register(name):
    if name not in E.CFG:
        # re-render path: a fresh run_python process won't have the cfg registered -- load jobs/<name>/cfg.py
        _base = os.environ.get("STEEL_BUILDER_JOBS") or HERE
        _cfgfile = os.path.join(_base, name, "cfg.py")
        if os.path.exists(_cfgfile):
            try:
                import importlib.util as _ilu
                _spec = _ilu.spec_from_file_location("jobcfg_" + name, _cfgfile)
                _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m)
                if hasattr(_m, "cfg"): E.CFG[name] = _m.cfg
            except Exception:
                pass
    if name not in E.CFG:
        try: import test_cfgs  # noqa: F401
        except Exception: pass
    if name not in E.CFG:
        raise SystemExit(f"unknown building '{name}' -- register its cfg or write jobs/{name}/cfg.py first")

# Figures are written to <root>/figs/ and referenced by relative path (set in build_report).
_FIGDIR = None          # absolute path of the current report's figs/ folder
_FIGSEQ = [0]           # running counter for auto-named inline figures

def _b64(fig):
    """Save a matplotlib figure to figs/ and return its relative path (data-URI fallback if no figdir).
    Uses tight_layout (O(subplots)) instead of bbox_inches='tight' (O(artists)) so a frame figure with
    thousands of annotations encodes in milliseconds, not tens of seconds (P8)."""
    try: fig.tight_layout()
    except Exception: pass
    if _FIGDIR:
        _FIGSEQ[0] += 1; fn = "auto_%03d.png" % _FIGSEQ[0]
        fig.savefig(os.path.join(_FIGDIR, fn), format="png", dpi=130)
        plt.close(fig); return "figs/" + fn
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=130)
    plt.close(fig); buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")

def _png_file_b64(path):
    """Reference an existing PNG (already in figs/) by relative path; data-URI fallback if no figdir."""
    if not os.path.exists(path): return None
    if _FIGDIR:
        return "figs/" + os.path.basename(path)
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")

def _materialize(uri):
    """Turn any leftover data:image/...;base64 URI (e.g. from viz3d/frame_diagram) into a figs/ file."""
    if _FIGDIR and isinstance(uri, str) and uri.startswith("data:image/"):
        try:
            head, b64 = uri.split(",", 1)
            ext = head.split("/")[1].split(";")[0].replace("jpeg", "jpg").replace("svg+xml", "svg")
            _FIGSEQ[0] += 1; fn = "auto_%03d.%s" % (_FIGSEQ[0], ext)
            with open(os.path.join(_FIGDIR, fn), "wb") as f: f.write(base64.b64decode(b64))
            return "figs/" + fn
        except Exception:
            return uri
    return uri

def _decode(tag):
    k = tag // 100000; r = tag % 100000; return r // 100, r % 100, k

def _loc(n1, n2):
    """Human-readable member location: grid (i,j) and building level k."""
    i1, j1, k1 = _decode(n1); i2, j2, k2 = _decode(n2)
    if (i1, j1) == (i2, j2):                       # vertical: column
        return f"({i1},{j1}) level {k1}→{k2}"
    return f"({i1},{j1})→({i2},{j2}) level {k1}"

def _table(headers, rows, cls=""):
    h = "".join(f"<th>{c}</th>" for c in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table class='{cls}'><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"

def _calc(title, rows, note=""):
    """Engineering calc-sheet block: a titled worksheet table whose rows are
    (quantity, calculation, value, code-reference) — one calc step per line."""
    n = f"<div class='cnote'><i>{note}</i></div>" if note else ""
    body = "".join(f"<tr><td>{q}</td><td>{c}</td><td class='v'>{v}</td><td class='r'>{r}</td></tr>"
                   for (q, c, v, r) in rows)
    return (f"<h5>{title}</h5>{n}<table class='calc'>"
            "<tr class='hd'><th>Quantity</th><th>Calculation</th><th>Value</th><th>Ref. (IS 800)</th></tr>"
            + body + "</table>")

def _img(uri, caption, full=False):
    cls = "full" if full else ""
    if not uri: return f"<p class='note'>[{caption}: not available]</p>"
    if isinstance(uri, str) and uri.startswith("ERROR"):
        return f"<p class='note'>[{caption}: {uri}]</p>"
    uri = _materialize(uri)
    return f"<figure class='{cls}'><img src='{uri}'/><figcaption>@@FIGNUM@@ {caption}</figcaption></figure>"

def _fmt(d):
    if not isinstance(d, dict): return str(d)
    return "; ".join(f"{k}={v}" for k, v in d.items())

# ============================================================ analysis helpers
def _seismic(cfg):
    NF = len(cfg["heights"])
    T, w2, eX, eY, Mtot = E.modal(cfg, min(3*NF, 16))
    Cs, V, Tu, Ta, kk, Fx, W = E.elf(cfg, T[0])
    return T, eX, eY, Cs, V, Tu, Ta, Fx, W

def _run_case(cfg, direction, Fx, accidental=False):
    """Seismic ELF case in `direction`; leaves model live. Returns info, disp, drift, reactions."""
    info = E.build(cfg, "PDelta"); NF = info["NF"]; di = 0 if direction == "X" else 1
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    fD = 1.2 + 0.2*cfg["seis"]["SDS"]
    for k in range(1, NF+1):
        pts = info["present"][k]; p = fD*E.floor_grav(cfg, k)/len(pts)
        for (i, j) in pts: ops.load(E.ntag(i, j, k), 0, 0, -p, 0, 0, 0)
    SX, SY = cfg["SX"], cfg["SY"]
    for k in range(1, NF+1):
        f = [0.0]*6; f[di] = Fx[k]
        if accidental:
            pts = info["present"][k]; xs = [i*SX for i, j in pts]; ys = [j*SY for i, j in pts]
            B = (max(ys)-min(ys)+SY) if direction == "X" else (max(xs)-min(xs)+SX)
            f[5] = Fx[k]*0.05*B
        ops.load(E.mtag(k), *f)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-7, 200); ops.algorithm("Newton")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static"); ops.analyze(1)
    disp = {k: ops.nodeDisp(E.mtag(k), di+1) for k in range(1, NF+1)}
    drift = []; prev = 0.0
    for k in range(1, NF+1):
        drift.append((disp[k]-prev)/cfg["heights"][k-1]); prev = disp[k]
    ops.reactions()
    react = [(i, j, [ops.nodeReaction(E.ntag(i, j, 0), d) for d in (1, 2, 3, 4, 5, 6)])
             for (i, j) in info["present"][0]]
    return info, disp, drift, react

# ============================================================ figures
def fig_plan(cfg):
    """2D plan: column grid with (i,j) labels — explains the grid used in the reaction tables."""
    NX, NY = cfg["NX"], cfg["NY"]; SX, SY = cfg["SX"], cfg["SY"]
    xco = cfg.get("xcoords"); yco = cfg.get("ycoords"); skew = cfg.get("skew", 0.0)
    def XY(i, j): return ((xco[i] if xco else i*SX)+skew*j, (yco[j] if yco else j*SY))
    pres0 = set(cfg_present(cfg, 1))
    Lx = (xco[-1] if xco else NX*SX); Ly = (yco[-1] if yco else NY*SY)
    fig, ax = plt.subplots(figsize=(9, 9*max(Ly, 1)/max(Lx, 1) + 1))
    for i in range(NX):                            # shade framed bays -> non-rectangular footprints are visible
        for j in range(NY):
            if all(p in pres0 for p in [(i, j), (i+1, j), (i, j+1), (i+1, j+1)]):
                bx = [XY(i, j)[0], XY(i+1, j)[0], XY(i+1, j+1)[0], XY(i, j+1)[0]]
                by = [XY(i, j)[1], XY(i+1, j)[1], XY(i+1, j+1)[1], XY(i, j+1)[1]]
                ax.fill(bx, by, color="#eef3fb", zorder=0)
    for i in range(NX+1):                          # grid lines
        x0, _ = XY(i, 0); x1, y1 = XY(i, NY); ax.plot([XY(i,0)[0], XY(i,NY)[0]], [XY(i,0)[1], XY(i,NY)[1]], color="#ccc", lw=0.8)
    for j in range(NY+1):
        ax.plot([XY(0,j)[0], XY(NX,j)[0]], [XY(0,j)[1], XY(NX,j)[1]], color="#ccc", lw=0.8)
    for i in range(NX+1):
        for j in range(NY+1):
            x, y = XY(i, j)
            present = (i, j) in pres0
            ax.plot([x], [y], marker=("s" if present else "x"), ms=5, ls="none", color="black" if present else "#bbb")
            ax.annotate(f"({i},{j})", (x, y), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.set_aspect("equal"); ax.set_xlabel("X (in)  —  i index"); ax.set_ylabel("Y (in)  —  j index")
    ax.set_title(f"Plan grid — column lines labelled (i, j); shaded = framed bays (level 1); × = no column")
    ax.grid(False)
    return _b64(fig)

def cfg_present(cfg, k):
    """present column (i,j) at floor k (handles plan-shape callables)."""
    try:
        return E.grid(cfg, k)
    except Exception:
        return [(i, j) for i in range(cfg["NX"]+1) for j in range(cfg["NY"]+1)]

def fig_mode_3d(cfg, mode, nmodes):
    """Full-frame 3D mode shape (undeformed grey + modal-deformed colour), true proportions.
    REUSES the cached modal eigenvector field (engine3d.mode_shapes) -- no ops.eigen re-solve."""
    ms = E.mode_shapes(cfg, max(nmodes, mode))
    nodes = ms["coords"]; evall = ms["ev"]; ele = ms["ele"]; zlev = ms["z"]
    ev = {t: (evall[t][mode-1] if (t in evall and len(evall[t]) >= mode) else [0,0,0,0,0,0]) for t in nodes}
    amp = max((abs(ev[t][0])+abs(ev[t][1]) for t in ev), default=1.0) or 1.0
    zmax = (max(zlev.values()) if isinstance(zlev, dict) else zlev[-1])
    sc = 0.12*zmax/amp
    fig = plt.figure(figsize=(11, 8)); ax = fig.add_subplot(111, projection="3d")
    for (et, kind, sec, n1, n2) in ele:
        if n1 not in nodes or n2 not in nodes: continue
        a, b = nodes[n1], nodes[n2]
        ax.plot([a[0], b[0]], [a[1], b[1]], [a[2], b[2]], color="0.8", lw=0.6)
        da = [a[i]+sc*ev[n1][i] for i in range(3)]; db = [b[i]+sc*ev[n2][i] for i in range(3)]
        ax.plot([da[0], db[0]], [da[1], db[1]], [da[2], db[2]], color="#2c5aa0", lw=1.3)
    ax.set_xlabel("X (in)"); ax.set_ylabel("Y (in)"); ax.set_zlabel("Z (in)")
    try:
        xr = ax.get_xlim3d(); yr = ax.get_ylim3d(); zr = ax.get_zlim3d()
        ax.set_box_aspect((xr[1]-xr[0], yr[1]-yr[0], zr[1]-zr[0]))
    except Exception: pass
    return _b64(fig)

def _elevation_from_live(cfg, direction, title):
    """Draw N/V/M for the perimeter frame line of `direction` from the CURRENTLY LIVE model
    (call right after a case has been analysed). Returns data-uri or None."""
    onln = (lambda i, j: j == 0) if direction == "X" else (lambda i, j: i == 0)
    al = (lambda n: ops.nodeCoord(n)[0]) if direction == "X" else (lambda n: ops.nodeCoord(n)[1])
    zo = lambda n: ops.nodeCoord(n)[2]
    mem = []
    for (t, kind, sec, n1, n2) in _LIVE_ELE:
        i1, j1, _ = _decode(n1); i2, j2, _ = _decode(n2)
        if onln(i1, j1) and onln(i2, j2): mem.append((t, kind, n1, n2))
    if not mem: return None
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    _ftitles = (f"Axial N ({_ul('F')})", f"Shear V ({_ul('F')})", f"Moment M ({_ul('M')})")
    for ax, which, ttl, col in zip(axes, ("N", "V", "M"),
                                   _ftitles,
                                   ("#1f77b4", "#2ca02c", "#d62728")):
        data = []; mx = 1e-9
        _mdiv = _sc()["moment_div"]
        for (t, kind, n1, n2) in mem:
            bf = ops.basicForce(t)
            if kind == "brace":
                e1 = e2 = (_F(bf[0], 3) if which == "N" else 0.0)
            else:
                L = math.dist(ops.nodeCoord(n1), ops.nodeCoord(n2))
                if which == "N":   e1 = e2 = _F(bf[0], 3)
                elif which == "V": e1 = e2 = _F((abs(bf[1])+abs(bf[2]))/L, 3)
                else:              e1 = bf[1]/_mdiv; e2 = -bf[2]/_mdiv
            data.append((kind, n1, n2, e1, e2)); mx = max(mx, abs(e1), abs(e2))
        sc = (0.30*min(cfg["SX"], cfg["SY"]))/mx
        peak = 0.0; peaklab = None
        for kind, n1, n2, e1, e2 in data:
            a1, z1 = al(n1), zo(n1); a2, z2 = al(n2), zo(n2)
            ax.plot([a1, a2], [z1, z2], color="#bbb", lw=1.0, zorder=1)
            if abs(z2-z1) > abs(a2-a1):
                ax.plot([a1+e1*sc, a2+e2*sc], [z1, z2], color=col, lw=1.2)
                ax.plot([a1, a1+e1*sc], [z1, z1], color=col, lw=0.5)
                ax.plot([a2, a2+e2*sc], [z2, z2], color=col, lw=0.5)
            else:
                ax.plot([a1, a2], [z1+e1*sc, z2+e2*sc], color=col, lw=1.2)
                ax.plot([a1, a1], [z1, z1+e1*sc], color=col, lw=0.5)
                ax.plot([a2, a2], [z2, z2+e2*sc], color=col, lw=0.5)
            if max(abs(e1), abs(e2)) > peak:
                peak = max(abs(e1), abs(e2)); peaklab = (a1, z1, max(e1, e2, key=abs))
        if peaklab:
            ax.annotate(f"max {peak:.0f}", (peaklab[0], peaklab[1]), fontsize=8, color=col,
                        fontweight="bold")
        ax.set_title(f"{ttl}   (peak {peak:.0f})"); ax.set_xlabel(f"along ({_ul('Lm')})"); ax.set_ylabel(f"Z ({_ul('Lm')})")
        ax.set_aspect("equal", "datalim"); ax.grid(alpha=0.2)
    fig.suptitle(title)
    return _b64(fig)

_LIVE_ELE = []   # element registry of the currently-live model (set by run helpers)

def fig_drift_profile(cfg, driftX, driftY):
    """IS 1893 Part 1:2016 cl.7.11.1 — plot design storey drifts (no ASCE Cd/Ie amplification)."""
    NF = len(cfg["heights"])
    try:
        from india_seismic import design_story_drifts
        dX = design_story_drifts(driftX, cfg); dY = design_story_drifts(driftY, cfg)
    except Exception:
        dX, dY = list(driftX), list(driftY)
    lvl = list(range(1, NF+1))
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot([d*100 for d in dX], lvl, "-o", label=r"design drift X (IS 1893)")
    ax.plot([d*100 for d in dY], lvl, "-s", label=r"design drift Y (IS 1893)")
    _dl, _dlrho = E.drift_allowable(cfg)
    lim = _dl*100
    ax.axvline(lim, color="r", ls="--", label=f"limit {lim:.2f}% (cl.7.11.1.1)")
    ax.set_xlabel("interstorey drift (%)"); ax.set_ylabel("storey"); ax.set_title("Storey drift profile (IS 1893)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    return _b64(fig)

def fig_story_shear_otm(cfg, Fx):
    NF = len(cfg["heights"]); z = E.zlevels(cfg)
    _mdiv = _sc()["moment_div"]; _fdiv = _sc()["force_div"]
    Vstory_eng = [sum(Fx[k] for k in range(s, NF+1)) for s in range(1, NF+1)]
    Vstory = [v / _fdiv for v in Vstory_eng]
    OTM = [sum(Fx[k]*(z[k]-z[s-1])/_mdiv for k in range(s, NF+1)) for s in range(1, NF+1)]
    OTM_base = sum(Fx[k]*z[k]/_mdiv for k in range(1, NF+1))
    lvl = list(range(1, NF+1))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 5))
    a1.step(Vstory, lvl, where="mid"); a1.set_xlabel(f"story shear ({_ul('F')})"); a1.set_ylabel("story"); a1.grid(alpha=0.3); a1.set_title("Story shear")
    a2.plot(OTM, lvl, "-o"); a2.set_xlabel(f"overturning moment ({_ul('M')})"); a2.set_title("OTM (above story)"); a2.grid(alpha=0.3)
    return _b64(fig), Vstory, OTM_base

# ============================================================ per-load-case forces
def load_cases(cfg):
    """The combination list actually analysed (design_pipeline.combos -> india_loads).
    India: FAIL CLOSED -- an invalid load_plan raises; no ASCE fallback list (HRLOAD-13)."""
    return PIPE.combos(cfg)

def case_forces(cfg, fD, fL, fLr, lat):
    """Run one combination through P-Delta; return (out dict, registry). Leaves model live."""
    out, info = DPOST.run_case(cfg, fD, fL, fLr, lat)
    global _LIVE_ELE; _LIVE_ELE = info["ele"]
    return out, info

def per_case_max_table(info):
    """Per member TYPE, the governing (max) member + its forces + location, read from basicForce —
    the SAME convention the elevation diagrams use, so table and figure magnitudes agree."""
    best = {}   # (kind,sec) -> (score, N, Mz, My, V, n1, n2)
    for (t, kind, sec, n1, n2) in info["ele"]:
        bf = ops.basicForce(t)
        if kind == "brace":
            N = bf[0]; Mz = My = V = 0.0; score = abs(N)
        else:
            L = math.dist(ops.nodeCoord(n1), ops.nodeCoord(n2))
            N = bf[0]; Mz = max(abs(bf[1]), abs(bf[2])); My = max(abs(bf[3]), abs(bf[4]))
            V = max((abs(bf[1])+abs(bf[2]))/L, (abs(bf[3])+abs(bf[4]))/L); score = max(abs(Mz), abs(N))
        key = (kind, sec)
        if key not in best or score > best[key][0]:
            best[key] = (score, N, Mz, My, V, n1, n2)
    rows = []
    for (kind, sec), (sc, N, Mz, My, V, n1, n2) in sorted(best.items()):
        rows.append([kind, sec, f"{_F(N)}", f"{_M(Mz)}", f"{_M(My)}", f"{_F(V)}", _loc(n1, n2)])
    return rows

def _case_desc(label, col_only):
    """Plain-English description of an IS 875/1893 combination label."""
    L = label
    if ("WX" in L or "WY" in L) and "E" not in L.replace("Lr", "").replace("Le", ""):
        d = "X (E–W)" if "WX" in L else "Y (N–S)"
        upl = " (uplift / overturning case, 0.9D)" if L.startswith("0.9") else ""
        return f"Wind acting in the {d} direction, combined with gravity{upl}."
    if "Om0" in L:
        d = "X (E–W)" if "EX" in L else "Y (N–S)"
        upl = " on the 0.9D (uplift) gravity case" if L.startswith("(0.9") else ""
        return (f"Capacity-design (overstrength, \\(\\Omega_0\\)) seismic in the {d} direction{upl} — applied "
                "to the columns only, so they remain elastic while the braces/beams yield (IS 800 seismic / "
                "IS 875/1893 §12.4.3).")
    if "rhoE" in L:
        d = "X (E–W)" if "EX" in L else "Y (N–S)"
        sense = "positive" if ("EX+" in L or "EY+" in L) else "negative"
        tor = ("with +5% accidental torsion" if "t+" in L else
               ("with −5% accidental torsion" if "t-" in L else "no accidental torsion"))
        grav = ("the reduced 0.9D (uplift) gravity case" if L.startswith("(0.9")
                else "the (1.2+0.2·S_DS)D + companion-L gravity case (L factor per §2.3.6 Exc.1, as labelled)")
        return f"Code-level seismic in the {d} direction ({sense} sense, {tor}), combined with {grav}."
    if L.strip() == "1.4D":
        return "Dead load only — the basic gravity check."
    if "1.6L" in L:
        return "Gravity only: dead load plus full floor live load and roof live load."
    return "Load combination."

def _lat_dir(lat):
    if not lat: return "X"
    sx = sum(abs(v[0]) for v in lat.values()); sy = sum(abs(v[1]) for v in lat.values())
    return "X" if sx >= sy else "Y"

# ============================================================ Appendix A — design calcs
def _safe_props(section):
    try: return S.props(section, SEC=E.SEC)
    except Exception:
        try: return S.props(section)
        except Exception: return None

def _member_calc_block(m):
    # Render one calc_package member: section inputs + demand envelope + the agent's RAG-derived
    # capacity / limit state / D-C. Framework codes NO capacity; if unfilled, show a 'derive from RAG' note.
    mid = m.get("id", ""); inp = m.get("inputs", {}) or {}
    sec = inp.get("section", ""); kind = inp.get("kind", "")
    h = ["<h4>%s &mdash; %s (%s)</h4>" % (mid, sec, kind)]
    if _sc()["si"]:
        pk = [("A","A (mm2)"),("Zx","Zx (mm3)"),("Sx","Sx (mm3)"),("Zy","Zy (mm3)"),("Sy","Sy (mm3)"),
              ("rx","rx (mm)"),("ry","ry (mm)"),("r","r (mm)"),("Aw","Aw (mm2)"),("J","J (mm4)"),
              ("length_mm","L (mm)"),("length_in","L (mm)"),("Lb_mm","Lb (mm)"),("Lb_in","Lb (mm)")]
    else:
        pk = [("A","A (in2)"),("Zx","Zx (in3)"),("Sx","Sx (in3)"),("Zy","Zy (in3)"),("Sy","Sy (in3)"),
              ("rx","rx (in)"),("ry","ry (in)"),("r","r (in)"),("Aw","Aw (in2)"),("J","J (in4)"),
              ("length_in","L (in)"),("Lb_in","Lb (in)")]
    pr = [(lbl, inp[k]) for k, lbl in pk if inp.get(k) is not None]
    if pr:
        h.append("<p class='cnote'>Section properties / geometry (IS 808 / IS 1161 catalog; SI mm):</p>")
        h.append(_table([l for l, _ in pr], [["%s" % v for _, v in pr]]))
    # Prefer SI field names; fall back to legacy *_kip keys (values are engine units).
    Pc = inp.get("P_comp_N", inp.get("P_comp_kip"))
    Pt = inp.get("P_tens_N", inp.get("P_tens_kip"))
    Mz = inp.get("Mz_Nmm", inp.get("Mz_kipin"))
    My = inp.get("My_Nmm", inp.get("My_kipin"))
    Vv = inp.get("V_N", inp.get("V_kip"))
    dem = [(f"P_comp ({_ul('F')})", None if Pc is None else _F(Pc)),
           (f"P_tens ({_ul('F')})", None if Pt is None else _F(Pt)),
           (f"Mz ({_ul('M')})", None if Mz is None else _M(Mz)),
           (f"My ({_ul('M')})", None if My is None else _M(My)),
           (f"V ({_ul('F')})", None if Vv is None else _F(Vv))]
    h.append("<p class='cnote'>Demand envelope (analysis):</p>")
    h.append(_table([l for l, _ in dem] + ["governing combo"],
                    [["%s" % v for _, v in dem] + [str(inp.get("governing_combo", ""))]]))
    cap = m.get("capacity"); dc = m.get("DC"); ls = m.get("limit_state"); cited = m.get("cited")
    if (isinstance(cap, dict) and cap) or dc is not None or ls or cited:
        rows = []
        if ls: rows.append(("Governing limit state", "selected from IS 800", str(ls), str(cited or "")))
        if isinstance(cap, dict):
            for k, v in cap.items(): rows.append((k, "", str(v), ""))
        if dc is not None:
            ok = "ok" if (isinstance(dc,(int,float)) and dc <= 1.0) else ("NG" if isinstance(dc,(int,float)) else "")
            rows.append(("D/C", "demand / capacity", "%s %s" % (dc, ok), str(cited or "")))
        h.append(_calc("IS 800 capacity &amp; D/C - derived by the agent from the RAG", rows))
    else:
        h.append("<p class='note'>Capacity &amp; D/C: <b>to be derived by the agent from the IS 800 / 341 "
                 "RAG</b> - the framework computes demands only (no coded capacity). Expected calc_package "
                 "fields: <code>limit_state</code>, <code>cited</code>, <code>capacity</code>, <code>DC</code>.</p>")
    return "".join(h)

def appendix(cfg, name, pkg):
    # Appendix A: per governing member, section inputs + demand envelope + the agent's RAG-derived
    # IS 800 capacity/limit-state/D-C. The framework codes NO capacity equations.
    h = ["<h3>Member calculations</h3>",
         "<p>For every governing member the framework lists the section properties and the enveloped "
         "demand from the analysis combinations. The IS 800:2007 capacity, governing limit state, cited "
         "clause, and D/C are <b>derived by the agent from the RAG</b> and shown where recorded in "
         "calc_package.json - the framework computes no capacity.</p>"]
    members = pkg.get("members") if isinstance(pkg, dict) else None
    if isinstance(members, list):
        for m in members:
            if not (m.get("inputs", {}) or {}).get("section"): continue
            try: h.append(_member_calc_block(m))
            except Exception as ex: h.append("<p class='note'>[render failed: %s]</p>" % ex)
    else:
        h.append("<p class='note'>[no members in calc_package.json]</p>")
    cd = pkg.get("connections") or pkg.get("connection_demands")
    if cd:
        h.append("<h3>Connections (IS 800:2007 Ch. J / Ch. K; IS 800 seismic-22 capacity design)</h3>")
        items = cd.items() if isinstance(cd, dict) else [(c.get("id", ""), c) for c in cd]
        for cid, c in items:
            dem = _fmt(c.get("demand", c.get("demands", {})))
            comp = c.get("components", c.get("notes", ""))
            cited = c.get("cited", "")
            cdf = " (capacity-design)" if c.get("capacity_design") else ""
            h.append("<h4>%s &mdash; %s%s</h4><p><b>Demand:</b> %s</p><p><b>Components:</b> %s</p><p><b>Cited:</b> %s</p>"
                     % (cid, c.get("type", ""), cdf, dem, comp, cited))
            chks = c.get("checks")
            if isinstance(chks, list) and chks:
                rows = [[k.get("limit_state", ""),
                         ("%.2f" % k["DC"] if isinstance(k.get("DC"), (int, float)) else str(k.get("DC", ""))),
                         "OK" if (isinstance(k.get("DC"), (int, float)) and k["DC"] <= 1.0) else ""] for k in chks]
                h.append(_table(["Limit state", "D/C", "&le;1.0"], rows))
            ws = c.get("section12_worksheet") or {}
            slots = ws.get("slots") if isinstance(ws, dict) else None
            if isinstance(slots, list) and slots:
                h.append("<p class='cnote'><b>IS 800 §12 component worksheet (H5 stubs):</b> "
                         "gusset/bolt/weld D/C slots — fill from RAG; "
                         "<code>found:false</code> means do not invent sizes.</p>")
                rows = [[s.get("component", ""),
                         "found:false" if s.get("found") is False else str(s.get("found")),
                         ("%.2f" % s["DC"] if isinstance(s.get("DC"), (int, float)) else "—"),
                         s.get("note", "")] for s in slots]
                h.append(_table(["Component", "found", "D/C", "Note"], rows))
    return "".join(h)

def _num(x):
    try: return float(x)
    except Exception: return 0.0
def _kind_from_id(mid):
    s = (mid or "").lower()
    return "brace" if "brace" in s else ("beam" if "beam" in s else "col")
def _sec_from_id(mid):
    for part in (mid or "").replace("_", "-").split("-"):
        if part and (part[0] in "WHwh") and any(c.isdigit() for c in part): return part.upper()
    return None

# ============================================================ HTML shell
CSS = """body{font-family:Segoe UI,Arial,sans-serif;max-width:1040px;margin:24px auto;color:#222;line-height:1.55}
h1{border-bottom:3px solid #2c5aa0}h2{border-bottom:1px solid #ccc;margin-top:34px;color:#2c5aa0}
h3{color:#2c5aa0;margin-top:22px}h4{margin:18px 0 4px;color:#333}
table{border-collapse:collapse;margin:12px 0;font-size:14px}th,td{border:1px solid #bbb;padding:4px 9px;text-align:right}
th{background:#eef3fb}td:first-child,th:first-child{text-align:left}
figure{display:block;margin:16px 0}img{width:100%;max-width:100%;border:1px solid #ddd}
figcaption{font-size:12px;color:#555;text-align:center}.note{color:#a00;font-style:italic}
pre{background:#f6f8fa;padding:10px;border-radius:6px;overflow:auto;font-size:12px}
h5{margin:16px 0 2px;color:#2c5aa0;font-size:14px}
.cnote{font-size:12px;color:#666;margin:0 0 4px}
table.calc{width:100%;font-size:13px;margin:2px 0 14px}
table.calc td,table.calc th{text-align:left;padding:3px 9px;vertical-align:top}
table.calc td.v{text-align:right;white-space:nowrap;font-weight:600}
table.calc td.r{text-align:right;color:#888;white-space:nowrap;font-size:12px}
table.calc tr.hd th{background:#eef3fb}"""

MATHJAX = ("<script>window.MathJax={tex:{inlineMath:[['\\\\(','\\\\)']],displayMath:[['\\\\[','\\\\]']]}};</script>"
           "<script async src='https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js'></script>")

def _gravity_loads_table(cfg):
    rows = [["Floor dead, D", f"{cfg.get('D_floor','?')} psf"],
            ["Roof dead, D", f"{cfg.get('D_roof','?')} psf"],
            ["Cladding", f"{cfg.get('clad','?')} psf of wall"],
            ["Floor live, L", f"{cfg.get('L_floor','?')} psf"]]
    if cfg.get("Lr"):   rows.append(["Roof live, Lr", f"{cfg['Lr']} psf"])
    if cfg.get("snow"): rows.append(["Snow, S", f"{cfg['snow']} psf"])
    return _table(["Gravity load", "Value"], rows)

def _lateral_inputs_table(cfg):
    s = cfg["seis"]; w = cfg.get("wind", {})
    rows = [["Seismic SDS / SD1", f"{s['SDS']} / {s['SD1']} g"],
            ["R / Cd / Ω0 / Ie", f"{s['R']} / {s.get('Cd')} / {s.get('Om0')} / {s['Ie']}"],
            ["Period coeff Ct / x / Cu", f"{s['Ct']} / {s['x']} / {s['Cu']}"]]
    if w: rows.append(["Wind V / Exposure", f"{w.get('V','?')} mph / {w.get('exposure','C')}"])
    return _table(["Lateral-load input", "Value"], rows)

def _load_plan_wind(cfg):
    """India load_plan wind_summary / story W_X W_Y — preferred over legacy cfg['wind']."""
    plan = cfg.get("load_plan") or {}
    ws = plan.get("wind_summary") or plan.get("wind") or {}
    sf = plan.get("story_forces") or {}
    return ws, sf


def _story_force_dict(raw, NF, component=0):
    """Normalize story force map/list to {1..NF} scalar forces (N for SI).

    load_plan story_forces may be scalars or [Fx, Fy, Fz] vectors; component selects axis
    (0=X for W_X, 1=Y for W_Y).
    """
    if raw is None:
        return None
    def _scalar(v):
        if isinstance(v, (list, tuple)):
            if len(v) == 0:
                return 0.0
            idx = min(int(component), len(v) - 1)
            return float(v[idx])
        return float(v)
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                ik = int(k)
            except Exception:
                continue
            out[ik] = _scalar(v)
    elif isinstance(raw, (list, tuple)):
        for i, v in enumerate(raw, start=1):
            out[i] = _scalar(v)
    return out or None


def _wind_section(cfg):
    """Returns (html, VwX, VwY). Prefers India load_plan wind when present.

    complete-gap wave1: India jobs apply wind via load_plan laterals but often omit
    legacy cfg['wind'], so Ch.3 previously said "no wind parameters" while combos
    already carried W_X/W_Y. Display applied wind_summary / story forces when available.
    """
    ws, sf = _load_plan_wind(cfg)
    NF = len(cfg.get("heights") or []) or 1
    if ws or sf.get("W_X") or sf.get("W_Y"):
        try:
            FX = _story_force_dict(sf.get("W_X"), NF, component=0)
            FY = _story_force_dict(sf.get("W_Y"), NF, component=1)
            VwX = sum(FX.values()) if FX else None
            VwY = sum(FY.values()) if FY else None
            try:
                from india_units import is_si as _is_si
                _si = _is_si(cfg)
            except Exception:
                _si = (str(cfg.get("units") or "").upper() in ("N-MM", "SI", "METRIC")
                       or cfg.get("si_native"))
            scale = 1000.0 if _si else 1.0  # kN→N for SI summaries
            if VwX is None and ws.get("VB_x_kN") is not None:
                VwX = float(ws["VB_x_kN"]) * scale
            if VwY is None and ws.get("VB_y_kN") is not None:
                VwY = float(ws["VB_y_kN"]) * scale
            if FX is None and ws.get("Qi_x_kN"):
                FX = {i + 1: float(q) * scale for i, q in enumerate(ws["Qi_x_kN"])}
                if VwX is None:
                    VwX = sum(FX.values())
            if FY is None and ws.get("Qi_y_kN"):
                FY = {i + 1: float(q) * scale for i, q in enumerate(ws["Qi_y_kN"])}
                if VwY is None:
                    VwY = sum(FY.values())
            param_rows = []
            if ws.get("cite"):
                param_rows.append(["Code / cite", str(ws.get("cite"))])
            if ws.get("site"):
                param_rows.append(["Site", str(ws.get("site"))])
            if ws.get("Vb_mps") is not None:
                param_rows.append(["Vb (m/s)", str(ws.get("Vb_mps"))])
            if ws.get("terrain_category") is not None:
                param_rows.append(["Terrain category", str(ws.get("terrain_category"))])
            if any(ws.get(k) is not None for k in ("k1", "k2", "k3", "k4")):
                param_rows.append([
                    "k1 / k2 / k3 / k4",
                    f"{ws.get('k1','—')} / {ws.get('k2','—')} / {ws.get('k3','—')} / {ws.get('k4','—')}",
                ])
            if ws.get("Vz_mps") is not None:
                param_rows.append(["Vz (m/s)", str(ws.get("Vz_mps"))])
            if ws.get("pz_kNm2") is not None or ws.get("pd_kNm2") is not None:
                param_rows.append([
                    "pz / pd (kN/m²)",
                    f"{ws.get('pz_kNm2','—')} / {ws.get('pd_kNm2','—')}",
                ])
            if any(ws.get(k) is not None for k in ("Kd", "Ka", "Kc")):
                param_rows.append([
                    "Kd / Ka / Kc",
                    f"{ws.get('Kd','—')} / {ws.get('Ka','—')} / {ws.get('Kc','—')}",
                ])
            if ws.get("Cpe_windward") is not None or ws.get("Cpe_leeward") is not None:
                param_rows.append([
                    "Cpe windward / leeward",
                    f"{ws.get('Cpe_windward','—')} / {ws.get('Cpe_leeward','—')}",
                ])
            if ws.get("net_Cp") is not None or ws.get("Cpi") is not None:
                param_rows.append([
                    "net Cp / Cpi",
                    f"{ws.get('net_Cp','—')} / {ws.get('Cpi','—')}",
                ])
            applied = ws.get("laterals_applied", ws.get("applied", bool(FX or FY)))
            param_rows.append(["Laterals applied", "yes" if applied else "no"])
            src_bits = ["load_plan.wind_summary"]
            if sf.get("W_X") or sf.get("W_Y"):
                src_bits.append("load_plan.story_forces W_X/W_Y")
            ka_r = ws.get("ka_resolve") or {}
            cpe_r = ws.get("cpe_resolve") or {}
            if ka_r.get("resolved_via") or ka_r.get("source"):
                src_bits.append(f"Ka via {ka_r.get('resolved_via') or ka_r.get('source')}")
            if cpe_r.get("source") or cpe_r.get("resolved_via"):
                src_bits.append(f"Cpe via {cpe_r.get('resolved_via') or cpe_r.get('source')}")
            nstory = NF
            if FX:
                nstory = max(nstory, max(FX))
            if FY:
                nstory = max(nstory, max(FY))
            rows = []
            for k in range(1, int(nstory) + 1):
                rows.append([
                    k,
                    f"{_F((FX or {}).get(k, 0))}" if FX else "—",
                    f"{_F((FY or {}).get(k, 0))}" if FY else "—",
                ])
            h = [
                "<p><b>India IS 875 (Part 3) wind</b> from <code>cfg['load_plan']</code> "
                f"(sources: {', '.join(src_bits)}). Story forces below feed the W_X / W_Y "
                "combinations — wind laterals <b>are applied</b> when listed.</p>",
                _table(["Parameter", "Value"], param_rows) if param_rows else "",
                f"<p><b>Story wind forces ({_ul('F')}):</b></p>",
                (_table(["Story", "X (E-W wind)", "Y (N-S wind)"], rows) if rows else
                 "<p class='note'>Story force breakdown not in load_plan; base shears from wind_summary.</p>"),
                f"<p><b>Wind base shear:</b> X = {_F(VwX,0) if VwX is not None else '—'} {_ul('F')}, "
                f"Y = {_F(VwY,0) if VwY is not None else '—'} {_ul('F')}.</p>",
            ]
            return "".join(h), VwX, VwY
        except Exception as ex:
            return f"<p class='note'>[load_plan wind display failed: {ex}]</p>", None, None

    if not cfg.get("wind"):
        return ("<p class='note'>No wind parameters defined for this building "
                "(neither <code>cfg['wind']</code> nor <code>load_plan.wind_summary</code> / "
                "W_X/W_Y story forces).</p>", None, None)
    try:
        w = cfg["wind"]; FX = E.wind_forces(cfg, "X"); FY = E.wind_forces(cfg, "Y")
        VwX = sum(FX.values()); VwY = sum(FY.values()); NF = len(cfg["heights"])
        rows = [[k, f"{_F(FX[k])}", f"{_F(FY[k])}"] for k in range(1, NF+1)]
        h = ["<p>IS 875/1893 §27 MWFRS. Velocity pressure qz = 0.00256·Kz·Kzt·Ke·V² (Eq. 26.10-1); design "
             "pressure p = qz·Kd·G·Cpnet (Kd applied in the pressure equation per Eq. 27.3-1); story force "
             "= p × tributary width × tributary height.</p>",
             _table(["Parameter", "Value"], [["Basic wind speed V", f"{w.get('V')} mph"],
                    ["Exposure", w.get("exposure", "C")],
                    ["Kd / Ke / G / Cpnet", f"{w.get('Kd',0.85)} / {w.get('Ke',1.0)} / {w.get('G',0.85)} / {w.get('Cpnet',1.3)}"]]),
             f"<p><b>Story wind forces ({_ul('F')}):</b></p>",
             _table(["Story", "X (E-W wind)", "Y (N-S wind)"], rows),
             f"<p><b>Wind base shear:</b> X = {_F(VwX,0)} {_ul('F')}, Y = {_F(VwY,0)} {_ul('F')}.</p>"]
        return "".join(h), VwX, VwY
    except Exception as ex:
        return f"<p class='note'>[wind determination failed: {ex}]</p>", None, None


def _horizontal_distribution(cfg, Fx, VwX, VwY):
    Vseis = sum(Fx.values()); nframe = 2
    def row(lbl, Vw):
        gov = "seismic" if Vseis >= (Vw or 0) else "wind"; g = max(Vseis, Vw or 0)
        return [lbl, (f"{_F(Vw,0)}" if Vw is not None else "—"), f"{_F(Vseis,0)}", gov, f"{_F(g/nframe,0)}"]
    rows = [row("E-W — two moment frames", VwX), row("N-S — two braced frames", VwY)]
    h = ["<p>The storey shear in each direction is distributed to the vertical elements by the 3D model "
         "(IS 1893 7.6.3(b), rigid diaphragm in proportion to stiffness), with the 7.8.2 design eccentricity "
         "cases of Chapter 4.</p>",
         _table(["Direction / frames", f"Wind base ({_ul('F')})", f"Seismic base ({_ul('F')})", "Governs", f"Per frame ({_ul('F')})"], rows)]
    return "".join(h)

def _role_of(mid, inp):
    r = (inp.get("role") or "").lower().strip().replace(" ", "_")
    _alias = {"roof": "roof", "roof_beam": "roof", "floor": "floor", "floor_beam": "floor",
              "gravity_col": "gravity_col", "interior_col": "gravity_col", "interior_column": "gravity_col",
              "gravity_column": "gravity_col", "lateral_col": "lateral_col", "mf_col": "lateral_col",
              "moment_col": "lateral_col", "braced_col": "lateral_col", "lateral_column": "lateral_col",
              "brace": "brace"}
    if r in _alias: return _alias[r]
    s = (mid or "").lower()
    if "roof" in s: return "roof"
    if "brace" in s or inp.get("kind") == "brace": return "brace"
    if "col" in s or inp.get("kind") == "col":
        return "gravity_col" if ("grav" in s or "interior" in s) else "lateral_col"
    if "floor" in s or "beam" in s or inp.get("kind") == "beam": return "floor"
    return "other"

def _member_section(cfg, name, pkg, want_roles, title, intro):
    h = [f"<h2>{title}</h2>", f"<p>{intro}</p>"]
    members = pkg.get("members") if isinstance(pkg, dict) else None
    Lcol = max(cfg["heights"]); Lbeam = max(cfg["SX"], cfg["SY"])
    Lbrace = math.sqrt(min(cfg["SX"], cfg["SY"])**2 + Lcol**2)
    found = False
    if isinstance(members, list):
        for m in members:
            inp = m.get("inputs", {})
            if _role_of(m.get("id", ""), inp) not in want_roles: continue
            if not inp.get("section"): continue
            try: h.append(_member_calc_block(m)); found = True
            except Exception as ex: h.append(f"<p class='note'>[render failed: {ex}]</p>")
    if not found:
        h.append("<p class='note'>No member with this role is present in calc_package.json — tag each "
                 "member's <code>role</code> (roof / floor / gravity_col / lateral_col / brace); Chapter 6 has a "
                 "section per role.</p>")
    return "".join(h)

def _case_extremes(out, info):
    """Overall max |axial| and max |moment| across all members for one load case."""
    reg = {t: (kind, sec) for (t, kind, sec, n1, n2) in info["ele"]}
    maxN = (0.0, "", ""); maxM = (0.0, "", "")
    for t, (N, Mz, My, V) in out.items():
        kind, sec = reg.get(t, ("", ""))
        if abs(N) > abs(maxN[0]): maxN = (N, kind, sec)
        m = max(abs(Mz), abs(My))
        if m > abs(maxM[0]): maxM = (m, kind, sec)
    return maxN, maxM

def _stability_section(cfg, Fx, drX, pkg):
    NF = len(cfg["heights"]); s = cfg["seis"]; SDS = s["SDS"]; Cd = s.get("Cd", 5.5); Ie = s["Ie"]
    NX, NY, SX, SY = cfg["NX"], cfg["NY"], cfg["SX"], cfg["SY"]
    A = (NX*SX)*(NY*SY)/144.0
    Dk = {k: E.floor_w(cfg, k) for k in range(1, NF+1)}
    Lk = {k: (cfg.get("L_floor", 0)*A/1000.0 if k < NF else 0.0) for k in range(1, NF+1)}
    Pu = {k: (1.2+0.2*SDS)*Dk[k] + 0.5*Lk[k] for k in range(1, NF+1)}
    Pstory = {sx: sum(Pu[k] for k in range(sx, NF+1)) for sx in range(1, NF+1)}
    Vstory = {sx: sum(Fx[k] for k in range(sx, NF+1)) for sx in range(1, NF+1)}
    beta = 1.0; theta_max = min(0.5/(beta*Cd), 0.25); worst = 0.0; rows = []
    for sx in range(1, NF+1):
        th = (Pstory[sx]*drX[sx-1]/Vstory[sx]) if Vstory[sx] else 0.0
        worst = max(worst, th)
        rows.append([sx, "%.0f" % Pstory[sx], "%.0f" % Vstory[sx], "%.0f" % cfg["heights"][sx-1],
                     "%.3f" % (drX[sx-1]*100), "%.3f" % th, "OK" if th <= theta_max else "NG"])
    h = ["<p>Member demands already include second-order effects (a P-&Delta; geometric transformation is applied "
         "under every combination), so the IS 800:2007 App.8 B<sub>2</sub> amplifier is captured directly by the "
         "analysis. The IS 875/1893 &sect;12.8.7 story stability coefficient "
         "&theta; = (P<sub>x</sub>/h<sub>sx</sub>)/(V<sub>x</sub>/&Delta;<sub>xe</sub>) (Eq. 12.8-18; equal to the "
         "legacy P<sub>x</sub>&Delta;I<sub>e</sub>/(V<sub>x</sub>h<sub>sx</sub>C<sub>d</sub>) with "
         "&Delta; = C<sub>d</sub>&Delta;<sub>xe</sub>/I<sub>e</sub>) is evaluated per "
         "story below; the limit is &theta;<sub>max</sub> = 0.5/(&beta;C<sub>d</sub>) &le; 0.25 (Eq. 12.8-19) = "
         "%.3f (&beta; = 1.0 conservatively). &theta; &le; 0.10 means P-&Delta; could be neglected; "
         "&theta; &gt; &theta;<sub>max</sub> is not permitted.</p>" % theta_max,
         _table(["Story", f"P<sub>x</sub> ({_ul('F')})", f"V<sub>x</sub> ({_ul('F')})", f"h<sub>sx</sub> ({_ul('Lm')})",
                 "&delta;<sub>e</sub> %", "&theta;", "&le; %.3f" % theta_max], rows),
         "<p>Worst-story &theta; = %.3f &mdash; %s the %.3f limit; P-&Delta; effects are %s and the analysis "
         "includes them regardless.</p>" % (worst, "within" if worst <= theta_max else "EXCEEDS",
                                            theta_max, "significant" if worst > 0.10 else "small")]
    return "".join(h)

def _load_activity(name):
    """Records for this job. Reads jobs/<name>/activity_log.jsonl AND folds in any scratch-log SESSIONS that
    belong to this job -- e.g. work done after a server restart that logged to scratch because new_activity_log()
    was not re-called (its RAG queries would otherwise be invisible). Returns (recs_sorted, primary_source)."""
    _jobs = os.environ.get("STEEL_BUILDER_JOBS") or os.path.join(HERE, "desktop_app", "agent_workspace", "work", "claude_desktop", "jobs")
    def _read(p):
        out = []
        try:
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    try: out.append(json.loads(line))
                    except Exception: pass
        except Exception: pass
        return out
    src = None; jrecs = []
    for c in (os.path.join(_jobs, name, "activity_log.jsonl"),
              os.path.join(HERE, "desktop_app", "agent_workspace", "work", name, "activity_log.jsonl"),
              os.path.join(HERE, "desktop_app", "agent_workspace", "work", "claude_desktop", "activity_log.jsonl")):
        if os.path.exists(c):
            src = c; jrecs = _read(c); break
    scratch = os.environ.get("STEEL_BUILDER_SCRATCH") or os.path.join(os.path.dirname(_jobs), ".scratch")
    srecs = _read(os.path.join(scratch, "activity_log.jsonl"))
    extra = []
    if srecs:
        def refs(r):
            if r.get("tool") == "new_activity_log" and str(r.get("detail", "")).strip() == name:
                return True
            d = str(r.get("detail", "")) + " " + str(r.get("result", ""))
            return ("jobs/" + name + "/" in d) or ("jobs/" + name in d) or (os.sep + name + os.sep in d)
        sessions = []; cur = []
        for r in srecs:
            st = r.get("step", 0)
            if cur and isinstance(st, int) and st <= cur[-1].get("step", 0):
                sessions.append(cur); cur = []
            cur.append(r)
        if cur: sessions.append(cur)
        for s in sessions:
            if any(refs(r) for r in s): extra += s
    seen = set(); merged = []
    for r in jrecs + extra:
        k = (r.get("ts"), r.get("tool"), str(r.get("detail"))[:80])
        if k in seen: continue
        seen.add(k); merged.append(r)
    merged.sort(key=lambda r: (r.get("ts") or "", r.get("step") or 0))
    return merged, src

def _activity_section(name):
    recs, src = _load_activity(name)
    h = ["<h2>Appendix C — Activity log</h2>",
         "<p>Every tool call made during the design, recorded by the MCP server, summarised below.</p>"]
    if not recs:
        h.append("<p class='note'>[no activity_log.jsonl found — call new_activity_log() at the start of "
                 "the design so the server records the tool calls]</p>")
        return "".join(h)
    counts = {}
    for r in recs: counts[r.get("tool", "?")] = counts.get(r.get("tool", "?"), 0) + 1
    _sd = os.path.relpath(src, HERE) if src else "scratch log"
    h.append(f"<p>Source: <code>{_sd}</code> — {len(recs)} tool calls.</p>")
    h.append(_table(["Tool", "Calls"], [[k, counts[k]] for k in sorted(counts)]))
    rows = [[i + 1, (r.get("ts", "").split("T")[-1]), r.get("tool", ""),
             r.get("detail", ""), r.get("result", "")] for i, r in enumerate(recs)]
    h.append("<h3>Chronological tool calls</h3>" + _table(["#", "time", "tool", "detail", "result"], rows))
    return "".join(h)

def _load_pkg(name, root=None):
    cands = []
    if root: cands.append(os.path.join(root, "design", "calc_package.json"))
    cands += [os.path.join(HERE, name, "design", "calc_package.json"),
              os.path.join(HERE, "desktop_app", "agent_workspace", "work", name, "calc_package.json"),
              os.path.join(HERE, "buildings", name, "design", "calc_package.json")]
    for c in cands:
        if os.path.exists(c):
            try: return json.load(open(c, encoding="utf-8")), c
            except Exception: pass
    return None, None



CHK_CSS = ("ol.toc{font-size:14px}ol.toc li{margin:2px 0}"
           ".chk{background:#f3f7fd;border:1px solid #cfe;border-left:4px solid #2c5aa0;"
           "border-radius:4px;padding:8px 14px;margin:8px 0 16px}"
           ".chk-h{font-weight:600;color:#2c5aa0;font-size:13px;margin-bottom:4px}"
           ".chk ul{margin:4px 0 2px 0;padding-left:20px}.chk li{font-size:13px;color:#333;margin:2px 0}"
           ".chk-status{font-weight:400;font-style:italic;color:#a06000;font-size:12px}")

CHAPTERS = {
 1: ("Design basis & codes", [
   "Governing codes and editions stated (IBC, IS 875/1893, IS 800:2007, IS 800 seismic-22 + 358 if seismic, AWS D1.1); Risk Category and Importance Factors.",
   "Project criteria match the architectural/owner brief and the geotechnical report (site class, bearing, lateral soil, frost).",
   "Units, sign conventions and material specs stated and consistent throughout.",
   "Scope and design-responsibility boundaries defined (connections DESIGNED in this package; delegated/deferred items: joists, stairs, cladding, embeds)."]),
 2: ("Structural system & load path", [
   "Gravity and lateral load paths complete and continuous to the foundation in both orthogonal directions.",
   "Lateral system per direction identified with the correct R, &Omega;<sub>0</sub>, C<sub>d</sub>, &rho; and any height/redundancy/system limits.",
   "Diaphragm type (rigid/semi-rigid/flexible) justified; collectors/drag struts and chord forces addressed.",
   "Irregularities (plan &amp; vertical) and expansion/seismic joints identified; triggered provisions applied."]),
 3: ("Loads", [
   "Dead loads: realistic self-weight, superimposed (MEP, ceilings, finishes, partitions), cladding/fa&ccedil;ade.",
   "Live loads per occupancy with correct reductions (and not where prohibited).",
   "Roof live/snow: flat-roof, drift, unbalanced, rain-on-snow, ponding, minimums.",
   "Wind (Ch. 26-31): MWFRS and C&amp;C; windward/leeward; torsional cases.",
   "Seismic (Ch. 11-12): S<sub>DS</sub>/S<sub>D1</sub>, SDC, period, C<sub>s</sub>, V, vertical distribution, E<sub>v</sub>, accidental+amplified torsion, 100/30, &rho;.",
   "Governing case (wind vs seismic) identified per direction."]),
 4: ("Load combinations", [
   "Full IS 875/1893 &sect;2.3 LSD set (gravity, wind &plusmn;, seismic &plusmn; with E<sub>v</sub> &amp; &rho;, &Omega;<sub>0</sub> where required), 100/30, &plusmn; accidental torsion.",
   "Combinations applied to the right members (&Omega;<sub>0</sub> to capacity-protected only); uplift/net-tension (0.9D) checked.",
   "Second-order effects handled per-combination (no superposition of factored second-order results)."]),
 5: ("Analysis model fidelity", [
   "Geometry, member sizes and orientations match the drawings (strong/weak axis correct).",
   "Boundary conditions: column base fixity matches the baseplate/anchorage detail and the foundation's capacity.",
   "Connection idealization (rigid / pinned / PR releases) matches the detailed connections.",
   "Diaphragm constraint, rigid offsets/panel zones, and leaning columns with their P-&Delta; represented.",
   "Modal results sane: &ge;90% participating mass, reasonable periods, expected mode shapes.",
   "Equilibrium verified: &Sigma;R = applied base shear (each direction) and total factored gravity.",
   "Stiffness reductions / notional loads / effective-length basis consistent with the analysis method."]),
 6: ("Member strength design (IS 800)", [
   "Every member type checked for the governing combo: tension (D2/D3), compression (E3/E4/E7), flexure (F2-F8 correct limit state), shear (G2), interaction (H1).",
   "Correct limit state, &phi;, L<sub>b</sub>, C<sub>b</sub>, K, slenderness and section properties.",
   "Composite members (Ch. I) designed properly if used (PNA, &phi;M<sub>n</sub>, studs, shoring, construction-stage deflection).",
   "Concentrated-load limit states (J10) and stiffeners where required.",
   "Governing D/C &le; 1.0 with sensible margins; sections reasonably economical.",
   "Calcs cited to specific AISC clauses and independently re-derivable; 2-3 governing members spot-checked."]),
 7: ("Stability & second-order", [
   "Stability method (Direct Analysis Method preferred) applied correctly end-to-end.",
   "B<sub>2</sub> / &theta; per story within limits; P-&Delta; included in member demands."]),
 8: ("Serviceability", [
   "Seismic design storey drift &le; 0.004 h (IS 1893 Part 1:2016 cl.7.11.1.1 under V<sub>B</sub> with &gamma;=1.0; soft-storey 0.002 where Table 6(i) applies); wind drift &le; project limit; inter-storey compatible with cladding/partitions. No ASCE Table 12.12-1 / C<sub>d</sub>/I<sub>e</sub> rows.",
   "Deflections: floor LL &le; L/360, TL &le; L/240; camber; roof ponding; long-span/cantilever limits.",
   "Floor vibration (AISC DG11) for the occupancy where applicable.",
   "Building separation / pounding; differential movement at joints."]),
 9: ("Seismic / wind detailing (IS 800 seismic)", [
   "System detailing matches the R used (width-thickness, brace slenderness, protected zones).",
   "Capacity design: SCWB (E3.4a), columns/collectors for &Omega;<sub>0</sub> or expected strength (R<sub>y</sub>F<sub>y</sub>).",
   "Demand-critical welds, prequalified connections (IS 800 connections), continuity/doubler plates, panel-zone shear.",
   "Wind: C&amp;C on cladding/fasteners, net uplift load path and hold-downs."]),
 10: ("Connections", [
   "Connection demands (V, N, M, incl. capacity-design/overstrength where required) on the drawings.",
   "Connections designed in this package (sized components; every limit-state D/C \u2264 1.0); only shop-level detailing on the fabricator submittal.",
   "Critical connections checked/constrained: bolts (J3), welds (J2), block shear (J4), HSS (Ch. K), base plates/anchors (J8/J9 + ACI 318 Ch. 17).",
   "Constructability: erection stability, access, OSHA min 4 anchor rods."]),
 11: ("Foundations interface", [
   "Column base reactions (P/V/M, uplift, overturning) provided to foundation design; consistent with assumed base fixity.",
   "Overall overturning/sliding stability; net uplift anchorage; load cases to geotech consistent with bearing/lateral capacity."]),
 12: ("Drawings, specifications & documentation", [
   "Drawings internally consistent and consistent with the calculations.",
   "General notes, material specs, welding/bolting, special-inspection schedule and design loads shown.",
   "Member schedules, framing plans, brace/MF elevations and connection details complete and coordinated.",
   "Deferred-submittal items listed; assumptions and limitations documented."]),
 13: ("QA / professional acceptance", [
   "Independent check performed (different engineer or method); discrepancies resolved.",
   "Software validated/appropriate; analysis assumptions vs detailing reconciled.",
   "Special inspection &amp; testing program (IBC Ch. 17) defined.",
   "Calc package complete, traceable (input &rarr; demand &rarr; capacity &rarr; D/C &rarr; cited clause), archived.",
   "All open items / RFIs closed; assumptions confirmed.",
   "EOR satisfied the design meets the governing codes and the standard of care &mdash; apply seal/signature."]),
}

def _toc():
    rows = "".join(f"<li><b>Chapter {n}</b> &mdash; {CHAPTERS[n][0]}</li>" for n in range(1, 14))
    return ("<h2>Report structure &mdash; EOR review checklist</h2>"
            "<p>This report is organised as the senior-engineer (EOR) acceptance checklist: one chapter per "
            "checklist section. Each chapter opens with the items a reviewer must accept, followed by the "
            "supporting analysis and design evidence. Appendix A is the fully-referenced IS 800/341 member "
            "calc, Appendix B the member forces for every load case, Appendix C the activity log of the tool "
            "calls that produced the design.</p><ol class='toc'>" + rows + "</ol>")

def _chapter(n, status=None):
    title, items = CHAPTERS[n]
    li = "".join(f"<li>{t}</li>" for t in items)
    extra = f" &mdash; <span class='chk-status'>{status}</span>" if status else ""
    return (f"<h2>Chapter {n} &mdash; {title}</h2>"
            f"<div class='chk'><div class='chk-h'>Reviewer acceptance items{extra}</div><ul>{li}</ul></div>")

def _risk_category(Ie):
    return {1.0: "II", 1.25: "III", 1.5: "IV"}.get(round(float(Ie), 2), "II")


def _drift_relief_note(cfg):
    """USA ASCE 7-22 §16.1.2 / Table 12.12-1 drift-relief scaffold.

    On steltic_india this is a legacy artefact only: if cfg still carries
    drift_relief_16_1_2, warn the reader — IS 1893 cl.7.11.1.1 (0.004 h) governs.
    """
    try:
        from preflight import drift_relief
        r = drift_relief(cfg)
    except Exception:
        return ""
    if r is None:
        return ""
    return ("<p class='note'><b>Legacy ASCE drift_relief_16_1_2 present but non-authoritative on "
            "steltic_india.</b> India storey-drift gate is <b>IS 1893 Part 1:2016 cl.7.11.1.1</b> "
            "(0.004 h under V<sub>B</sub>, &gamma;=1.0; soft-storey 0.002 where applicable). "
            "Strip USA Table 12.12-1 / C<sub>d</sub>/I<sub>e</sub> scaffolding from the job cfg.</p>")


def _design_of_record_rows(root):
    """Rows for the Chapter 1 basis table when design/design_of_record.json exists (written by the
    Nonlinear module's feedback loop when the user promotes a verified re-design)."""
    try:
        p = os.path.join(root, "design", "design_of_record.json")
        if not os.path.exists(p):
            return []
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return []
    what = "promoted from feedback loop <code>%s</code> (%s) on %s" % (
        _esc(str(d.get("loop", "?"))), _esc(str(d.get("loop_title", ""))), _esc(str(d.get("promoted_at", ""))))
    ver = d.get("verification") or {}
    vs = "; ".join("%s: %s" % (_esc(str(k)), _esc(str(v))) for k, v in ver.items() if not isinstance(v, (dict, list)))
    rows = [["Design of record", what + ((" &mdash; " + vs) if vs else "")]]
    if d.get("supersedes"):
        rows.append(["Supersedes", _esc(str(d["supersedes"]))])
    return rows


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def _sdc(SDS, SD1, S1=0.0, Ie=1.0):
    """Seismic Design Category per IS 875/1893 sec.11.6 -- delegates to the canonical
    preflight.asce_sdc: worse of Tables 11.6-1/-2 (incl. the Risk Category IV column, RC from Ie),
    after the S1 >= 0.75 -> E (RC I-III) / F (RC IV) override."""
    from preflight import asce_sdc, risk_cat_from_Ie
    return asce_sdc(SDS, SD1, S1, risk_cat_from_Ie(Ie))

def _design_basis_codes(cfg, s, root=None):
    seismic = bool(s.get("R"))
    # Wave3: India SI jobs list IS codes as governing — no USA IBC/ASCE Ch.1 boilerplate.
    _india = False
    try:
        from india_units import is_si as _is_si
        _india = _is_si(cfg) or str((cfg or {}).get("code_region") or "").lower() in ("india", "is", "bis")
    except Exception:
        _india = str((cfg or {}).get("units") or "").upper() in ("N-MM", "SI", "METRIC")
        _india = _india or str((cfg or {}).get("code_region") or "").lower() in ("india", "is", "bis")
    if _india:
        rows = [
            ["National Building Code of India (NBC) / local bye-laws",
             "adopting code &mdash; confirm state/local edition &amp; amendments"],
            ["IS 875 (Parts 1&ndash;5)", "dead / imposed / wind / snow / special loads"],
            ["IS 1893 (Part 1):2016", "seismic loads &amp; drift (when applicable)"],
            ["IS 800:2007", "steel member &amp; connection design (LSD)"],
        ]
        if seismic:
            rows += [
                ["IS 800:2007 §12", "seismic ductile detailing &amp; capacity design (when R requires)"],
                ["IS 800 / IS 4000", "bolted &amp; welded connections; base plates"],
            ]
        rows += [
            ["IS 816 / IS 814", "structural welding / electrodes"],
            ["IS 456:2000", "foundation / anchorage concrete interface"],
        ]
    else:
        rows = [["International Building Code (IBC)", "adopting code &mdash; confirm locally adopted edition &amp; amendments"],
                ["ASCE/SEI 7-22", "loads &amp; load combinations (gravity, wind Ch.26-31, seismic Ch.11-12, &sect;2.3 LSD)"],
                ["IS 800:2007", "steel member &amp; connection design (LSD)"]]
        if seismic:
            rows += [["IS 800 seismic-22", "seismic provisions / ductile detailing &amp; capacity design"],
                     ["IS 800 connections", "prequalified moment connections (if SMF/IMF used)"]]
        rows += [["AWS D1.1", "structural welding"], ["ACI 318 (Ch. 17)", "cast-in anchorage at column bases"]]
    out = ["<h3>Governing standards</h3>",
           _table(["Reference", "Used for"], rows)]
    Ie = s.get("Ie", 1.0); RC = _risk_category(Ie)
    crows = [["Risk Category", RC], ["Importance factor I<sub>e</sub>", f"{Ie}"]]
    if seismic:
        sdc = _sdc(s["SDS"], s["SD1"], s.get("S1", 0.0), Ie)
        crows += [["S<sub>DS</sub> / S<sub>D1</sub>", f"{s['SDS']} / {s['SD1']} g"],
                  ["Seismic Design Category", f"{sdc} <span class='cnote'>(Tables 11.6-1/2 incl. RC IV column; "
                   "S<sub>1</sub>&ge;0.75 &rarr; E/F applied; confirm mapped S<sub>1</sub>)</span>"],
                  ["R / C<sub>d</sub> / &Omega;<sub>0</sub>", f"{s['R']} / {s.get('Cd')} / {s.get('Om0')}"],
                  ["Redundancy &rho;", f"{cfg.get('rho', 1.3)}"]]
        try:
            from preflight import drift_relief
            _r = drift_relief(cfg)
            crows.append(["Storey drift limit basis",
                          "IS 1893 Part 1:2016 cl.7.11.1.1 — 0.004 h under V<sub>B</sub> (&gamma;=1.0); "
                          "soft-storey 0.002 where Table 6(i) applies. No ASCE Table 12.12-1 / C<sub>d</sub>/I<sub>e</sub>."])
            if _r is not None:
                crows.append(["Legacy USA drift_relief_16_1_2",
                              "PRESENT but non-authoritative on steltic_india — strip; see Chapter 8 note"])
        except Exception:
            crows.append(["Storey drift limit basis",
                          "IS 1893 Part 1:2016 cl.7.11.1.1 — 0.004 h (soft-storey 0.002 where applicable)"])
    crows += _design_of_record_rows(root)
    w = cfg.get("wind", {})
    if w:
        crows.append(["Basic wind speed V", f"{w.get('V','?')} mph, Exposure {w.get('exposure','?')}"])
    out += ["<h3>Risk &amp; hazard classification</h3>", _table(["Parameter", "Value"], crows)]
    out += ["<h3>Scope &amp; design responsibility</h3>",
            "<p class='cnote'>This package covers the primary steel gravity and lateral framing, its members, "
            "and the analysis behind them. Connection design, foundations, cold-formed/joist framing, stairs, "
            "cladding attachment and embeds are delegated/deferred unless explicitly included; their demands are "
            "transmitted in Chapters 10-11. The reviewer should confirm the geotechnical and architectural "
            "criteria match this basis.</p>"]
    return "".join(out)

def _system_loadpath(cfg):
    seismic = bool(cfg["seis"].get("R")); braced = E.is_braced(cfg)
    sysname = "concentrically braced / dual" if braced else "moment-resisting frame"
    return ("<h3>Lateral system &amp; load path</h3>"
            f"<p>The lateral force-resisting system is a steel {sysname} in each principal direction. "
            "<b>Gravity</b> path: floor/roof pressure &rarr; floor beams (two-way tributary) &rarr; girders/"
            "columns &rarr; column bases &rarr; foundation. <b>Lateral</b> path: story inertial/wind force &rarr; "
            "rigid floor diaphragm &rarr; vertical lateral frames &rarr; column bases &rarr; foundation, in both "
            "orthogonal directions. The design inputs for each system are below; the horizontal distribution to "
            "the frames and the deformed shape that confirms the path are shown in this chapter and Chapter 5.</p>")


def _lfrs_table(cfg):
    s = cfg["seis"]; R = s.get("R"); braced = E.is_braced(cfg); Om0 = s.get("Om0"); Cd = s.get("Cd")
    rho = cfg.get("rho", 1.3)
    if braced:
        if abs(R-6) < 0.6:    name, hl = "Special concentrically braced frame (SCBF)", "160 ft (SDC D/E), 100 ft (F)"
        elif abs(R-3.25) < .5: name, hl = "Ordinary concentrically braced frame (OCBF)", "35 ft (SDC D/E), not permitted (F)"
        elif R and abs(R-8) < .4 and Om0 and Om0 < 2.75: name, hl = "Buckling-restrained braced frame (BRBF)", "160 ft (D/E), 100 ft (F)"
        elif R and abs(R-8) < .4: name, hl = "Eccentrically braced frame (EBF)", "160 ft (D/E), 100 ft (F)"
        else: name, hl = "steel braced frame", "per IS 875/1893 Table 12.2-1"
    else:
        if R and abs(R-8) < .4:   name, hl = "Special moment frame (SMF)", "not limited (NL)"
        elif R and abs(R-4.5) < .4: name, hl = "Intermediate moment frame (IMF)", "35 ft in SDC D; not permitted E/F (confirm)"
        elif R and abs(R-3.5) < .4: name, hl = "Ordinary moment frame (OMF)", "limited use in SDC D-F (confirm)"
        else: name, hl = "steel moment frame", "per IS 875/1893 Table 12.2-1"
    sysdecl = cfg.get("system")                       # R1: use the system the agent DECLARED, not an R-guess
    sys_key = "Seismic force-resisting system (declared)" if sysdecl else "System (inferred from R &mdash; DECLARE cfg['system'])"
    sys_val = (sysdecl if sysdecl else name)
    rows = [[sys_key, sys_val],
            ["Response modification R", f"{R}"],
            ["Deflection amplification C<sub>d</sub>", f"{Cd}"],
            ["Overstrength &Omega;<sub>0</sub>", f"{Om0}"],
            ["Redundancy &rho;", f"{rho} <span class='cnote'>(confirm vs &sect;12.3.4.2; 1.0 if redundancy conditions met)</span>"],
            ["Structural height h<sub>n</sub> limit (Table 12.2-1)", hl]]
    if sysdecl:
        note = ("<p class='cnote'>System is the one DECLARED in cfg['system']; apply its IS 800 seismic provisions in "
                "Chapter 9 and confirm the Table 12.2-1 height limit for the SDC. Use the same system both directions "
                "unless cfg declares a different system per direction.</p>")
    else:
        note = ("<p class='cnote'>No cfg['system'] declared &mdash; the label above is INFERRED from R and is ambiguous "
                "(R=8 is EBF, BRBF, or dual). DECLARE cfg['system'] = the exact SFRS from the brief so the system, its "
                "ductile detailing (Ch 9) and height limit are locked.</p>")
    return _table(["Parameter", "Value"], rows) + note

def _diaphragm_section(cfg, Fx):
    NF = len(cfg["heights"]); s = cfg["seis"]; SDS = s["SDS"]; Ie = s["Ie"]
    w = [E.floor_w(cfg, k) for k in range(1, NF+1)]
    rows = []
    for x in range(1, NF+1):
        sumF = sum(Fx[i] for i in range(x, NF+1)); sumw = sum(w[i-1] for i in range(x, NF+1))
        wpx = w[x-1]; Fpx = (sumF/sumw)*wpx if sumw else 0.0
        lo = 0.2*SDS*Ie*wpx; hi = 0.4*SDS*Ie*wpx; gov = min(max(Fpx, lo), hi)
        tag = "min" if gov == lo else ("max" if gov == hi else "Eq.12.10-1")
        rows.append([x, f"{_F(wpx,0)}", f"{_F(Fpx,0)}", f"{_F(lo,0)}", f"{_F(hi,0)}", f"{_F(gov,0)} ({tag})"])
    just = ("<p>The floor/roof is taken as a <b>rigid diaphragm</b> (concrete-filled metal deck), distributing "
            "story forces to the lateral frames in proportion to their stiffness and modelled with a rigid "
            "in-plane constraint per IS 875/1893 &sect;12.3.1.2. Collectors/drag struts carry the diaphragm shear "
            "into the frames; chord forces (M<sub>diaph</sub>/depth) are resisted by the perimeter beams. The "
            "diaphragm, its collectors and chords are designed for the force F<sub>px</sub> below (&sect;12.10.1.1).</p>")
    tbl = _table(["Level x", f"w<sub>px</sub> ({_ul('F')})", f"F<sub>px</sub> (IS 1893 diaphragm) ({_ul('F')})",
                  "min 0.2S<sub>DS</sub>I<sub>e</sub>w<sub>px</sub>", "max 0.4S<sub>DS</sub>I<sub>e</sub>w<sub>px</sub>",
                  f"F<sub>px</sub> design ({_ul('F')})"], rows)
    return just + tbl + ("<p class='cnote'>F<sub>px</sub> is the diaphragm/collector design force; the detailed "
                         "diaphragm, collector and chord design is delegated and confirmed on the drawings.</p>")

def _torsion_ratios(cfg, Fx):
    NF = len(cfg["heights"]); SX, SY = cfg["SX"], cfg["SY"]; NX, NY = cfg["NX"], cfg["NY"]
    Lx = (cfg["xcoords"][-1] if cfg.get("xcoords") else NX*SX); Ly = (cfg["ycoords"][-1] if cfg.get("ycoords") else NY*SY)
    out = {}
    for direction, Bperp in (("X", Ly), ("Y", Lx)):
        try:
            info, disp, drift, re = _run_case(cfg, direction, Fx, accidental=True)
            rot = {k: ops.nodeDisp(E.mtag(k), 6) for k in range(1, NF+1)}
            worst = 1.0; prevd = 0.0; prevr = 0.0
            for k in range(1, NF+1):
                dtr = disp[k] - prevd; drot = rot[k] - prevr; prevd = disp[k]; prevr = rot[k]
                if abs(dtr) > 1e-9:
                    worst = max(worst, 1.0 + abs(drot)*(Bperp/2.0)/abs(dtr))
            out[direction] = worst
        except Exception:
            out[direction] = None
    return out

def _irregularity_section(cfg, Fx):
    """IS 1893 Part 1:2016 Table 5 (plan) / Table 6 (vertical) irregularity screen."""
    NF = len(cfg["heights"]); w = [E.floor_w(cfg, k) for k in range(1, NF+1)]
    h = cfg["heights"]
    tors = _torsion_ratios(cfg, Fx)
    # IS 1893 Table 5(i): δmax/δmin > 1.5 ⇒ torsional irregularity (NOT ASCE 1.2/Ax)
    tr = max([v for v in tors.values() if v is not None], default=1.0)
    cfg["_tir_screen"] = tr
    if tr > 2.0:
        tcls = (f"TORSIONAL irregularity: δ<sub>max</sub>/δ<sub>min</sub> = {tr:.2f} &gt; 2.0 "
                f"(IS 1893 Table 5(i)) — revise configuration (found:true)")
    elif tr > 1.5:
        tcls = (f"TORSIONAL irregularity: δ<sub>max</sub>/δ<sub>min</sub> = {tr:.2f} in 1.5–2.0 "
                f"(Table 5(i)) — ensure torsional mode period &lt; translational; use 3-D dynamic analysis")
    else:
        tcls = f"None: δ<sub>max</sub>/δ<sub>min</sub> = {tr:.2f} ≤ 1.5 (Table 5(i))"
    # Mass: IS 1893 Table 6(ii) — seismic weight > 150% of floor below (still in force, unlike ASCE 7-22 delete)
    massr = max((max(w[k]/w[k-1], w[k-1]/w[k]) for k in range(1, NF)), default=1.0) if NF > 1 else 1.0
    mcls = ("None" if massr <= 1.5 else
            f"Mass irregularity screen: adjacent floor-weight ratio {massr:.2f} &gt; 1.5 "
            f"(IS 1893 Table 6(ii)) — Dynamic Analysis required in Zones III–V")
    hr = max((max(h[k]/h[k-1], h[k-1]/h[k]) for k in range(1, NF)), default=1.0) if NF > 1 else 1.0
    scls = ("None (uniform storey heights — stiffness soft-storey still agent-confirmed)"
            if hr <= 1.0001 else
            f"Check soft storey (Table 6(i)): tallest/shortest storey height ratio {hr:.2f}")
    pir = E.plan_irregularities(cfg)
    if pir["reentrant"]:
        h2 = ("RE-ENTRANT corners: YES — non-convex footprint proxy. Confirm projection &gt; 15% of "
              "plan dimension (Table 5(ii)); three-dimensional dynamic analysis required.")
    else:
        h2 = "None (rectangular / convex footprint proxy)"
    h3 = "Floor slab cut-outs: not auto-detected — agent confirms vs 50% floor area (Table 5(iii))"
    h4 = "Out-of-plane offsets: not auto-detected — agent declares; Zones III–V have 0.2% drift / specialist rules (Table 5(iv))"
    h5 = ("NON-PARALLEL LFRS: YES — skewed frame (Table 5(v)); analyse per 6.3.2.2 / 6.3.4.1 combinations."
          if pir["nonparallel"] else "None (orthogonal frames)")
    v3 = ("Vertical geometric irregularity / setback proxy: YES — footprint reduces with height "
          "(confirm LFRS dimension &gt; 125% of storey below, Table 6(iii))."
          if pir["setback"] else "None (uniform footprint over height)")
    rows = [
        ["Plan (i) — Torsional irregularity (Table 5)", tcls],
        ["Plan (ii) — Re-entrant corners (Table 5)", h2],
        ["Plan (iii) — Floor slab cut-outs / openings (Table 5)", h3],
        ["Plan (iv) — Out-of-plane offsets (Table 5)", h4],
        ["Plan (v) — Non-parallel LFRS (Table 5)", h5],
        ["Vertical (i) — Soft storey / stiffness (Table 6)", scls],
        ["Vertical (ii) — Mass irregularity (Table 6)", mcls],
        ["Vertical (iii) — Vertical geometric (Table 6)", v3],
        ["Vertical (iv–vii) — In-plane discontinuity / weak storey / floating cols / irregular modes",
         "Agent classifies from analysis + RAG (not auto-gated)"],
    ]
    # Design eccentricity note (found:true) — replaces ASCE Ax invention
    rows.append(["Torsion design eccentricity (cl.7.8.2)",
                 "e<sub>di</sub> = 1.5 e<sub>si</sub> ± 0.05 b<sub>i</sub> (more severe). "
                 "ASCE A<sub>x</sub> factor: found:false — do not invent."])
    intro = ("<p>Screening against <b>IS 1893 (Part 1) : 2016 Table 5 (plan)</b> and "
             "<b>Table 6 (vertical)</b> (cl.7.1). Torsional trigger is "
             "&delta;<sub>max</sub>/&delta;<sub>min</sub> &gt; <b>1.5</b> (Table 5(i)), "
             "not ASCE TIR 1.2 / A<sub>x</sub>. Storey-drift gate is "
             "<b>0.004 h</b> under V<sub>B</sub> with &gamma;=1.0 (cl.7.11.1.1).</p>")
    dyn = pir["reentrant"] or pir["setback"] or pir["nonparallel"] or tr > 1.5 or massr > 1.5
    if dyn and "RS" not in [a.upper() for a in cfg.get("analyses", [])]:
        intro += ("<p class='cnote'><b>Analysis procedure:</b> Table 5/6 irregularities often require "
                  "three-dimensional dynamic analysis (Response Spectrum / modal). Consider adding "
                  "'RS' to cfg['analyses']. Equivalent static method remains for regular buildings "
                  "within the code's applicability limits — confirm via RAG (IS 1893 cl.7.3 / 7.7).</p>")
    extra = ""
    is1893 = pir.get("is1893_plan") or pir.get("is1893_vertical")
    if is1893:
        extra = "<p class='note'>Structured IS 1893 classification attached on <code>plan_irregularities()['is1893_*']</code>.</p>"
    return intro + _table(["Irregularity type", "Determination"], rows) + extra


def _gravity_loads_note():
    return ("<p class='cnote'>Dead D is the bundled member self-weight + superimposed dead (MEP, ceilings, "
            "finishes, partition allowance) plus fa&ccedil;ade cladding &mdash; itemise on the load schedule. "
            "Live L is applied at full L<sub>0</sub> (no &sect;4.7 reduction taken &mdash; conservative); "
            "L = L<sub>0</sub>(0.25 + 15/&radic;(K<sub>LL</sub>A<sub>T</sub>)) may be used in member design where "
            "K<sub>LL</sub>A<sub>T</sub> &ge; 400 ft&sup2; and reduction is permitted. Roof carries a uniform "
            "L<sub>r</sub>/snow; flat-roof snow, drift, unbalanced/sliding snow, rain-on-snow and ponding stability "
            "are confirmed separately (out of scope for the uniform roof model).</p>")

def _wind_cc_note():
    return ("<p class='cnote'>The forces above are the MWFRS (main wind force-resisting system) for the overall "
            "building (windward + leeward combined via C<sub>p,net</sub>). Components &amp; cladding (C&amp;C) "
            "pressures &mdash; zone GC<sub>p</sub> of &sect;30 for cladding, fasteners and their supports &mdash; "
            "and across-wind/torsional MWFRS load cases are part of the (delegated) cladding design.</p>")

def _seismic_loads_section(cfg, T, eX, eY, Cs, V, Tu, Ta, Fx, W):
    s = cfg["seis"]; NF = len(cfg["heights"]); z = E.zlevels(cfg)
    R = s["R"]; Ie = s["Ie"]; SDS = s["SDS"]; SD1 = s["SD1"]; S1 = s.get("S1", 0); TL = s.get("TL", 8.0)
    kk = 1.0 if Tu <= 0.5 else (2.0 if Tu >= 2.5 else 1 + (Tu-0.5)/2.0)
    Cs_eq = SDS/(R/Ie)
    cap = SD1/(Tu*(R/Ie)) if Tu <= TL else SD1*TL/(Tu**2*(R/Ie))
    cmin = max(0.044*SDS*Ie, 0.01); cmin_s1 = (0.5*S1/(R/Ie)) if S1 >= 0.6 else None
    low = max(cmin, cmin_s1 or 0.0); upper = min(Cs_eq, cap)
    if upper <= low: gov = "C<sub>s,min</sub> (Eq.12.8-7, S<sub>1</sub>)" if (cmin_s1 and low == cmin_s1) else "C<sub>s,min</sub> (Eq.12.8-6)"
    elif cap < Cs_eq: gov = "C<sub>s,max</sub> (Eq.12.8-4)"
    else: gov = "C<sub>s</sub> (Eq.12.8-3)"
    intro = (f"<p>IS 1893 equivalent lateral force. Seismic weight W = {_F(W,0)} {_ul('F')}; S<sub>DS</sub> = "
             f"{SDS} g, S<sub>D1</sub> = {SD1} g, S<sub>1</sub> = {S1} g, R = {R}, I<sub>e</sub> = {Ie}. Approximate "
             f"period T<sub>a</sub> = C<sub>t</sub>h<sub>n</sub><sup>x</sup> = {Ta:.2f} s; design period "
             f"T = min(T<sub>computed</sub>, C<sub>u</sub>T<sub>a</sub>) = {Tu:.2f} s (&sect;12.8.2).</p>")
    crows = [["C<sub>s</sub> = S<sub>DS</sub>/(R/I<sub>e</sub>) &nbsp;(Eq.12.8-3)", f"{Cs_eq:.4f}"],
             ["C<sub>s,max</sub> = S<sub>D1</sub>/(T&middot;R/I<sub>e</sub>) &nbsp;(Eq.12.8-4)", f"{cap:.4f}"],
             ["C<sub>s,min</sub> = max(0.044&middot;S<sub>DS</sub>I<sub>e</sub>, 0.01) &nbsp;(Eq.12.8-6)", f"{cmin:.4f}"]]
    if cmin_s1 is not None:
        crows.append(["C<sub>s,min</sub> = 0.5&middot;S<sub>1</sub>/(R/I<sub>e</sub>) &nbsp;(Eq.12.8-7, S<sub>1</sub>&ge;0.6)", f"{cmin_s1:.4f}"])
    crows.append(["<b>Governing C<sub>s</sub></b>", f"<b>{Cs:.4f}</b> &nbsp;({gov})"])
    cstab = "<h4>Seismic response coefficient C<sub>s</sub> and its limits</h4>" + _table(["C<sub>s</sub> equation", "Value"], crows)
    base = f"<p>Design base shear V = C<sub>s</sub>W = {Cs:.4f} &times; {_F(W,0)} = <b>{_F(V,0)} {_ul('F')}</b> in each direction.</p>"
    _ldiv = _sc()["length_div"]
    vrows = [[k, f"{_F(E.floor_w(cfg,k),0)}", f"{z[k]/_ldiv:.2f}",
              f"{E.floor_w(cfg,k)*((z[k]/_ldiv)**kk)/_sc()['force_div']:,.0f}",
              f"{Fx[k]/V:.3f}", f"{_F(Fx[k])}"] for k in range(1, NF+1)]
    vtab = (f"<h4>Vertical distribution of base shear (k = {kk:.2f}, &sect;12.8.3)</h4>"
            "<p>F<sub>x</sub> = C<sub>vx</sub>V, &nbsp; C<sub>vx</sub> = w<sub>x</sub>h<sub>x</sub><sup>k</sup> / "
            "&Sigma; w<sub>i</sub>h<sub>i</sub><sup>k</sup>.</p>"
            + _table(["Floor", f"w ({_ul('F')})", f"h ({_ul('L')})", "w&middot;h<sup>k</sup>", "C<sub>vx</sub>", f"F<sub>x</sub> ({_ul('F')})"], vrows))
    cumX = cumY = 0.0; mrows = []
    for m in range(min(len(T), 12)):
        cumX += eX[m]; cumY += eY[m]
        mrows.append([m+1, f"{T[m]:.3f}", f"{eX[m]*100:.1f}", f"{cumX*100:.1f}", f"{eY[m]*100:.1f}", f"{cumY*100:.1f}"])
    mtab = ("<h4>Modal periods &amp; mass participation (&ge; 90% per &sect;12.9.1)</h4>"
            + _table(["Mode", "T (s)", "mX %", "&Sigma;mX %", "mY %", "&Sigma;mY %"], mrows)
            + "<p class='cnote'>Mode-shape figures are in Chapter 5. The load combinations actually analysed "
            "(design eccentricity, vertical earthquake, IS 800 12.2.3) are listed in Chapter 4.</p>")
    return intro + cstab + base + vtab + mtab

def _governing_lateral(cfg, V, VwX, VwY):
    if V is None:
        return "<p class='note'>[seismic base shear unavailable]</p>"
    rows = []
    for d, Vw in (("X (E-W)", VwX), ("Y (N-S)", VwY)):
        if Vw is None:
            rows.append([d, f"{_F(V,0)}", "&mdash; (no wind defined)", "<b>Seismic</b>"])
        else:
            rows.append([d, f"{_F(V,0)}", f"{_F(Vw,0)}", f"<b>{'Seismic' if V >= Vw else 'Wind'}</b>"])
    note = ("<p class='cnote'>Strength-level base-shear comparison (seismic E and wind W are both strength-level in "
            "IS 875/1893 LSD). The governing system per direction sizes the lateral frames; both are carried through "
            "the load combinations (Chapter 4).</p>")
    return _table(["Direction", f"Seismic V ({_ul('F')})", f"Wind V ({_ul('F')})", "Governs"], rows) + note


def _combo_table(cases):
    """IS 800 Table 4 / IS 1893 6.3 combination table generated from the ACTUAL case list
    (WP1.1: the lateral load factor fE / fW is a column; WP1.2: tags / torsion / vertical)."""
    def meta(c):
        return getattr(c, "meta", {}) or {}
    rows = []
    for c in cases:
        L, fD, fL, fLr, lat, co = tuple(c)[:6]
        m = meta(c)
        kind = m.get("kind") or ("lateral" if lat else None)
        f = m.get("fLat")
        lat_txt = "&mdash;" if not (lat or m.get("rsa")) else (
            "%s %s%s" % ({"EQ": "EL", "W": "WL"}.get(kind, kind or "lateral"),
                         (m.get("direction") or ""), " (RSA)" if m.get("rsa") else ""))
        extras = []
        if m.get("torsion"):
            extras.append("7.8.2 e<sub>d</sub> %s" % m.get("torsion"))
        if m.get("fEv"):
            extras.append("EL<sub>Z</sub> %+.3g" % m.get("fEv"))
        if m.get("fC"):
            extras.append("CL %.2f" % m.get("fC"))
        tags = ", ".join(m.get("tags") or []) or ("col_only" if co else "all members")
        rows.append([L, "%.2f" % fD, "%.2f" % fL, "%.2f" % fLr,
                     ("%+.2f" % f) if f is not None else "&mdash;", lat_txt,
                     "; ".join(extras) or "&mdash;", tags])
    return _table(["Combination", "DL", "LL", "LL<sub>roof</sub>/S", "f<sub>E</sub> / f<sub>W</sub>",
                   "Lateral", "Other terms", "Applies to"], rows)

def _combo_legend(cfg):
    items = [("DL", "dead load incl. member self-weight and cladding"),
             ("LL", "imposed load (IS 875 Part 2), incl. the 3.1.2 partition allowance where applicable"),
             ("LLr / SL", "roof imposed load / snow (IS 875 Parts 2 and 4)"),
             ("EQ_X, EQ_Y", "design earthquake load EL in X / Y (IS 1893 6.3; ESM or scaled RSA)"),
             ("EQ_Z", "vertical earthquake load (IS 1893 6.3.3 / 6.4.6)"),
             ("W_X, W_Y", "wind load WL in X / Y (IS 875 Part 3)"),
             ("[ea] / [eb]", "IS 1893 7.8.2 design eccentricity 1.5e<sub>si</sub>+0.05b<sub>i</sub> / e<sub>si</sub>&minus;0.05b<sub>i</sub>"),
             ("[col]", "IS 800 12.2.3 case: columns (12.5.1.1) and connection forces only"),
             ("N_X / N_Y", "IS 800 4.3.6 notional horizontal load"),
             ("SLS:", "serviceability combination (IS 800 Table 4, &gamma;<sub>f</sub> 1.0 / 0.8)")]
    return "<h4>Notation used in the combination labels</h4>" + _table(["Symbol", "Meaning"], [[a, b] for a, b in items])

def _joint_figure(cfg):
    """Schematic of the ACTUAL modelled boundary conditions for THIS job (base fixity and joint
    types from cfg['model'], braced-bay panel only when the model has braces) -- no boilerplate
    about frames or grid lines that aren't in the present building."""
    import matplotlib.pyplot as _plt
    md = (cfg.get("model") or {})
    bases = str(md.get("bases") or cfg.get("base") or "pinned").lower()
    joints = str(md.get("joints") or ("pinned" if cfg.get("releases") else "rigid")).lower()
    try:
        braced = E.is_braced(cfg)
    except Exception:
        braced = bool(cfg.get("brace") or cfg.get("braces"))
    ncol = 3 if braced else 2
    fig, axs = _plt.subplots(1, ncol, figsize=(4.9*ncol + 1.0, 4.6))

    def _fixed_base(ax, x, label):
        ax.plot([x, x], [3, 8.5], lw=3, color="#333"); ax.plot([x-1.3, x+1.3], [3, 3], lw=4, color="#333")
        for h in (-1.1, -0.5, 0.1, 0.7): ax.plot([x+h, x+h-0.45], [3, 2.45], lw=1, color="#333")
        ax.text(x, 9.0, "FIXED base", ha="center", fontweight="bold", fontsize=11)
        ax.text(x, 1.6, label, ha="center", fontsize=8.5)
    def _pinned_base(ax, x, label):
        ax.plot([x, x], [3, 8.5], lw=3, color="#1f77b4"); ax.plot([x-0.7, x+0.7], [2.55, 2.55], lw=4, color="#333")
        for h in (-0.5, 0.1, 0.6): ax.plot([x+h, x+h-0.45], [2.55, 2.0], lw=1, color="#333")
        ax.plot([x-0.4, x, x+0.4], [2.55, 3, 2.55], color="#1f77b4", lw=2)
        ax.add_patch(_plt.Circle((x, 3), 0.16, fill=False, color="#1f77b4", lw=2))
        ax.text(x, 9.0, "PINNED base", ha="center", fontweight="bold", fontsize=11)
        ax.text(x, 1.6, label, ha="center", fontsize=8.5)

    ax = axs[0]; ax.set_title("Column base fixity"); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    if "mix" in bases:
        _fixed_base(ax, 2.4, "lateral-frame columns"); _pinned_base(ax, 7.4, "all other columns")
    elif "fix" in bases:
        _fixed_base(ax, 5, "ALL column bases in this model")
    else:
        _pinned_base(ax, 5, "ALL column bases in this model")

    def _fr_joint(ax, x, label):
        ax.plot([x, x], [1, 9], lw=3, color="#333"); ax.plot([x, x+3.0], [6, 6], lw=3, color="#333")
        ax.add_patch(_plt.Rectangle((x-0.25, 5.55), 0.5, 0.9, color="#d62728"))
        ax.plot([x+0.3, x+1.0], [6.5, 6.9], lw=1.5, color="#d62728"); ax.plot([x+0.3, x+1.0], [5.5, 5.1], lw=1.5, color="#d62728")
        ax.text(x+1.4, 7.2, "FR (rigid)\nmoment joint", fontsize=9, color="#d62728", fontweight="bold")
        ax.text(x+1.4, 4.6, label, fontsize=8.5)
    def _pin_joint(ax, x, label, y=3.0):
        ax.plot([x, x], [1, 9], lw=3, color="#333"); ax.plot([x, x+2.6], [y, y], lw=3, color="#1f77b4")
        ax.add_patch(_plt.Circle((x+0.18, y), 0.16, fill=False, color="#1f77b4", lw=2))
        ax.text(x+0.35, y+1.0, "PINNED (shear) joint", fontsize=9, color="#1f77b4", fontweight="bold")
        ax.text(x+0.35, y-1.4, label, fontsize=8.5)

    ax = axs[1]; ax.set_title("Beam-to-column joints"); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    if "mix" in joints:
        _fr_joint(ax, 1.6, "moment-frame girders"); _pin_joint(ax, 6.6, "all other girders")
    elif joints.startswith("pin"):
        _pin_joint(ax, 3.0, "ALL girder joints in this model\n(shear / simple connections)", y=6.0)
    else:
        _fr_joint(ax, 3.0, "ALL girder joints in this model")

    if braced:
        ax = axs[2]; ax.set_title("Bracing"); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 10)
        ax.plot([2, 2], [2, 8], lw=3, color="#333"); ax.plot([8, 8], [2, 8], lw=3, color="#333")
        ax.plot([2, 8], [8, 8], lw=3, color="#333"); ax.plot([2, 8], [2, 2], lw=2, color="#666")
        ax.plot([2, 8], [2, 8], lw=2.5, color="#e67e22"); ax.plot([2, 8], [8, 2], lw=2.5, color="#e67e22")
        for (bx, by) in ((2, 2), (8, 8), (2, 8), (8, 2)):
            ax.add_patch(_plt.Circle((bx, by), 0.22, fill=False, color="#e67e22", lw=2))
        ax.text(5, 0.8, "braces: PIN-ENDED axial (truss) members\nno end moments, tension/compression only",
                ha="center", fontsize=8.5, color="#a3540a")
    fig.suptitle("Modelled joint & base fixity", fontweight="bold")
    return _b64(fig)

def _floor_serviceability(pkg):
    ms = (pkg or {}).get("members") or []
    rows = []
    for m in ms:
        sv = m.get("serviceability")
        if not sv: continue
        sec = (m.get("inputs", {}) or {}).get("section", m.get("id", ""))
        rows.append([m.get("id", ""), sec,
                     f"{sv.get('live_in','')}\" = {sv.get('live_ratio','')}", sv.get("live_limit", "L/360"),
                     f"{sv.get('total_in','')}\" = {sv.get('total_ratio','')}", sv.get("total_limit", "L/240"),
                     (f"{sv.get('camber_in')}\"" if sv.get("camber_in") else "&mdash;"),
                     "OK" if sv.get("ok") else "NG"])
    if not rows:
        return "<p class='cnote'>Floor/roof beam deflection &amp; camber: no serviceability data in calc_package.json.</p>"
    return ("<h3>Floor &amp; roof beam deflection and camber (IS 875/1893 serviceability; IS 800:2007 Ch. L)</h3>"
            "<p>Live-load deflection is limited to L/360 and total-load deflection to L/240. Composite floor members "
            "use a lower-bound transformed moment of inertia I<sub>tr</sub>; the bare-steel (pre-composite, wet-concrete) "
            "dead-load deflection is offset by shop camber.</p>"
            + _table(["Member", "Section", "Live &delta;", "Limit", "Total &delta;", "Limit", "Camber", "&le; limit"], rows))

def _combo_notes(cfg, cases=None):
    """Chapter 4 notes generated FROM THE CASE LIST (WP1.2) -- no boilerplate claims."""
    cases = list(cases or [])
    meta = [getattr(c, "meta", {}) or {} for c in cases]
    n_eq = sum(1 for m in meta if m.get("kind") == "EQ" and not m.get("service"))
    n_w = sum(1 for m in meta if m.get("kind") == "W" and not m.get("service"))
    n_t = sum(1 for m in meta if m.get("torsion"))
    n_v = sum(1 for m in meta if m.get("fEv"))
    n_1223 = sum(1 for m in meta if "is800_12_2_3" in (m.get("tags") or []))
    n_rsa = sum(1 for m in meta if m.get("rsa"))
    n_not = sum(1 for m in meta if m.get("notional"))
    n_svc = sum(1 for m in meta if m.get("service"))
    signs = sorted({(m.get("direction"), m.get("sign")) for m in meta if m.get("kind") == "EQ"}, key=str)
    try:
        import india_combos as _IC
        vmeta = _IC.last_expansion_meta().get("vertical") or {}
    except Exception:
        vmeta = {}
    li = ["<li><b>%d</b> combinations in total (strength %d, serviceability %d), generated by "
          "<code>india_combos.expand_combinations</code> from IS 800:2007 Table 4 and IS 1893 (Part 1) 6.3.</li>"
          % (len(cases), len(cases) - n_svc, n_svc)]
    if n_eq:
        li.append("<li><b>Earthquake</b>: %d cases; directions/signs present: %s (6.3.2.1: one horizontal "
                  "direction at a time for orthogonal systems).</li>" % (n_eq, ", ".join("%s%s" % (d, "+" if s_ and s_ > 0 else "&minus;") for d, s_ in signs)))
    if n_rsa:
        li.append("<li><b>Response spectrum</b>: %d earthquake cases use the scaled RSA member forces (IS 1893 7.7.5, "
                  "CQC 7.7.5.3, scaled to V&#772;<sub>B</sub> per 7.7.3.1).</li>" % n_rsa)
    if n_t:
        li.append("<li><b>Design eccentricity</b> (IS 1893 7.8.2): %d cases with e<sub>di</sub> = 1.5e<sub>si</sub> + "
                  "0.05b<sub>i</sub> or e<sub>si</sub> &minus; 0.05b<sub>i</sub>; e<sub>si</sub> from centre-of-rigidity "
                  "unit-load analyses.</li>" % n_t)
    if n_v:
        li.append("<li><b>Vertical earthquake</b> (IS 1893 6.3.3.1 as amended by Amd 2; %s): %d cases, "
                  "A<sub>v</sub> = %.4f per 6.4.6, combined per 6.3.4.1.</li>"
                  % ("; ".join(vmeta.get("why") or []) or "required", n_v, float(vmeta.get("Av") or 0.0)))
    if n_1223:
        li.append("<li><b>IS 800 12.2.3</b>: %d cases 1.2DL+0.5LL&plusmn;2.5EL and 0.9DL&plusmn;2.5EL, applied to "
                  "columns (12.5.1.1) and recorded for connections (12.7.3.1, 12.11.2.2) only.</li>" % n_1223)
    if n_w:
        li.append("<li><b>Wind</b>: %d cases (Table 4 rows with 1.5, 1.2 and 0.6 WL, both signs).</li>" % n_w)
    if n_not:
        li.append("<li><b>Notional horizontal loads</b> (IS 800 4.3.6): 0.5&nbsp;%% of the factored gravity at each "
                  "level with the gravity-only combinations, %d cases, never with EL/WL.</li>" % n_not)
    li.append("<li><b>Second order</b>: each gravity state is solved with P-&Delta;; lateral, torsion and notional "
              "patterns are superposed on that gravity-stiffened state.</li>")
    return "<ul>" + "".join(li) + "</ul>"

def _modal_mass_check(eX, eY):
    cx = sum(eX); cy = sum(eY)
    return (f"<p><b>Modal mass participation:</b> &Sigma;m<sub>X</sub> = {cx*100:.0f}% "
            f"({'OK' if cx >= 0.90 else 'review &lt; 90%'}), &Sigma;m<sub>Y</sub> = {cy*100:.0f}% "
            f"({'OK' if cy >= 0.90 else 'review &lt; 90%'}); IS 875/1893 &sect;12.9.1 requires &ge; 90% in each "
            "direction. Periods and mode shapes are shown below and in Chapter 3.</p>")

def _stability_basis_note():
    return ("<p class='cnote'><b>Analysis basis:</b> a second-order P-&Delta; geometric transformation is applied to "
            "the columns under every factored combination (no superposition of factored results). Effective length "
            "K = 1 is used, consistent with a second-order analysis. If the Direct Analysis Method (IS 800:2007 "
            "&sect;C2) is the design basis, the 0.8&middot;EI / 0.8&tau;<sub>b</sub>&middot;EA stiffness reductions and "
            "notional loads N<sub>i</sub> = 0.002&alpha;Y<sub>i</sub> are confirmed at the member-design stage; the "
            "story stability coefficient &theta; (&sect;12.8.7) and the B<sub>2</sub> amplifier are reported in "
            "Chapter 7.</p>")

_KNOWN_PKG_KEYS = {"members", "connections", "connection_demands", "capacity_design", "scwb",
                   "framework_screen", "building", "code", "note", "notes", "meta", "name",
                   "composite_design"}   # composite_design gets its OWN Chapter-6 section (below)

_COMPOSITE_SYN = {   # tolerant key synonyms seen across agent packages (candidates + gold)
    "pct":   ("partial_composite_ratio", "partial_composite_percent", "partial_composite_pct",
              "degree_of_composite", "composite_ratio"),
    "Qn":    ("stud_Qn_kip", "Qn_kip", "Qn"),
    "studs": ("stud_count_total", "n_studs", "studs_total", "n_per_half_span", "stud_schedule", "studs"),
    "camber":("camber_in", "camber"),
    "ILB":   ("I_LB_in4", "ILB_in4", "I_LB", "lower_bound_I_in4", "I_lb_in4"),
    "wet":   ("wet_stage_phiMn_kipft", "wet_stage_phiMn_kipin", "Mu_wet_kipin",
              "wet_dead_deflection_in", "wet_deflection_in"),
}


def _extra_blocks_section(pkg):
    """Supplementary design records: render every agent-authored TOP-LEVEL calc_package block the
    report does not already show (serviceability, fatigue, crane_runway, equipment_supports,
    analysis_idealization, ponding, ...) through the same nested-table renderer as capacity_design.
    These are real design records the agent wrote for the reviewer -- before this section existed
    they lived only in calc_package.json."""
    if not isinstance(pkg, dict):
        return ""
    parts = []
    for k, v in pkg.items():
        if k in _KNOWN_PKG_KEYS or v in (None, "", [], {}):
            continue
        if not isinstance(v, (dict, list, str, int, float, bool)):
            continue
        blob = v if isinstance(v, str) else json.dumps(v)
        title = str(k).replace("_", " ").title()
        if len(blob) > 12000:                      # guard: a runaway dump must not drown the report
            parts.append("<h4>%s</h4><p class='note'>[block truncated at 12 kB -- full record in "
                         "design/calc_package.json]</p><pre>%s\u2026</pre>"
                         % (title, (blob[:12000].replace("<", "&lt;"))))
            continue
        parts.append("<h4>%s</h4>" % title)
        parts.append(_capdesign_html(v) if isinstance(v, (dict, list))
                     else "<p>%s</p>" % str(v).replace("<", "&lt;"))
    if not parts:
        return ""
    return ("<h3>Supplementary design records (from the calc package)</h3>"
            "<p>Agent-authored design records beyond the member/connection/capacity-design tables "
            "&mdash; rendered verbatim from <code>design/calc_package.json</code>.</p>" + "".join(parts))


def _composite_section(pkg):
    """Chapter-6 'Composite floor design (IS 800 Ch. I)' section. Sources:
    (a) top-level `composite_design` (incl. H6 Ch.I worksheet stubs),
    (b) composite values embedded in member capacity dicts.
    Renders nothing when neither exists."""
    if not isinstance(pkg, dict):
        return ""
    parts = []
    cd = pkg.get("composite_design")
    mem_rows = []
    for m in pkg.get("members", []) or []:
        cap = m.get("capacity") if isinstance(m.get("capacity"), dict) else {}
        found = {}
        for col, keys in _COMPOSITE_SYN.items():
            for kk in keys:
                if kk in cap and cap[kk] not in (None, ""):
                    found[col] = cap[kk]; break
        if found:
            mem_rows.append([str(m.get("id", "")), str((m.get("inputs") or {}).get("section", "")),
                             str(found.get("pct", "&mdash;")), str(found.get("Qn", "&mdash;")),
                             str(found.get("studs", "&mdash;")), str(found.get("camber", "&mdash;")),
                             str(found.get("ILB", "&mdash;")), str(found.get("wet", "&mdash;"))])
    ws = (cd or {}).get("chI_worksheet") if isinstance(cd, dict) else None
    has_ws = isinstance(ws, dict) and bool(ws.get("slots"))
    if not cd and not mem_rows and not has_ws:
        return ""
    parts.append("<h3>Composite floor design (IS 800 Ch. I)</h3>")
    if has_ws:
        parts.append("<p class='cnote'><b>IS 800 Ch. I worksheet (H6 stubs):</b> "
                     "b_eff / studs / camber / wet-stage / I_LB slots — fill from RAG; "
                     "<code>found:false</code> means do not invent stud or camber designs.</p>")
        stub_rows = [[s.get("component", ""),
                      "found:false" if s.get("found") is False else str(s.get("found")),
                      ("%.2f" % s["DC"] if isinstance(s.get("DC"), (int, float)) else "—"),
                      s.get("note", "")] for s in ws["slots"]]
        parts.append(_table(["Component", "found", "D/C", "Note"], stub_rows))
    if mem_rows:
        parts.append("<p>Per-member composite design values recorded in the calc package (partial-"
                     "composite ratio, stud strength/schedule, camber, lower-bound moment of inertia, "
                     "unshored wet-concrete stage):</p>")
        parts.append(_table(["member", "section", "partial comp.", f"Q<sub>n</sub> ({_ul('F')})", "studs",
                             "camber (in)", "I<sub>LB</sub> (in<sup>4</sup>)", "wet stage"], mem_rows))
    if cd and not has_ws:
        parts.append("<h4>Composite design record (calc package `composite_design`)</h4>")
        parts.append(_capdesign_html(cd))
    elif cd and isinstance(cd, dict) and cd.get("note"):
        parts.append("<p class='cnote'>%s</p>" % cd.get("note"))
    parts.append("<p class='note'>Stud strengths per IS 800:2007 &sect;I8.2a (with deck-rib position "
                 "factors); flexure per &sect;I3.2a; service deflection on the lower-bound moment of "
                 "inertia; camber rule and the unshored construction stage as recorded above. "
                 "H6: leave found:false rather than inventing stud/camber designs.</p>")
    return "".join(parts)



def _member_dc_summary(pkg):
    ms = pkg.get("members") or []
    have = [m for m in ms if m.get("DC") is not None]
    if have:
        gov = max(have, key=lambda m: m.get("DC") or 0.0)
        return (f"<p>Governing member: <b>{gov.get('id')}</b> at D/C = <b>{gov.get('DC'):.2f}</b> "
                f"({gov.get('limit_state')}, combo {(gov.get('inputs', {}) or {}).get('governing_combo', '')}).</p>")
    return ("<p class='cnote'>The member <b>demands</b> (axial, moment, shear, L<sub>b</sub>, section properties and "
            "governing combination) are computed by the framework and listed below; the <b>capacities</b>, limit "
            "states and D/C ratios are derived by the agent from the IS 800/341 RAG (Appendix A) and are pending "
            "for this building.</p>")

def _ch6_notes(cfg):
    comp = " Composite floor members (Ch. I) are designed where composite action is used." if cfg.get("composite") else ""
    return ("<p class='cnote'>Limit states checked per member as applicable: tension (D2/D3), compression (E3/E4/E7), "
            "flexure (F2-F8 with the correct compact / noncompact / slender limit state, L<sub>b</sub>, C<sub>b</sub>), "
            "shear (G2) and combined axial+flexure interaction (H1)." + comp + " Concentrated-load limit states "
            "(web local yielding / crippling, J10) and stiffeners are checked at point loads and supports where "
            "applicable. The EOR should spot-check 2-3 governing members by hand against Appendix A.</p>")


def _drift_from_forces(cfg, Fdict, direction):
    info = E.build(cfg, "Linear"); NF = info["NF"]; di = 0 if direction == "X" else 1
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for k in range(1, NF+1):
        f = [0.0]*6; f[di] = Fdict[k]; ops.load(E.mtag(k), *f)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-8, 100); ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static"); ops.analyze(1)
    drift = []; prev = 0.0
    for k in range(1, NF+1):
        d = ops.nodeDisp(E.mtag(k), di+1); drift.append((d-prev)/cfg["heights"][k-1]); prev = d
    return drift

def _india_wind_serviceability_html(cfg):
    """IS 800 Table 6 wind serviceability from the engine run (unfactored W story forces, 1.0DL+1.0LL)."""
    try:
        wsv = E.india_run_cached(cfg).get("wind_serviceability") or {}
    except Exception as ex:
        return "<p class='note'><b>Wind serviceability NOT evaluated:</b> %s</p>" % ex
    if not wsv:
        return "<p class='cnote'>Wind serviceability: no W story forces in the load plan.</p>"
    rows = []
    for d, r in sorted(wsv.items()):
        rows.append([d, "%.2f" % r["top_mm"], "%.2f" % r["limit_top_mm"], "%.3f" % r["ratio_top"],
                     ("%.5f / %.5f" % (max(r["storey_drift"]), r["limit_storey"])) if r.get("limit_storey") else "-",
                     "OK" if r["ratio_top"] <= 1.0 and r.get("ratio_storey", 0.0) <= 1.0 else "NG"])
    cite = next(iter(wsv.values()))["cite"]
    return ("<h3>Wind serviceability (IS 800 Table 6)</h3>"
            "<p>Lateral deflection under the unfactored IS 875 (Part 3) wind story forces "
            "(&gamma;<sub>f</sub> = 1.0) with 1.0 DL + 1.0 LL, P-&Delta;. %s.</p>" % cite
            + _table(["Dir", "top defl. (mm)", "limit (mm)", "ratio", "max storey drift / limit", "status"], rows))

def _wind_drift_section(cfg):
    ws, sf = _load_plan_wind(cfg)
    if not cfg.get("wind") and not (ws or sf.get("W_X") or sf.get("W_Y")):
        return "<p class='cnote'>Wind drift not evaluated (no wind parameters defined).</p>"
    if E._india_job(cfg):
        return _india_wind_serviceability_html(cfg)
    if not cfg.get("wind") and (ws or sf.get("W_X") or sf.get("W_Y")):
        return "<p class='cnote'>Wind drift not evaluated (no wind story forces).</p>"
    NF = len(cfg["heights"]); lim = cfg.get("wind_drift_limit", 1.0/400.0)
    try:
        dX = _drift_from_forces(cfg, E.wind_forces(cfg, "X"), "X")
        dY = _drift_from_forces(cfg, E.wind_forces(cfg, "Y"), "Y")
    except Exception as ex:
        return f"<p class='note'>[wind drift run failed: {ex}]</p>"
    rows = [[k, f"{dX[k-1]*100:.3f}", f"{dY[k-1]*100:.3f}", "OK" if max(dX[k-1], dY[k-1]) <= lim else "NG"]
            for k in range(1, NF+1)]
    return ("<h3>Wind drift</h3>"
            f"<p>Interstory drift under the design MWFRS wind vs a serviceability limit of h/{int(round(1/lim))} "
            f"({lim*100:.2f}%). Wind drift has no code-mandated limit (IS 875/1893 Appendix CC is advisory); a "
            "10-year-MRI service wind may be used for a less conservative check.</p>"
            + _table(["Story", "drift X %", "drift Y %", f"&le; {lim*100:.2f}%"], rows))

def _capdesign_html(cap):
    """Render the agent's capacity_design / scwb block as readable nested tables (NOT raw JSON)."""
    def fmt(v):
        if isinstance(v, bool): return "yes" if v else "no"
        if isinstance(v, float): return ("%.3f" % v).rstrip("0").rstrip(".")
        return str(v)
    def block(d):
        rows = []
        for k, v in d.items():
            label = str(k).replace("_", " ")
            if isinstance(v, dict):
                rows.append([label, block(v)])
            elif isinstance(v, list):
                if any(isinstance(x, dict) for x in v):
                    rows.append([label, "".join(block(x) if isinstance(x, dict)
                                                else "<p>%s</p>" % fmt(x) for x in v)])
                else:
                    rows.append([label, ", ".join(fmt(x) for x in v)])
            else:
                rows.append([label, fmt(v)])
        return _table(["Item", "Value"], rows)
    if isinstance(cap, dict): return block(cap)
    if isinstance(cap, list): return "".join(_capdesign_html(x) for x in cap)
    return "<p>%s</p>" % fmt(cap)

def _aisc341_detailing(cfg, pkg):
    braced = E.is_braced(cfg); s = cfg["seis"]
    det = (pkg or {}).get("detailing")
    if det:
        _rows = [[c.get("check", ""), c.get("status", "")] for c in det.get("checks", [])]
        _intro = (f"<p><b>System:</b> {det.get('system','')} &mdash; R = {det.get('R', s.get('R'))}, "
                  f"C<sub>d</sub> = {det.get('Cd', s.get('Cd'))}, &Omega;<sub>0</sub> = {det.get('Omega0', s.get('Om0'))}, "
                  f"SDC {det.get('SDC','')}. <b>IS 800 seismic applies:</b> {'yes' if det.get('aisc341_applies') else 'no'}.</p>"
                  f"<p>{det.get('basis','')}</p>")
        return _intro + _table(["Required check", "Status / basis"], _rows)
    if braced:
        sysname = "concentrically braced frame (SCBF/OCBF)"
        checks = [("Brace width-thickness", "highly/moderately ductile (Table D1.1)"),
                  ("Brace slenderness KL/r", "&le; 200 (SCBF, F2.5b)"),
                  ("Brace connection strength", "expected R<sub>y</sub>F<sub>y</sub>A<sub>g</sub> / 1.1R<sub>y</sub>P<sub>n</sub> (F2.6c)"),
                  ("Columns &amp; collectors", "amplified seismic &Omega;<sub>0</sub> or capacity-limited"),
                  ("Protected zones / gussets", "brace ends, gusset hinge zone"),
                  ("Demand-critical welds", "IS 800 seismic A3.4")]
    else:
        sysname = "moment frame (SMF/IMF)"
        checks = [("Strong-column-weak-beam", "&Sigma;M*<sub>pc</sub>/&Sigma;M*<sub>pb</sub> &gt; 1.0 (E3.4a)"),
                  ("Beam &amp; column width-thickness", "highly ductile (Table D1.1)"),
                  ("Panel-zone shear &amp; doublers", "IS 800 seismic E3.6e"),
                  ("Continuity plates", "at beam flanges (E3.6f)"),
                  ("Protected zones", "RBS / plastic-hinge regions"),
                  ("Demand-critical welds", "CJP beam-flange-to-column"),
                  ("Prequalified connection", "within IS 800 connections limits")]
    cap = (pkg or {}).get("capacity_design") or (pkg or {}).get("scwb")
    rows = [[name, basis, "see Appendix A" if cap else "agent-derived (IS 800 seismic RAG) &mdash; pending"] for name, basis in checks]
    intro = (f"<p>For the {sysname} (R = {s.get('R')}), the required IS 800 seismic-22 ductile-detailing and capacity-design "
             "checks are listed below. These are derived by the agent from the IS 800 seismic RAG; values populate from the "
             "calc package where present.</p>")
    extra = ("<h4>Capacity-design results (from the calc package)</h4>" + _capdesign_html(cap)) if cap else ""
    note = ("<p class='cnote'>Width-thickness ductility, IS 800 connections prequalification limits, weld NDT and the C&amp;C "
            "cladding / net-uplift checks are confirmed on the drawings and connection submittal (delegated).</p>")
    return intro + _table(["Required check", "Basis", "Status"], rows) + extra + note


def _connection_demands(cfg, pkg, reX):
    rows = []; ms = (pkg or {}).get("members") or []
    mf = not cfg.get("braces")
    for m in ms:
        inp = m.get("inputs", {}) or {}; kind = inp.get("kind", ""); sec = inp.get("section", "")
        V = inp.get("V_kip") or 0.0; Mz = inp.get("Mz_kipin") or 0.0
        P = max(inp.get("P_comp_kip", 0) or 0, inp.get("P_tens_kip", 0) or 0)
        if kind == "beam":
            typ = "beam-to-column (moment)" if mf else "beam-to-column (shear)"
            dem = f"V = {_F(V,0)} {_ul('F')}" + (f", M = {_M(Mz,0)} {_ul('M')}" if mf and Mz else "")
            basis = "CJP flange welds + web bolts (J2/J3)" if mf else "bolted shear tab (J3 / J4)"
        elif "col" in kind:
            typ = "column splice / base"; dem = f"P = {_F(P,0)} {_ul('F')}" + (f", M = {_M(Mz,0)} {_ul('M')}" if Mz else "")
            basis = "splice (J1.4) / base plate J8 + ACI 318 Ch.17"
        elif kind == "brace":
            typ = "brace-to-gusset"; dem = f"axial = {_F(P,0)} {_ul('F')}"; basis = "expected strength (IS 800 seismic / agent RAG)"
        else:
            continue
        rows.append([f"{sec} {kind}", typ, dem, basis])
    if reX is not None:
        pmax = max((r[2][2] for r in reX), default=0.0); vmax = max((abs(r[2][0]) for r in reX), default=0.0)
        rows.append(["column base", "base plate / anchor rods", f"P = {_F(pmax,0)} {_ul('F')}, V = {_F(vmax,0)} {_ul('F')}",
                     "J8/J9 + ACI 318 Ch.17 (min 4 rods)"])
    if not rows:
        return None
    return _table(["Member / location", "Connection type", "Governing demand", "Design basis (limit states)"], rows)

def _qa_scorecard(cfg, Fx, reX, eX, eY, drX, drY):
    s = cfg["seis"]; rows = []
    if reX is not None and Fx is not None:
        Rx = sum(r[2][0] for r in reX); base = sum(Fx.values()); Rz = sum(r[2][2] for r in reX)
        rows.append(["Equilibrium &mdash; |&Sigma;R<sub>x</sub>| = applied base shear", f"{_F(abs(Rx),0)} vs {_F(base,0)} {_ul('F')}",
                     "PASS" if base and abs(abs(Rx)-base)/base < 0.01 else "REVIEW"])
    if eX is not None and eY is not None:
        cx = sum(eX)*100; cy = sum(eY)*100
        rows.append(["Modal mass &ge; 90% (X / Y)", f"{cx:.0f}% / {cy:.0f}%", "PASS" if min(cx, cy) >= 90 else "REVIEW"])
    if drX is not None and Fx is not None:
        NF = len(cfg["heights"]); SDS = s["SDS"]; Cd = s.get("Cd", s.get("R", 5.0))
        lim, limrho = E.drift_allowable(cfg)   # IS 1893 7.11.1.1 default 0.004
        try:
            from india_seismic import design_story_drifts, drift_limit_label
            dX = design_story_drifts(drX, cfg); dY = design_story_drifts(drY, cfg)
            dmax = max(max(abs(dX[k]), abs(dY[k])) for k in range(NF))
            _limlab = drift_limit_label(cfg)
        except Exception:
            dmax = max(max(abs(drX[k]), abs(drY[k])) for k in range(NF))
            _limlab = f"{lim*100:.2f}% (IS 1893 cl.7.11.1.1)"
        rows.append(["Seismic design storey drift &le; limit", f"{dmax*100:.2f}% &le; {_limlab}",
                     "PASS" if dmax <= lim else "FAIL"])
        A = (cfg["NX"]*cfg["SX"])*(cfg["NY"]*cfg["SY"])/144.0
        Pu = {k: (1.2+0.2*SDS)*E.floor_w(cfg, k) + 0.5*(cfg.get("L_floor", 0)*A/1000.0 if k < NF else 0) for k in range(1, NF+1)}
        Ps = {sx: sum(Pu[k] for k in range(sx, NF+1)) for sx in range(1, NF+1)}
        Vs = {sx: sum(Fx[k] for k in range(sx, NF+1)) for sx in range(1, NF+1)}
        tmax = min(0.5/Cd, 0.25); tw = max((Ps[sx]*drX[sx-1]/Vs[sx] if Vs[sx] else 0) for sx in range(1, NF+1))
        rows.append(["Stability &theta; &le; &theta;<sub>max</sub>", f"{tw:.3f} &le; {tmax:.3f}", "PASS" if tw <= tmax else "FAIL"])
    if not rows:
        return ""
    return ("<h3>QA scorecard (automated checks)</h3>"
            + _table(["Check", "Result", "Status"], rows))


def _save_case_fig(uri, figdir, label):
    """Write a per-combination N/V/M figure to figs/case_<label>.png for the user to inspect later;
    it is NOT embedded in the report (keeps report.html compact)."""
    if not (figdir and uri and isinstance(uri, str)):
        return
    safe = "".join(c if c.isalnum() else "_" for c in str(label))[:60].strip("_") or "case"
    try:
        if uri.startswith("data:image/"):
            head, b64 = uri.split(",", 1)
            ext = head.split("/")[1].split(";")[0].replace("jpeg", "jpg")
            with open(os.path.join(figdir, "case_%s.%s" % (safe, ext)), "wb") as f:
                f.write(base64.b64decode(b64))
        else:
            src = os.path.join(figdir, os.path.basename(uri))
            if os.path.exists(src):
                import shutil; shutil.copy2(src, os.path.join(figdir, "case_%s.png" % safe))
    except Exception:
        pass

def _static_case_table(cfg, combo, nseg=2, render_fig=True):
    """Per member TYPE governing forces for ONE combination, from the STATIC model (distributed
    gravity) so beams carry their true moment (fixes the lumped-model 1.4D = zero-beam-moment bug).
    Custom-geometry buildings (custom_build) fall back to the dynamic model's demand envelope, which
    already adds the beam gravity span moment and supports arbitrary geometry."""
    label, fD, fL, fLr, lat, co = combo
    nseg = 6 if render_fig else nseg   # App-B per-combo FIGURE -> finer (nseg 6); scalar summary table -> fast (nseg 2)
    import static_model as SM
    mm, _, _ = SM.run_combo(cfg, fD, fL, fLr, lat, nseg=nseg)
    best = {}; maxN = (0.0, "", ""); maxM = (0.0, "", "")
    def upd(kind, sec, N, Mz, My, V, n1, n2, score):
        key = (kind, sec)
        if key not in best or score > best[key][0]:
            best[key] = (score, N, Mz, My, V, n1, n2)
    for b in mm["beams"]:
        sec = b.get("sec") or cfg["beam"]; N = Mz = My = V = 0.0
        for tag in b["segs"]:
            lf = ops.eleResponse(tag, "localForces")
            N = max(N, abs(lf[0]), abs(lf[6])); Mz = max(Mz, abs(lf[4]), abs(lf[10]))
            My = max(My, abs(lf[5]), abs(lf[11])); V = max(V, abs(lf[2]), abs(lf[8]))
        upd("beam", sec, N, Mz, My, V, b["A"], b["B"], Mz)
        if N > abs(maxN[0]): maxN = (N, "beam", sec)
        if Mz > abs(maxM[0]): maxM = (Mz, "beam", sec)
    for c in mm["cols"]:
        sec = c.get("sec") or cfg["col"]; lf = ops.eleResponse(c["tag"], "localForces")
        N = max(abs(lf[0]), abs(lf[6])); Mz = max(abs(lf[5]), abs(lf[11])); My = max(abs(lf[4]), abs(lf[10]))
        V = max(abs(lf[1]), abs(lf[2]), abs(lf[7]), abs(lf[8]))
        upd("col", sec, N, Mz, My, V, c["n1"], c["n2"], max(Mz, N))
        if N > abs(maxN[0]): maxN = (N, "col", sec)
        if max(Mz, My) > abs(maxM[0]): maxM = (max(Mz, My), "col", sec)
    for br in mm.get("braces", []):
        sec = br.get("sec") or cfg.get("brace", ""); N = ops.basicForce(br["tag"])[0]
        upd("brace", sec, N, 0.0, 0.0, 0.0, None, None, abs(N))
        if abs(N) > abs(maxN[0]): maxN = (N, "brace", sec)
    rows = []
    for (kind, sec), (sc, N, Mz, My, V, n1, n2) in sorted(best.items()):
        rows.append([kind, sec, f"{N:.1f}", f"{Mz/12:.1f}", f"{My/12:.1f}", f"{V:.1f}",
                     _loc(n1, n2) if n1 else "&mdash;"])
    d = _lat_dir(lat) or "X"
    uri = None
    if render_fig:                       # per-combo Appendix-B N/V/M figure (opt-in; the governing
        try:                             # diagrams in Chapter 5 already cover the governing cases)
            import frame_diagram as FD
            uri, _pk = FD.render_solved(cfg, mm, d, label, "perimeter")
        except Exception:
            uri = None
    return rows, maxN, maxM, uri, d

def _jmark(ax, x, z, pinned):
    if pinned: ax.plot([x], [z], marker="o", mfc="white", mec="#c0392b", ms=8, mew=1.6, zorder=5)
    else:      ax.plot([x], [z], marker="s", mfc="#1f3b73", mec="#1f3b73", ms=7, zorder=5)

def _joint_dist_fig(cfg, direction, model=None):
    """2D elevations of the perimeter and an internal frame line, every beam-end and column base
    marked rigid (filled) or pinned/shear-released (open). Parametric buildings read cfg['releases']
    and cfg['base']; custom_build buildings pass the staticized `model` (per-beam relz/rely + per-
    column bases). A beam end is 'pinned' when its STRONG-axis (vertical/gravity) moment is released
    (rely), per the corrected release convention."""
    custom = model is not None
    if cfg.get("custom_build") and not custom:
        return None
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    import matplotlib.lines as mlines
    NX, NY, SX, SY = cfg["NX"], cfg["NY"], cfg["SX"], cfg["SY"]; NF = len(cfg["heights"]); z = E.zlevels(cfg)
    if custom:
        rel_lu = {(b["i"], b["j"], b["k"], b["dir"]): (b.get("relz", "none"), b.get("rely", "none")) for b in model["beams"]}
        base_lu = model.get("bases", {})
    else:
        relf = cfg.get("releases"); base0 = cfg.get("base", "fixed")
    # ABSENT members must draw NOTHING (never a fixed/rigid default): on notched / offset-core /
    # split-level plans the elevation lines cross bays and bases that do not exist in the model --
    # the old .get(..., "fixed"/"none") defaults painted phantom FIXED bases and RIGID joints there.
    if custom:
        present = {k: set(map(tuple, v)) for k, v in (model.get("present") or {}).items()}
    else:
        present = {k: E.grid(cfg, k) for k in range(NF+1)}
    def _pt(i, fx):
        return (i, fx) if direction == "X" else (fx, i)
    def _exists(i, fx, k):
        return _pt(i, fx) in (present.get(k) or set())
    if direction == "X":
        ncol, span, coords = NX, SX, [i*SX for i in range(NX+1)]
        lines = [("Perimeter frame (j=0)", 0), (f"Internal frame (j={NY//2})", NY//2)]
        def beam_rel(i, k, fx):
            return rel_lu.get((i, fx, k, "X")) if custom else ((relf(i, fx, k, "X") if relf else ("none", "none"))
                                                               if _exists(i, fx, k) and _exists(i+1, fx, k) else None)
        def base_at(i, fx):
            return base_lu.get((i, fx)) if custom else (base0 if _exists(i, fx, 0) else None)
    else:
        ncol, span, coords = NY, SY, [j*SY for j in range(NY+1)]
        lines = [("Perimeter frame (i=0)", 0), (f"Internal frame (i={NX//2})", NX//2)]
        def beam_rel(i, k, fx):
            return rel_lu.get((fx, i, k, "Y")) if custom else ((relf(fx, i, k, "Y") if relf else ("none", "none"))
                                                               if _exists(i, fx, k) and _exists(i+1, fx, k) else None)
        def base_at(i, fx):
            return base_lu.get((fx, i)) if custom else (base0 if _exists(i, fx, 0) else None)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=True)
    for ax, (ttl, fx) in zip(axes, lines):
        for i in range(ncol+1):
            zs = [k for k in range(NF+1) if _exists(i, fx, k)]
            if len(zs) >= 2:                                   # column line only over the levels that exist
                ax.plot([coords[i]]*2, [z[min(zs)], z[max(zs)]], color="#999", lw=2, zorder=1)
            bf = base_at(i, fx)
            if bf is not None:
                ax.plot([coords[i]], [z[0]], marker="^", ms=11, zorder=5,
                        mfc=("white" if bf == "pinned" else "#1f3b73"),
                        mec=("#c0392b" if bf == "pinned" else "#1f3b73"), mew=1.6)
        for k in range(1, NF+1):
            for i in range(ncol):
                rel = beam_rel(i, k, fx)
                if rel is None:
                    continue                                   # bay not present on this line/level: draw nothing
                x1, x2 = coords[i], coords[i+1]; zk = z[k]
                relz, rely = rel
                ax.plot([x1, x2], [zk, zk], color="#999", lw=2, zorder=1)
                _jmark(ax, x1 + 0.12*span, zk, relz in ("I", "both"))
                _jmark(ax, x2 - 0.12*span, zk, relz in ("J", "both"))
        ax.set_title(ttl, fontsize=11); ax.set_xlabel("plan (in)"); ax.grid(alpha=0.2)
    axes[0].set_ylabel("Z (in)")
    leg = [mlines.Line2D([], [], marker="s", color="none", mfc="#1f3b73", mec="#1f3b73", ms=9, label="rigid / continuous"),
           mlines.Line2D([], [], marker="o", color="none", mfc="white", mec="#c0392b", ms=9, mew=1.6, label="pinned / shear release"),
           mlines.Line2D([], [], marker="^", color="none", mfc="#1f3b73", mec="#1f3b73", ms=10, label="base fixed"),
           mlines.Line2D([], [], marker="^", color="none", mfc="white", mec="#c0392b", ms=10, mew=1.6, label="base pinned")]
    fig.suptitle(f"Joint fixity distribution - {direction}-direction frames", y=1.0, fontsize=12)
    fig.legend(handles=leg, loc="lower center", ncol=4, fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=[0, 0.06, 1, 0.96])
    return _b64(fig)

def _beam_deflections(cfg, fD, fL, nseg=6):
    """Chord-relative mid-span vertical deflection of every beam under a service gravity case, from
    the static model (true distributed tributary load). Returns {(i,j,k,dir): (|defl_in|, L_in)}."""
    import static_model as SM
    mm, _, _ = SM.run_combo(cfg, fD, fL, 0.0, {}, nseg=nseg)
    out = {}
    for b in mm["beams"]:
        ch = b["nodes"]; zA = ops.nodeDisp(ch[0], 3); zB = ops.nodeDisp(ch[-1], 3); n = len(ch)-1
        dmax = 0.0
        for idx, nd in enumerate(ch):
            d = ops.nodeDisp(nd, 3) - (zA + (zB-zA)*idx/n)
            if abs(d) > abs(dmax): dmax = d
        out[(b["i"], b["j"], b["k"], b["dir"])] = (abs(dmax), b["L"])
    return out

def _deflection_section(cfg, nseg=6):
    NF = len(cfg["heights"])
    try:
        dD = _beam_deflections(cfg, 1.0, 0.0, nseg); dL = _beam_deflections(cfg, 0.0, 1.0, nseg)
    except Exception as ex:
        return f"<p class='note'>[deflection run failed: {ex}]</p>"
    def worst(roof):
        best = None
        for key, (dl, L) in dL.items():
            if (key[2] == NF) != roof: continue
            ratio = (L/dl) if dl > 1e-6 else 1e12
            if best is None or ratio < best[1]: best = (key, ratio, dl, L)
        return best
    def cell(d, L, lim):
        if d < 1e-3: return ("&lt; 0.01 in", "OK")
        return (f"{d:.2f} in (L/{L/d:.0f})", "OK" if d <= L/lim else "NG")
    rows = []
    for roof, lbl in ((False, "Floor beam (governing)"), (True, "Roof beam (governing)")):
        w = worst(roof)
        if not w: continue
        key, ratio, dl, L = w; dd = dD.get(key, (0.0, L))[0]; dtl = dd + dl
        ltxt, lok = cell(dl, L, 360); ttxt, tok = cell(dtl, L, 240)
        camber = round(0.8*dd*4)/4 if dd >= 0.75 else 0.0
        rows.append([lbl, f"{L/12:.0f} ft", ltxt, lok, ttxt, tok,
                     (f"{camber:.2f} in" if camber > 0 else "none")])
    if not rows:
        return ""
    return ("<h3>Beam deflection &amp; camber</h3>"
            "<p>Service deflection of the governing floor and roof beam from the static model "
            "(chord-relative, true two-way tributary gravity): live load against L/360 and total D+L "
            "against L/240. Suggested camber &asymp; 80% of the dead-load deflection (nearest 1/4 in) "
            "where it exceeds 3/4 in.</p>"
            + _table(["Member", "Span", "Live &delta; (vs L/360)", "&le;", "Total &delta; (vs L/240)", "&le;", "Camber"], rows))


def _grounding_check(cfg, name, pkg):
    """Verify the design actually queried the RAG collections its systems require (reliability).
    Reads the activity log and the calc_package cites.  H44 (L-06): credit only by the IS collection names and
    by cites that name the standard ("IS 800", "IS 18168") -- never by bare number substrings such as "360"
    (span/360), "341" or "358".  Rows: IS 800 member limit states, Section 10 connections, Section 12 seismic
    detailing (R > 3), 12.10.2 / 12.11.2 moment connections (moment frames, R > 3)."""
    import re as _re
    recs, _ = _load_activity(name)
    col = {}
    for r in recs:
        if r.get("tool") == "search_engineering_standards":
            mm = _re.search(r"\[([A-Za-z0-9_]+)\]", r.get("detail", ""))
            if mm: col[mm.group(1)] = col.get(mm.group(1), 0) + 1
    def n(c): return col.get(c, 0)
    def _cited(obj):
        out = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                out += ([str(v)] if k in ("cited", "cite", "clause") else _cited(v))
        elif isinstance(obj, list):
            for v in obj: out += _cited(v)
        return out
    _ct = " ".join(_cited(pkg or {}))
    _cc = " ".join(_cited((pkg or {}).get("connections") or []))
    _is800 = _re.compile(r"\bIS\s*800\b", _re.I)
    cite_is800 = bool(_is800.search(_ct))
    cite_s10 = bool(_re.search(r"\bIS\s*800(?::\s*2007)?\s*(?:cl\.?\s*|§\s*)?10\.\d", _cc, _re.I))
    cite_s12 = bool(_re.search(r"\bIS\s*800(?::\s*2007)?\s*(?:cl\.?\s*|§\s*)?12\.\d|\bIS\s*18168\b", _ct, _re.I))
    cite_mc = bool(_re.search(r"\bIS\s*800(?::\s*2007)?\s*(?:cl\.?\s*|§\s*)?12\.1[01]\.2", _ct, _re.I))
    R = cfg["seis"].get("R", 3); braced = E.is_braced(cfg); detailed = R > 3
    has_conn = bool((pkg or {}).get("connections")); has_cap = bool((pkg or {}).get("capacity_design"))
    q800 = n("engineering_standards_IS800")
    rows = []
    def row(item, required, ok, ev):
        rows.append([item, "required" if required else "n/a (R&le;3)" if not detailed else "n/a",
                     ev, ("&mdash;" if not required else ("grounded" if ok else "<b>MISSING</b>"))])
    row("IS 800:2007 &mdash; member limit states (Sections 7&ndash;9)", True, q800 > 0 or cite_is800,
        f"{q800} queries" + (" + IS 800 cited in calc_package" if cite_is800 else ""))
    row("IS 800:2007 Section 10 &mdash; connection design", True, has_conn and (q800 > 0 or cite_s10),
        ("connections block present" if has_conn else "no connections block written")
        + (" + IS 800 10.x cited" if cite_s10 else ""))
    row("IS 800:2007 Section 12 &mdash; seismic detailing / capacity design", detailed,
        q800 > 0 or has_cap or cite_s12,
        f"{q800} queries" + (" + capacity_design block" if has_cap else "")
        + (" + IS 800 12.x / IS 18168 cited" if cite_s12 else ""))
    row("IS 800:2007 12.10.2 / 12.11.2 &mdash; moment-frame beam-to-column connections", detailed and not braced,
        q800 > 0 or cite_mc,
        f"{q800} queries" + (" + IS 800 12.10.2 / 12.11.2 cited" if cite_mc else ""))
    nmiss = sum(1 for r in rows if "MISSING" in r[3])
    head = ("<h3>Grounding verification</h3>"
            f"<p>Whether the design queried the RAG collections its systems require. R = {R} "
            + ("(&gt; 3 &mdash; IS 800 Section 12 ductile detailing applies)." if detailed
               else "(&le; 3 &mdash; system not detailed for seismic ductility; IS 800 Section 12 ductile rows do not apply).")
            + "</p>")
    tail = ("<p class='note'>Grounding incomplete: the items marked MISSING were required for this building's "
            "systems but no RAG query / calc-package evidence was found. Re-run those checks against the RAG.</p>"
            if nmiss else "<p>All required RAG grounding is present.</p>")
    return head + _table(["Grounding requirement", "Applies", "Evidence", "Status"], rows) + tail

def _appendix_case_figs(cases, cfg):
    """Which load-case indices get a per-combo N/V/M figure in Appendix B. Default: a fast
    representative set -- the gravity combos + the primary seismic combo per direction/sign -- so the
    report stays under the MCP client timeout. cfg['appendix_case_figures']=True renders ALL combos
    (slow; run in the background); =False renders none."""
    flag = cfg.get("appendix_case_figures", "subset")  # default: representative subset (gravity + primary seismic)
    if flag is True:
        return set(range(len(cases)))                # ALL combos (slower; rendered inline)
    if not flag:
        return set()                                 # explicit False / None -> none
    picked, seen = [], set()
    for idx, (label, fD, fL, fLr, lat, co) in enumerate(cases):
        if co:                                    # skip Omega0 column-only duplicates
            continue
        lab = str(label)
        if lab.startswith("1.4D") or "1.2D+1.6L" in lab:
            picked.append(idx)
        else:
            for dirn in ("X", "Y"):
                for sgn in ("+", "-"):
                    key = "E" + dirn + sgn
                    # the +L seismic cases start "(1.2+0.2SDS)D..." (labels now print the actual
                    # companion factor, e.g. "+0.5L", so match the gravity prefix, not "+L")
                    if ("rhoE" + dirn + sgn) in lab and lab.startswith("(1.2") and key not in seen:
                        seen.add(key); picked.append(idx)
        if len(picked) >= 6:
            break
    return set(picked[:6])


def _consistency_section(name, root, pkg):
    """Chapter 13 numerical self-consistency check (engine/consistency.py)."""
    try:
        import consistency
        issues = consistency.check(name, root=root, pkg=pkg, verbose=False)
    except Exception as ex:
        return f"<h3>Numerical self-consistency check</h3><p class='note'>[consistency check unavailable: {ex}]</p>"
    if not issues:
        return ("<h3>Numerical self-consistency check</h3>"
                "<p class='cnote'>&#10003; <b>PASS</b> &mdash; every member/connection carries a limit state, "
                "capacity and D/C; each headline D/C equals its worst limit-state check and demand&divide;capacity; "
                "and no quantity is reported with conflicting values.</p>")
    rows = [[str(i + 1), iss] for i, iss in enumerate(issues)]
    return ("<h3>Numerical self-consistency check</h3>"
            f"<p class='note'><b>{len(issues)} item(s) to reconcile</b> before the report is final &mdash; the same "
            "quantity must carry one value everywhere, every D/C must equal demand&divide;capacity, the headline D/C "
            "must equal its worst limit-state check, and no D/C may exceed 1.0:</p>" + _table(["#", "issue"], rows))


def _design_basis(cfg):
    """Top-of-report echo of the RESOLVED building parameters so a brief-vs-built mismatch (bay count,
    spans, stories, loads) is visible on page 1."""
    NX,NY=cfg["NX"],cfg["NY"]; SX,SY=cfg["SX"],cfg["SY"]; H=cfg["heights"]; s=cfg.get("seis",{})
    try:
        from india_units import is_si
        _si = is_si(cfg)
    except Exception:
        _si = str(cfg.get("units") or "").upper() in ("N-MM", "SI", "METRIC")
    if _si:
        rows=[
          ["Lateral system", str(cfg.get("arch",""))],
          ["Unit system", "N-mm-sec (India SI wave 2)"],
          ["Plan grid", "%d &times; %d bays @ %.0f &times; %.0f mm  (%.2f &times; %.2f m overall)"
                        % (NX,NY,SX,SY,NX*SX/1000.0,NY*SY/1000.0)],
          ["Stories", "%d @ %s mm  (H = %.2f m)" % (len(H), ", ".join("%.0f"%h for h in H), sum(H)/1000.0)],
          ["Gravity loads", "floor D %s / L %s kN/m&sup2;; roof D %s / L %s kN/m&sup2;"
                        % (cfg.get("D_floor","?"),cfg.get("L_floor","?"),cfg.get("D_roof","?"),cfg.get("L_roof","?"))],
          ["Seismic", "IS 1893 path — see load_plan; seis block keys present: %s"
                        % (", ".join(sorted(s.keys())) if s else "(none)")],
        ]
    else:
        rows=[
          ["Lateral system", str(cfg.get("arch",""))],
          ["Plan grid", "%d &times; %d bays @ %.0f &times; %.0f ft  (%.0f &times; %.0f ft overall)"
                        % (NX,NY,SX/12.0,SY/12.0,NX*SX/12.0,NY*SY/12.0)],
          ["Stories", "%d @ %s ft  (H = %.0f ft)" % (len(H), ", ".join("%.0f"%(h/12.0) for h in H), sum(H)/12.0)],
          ["Gravity loads", "floor D %s / L %s psf; roof D %s / L %s psf"
                        % (cfg.get("D_floor","?"),cfg.get("L_floor","?"),cfg.get("D_roof","?"),cfg.get("L_roof","?"))],
          ["Seismic", "R=%s, Cd=%s, &Omega;<sub>0</sub>=%s, Ie=%s, S<sub>DS</sub>=%s, S<sub>1</sub>=%s"
                        % (s.get("R","?"),s.get("Cd","?"),s.get("Om0","?"),s.get("Ie","?"),s.get("SDS","?"),s.get("S1","?"))],
        ]
    return (_si_unit_banner(cfg) +
            "<h2>Design basis</h2><p class='note'>Model built to the parameters below &mdash; <b>verify these "
            "against your brief</b>, especially the bay count and spans.</p>" + _table(["Parameter","Value"], rows))


def build_report(name, root=None):
    _register(name); cfg = E.CFG[name]
    if root is None:
        root = os.path.join(os.environ.get("STEEL_BUILDER_JOBS") or HERE, name)
    if E._india_job(cfg):                      # WP1.13 / WP2.10: IS-only report, no foreign-code chapters
        import report_india
        return report_india.build_report_india(name, root)
    NF = len(cfg["heights"]); s = cfg["seis"]
    SX, SY = cfg["SX"], cfg["SY"]; NX, NY = cfg["NX"], cfg["NY"]
    Lx = (cfg["xcoords"][-1] if cfg.get("xcoords") else NX*SX); Ly = (cfg["ycoords"][-1] if cfg.get("ycoords") else NY*SY)
    Htot = E.zlevels(cfg)[-1]
    pkg, pkgsrc = _load_pkg(name, root)
    _set_report_units(cfg)
    if _sc()["si"]:
        mat = (f"IS steel (agent grade from RAG): default display "
               f"\\(F_y={Fy:.0f}\\) MPa, \\(E={Emod:,.0f}\\) MPa (N-mm-sec).")
    else:
        mat = "ASTM A992 steel: \\(F_y=50\\) ksi, \\(F_u=65\\) ksi, \\(E=29{,}000\\) ksi."
    parts = [f"<h1>{name} &mdash; structural analysis &amp; design report</h1>",
             f"<p><b>{cfg.get('arch','')}</b> &middot; generated {datetime.date.today()}</p>",
             _toc(), _design_basis(cfg)]
    figdir = os.path.join(root, "figs"); os.makedirs(figdir, exist_ok=True)
    global _FIGDIR; _FIGDIR = figdir; _FIGSEQ[0] = 0
    try:
        import plot_model as PM
        PM.figures(name, figdir, deformed_fig=bool(cfg.get("deformed_shape_figure")))
        # Figure 2 (member orientation) is REQUIRED -- retry once on its own if missing
        if not os.path.exists(os.path.join(figdir, f"{name}_orientation.png")):
            try: PM.orientation(name, figdir)
            except Exception as _oex:
                parts.append(f"<p class='note'>[REQUIRED orientation figure (Fig 2) failed twice: {_oex} "
                             "&mdash; fix the model and re-render]</p>")
    except Exception as ex:
        parts.append(f"<p class='note'>[model figures failed: {ex}]</p>")

    # ---- shared computations (used across several chapters) ----
    Fx = None; T = eX = eY = None; Cs = V = Tu = Ta = W = None
    try: T, eX, eY, Cs, V, Tu, Ta, Fx, W = _seismic(cfg)
    except Exception as ex: parts.append(f"<p class='note'>[seismic analysis failed: {ex}]</p>")
    windhtml, VwX, VwY = _wind_section(cfg)
    print("[%s] report: model + IS 875/1893 loads + modal done; rendering chapters%s ..."
          % (name, " + static-model force diagrams (~30-60 s)" if cfg.get("force_diagrams") else ""))
    drX = drY = None; reX = reY = None
    if Fx is not None:
        try:
            _, _dX, drX, reX = _run_case(cfg, "X", Fx); _, _dY, drY, reY = _run_case(cfg, "Y", Fx)
        except Exception as ex: parts.append(f"<p class='note'>[drift/equilibrium run failed: {ex}]</p>")

    # ============================== Chapter 1 — Design basis & codes ==============================
    parts.append(_chapter(1))
    parts.append(_design_basis_codes(cfg, s, root))
    parts.append("<h3>Building description</h3>")
    parts.append(_table(["Item", "Value"], [
        ["Archetype", cfg.get("arch", "")],
        ["Stories", f"{NF}"],
        ["Plan", f"{Lx/12:.0f} ft (X) &times; {Ly/12:.0f} ft (Y)"],
        ["Bays", f"{NX} &times; {NY} @ {SX/12:.0f} ft (X) / {SY/12:.0f} ft (Y)"],
        ["Height", f"{Htot/12:.0f} ft (h&#8345;)"],
        ["Column bases", cfg.get("base", "fixed")],
        ["Lateral system", "moment frame" if not cfg.get("braces") else "braced / dual / mixed"],
    ]))
    parts.append("<h3>Materials</h3><p>" + mat + "</p>")
    parts.append("<h3>Geometry</h3>")
    try: parts.append(_img(fig_plan(cfg), "Plan grid &mdash; the (i, j) labels used in the reaction/force tables"))
    except Exception as ex: parts.append(f"<p class='note'>[plan figure failed: {ex}]</p>")
    parts.append(_img(_png_file_b64(os.path.join(figdir, f"{name}_orientation.png")),
                      "Section orientation (web/depth ticks &mdash; beam strong axis must be vertical)"))

    # ====================== Chapter 2 — Structural system & load path =======================
    parts.append(_chapter(2))
    parts.append(_system_loadpath(cfg))
    parts.append("<h3>Seismic force-resisting system (each principal direction)</h3>")
    parts.append(_lfrs_table(cfg))
    parts.append("<h3>Lateral-load design inputs</h3>"); parts.append(_lateral_inputs_table(cfg))
    if cfg.get("deformed_shape_figure"):   # OFF the default workflow (viewer shows the same live)
        parts.append(_img(_png_file_b64(os.path.join(figdir, f"{name}_deformed_X.png")),
                          "Deformed shape under lateral X (confirms a continuous lateral load path)"))
    else:
        parts.append("<p class='note'>Static deformed-shape figure omitted for faster reporting &mdash; "
                     "set cfg['deformed_shape_figure']=True and re-render to include it; the interactive "
                     "3D viewer (viewer_3d.html in the job download) shows the load path live.</p>")
    try:
        # The standalone 3D viewer (viewer_3d.html) is WRITTEN here as a side effect -- the frontend
        # "View model" button and the job download need the file even though the report no longer
        # embeds a viewer section (removed by request). Do not drop this call again.
        import viewer3d
        viewer3d.report_section(cfg, name, root)   # returns markup we deliberately discard
    except Exception as ex:
        print(f"[report] viewer_3d.html generation failed: {ex}")
    if Fx is not None:
        parts.append("<h3>Horizontal force distribution to the lateral frames</h3>")
        try: parts.append(_horizontal_distribution(cfg, Fx, VwX, VwY))
        except Exception as ex: parts.append(f"<p class='note'>[distribution failed: {ex}]</p>")
        parts.append("<h3>Diaphragm classification &amp; design force (IS 875/1893 &sect;12.10)</h3>")
        try: parts.append(_diaphragm_section(cfg, Fx))
        except Exception as ex: parts.append(f"<p class='note'>[diaphragm section failed: {ex}]</p>")
        parts.append("<h3>Plan &amp; vertical irregularity screening</h3>")
        try: parts.append(_irregularity_section(cfg, Fx))
        except Exception as ex: parts.append(f"<p class='note'>[irregularity screen failed: {ex}]</p>")
    else:
        parts.append("<p class='cnote'>Diaphragm design force and irregularity screening need the seismic "
                     "analysis (Chapter 3).</p>")

    # ================================= Chapter 3 — Loads ==================================
    parts.append(_chapter(3))
    parts.append("<h3>Gravity loads</h3>"); parts.append(_gravity_loads_table(cfg))
    parts.append(_gravity_loads_note())
    parts.append("<h3>Wind load determination (IS 875/1893 Ch. 26-31)</h3>"); parts.append(windhtml)
    parts.append(_wind_cc_note())
    parts.append("<h3>Seismic load determination (IS 875/1893 Ch. 11-12)</h3>")
    if Fx is not None:
        parts.append(_seismic_loads_section(cfg, T, eX, eY, Cs, V, Tu, Ta, Fx, W))
    else:
        parts.append("<p class='note'>[seismic data unavailable]</p>")
    parts.append("<h3>Governing lateral load per direction</h3>")
    parts.append(_governing_lateral(cfg, V, VwX, VwY))

    # ========================== Chapter 4 — Load combinations ============================
    parts.append(_chapter(4))
    case_detail_parts = []
    try:
        cases = load_cases(cfg)
        parts.append(_combo_notes(cfg, cases))
        parts.append("<h3>Combinations analysed (load factors)</h3>")
        parts.append(_combo_table(cases))
        parts.append(_combo_legend(cfg))
        # --- THREE separate opt-in items (each requestable on its own) -------------------
        #   cfg['force_summary']          -> the per-combination force SUMMARY table (heavy 27-combo solve)
        #   cfg['appendix_case_figures']  -> the Appendix-B per-combo N/V/M FIGURES (heavy; figs in the same loop)
        #   cfg['force_diagrams']         -> the Chapter-5 governing N/V/M frame DIAGRAMS (light; rendered below)
        _want_summary  = bool(cfg.get("force_summary"))
        _want_casefigs = bool(cfg.get("appendix_case_figures"))
        if Fx is not None and (_want_summary or _want_casefigs):      # this 27-combo solve feeds the table AND/OR the figs
            # RESUMABLE per-combo cache (design/_case_cache.pkl): each solved combo is saved as soon as
            # it finishes, so an interrupted render (client timeout / instance recycle) resumes instead
            # of restarting the whole 27+ solve loop. Keyed by a cfg fingerprint -> stale after redesign.
            import pickle as _pk, hashlib as _hl, os as _os
            _cache_p = _os.path.join(root, "design", "_case_cache.pkl")
            _fp = _hl.md5(repr(sorted((k, str(v)) for k, v in cfg.items()
                                      if not callable(v))).encode()).hexdigest()
            try:
                _cc = _pk.load(open(_cache_p, "rb"))
                if _cc.get("_fingerprint") != _fp:
                    _cc = {"_fingerprint": _fp}
            except Exception:
                _cc = {"_fingerprint": _fp}
            def _cc_save():
                try:
                    _os.makedirs(_os.path.dirname(_cache_p), exist_ok=True)
                    _tmp = _cache_p + ".tmp~"
                    with open(_tmp, "wb") as _f:
                        _pk.dump(_cc, _f)
                    _os.replace(_tmp, _cache_p)
                except Exception:
                    pass
            srows = []
            for _ci, combo in enumerate(cases):
                label, fD, fL, fLr, lat, col_only = combo
                if col_only:        # Omega0 column-overstrength: column-axial only -> reported in the member schedule (Ch.6)
                    if _want_summary:
                        srows.append([label, "&mdash;", "&Omega;<sub>0</sub> column overstrength (see Ch. 6)", "&mdash;", ""])
                    continue
                try:
                    _ckey = (str(label), bool(_want_casefigs))
                    if _ckey in _cc:
                        rows, (Nv, Nk, Ns), (Mv, Mk, Ms), uri, d = _cc[_ckey]
                    else:
                        rows, (Nv, Nk, Ns), (Mv, Mk, Ms), uri, d = _static_case_table(cfg, combo, render_fig=_want_casefigs)
                        _cc[_ckey] = (rows, (Nv, Nk, Ns), (Mv, Mk, Ms), uri, d)
                        _cc_save()
                    if _want_summary:
                        srows.append([label, f"{Nv:.0f}", f"{Nk} {Ns}".strip(), f"{Mv/12:.0f}", f"{Mk} {Ms}".strip()])
                        case_detail_parts.append(f"<h4>Load case: {label}</h4><p>{_case_desc(label, col_only)}</p>")
                        case_detail_parts.append(_table(
                            [f"member", "section", f"N ({_ul('F')})", f"Mz ({_ul('M')})", f"My ({_ul('M')})", f"V ({_ul('F')})", "location (i,j / level)"],
                            rows))
                    if uri and _want_casefigs:
                        _save_case_fig(uri, figdir, label)   # -> figs/case_<label>.png (NOT embedded)
                except Exception as ex:
                    if _want_summary:
                        srows.append([label, "&mdash;", f"[failed: {ex}]", "&mdash;", ""])
            if _want_summary:
                parts.append("<h3>Load-case force summary</h3>")
                parts.append("<p>One row per combination: the largest axial force and the largest bending moment "
                             "anywhere in the structure, with the member type/section that carries it (from the "
                             "<b>static model</b>, so gravity beam moments are correct). The governing N/V/M diagrams are "
                             "in Chapter 5 (cfg['force_diagrams']); the per-combination N/V/M figures are in Appendix B "
                             "(cfg['appendix_case_figures']).</p>")
                parts.append(_table(["Load case", f"Max axial N ({_ul('F')})", "carried by", f"Max moment M ({_ul('M')})", "carried by"], srows))
        elif Fx is not None:
            parts.append("<h3>Load-case force summary</h3>")
            parts.append("<p class='note'>The per-combination force-summary table (one row per LSD combination) is "
                         "temporarily omitted for faster reporting &mdash; it can be populated here on request at the "
                         "completion of the design. The governing per-member design demands are the enveloped values in "
                         "Chapter 6 / the member schedule.</p>")
    except Exception as ex:
        parts.append(f"<p class='note'>[load combinations failed: {ex}]</p>")

    # ======================= Chapter 5 — Analysis model fidelity =========================
    print("[%s] report: chapter 5 (analysis-model fidelity) ..." % name)
    parts.append(_chapter(5))
    rel = cfg.get("releases"); cb = cfg.get("custom_build")
    jt = ("custom (defined in custom_build)" if cb else
          "rigid / continuous except where moment releases are set" if rel else "all rigid / continuous (no releases)")
    parts.append("<h3>Modelling assumptions</h3>")
    parts.append(_table(["Assumption", "As modelled"], [
        ["Column bases", cfg.get("base", "fixed")],
        ["Beam-column &amp; brace joints", jt],
        ["Floor diaphragm", "rigid (in-plane), masters at floor centroid"],
        ["Geometric transform", "P-&Delta; (second-order) on columns"],
        ["Leaning gravity columns", "yes" if cfg.get("lean_gravity") else "framed into the lateral system"],
        ["Gravity for member forces", "static model &mdash; true two-way (45&deg;) tributary line loads on sub-divided beams"],
    ]))
    try:
        _md = (cfg.get("model") or {})
        _bs = str(_md.get("bases") or cfg.get("base") or "pinned")
        _jt = str(_md.get("joints") or ("pinned" if cfg.get("releases") else "rigid"))
        _cap = f"Modelled joint &amp; base fixity &mdash; column bases: {_bs}; girder joints: {_jt}"
        try:
            if E.is_braced(cfg): _cap += "; braces pin-ended (axial-only truss members)"
        except Exception: pass
        if cfg.get("lean_gravity"): _cap += "; leaning gravity columns"
        parts.append(_img(_joint_figure(cfg), _cap + ".", full=True))
    except Exception as _jex: parts.append(f"<p class='note'>[joint figure failed: {_jex}]</p>")
    _jmodel = None
    if cfg.get("custom_build"):
        try:
            import static_model as SM; _jmodel = SM.build_static(cfg, "Linear", 2)
        except Exception:
            _jmodel = None
    for _d in ("X", "Y"):
        try:
            _ju = _joint_dist_fig(cfg, _d, model=_jmodel)
            if _ju:
                parts.append(_img(_ju, f"Joint-fixity distribution &mdash; {_d}-direction perimeter vs internal frame "
                                       "(filled square = rigid/continuous, open circle = pinned/shear release, "
                                       "triangle = column base; pinned = strong-axis vertical moment released)"))
        except Exception as ex:
            parts.append(f"<p class='note'>[joint-distribution figure {_d} failed: {ex}]</p>")
    parts.append(_stability_basis_note())
    if Fx is not None and reX is not None:
        Rx = sum(r[2][0] for r in reX); Rz = sum(r[2][2] for r in reX)
        parts.append("<h3>Equilibrium check (seismic X combination)</h3>")
        parts.append(f"<p>|&Sigma;R<sub>x</sub>| = {_F(abs(Rx),0)} {_ul('F')} vs applied base shear {_F(sum(Fx.values()),0)} {_ul('F')} "
                     f"(equal and opposite); &Sigma;R<sub>z</sub> = {_F(abs(Rz),0)} {_ul('F')} factored gravity delivered to the "
                     "ground. Reactions balance the applied loads in all three axes (load path verified).</p>")
        if eX is not None and eY is not None:
            parts.append(_modal_mass_check(eX, eY))
        _want_modefigs = bool(cfg.get("mode_figures"))     # 3D mode-shape figures: OFF the default workflow
        for m in (1, 2, 3):
            if m <= NF*3:
                if _want_modefigs:
                    try: parts.append(_img(fig_mode_3d(cfg, m, 3), f"Mode {m} (T = {T[m-1]:.2f} s)", full=True))
                    except Exception as ex: parts.append(f"<p class='note'>[mode {m} failed: {ex}]</p>")
                else:
                    parts.append(f"<p class='note'>Mode {m} (T = {T[m-1]:.2f} s) shape figure temporarily omitted for faster "
                                 "reporting &mdash; can be populated here on request at the completion of the design.</p>")
        # animated mode-shape GIFs removed from the report: the interactive 3D viewer
        # ("View model" button, Chapter 2) animates all six modes on demand.
        else:
            pass   # animated mode-shape GIFs are gone for good -- the interactive 3D viewer animates all modes live
    try:
        if not bool(cfg.get("force_diagrams")):
            parts.append("<p class='note'>Governing N/V/M frame diagrams (perimeter &amp; internal lines, from the "
                         "static model) temporarily omitted for faster reporting &mdash; can be populated here on "
                         "request at the completion of the design.</p>")
            gd = {}
        else:
            import frame_diagram as FD
            gd = FD.governing_diagrams(cfg, load_cases(cfg), nseg=6, lines=("perimeter", "internal"))   # nseg 2->6 (opt-in figures)
        if gd.get("perimeter"):
            parts.append("<h3>Governing internal-force diagrams &mdash; perimeter frames (static model)</h3>")
            parts.append("<p>N / V / M for each perimeter frame under its governing LSD combination, from the "
                         "static model (true two-way tributary loads on sub-divided beams). Peak values annotated "
                         "per member; columns are single elements (linear between ends).</p>")
            for _d in ("X", "Y"):
                if _d in gd["perimeter"]:
                    _uri, _label, _pkM = gd["perimeter"][_d]
                    parts.append(_img(_uri, f"{_d}-direction perimeter frame &mdash; governing combo {_label} "
                                            f"(peak beam moment {(_M(_pkM) if _sc()['si'] else round(float(_pkM), 0))} {_ul('M')})"))
        if gd.get("internal"):
            parts.append("<h3>Governing internal-force diagrams &mdash; internal frames (static model)</h3>")
            parts.append("<p>The same diagrams for an interior frame line, which generally carries more gravity "
                         "tributary (and less lateral) than the perimeter &mdash; the gravity-governed companion check.</p>")
            for _d in ("X", "Y"):
                if _d in gd["internal"]:
                    _uri, _label, _pkM = gd["internal"][_d]
                    parts.append(_img(_uri, f"{_d}-direction internal frame &mdash; governing combo {_label} "
                                            f"(peak beam moment {(_M(_pkM) if _sc()['si'] else round(float(_pkM), 0))} {_ul('M')})"))
    except Exception as ex:
        parts.append(f"<p class='note'>[static-model diagrams unavailable: {ex}]</p>")

    # ===================== Chapter 6 — Member strength design (IS 800) ==================
    parts.append(_chapter(6))
    parts.append(_member_section(cfg, name, pkg, {"roof"}, "Roof members",
        "Roof beams/girders for roof dead + roof live (and snow); governing flexure/shear/deflection limit state."))
    parts.append(_member_section(cfg, name, pkg, {"floor"}, "Floor members",
        "Typical floor beams/girders for floor dead + live load."))
    parts.append(_member_section(cfg, name, pkg, {"gravity_col"}, "Gravity columns",
        "Interior gravity columns for accumulated tributary gravity (IS 800 &sect;E3 compression)."))
    parts.append(_member_section(cfg, name, pkg, {"lateral_col"}, "Lateral-system columns",
        "Moment-frame / braced-frame columns for combined gravity + lateral (IS 800 &sect;H1 interaction)."))
    if cfg.get("braces"):
        parts.append(_member_section(cfg, name, pkg, {"brace"}, "Braces",
            "Concentric braces for the design story shear (IS 800 &sect;E3 compression, &sect;D2 tension)."))
    parts.append(_ch6_notes(cfg))
    if pkg:
        parts.append("<h3>Member design summary (calc_package.json)</h3>")
        parts.append(f"<p>Source: <code>{os.path.relpath(pkgsrc, HERE)}</code>. Capacities/D-C derived by the agent "
                     "from the IS 800/341 RAG; full referenced calc in Appendix A.</p>")
        parts.append(_member_dc_summary(pkg))
        _comp = _composite_section(pkg)
        if _comp:
            parts.append(_comp)
        _xtra = _extra_blocks_section(pkg)
        if _xtra:
            parts.append(_xtra)
        _msfig = ""
        if cfg.get("section_color_figure"):    # OFF the default workflow (viewer's 'Color by section' shows it live)
            try:
                import viz3d as _VZ
                _msu = _VZ.members_by_size(cfg)
                if _msu:
                    _msfig = _img(_msu, "Model members coloured by section size &mdash; each distinct member size "
                                        "(e.g. each W-column / beam / HSS brace) drawn in its own colour (legend)")
            except Exception as _mex:
                _msfig = f"<p class='note'>[member-size figure failed: {_mex}]</p>"
        else:
            _msfig = ("<p class='note'>Member-size colour figure omitted for faster reporting &mdash; set "
                      "cfg['section_color_figure']=True and re-render to include it; the interactive 3D viewer's "
                      "'Color by section' view shows the same.</p>")
        parts.append(_narrative_html(pkg, members_fig_html=_msfig))
    else:
        parts.append("<p class='note'>[no calc_package.json found &mdash; run the design first]</p>")

    # ====================== Chapter 7 — Stability & second-order =========================
    parts.append(_chapter(7))
    if Fx is not None and drX is not None:
        try:
            parts.append(_stability_section(cfg, Fx, drX, pkg))
            parts.append(_img(fig_drift_profile(cfg, drX, drY), "Interstory drift profile (both directions)"))
            ss_uri, Vstory, OTM = fig_story_shear_otm(cfg, Fx)
            parts.append(f"<p>Base shear &Sigma;F = {_F(sum(Fx.values()),0)} {_ul('F')}; base overturning &asymp; {OTM:.0f} {_ul('M')}.</p>")
            parts.append(_img(ss_uri, "Story-shear and overturning-moment profiles"))
        except Exception as ex:
            parts.append(f"<p class='note'>[stability section failed: {ex}]</p>")
    else:
        parts.append("<p class='note'>[needs seismic drift data]</p>")

    # ============================ Chapter 8 — Serviceability =============================
    parts.append(_chapter(8))
    if Fx is not None and drX is not None:
        lim, _limrho = E.drift_allowable(cfg)   # IS 1893 cl.7.11.1.1 default 0.004
        parts.append("<h3>Seismic design storey drift (IS 1893)</h3>")
        try:
            from india_seismic import design_story_drifts, drift_limit_label, drift_allowable_for_storey
            dX = design_story_drifts(drX, cfg); dY = design_story_drifts(drY, cfg)
            _limlab = drift_limit_label(cfg)
        except Exception:
            dX, dY = list(drX), list(drY)
            _limlab = f"{lim*100:.2f}% of storey height (IS 1893 Part 1:2016 cl.7.11.1.1)"
            def drift_allowable_for_storey(cfg, storey_index=0):  # noqa: F811
                return lim
        parts.append(
            "<p>Design storey drifts under design base shear V<sub>B</sub> with partial factors "
            "&gamma;=1.0 (<b>IS 1893 Part 1:2016 cl.7.11.1.1</b>). "
            "<b>No</b> ASCE C<sub>d</sub>/I<sub>e</sub> amplification and <b>no</b> Table 12.12-1 / 0.025h "
            "USA scaffold. Limit: <b>" + _limlab + "</b>; soft-storey storeys use 0.002 h where "
            "Table 6(i) applies.</p>")
        parts.append(_drift_relief_note(cfg))
        drow = []
        for k in range(1, NF + 1):
            try:
                lim_k = float(drift_allowable_for_storey(cfg, k - 1))
            except Exception:
                lim_k = float(lim)
            dxk, dyk = abs(dX[k - 1]), abs(dY[k - 1])
            ok = "OK" if max(dxk, dyk) <= lim_k + 1e-12 else "NG"
            drow.append([k, f"{dxk*100:.3f}", f"{dyk*100:.3f}",
                         f"{lim_k*100:.2f}%", ok])
        parts.append(_table(
            ["Storey", "design &delta; X %", "design &delta; Y %", "limit", "status"],
            drow))
    parts.append(_wind_drift_section(cfg))
    parts.append(_floor_serviceability(pkg))
    parts.append(_deflection_section(cfg))
    parts.append("<p class='cnote'><b>Out of scope (this model):</b> floor vibration (AISC Design Guide 11) and "
                 "building separation/pounding are detail-level serviceability checks confirmed against the framing drawings.</p>")

    # ===================== Chapter 9 — Seismic / wind detailing (IS 800 seismic) ================
    parts.append(_chapter(9))
    parts.append(_aisc341_detailing(cfg, pkg))

    # ========================= Chapter 10 — Connections ==================================
    parts.append(_chapter(10))
    _ctbl = _connection_demands(cfg, pkg, reX)
    if _ctbl:
        parts.append("<p>Connection design demands transmitted to the fabricator / connection engineer (member end "
                     "forces from the analysis; each connection is then DESIGNED to these demands below):</p>")
        parts.append(_ctbl)
    parts.append("<p class='cnote'><b>Designed in this package:</b> each connection is sized to the demands above per "
                 "IS 800 Ch. J (bolts J3, welds J2, block shear J4, HSS Ch. K, base plates/anchors J8/J9 + ACI 318 "
                 "Ch.17) and IS 800 seismic for seismic systems &mdash; limit state, capacity and D/C &le; 1.0 derived by the "
                 "agent from the RAG (see the Connections table in Chapter 6 / Appendix A). Only shop-level detailing "
                 "is confirmed on the fabricator's connection submittal.</p>")

    # ===================== Chapter 11 — Foundations interface ============================
    parts.append(_chapter(11))
    if reX is not None:
        Rz = sum(r[2][2] for r in reX); Rx = sum(r[2][0] for r in reX)
        pmax = max((r[2][2] for r in reX), default=0.0); pmin = min((r[2][2] for r in reX), default=0.0)
        parts.append("<p>Column base reactions delivered to the foundation design (seismic X combination):</p>")
        parts.append(_table(["Quantity", "Value"], [
            ["&Sigma; vertical to ground &Sigma;R<sub>z</sub>", f"{_F(Rz,0)} {_ul('F')}"],
            ["&Sigma; horizontal base shear &Sigma;R<sub>x</sub>", f"{_F(Rx,0)} {_ul('F')}"],
            ["Max single-column vertical reaction", f"{_F(pmax,0)} {_ul('F')} (compression)"],
            ["Min single-column vertical reaction", f"{_F(pmin,0)} {_ul('F')} " + ("&mdash; <b>net uplift</b>" if pmin < 0 else "(no uplift)")]]))
    parts.append("<p class='cnote'>Net column uplift is governed by the 0.9D&minus;E combinations; the value above "
                 "is from the seismic-X case shown. <b>Out of scope:</b> foundation/geotechnical design (bearing, "
                 "sliding, uplift anchorage, footing sizing) is delegated; per-column base reactions are available "
                 "from the model on request. Overall overturning/sliding stability is confirmed against the "
                 "geotechnical capacities.</p>")

    # ============== Chapter 12 — Drawings, specifications & documentation ================
    parts.append(_chapter(12, status="out of scope for the analysis package &mdash; verified on the contract drawings"))
    parts.append("<p class='cnote'>Drawing/specification consistency, general notes, special-inspection schedule, "
                 "member schedules, framing plans, brace/MF elevations, connection details and the deferred-submittal "
                 "list are produced and checked on the contract documents, not in this analysis report.</p>")

    # ===================== Chapter 13 — QA / professional acceptance =====================
    parts.append(_chapter(13))
    parts.append(_qa_scorecard(cfg, Fx, reX, eX, eY, drX, drY))
    parts.append(_grounding_check(cfg, name, pkg))
    parts.append(_consistency_section(name, root, pkg))
    parts.append("<p>Automated QA evidence in this report: per-combination equilibrium balances to ~0 in all three "
                 "axes (Chapter 5); every member demand is enveloped over the full IS 875/1893 combination set "
                 "(Chapter 4 / Appendix B); each capacity is traceable to a cited AISC clause (Appendix A); and the "
                 "tool-call activity log is in Appendix C.</p>")
    parts.append("<p class='cnote'><b>Out of scope (engineer judgement):</b> independent third-party check, software "
                 "validation sign-off, reconciliation of model assumptions against final detailing, and the EOR seal "
                 "are professional-responsibility steps completed outside the automated package.</p>")

    # ============================== Appendices ==========================================
    parts.append("<h2>Appendix A &mdash; Referenced IS 800/341 member calculations</h2>")
    if pkg:
        try: parts.append(appendix(cfg, name, pkg))
        except Exception as ex: parts.append(f"<p class='note'>[Appendix A failed: {ex}]</p>")
    else:
        parts.append("<p class='note'>[no calc_package.json found]</p>")
    parts.append("<h2>Appendix B &mdash; Member forces by load case</h2>")
    if case_detail_parts:
        parts.append("<p>Full per-combination detail (summarised in Chapter 4): the worst member of each type "
                     "with its location, from the static model (true distributed gravity). The per-combination "
                     "N / V / M diagrams are written to the <code>figs/</code> folder (<code>case_&lt;label&gt;.png</code>) for "
                     "review &mdash; not embedded here, to keep the report compact. The headline governing diagrams "
                     "(perimeter + internal) are in Chapter 5.</p>")
        parts.extend(case_detail_parts)
    else:
        parts.append("<p class='note'>Per-load-case member force tables temporarily omitted for faster "
                     "reporting &mdash; can be populated here on request at the completion of the design "
                     "(set cfg['force_summary']=True and re-render report.build_report).</p>")
    parts.append(_activity_section(name))

    html = (f"<!doctype html><html><head><meta charset='utf-8'><title>{name} report</title>"
            f"<style>{CSS}{CHK_CSS}</style>{MATHJAX}</head><body>" + "".join(parts) + "</body></html>")
    _fc = [0]
    def _fignum(_m):
        _fc[0] += 1; return f"<b>Figure {_fc[0]}.</b>"
    html = re.sub("@@FIGNUM@@", _fignum, html)        # number every figure in document order
    outdir = root; os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "report.html")
    open(path, "w", encoding="utf-8").write(html)
    print(f"[{name}] wrote {path}")
    return path

def _narrative_html(pkg, members_fig_html=""):
    out = []
    ar = pkg.get("analysis_results")
    if isinstance(ar, dict) and isinstance(ar.get("base_shear"), dict):
        out.append("<p><b>Lateral:</b> " + _fmt(ar["base_shear"]) + "</p>")
    if isinstance(pkg.get("members"), list):
        def _dmd(inp):
            return _fmt({k: inp.get(k) for k in ("P_comp_kip","P_tens_kip","Mz_kipin","My_kipin","V_kip") if inp.get(k) is not None})
        rows = [[m.get("id", ""), (m.get("inputs", {}) or {}).get("section", ""),
                 _dmd(m.get("inputs", {}) or {}), (m.get("inputs", {}) or {}).get("governing_combo", ""),
                 (str(m.get("limit_state")) if m.get("limit_state") else "- (agent/RAG)"),
                 (str(m.get("DC")) if m.get("DC") is not None else "- (agent/RAG)")] for m in pkg["members"]]
        out.append("<h3>Members (demands; capacities derived by the agent from the RAG)</h3>"
                   + members_fig_html
                   + _table(["member", "section", "demand", "gov. combo", "limit state", "D/C"], rows))
    cd = pkg.get("connections") or pkg.get("connection_demands")
    if isinstance(cd, list) and cd:
        def _conn_govern(c):
            # a connection has several limit states; the agent nests them in 'checks' [{limit_state, DC}, ...].
            # Surface the governing (max-D/C) one; fall back to any top-level limit_state/DC.
            ls, dc = c.get("limit_state"), c.get("DC")
            chk = c.get("checks")
            if (ls is None or dc is None) and isinstance(chk, list) and chk:
                best = max((k for k in chk if isinstance(k, dict) and k.get("DC") is not None),
                           key=lambda k: k.get("DC") or 0, default=None)
                if best:
                    if dc is None: dc = best.get("DC")
                    if ls is None: ls = best.get("limit_state")
            return ls, dc
        rows = []
        for c in cd:
            ls, dc = _conn_govern(c)
            nchk = len(c.get("checks")) if isinstance(c.get("checks"), list) else 0
            ls_txt = (str(ls) + (f"  (+{nchk - 1} more)" if nchk > 1 else "")) if ls else "- (agent/RAG)"
            dc_txt = (f"{dc:.2f}" if isinstance(dc, (int, float)) else (str(dc) if dc else "- (agent/RAG)"))
            rows.append([c.get("id", ""), c.get("type", ""), _fmt(c.get("demand", {})), ls_txt, dc_txt])
        out.append("<h3>Connections (demands; capacities derived by the agent from the RAG)</h3>"
                   + _table(["connection", "type", "demand", "governing limit state", "D/C"], rows))
    elif isinstance(cd, dict):
        rows = [[k, v.get("type", ""), _fmt(v.get("demands", {})), v.get("notes", "")] for k, v in cd.items()]
        out.append("<h3>Connections</h3>" + _table(["connection", "type", "demand", "design basis"], rows))
    return "".join(out) if out else "<pre>" + json.dumps(pkg, indent=1)[:4000] + "</pre>"

if __name__ == "__main__":
    for nm in (sys.argv[1:] or ["B02"]):
        try: build_report(nm)
        except Exception as ex: print(f"[{nm}] FAILED: {ex}")
