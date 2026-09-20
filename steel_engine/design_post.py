"""
design_post.py  --  ANALYSIS / DEMAND extraction.

Demands only: this module runs one factored combination through P-Delta and extracts member forces. Member,
connection and Section 12 CAPACITIES are computed in code (WP2.3-2.5) by
  * india_is800.member_check_is800(member, combo_forces)   -- IS 800 7.1.2 / 8.2 / 8.4 / 9.3 per combination
  * india_connections.*                                      -- IS 800 10.3 / 10.4 / 10.5 / 6.4 / 7.4
  * india_is800_s12.section12_checks(system, model_data, cfg) -- IS 800 Section 12 (+ IS 18168 EBF links)
and fed with run_case_member_forces() below (concurrent P, Mz, My, V per element and per combination).

India SI path: engine unit system N-mm-sec - demands are N, N-mm. Legacy kip-in only for units='kip-in'.

What this module provides:
  * run_case(cfg, fD, fL, fLr, lateral) -- per-element envelope-style DEMANDS {tag: (N, Mz, My, V)}.
  * run_case_member_forces(...) -- per-element signed end forces for ONE combination in the format expected by
    india_is800.member_check_is800 (P_N + compression, bending-moment-diagram end values, sagging +).
  * _beam_grav(...) -- the beam gravity span moment/shear added to the joint-lumped model.
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
        if roof:
            # WP2.1.5 / HR800-22: roof imposed load from cfg (IS 875-2 Table 2: 0.75 or 1.5 kN/m2) - snow, when
            # present, is carried by the fLr slot as a separate load case; never a hard-coded 1.0.
            snow = float(cfg.get("snow", 0.0) or 0.0)
            if snow > 0:
                LrSp = snow
            elif cfg.get("Lr") is not None:
                LrSp = float(cfg["Lr"])
            else:
                raise ValueError("cfg['Lr'] (roof imposed load, kN/m2, IS 875-2 Table 2) is required on the SI path")
        else:
            LrSp = 0.0
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


def run_case_member_forces(cfg, fD, fL, fLr, lateral, *, combo=None, family="table4"):
    """ONE factored combination -> {tag: force record} for india_is800.member_check_is800 / section12_checks.

    Record: {combo, family, kind, section, P_N (+compression), Mz_i_Nmm, Mz_j_Nmm (strong axis), My_i_Nmm,
    My_j_Nmm (weak axis), Mz_mid_Nmm (beams: end mean + gravity span moment), Vy_N, Vz_N}.
    Moments are bending-moment-diagram values (beams: sagging +, i.e. top flange in compression, for the standard
    beam transform vecxz = +Z); single curvature gives equal signs at the two ends (Table 18 psi > 0).
    family: 'table4' | '12.2.3' | ... (the caller passes the load-plan family so Section 12 checks can select).
    """
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
        rec = {"combo": combo, "family": family, "kind": kind, "section": sec, "P_N": -bf[0]}
        if kind == "brace":
            rec.update(Mz_i_Nmm=0.0, Mz_j_Nmm=0.0, My_i_Nmm=0.0, My_j_Nmm=0.0)
            out[t] = rec
            continue
        L = math.dist(ops.nodeCoord(n1), ops.nodeCoord(n2))
        if kind == "beam":            # beams: strong axis = basic My (Iy_local = strong, transf 3)
            si, sj, wi, wj = bf[3], bf[4], bf[1], bf[2]
        else:                          # columns: strong axis = basic Mz
            si, sj, wi, wj = bf[1], bf[2], bf[3], bf[4]
        Mzi, Mzj = si, -sj
        Myi, Myj = wi, -wj
        Vy = abs(si + sj) / L
        Vz = abs(wi + wj) / L
        rec.update(Mz_i_Nmm=Mzi, Mz_j_Nmm=Mzj, My_i_Nmm=Myi, My_j_Nmm=Myj, Vy_N=Vy, Vz_N=Vz)
        if kind == "beam":
            Mg, Vg = _beam_grav(cfg, n1, n2, fD, fL, fLr)
            rec["Mz_mid_Nmm"] = 0.5 * (Mzi + Mzj) + Mg
            rec["Vy_N"] = Vy + Vg
        out[t] = rec
    return out, info
