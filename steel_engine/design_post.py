"""
design_post.py  --  ANALYSIS / DEMAND extraction only. NO coded member capacities.

This module deliberately contains NO IS 800 / AISC member-design equations. The framework computes
structural DEMANDS (the OpenSees model, IS loads from load_plan, the second-order P-Delta analysis);
member capacity checks are NOT coded anywhere. The design agent must query the IS 800 / IS 808 /
IS 816 / IS 4000 RAG, derive the governing limit-state equation for each member itself, compute the
capacity and D/C, cite the clause, and write its own calc_package.json. There is no oracle to fall
back on.

India SI path (wave 2): engine unit system N-mm-sec when activated — demands are (N, N·mm, N·mm, N).
Legacy kip-in remains for units='kip-in' / force_kip_in.

What this module provides:
  * run_case(cfg, fD, fL, fLr, lateral) -- analyse ONE factored load combination through proper
    P-Delta and return per-element DEMANDS {tag: (N, Mz, My, V)}. Pure structural analysis.
  * _beam_grav(...) -- the beam gravity span moment/shear added to the joint-lumped model
    (analysis bookkeeping, not a code check).

The India load_plan combination set + the per-member demand envelope live in
design_pipeline.py; the report scaffold lives in report.py. Neither computes a member capacity.
"""
import os, sys, math, csv, json
import openseespy.opensees as ops
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine3d as E
import sections as S


# ---------- beam gravity span moment/shear (analysis bookkeeping, NOT a code check) ----------
def _beam_grav(cfg, n1, n2, fD, fL, fLr):
    """Beam gravity span moment & shear (w*L^2/8, w*L/2) over the tributary bay.

    SI (N-mm): w in N/mm, pressures kN/m², L in mm → moment N·mm, shear N.
    Legacy kip-in: w in kip/in, pressures psf, L in in → moment kip-in, shear kip.
    """
    a = ops.nodeCoord(n1); b = ops.nodeCoord(n2); NF = len(cfg["heights"])
    k = n1 // 100000; roof = (k == NF)
    Lx = abs(a[0]-b[0]); Ly = abs(a[1]-b[1]); L = max(Lx, Ly)
    try:
        si = (E.unit_system() == "N-mm") or str(cfg.get("units") or "").upper().startswith("N-MM")
    except Exception:
        si = str(cfg.get("units") or "").upper().startswith("N-MM")
    if si:
        if cfg.get("lean_gravity"):
            # Lateral-frame beams carry only spandrel cladding line load (leaning gravity interior).
            th = cfg["heights"][k-1]; th = th if not roof else th/2.0  # mm
            w = fD * float(cfg.get("clad") or 0.0) * th / 1000.0      # kN/m = N/mm
            return w*L*L/8.0, w*L/2.0
        trib = cfg["SY"] if Lx >= Ly else cfg["SX"]  # mm
        Dp = cfg["D_roof"] if roof else cfg["D_floor"]
        Lp = 0.0 if roof else cfg["L_floor"]
        LrSp = (cfg.get("snow", 0.0) if cfg.get("snow", 0.0) > 0 else 1.0) if roof else 0.0  # kN/m²
        # p[kN/m²] * trib[mm]/1000 = kN/m = N/mm
        w = (fD*Dp + fL*Lp + fLr*LrSp) * trib / 1000.0
        return w*L*L/8.0, w*L/2.0
    # ---- legacy kip-in ----
    if cfg.get("lean_gravity"):
        th = cfg["heights"][k-1]/12.0; th = th if not roof else th/2.0   # ft
        w = fD * cfg.get("clad", 0.0) * th / 1000.0 / 12.0               # kip/in
        return w*L*L/8.0, w*L/2.0
    trib = cfg["SY"] if Lx >= Ly else cfg["SX"]
    Dp = cfg["D_roof"] if roof else cfg["D_floor"]
    Lp = 0.0 if roof else cfg["L_floor"]
    LrSp = (cfg.get("snow", 0.0) if cfg.get("snow", 0.0) > 0 else 20.0) if roof else 0.0
    w = (fD*Dp + fL*Lp + fLr*LrSp) / 1000.0 / 144.0 * trib     # kip/in
    return w*L*L/8.0, w*L/2.0


def run_case(cfg, fD, fL, fLr, lateral):
    """Analyse ONE factored load combination (supplied by the caller) under proper P-Delta and
    return per-element DEMANDS {tag: (N, Mz, My, V)}. The caller chooses the factors and the
    lateral pattern (IS partial-factor combinations (from load_plan): Ev in fD, rho, Omega0, 100/30, accidental torsion);
    this runs the actual nonlinear analysis, so no invalid superposition of factored results.
        fD, fL, fLr : dead / live / roof-live(or snow) load factors for THIS combination.
        lateral     : dict floor-> (fx, fy, mz) at the diaphragm master, scaled from the engine's
                      elementary patterns (E.elf seismic / E.wind_forces wind)."""
    info = E.build(cfg, "PDelta"); NF = info["NF"]; pres = info["present"]
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for k in range(1, NF+1):
        npts = len(pres[k])
        p = (fD*E.floor_dead(cfg, k) + fL*E.floor_live(cfg, k) + fLr*E.floor_roofLrS(cfg, k))/npts
        for (i, j) in pres[k]:
            ops.load(E.ntag(i, j, k), 0, 0, -p, 0, 0, 0)
    for k, (fx, fy, mz) in lateral.items():
        ops.load(E.mtag(k), fx, fy, 0, 0, 0, mz)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-7, 200); ops.algorithm("Newton")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static")
    ops.analyze(1)
    out = {}
    for (t, kind, sec, n1, n2) in info["ele"]:
        bf = ops.basicForce(t)
        if kind == "brace":
            out[t] = (bf[0], 0.0, 0.0, 0.0)            # (N, Mz, My, V); tension +
        else:
            c1, c2 = ops.nodeCoord(n1), ops.nodeCoord(n2)
            L = math.dist(c1, c2)
            N = bf[0]
            m_z = max(abs(bf[1]), abs(bf[2])); m_y = max(abs(bf[3]), abs(bf[4]))
            V = max((abs(bf[1])+abs(bf[2]))/L, (abs(bf[3])+abs(bf[4]))/L)
            if kind == "beam":
                # beam vertical/in-plane bending is the STRONG-axis demand (local-y basic moment);
                # add the gravity span moment (the model lumps floor gravity at the joints).
                Mg, Vg = _beam_grav(cfg, n1, n2, fD, fL, fLr)
                Mz = max(m_z, m_y) + Mg; My = min(m_z, m_y); V = max(V, Vg)
            else:                                   # column: strong axis = local z
                Mz = m_z; My = m_y
            out[t] = (N, Mz, My, V)
    return out, info
