"""X01 -- IS 1893 (Part 1):2016 Table 5(ii) (Amd 2) flexible-floor-diaphragm 3-D dynamic analysis.

Corpus (engineering_rag_india, IS_1893_Part_1_2016, Table 5(ii), Amd 2 Nov 2020, last para substituted):
  'In a building with re-entrant corners, three-dimensional dynamic analysis method with flexible floor diaphragm
   shall be adopted to capture the concentration of forces generated in the re-entrant corners especially in the
   floor diaphragm and special elements adjoining the re-entrant corner. This is in addition to the case of rigid
   diaphragm analysis, if applicable, and the worst effect considered.'
7.6.4: 'A floor diaphragm shall be considered to be flexible, if it deforms such that the maximum lateral
   displacement measured from the chord of the deformed shape at any point of the diaphragm is more than 1.2 times
   the average displacement of the entire diaphragm (see Fig. 6).'

Model (flexible variant of the SAME frame model -- static_model.build_static, so the column / beam / brace element
tags equal those of the rigid RSA of engine3d.rsa_analysis and the responses can be enveloped tag by tag):
  * the rigidDiaphragm constraints of the builder are intercepted and NOT applied; the diaphragm masters are fixed;
  * every framed bay panel (four corner nodes in the level's diaphragm) gets elastic ShellMITC4 membrane elements
    (ElasticMembranePlateSection, plate bending x 1e-6 so the deck adds no out-of-plane frame action), mesh 2 x 2 per
    panel by default (mid-edge nodes = the beam mid nodes where a beam exists), in-plane stiffness from the declared
    cfg['diaphragm_stiffness'] (EOR input);
  * the IS 1893 7.4 floor mass (engine3d.floor_w / g) is lumped to the deck nodes by tributary area (not to a master);
  * modes (7.7.5.2: enough for 90 % modal mass per direction), Ak per mode (6.4.2 RSA branch, R per direction), CQC
    (7.7.5.3(a)), and the same 7.7.3.1 scaling to V-bar_B per direction as the rigid run;
  * 7.8.2 accidental eccentricity: the static torsion cases of the combination set act on the rigid model exactly as
    for the rigid run (the envelope merges the RSA part); drift / 7.6.4 checks on the flexible model apply the
    7.8.2 torsion moments as a mass-proportional rotational force field about each level's mass centre.
"""
from __future__ import annotations

import hashlib
import math

import openseespy.opensees as ops

T5II_CLAUSE = "IS 1893 (Part 1):2016 Table 5(ii) (Amd 2)"
T5II_QUOTE = ("IS 1893 (Part 1):2016 Table 5(ii) (Amd 2, Nov 2020): 'In a building with re-entrant corners, "
              "three-dimensional dynamic analysis method with flexible floor diaphragm shall be adopted to capture the "
              "concentration of forces generated in the re-entrant corners especially in the floor diaphragm and "
              "special elements adjoining the re-entrant corner. This is in addition to the case of rigid diaphragm "
              "analysis, if applicable, and the worst effect considered.'")
Q_7_6_4 = ("IS 1893 (Part 1):2016 7.6.4: 'A floor diaphragm shall be considered to be flexible, if it deforms such that "
           "the maximum lateral displacement measured from the chord of the deformed shape at any point of the "
           "diaphragm is more than 1.2 times the average displacement of the entire diaphragm (see Fig. 6).'")
EC_IS456 = ("Ec = 5000 sqrt(fck) MPa, IS 456:2000 6.2.3.1 (IS 456 is not in the corpus: EOR-labelled default, verify)")
MODEL_TEXT = ("rigidDiaphragm constraints removed; each framed bay panel = elastic ShellMITC4 membrane elements "
              "(ElasticMembranePlateSection, plate bending x 1e-6), %s mesh per panel; floor mass (IS 1893 7.4) "
              "lumped to the deck nodes by tributary area; RSA as the rigid run (7.7.5, CQC, 7.7.3.1 scaling to "
              "V-bar_B per direction); 7.8.2 accidental torsion by the same static torsion cases as the rigid run")
ENVELOPE_TEXT = ("Table 5(ii) 'worst effect': every EQ combination is solved with the rigid-run and with the "
                 "flexible-run RSA responses (same gravity / 7.8.2 torsion static parts; the rigid records carry the "
                 "india_diaphragm collector / chord forces, the flexible records the beam axial forces of the deck "
                 "model); per member and combination "
                 "each record component keeps the larger |value| (sign of the larger kept; Mmaj_sag_max keeps the "
                 "larger signed value)")

DECK_NODE0 = 8_000_000          # deck-only nodes (panel centres, mid-edges without a beam)
DECK_ELE0 = 8_000_000           # deck shells
DECK_SEC = 800_001              # ElasticMembranePlateSection tag
EP_MOD = 1.0e-6                 # plate-bending modifier (membrane only)
_SAG = 8                        # static_model.REC_FIELDS index of Mmaj_sag_max
_CACHE = {}


class FlexibleDiaphragmError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------------------------
# trigger and declared stiffness
# ---------------------------------------------------------------------------------------------------------------
def trigger(cfg, irregularity=None):
    """(run?, why).  Automatic for a re-entrant plan (the H01 15 % projection test, IS 1893 Table 5(ii)) or on
    cfg['flexible_diaphragm_analysis'] = True; cfg['flexible_diaphragm_analysis'] = False opts out (the Table 5(ii)
    gate then stays unsatisfied unless an EOR record is given).  The private key '_flexible_diaphragm_run' is ignored."""
    flag = (cfg or {}).get("flexible_diaphragm_analysis")
    if flag is False:
        return False, "cfg['flexible_diaphragm_analysis'] = False (engine run declined)"
    if flag is True:
        return True, "cfg['flexible_diaphragm_analysis'] = True"
    if irregularity is None:
        import engine3d as E
        reent = bool(E.plan_irregularities(cfg).get("reentrant"))
    else:
        r = irregularity.get("reentrant")
        reent = bool(r.get("irregular")) if isinstance(r, dict) else bool(r)
    if reent:
        return True, "re-entrant plan (IS 1893 Table 5(ii) 15 % projection test)"
    return False, None


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def diaphragm_stiffness(cfg):
    """(record | None, error | None) from cfg['diaphragm_stiffness'] (EOR input):
      {'type': 'rc_slab' | 'metal_deck' | 'custom',
       one of: 'Gd_kN_per_m' (in-plane shear stiffness per unit width, = N/mm) | 'G_eff_MPa' + 't_mm' |
               'E_MPa' + 't_mm' | ('rc_slab') 't_mm' + 'fck_MPa' | ('metal_deck') 'topping_t_mm' + 'fck_MPa',
       'source' (required), 'cite', optional 'nu' (default 0.2), 'mesh' (1 or 2, default 2),
       'void_cells' {level: [[i, j], ...]} (panels without deck)}.
    The concrete modulus from fck is IS 456 6.2.3.1 as an EOR-labelled default (verify) -- only when the slab / the
    composite-deck topping thickness is declared; a bare metal deck needs Gd_kN_per_m (product / test value)."""
    ds = (cfg or {}).get("diaphragm_stiffness")
    need = ("cfg['diaphragm_stiffness'] = {type: 'rc_slab'|'metal_deck'|'custom', t_mm | G_eff_MPa | Gd_kN_per_m, "
            "source, cite} (EOR input)")
    if not isinstance(ds, dict) or not ds:
        return None, ("ERROR: %s flexible-diaphragm model needs the declared in-plane deck stiffness %s"
                      % (T5II_CLAUSE, need))
    typ = str(ds.get("type") or "").strip().lower()
    if typ not in ("rc_slab", "metal_deck", "custom"):
        return None, "ERROR: diaphragm_stiffness.type %r not one of rc_slab / metal_deck / custom (%s)" % (ds.get("type"), need)
    src = ds.get("source")
    if not (isinstance(src, str) and src.strip()):
        return None, "ERROR: diaphragm_stiffness.source missing (who supplied the deck stiffness; %s)" % need
    nu = ds.get("nu")
    nu = float(nu) if nu is not None else 0.2
    if not (0.0 <= nu < 0.5):
        return None, "ERROR: diaphragm_stiffness.nu = %r outside [0, 0.5)" % ds.get("nu")
    rec = {"type": typ, "source": src.strip(), "cite": ds.get("cite"), "nu": nu,
           "nu_basis": "declared" if ds.get("nu") is not None else "default 0.2 (EOR to confirm)",
           "mesh": int(ds.get("mesh", 2)), "verify": bool(ds.get("verify", False))}
    if rec["mesh"] not in (1, 2):
        return None, "ERROR: diaphragm_stiffness.mesh must be 1 or 2 (panel subdivision)"
    t = _num(ds.get("t_mm"))
    Gd = _num(ds.get("Gd_kN_per_m"))
    G = _num(ds.get("G_eff_MPa"))
    Em = _num(ds.get("E_MPa"))
    fck = _num(ds.get("fck_MPa"))
    if Gd is not None:
        Gt, basis = Gd, "declared in-plane shear stiffness Gd = %.4g kN/m (= N/mm)" % Gd
        t = t or 100.0                                   # nominal membrane thickness (only E h matters)
    elif G is not None and t is not None:
        Gt, basis = G * t, "declared G_eff %.4g MPa x t %.4g mm" % (G, t)
    elif Em is not None and t is not None:
        Gt, basis = Em * t / (2.0 * (1.0 + nu)), "declared E %.4g MPa x t %.4g mm, G = E / 2(1 + nu)" % (Em, t)
    elif typ == "rc_slab" and t is not None and fck is not None:
        Em = 5000.0 * math.sqrt(fck)
        Gt, basis = Em * t / (2.0 * (1.0 + nu)), "RC slab t %.4g mm, %s = %.0f MPa" % (t, EC_IS456, Em)
        rec["verify"] = True
    elif typ == "metal_deck" and _num(ds.get("topping_t_mm")) and fck is not None:
        t = _num(ds.get("topping_t_mm"))
        Em = 5000.0 * math.sqrt(fck)
        Gt, basis = (Em * t / (2.0 * (1.0 + nu)),
                     "composite deck: concrete topping above the ribs t %.4g mm, %s = %.0f MPa (deck sheet neglected)"
                     % (t, EC_IS456, Em))
        rec["verify"] = True
    elif typ == "metal_deck":
        return None, ("ERROR: metal_deck diaphragm_stiffness needs Gd_kN_per_m (product / test value) or the concrete "
                      "topping (topping_t_mm + fck_MPa, Ec per IS 456 6.2.3.1 as an EOR default) -- %s" % need)
    elif typ == "rc_slab":
        return None, "ERROR: rc_slab diaphragm_stiffness needs t_mm with fck_MPa or E_MPa (or G_eff_MPa) -- %s" % need
    else:
        return None, "ERROR: custom diaphragm_stiffness needs Gd_kN_per_m, or G_eff_MPa / E_MPa with t_mm -- %s" % need
    rec.update(Gt_N_per_mm=Gt, Et_N_per_mm=2.0 * (1.0 + nu) * Gt, h_mm=t, E_eff_MPa=2.0 * (1.0 + nu) * Gt / t,
               basis=basis)
    if not rec.get("cite"):
        rec["cite"] = basis
    rec["void_cells"] = {int(k): [tuple(int(a) for a in p) for p in v]
                         for k, v in dict(ds.get("void_cells") or {}).items()}
    return rec, None


# ---------------------------------------------------------------------------------------------------------------
# flexible model
# ---------------------------------------------------------------------------------------------------------------
def _poly_area(pts):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def build_flexible(cfg, transf="Linear", nseg=6, stiff=None):
    """Build static_model.build_static(cfg) WITHOUT its rigid diaphragms, add the deck membrane and return the
    static-model dict extended with 'deck': {level: {...}} and 'mass_nodes': {tag: (key, level, m, x, y)}."""
    import engine3d as E
    import static_model as SM
    if stiff is None:
        stiff, err = diaphragm_stiffness(cfg)
        if err:
            raise FlexibleDiaphragmError(err)
    calls = []
    real = ops.rigidDiaphragm

    def _skip(*a):
        calls.append(a)
        return 0
    ops.rigidDiaphragm = _skip
    try:
        model = SM.build_static(cfg, transf, nseg)
    finally:
        ops.rigidDiaphragm = real
    NX, NY = cfg["NX"], cfg["NY"]
    z = E.zlevels(cfg)
    NF = len(cfg["heights"])
    dia = {}
    for a in calls:                                          # the last call per master wins (replay adds beam nodes)
        dia[a[1]] = list(a[2:])
    lvl_nodes = {}
    for mst, sl in dia.items():
        try:
            zm = ops.nodeCoord(mst)[2]
        except Exception:
            continue
        k = min(range(len(z)), key=lambda q: abs(z[q] - zm))
        lvl_nodes.setdefault(k, set()).update(sl)
        try:
            ops.fix(mst, 1, 1, 0, 0, 0, 1)                   # the master carries nothing now
        except Exception:
            pass
    tags = set(ops.getNodeTags())
    for k in range(1, NF + 1):
        if k not in lvl_nodes:                               # builder without a diaphragm at k: its grid nodes
            lvl_nodes[k] = {E.ntag(i, j, k) for (i, j) in (model.get("present") or {}).get(k, set())
                            if E.ntag(i, j, k) in tags}
    mids = {}
    for b in model.get("beams") or []:
        ch = b.get("nodes") or []
        if len(ch) >= 3 and (len(ch) - 1) % 2 == 0:
            mids[frozenset((b["A"], b["B"]))] = ch[(len(ch) - 1) // 2]
    ops.section("ElasticMembranePlateSection", DECK_SEC, stiff["E_eff_MPa"], stiff["nu"], stiff["h_mm"], 0.0, EP_MOD)
    mesh = stiff["mesh"]
    nid, eid = DECK_NODE0, DECK_ELE0
    deck, mass_nodes = {}, {}
    for k in range(1, NF + 1):
        members = lvl_nodes.get(k) or set()
        grid_ = {}
        for n in members:
            r = n % 100000
            i, j = r // 100, r % 100
            if n // 100000 == k and n == E.ntag(i, j, k) and 0 <= i <= NX and 0 <= j <= NY:
                grid_[(i, j)] = n
        voids = set(stiff.get("void_cells", {}).get(k, []))
        cells = [(i, j) for i in range(NX) for j in range(NY)
                 if all(c in grid_ for c in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1))) and (i, j) not in voids]
        keyed = {}                                           # (2i+s, 2j+t) -> node tag
        for (i, j), n in grid_.items():
            keyed[(2 * i, 2 * j)] = n
        crd = {}
        area_share = {}
        shells = []
        A_tot = 0.0
        zk = z[k]

        def _node_at(key, xy, edge=None):
            nonlocal nid
            if key in keyed:
                return keyed[key]
            if edge is not None and edge in mids:
                keyed[key] = mids[edge]
                return keyed[key]
            ops.node(nid, xy[0], xy[1], zk)
            ops.fix(nid, 0, 0, 1, 1, 1, 0)
            keyed[key] = nid
            nid += 1
            return keyed[key]
        for (i, j) in cells:
            c = {(s, t): ops.nodeCoord(grid_[(i + s, j + t)])[:2] for s in (0, 1) for t in (0, 1)}

            def P(u, v):                                     # bilinear point of the panel, u, v in [0, 1]
                return tuple((1 - u) * (1 - v) * c[(0, 0)][q] + u * (1 - v) * c[(1, 0)][q]
                             + u * v * c[(1, 1)][q] + (1 - u) * v * c[(0, 1)][q] for q in (0, 1))
            if mesh == 1:
                quads = [[(0, 0), (2, 0), (2, 2), (0, 2)]]
            else:
                quads = [[(0, 0), (1, 0), (1, 1), (0, 1)], [(1, 0), (2, 0), (2, 1), (1, 1)],
                         [(1, 1), (2, 1), (2, 2), (1, 2)], [(0, 1), (1, 1), (1, 2), (0, 2)]]
            edge_of = {(1, 0): frozenset((grid_[(i, j)], grid_[(i + 1, j)])),
                       (1, 2): frozenset((grid_[(i, j + 1)], grid_[(i + 1, j + 1)])),
                       (0, 1): frozenset((grid_[(i, j)], grid_[(i, j + 1)])),
                       (2, 1): frozenset((grid_[(i + 1, j)], grid_[(i + 1, j + 1)]))}
            for q in quads:
                ns, pts = [], []
                for (s, t) in q:
                    key = (2 * i + s, 2 * j + t)
                    xy = P(s / 2.0, t / 2.0)
                    n = _node_at(key, xy, edge_of.get((s, t)))
                    ns.append(n); pts.append(xy); crd[n] = xy
                ops.element("ShellMITC4", eid, *ns, DECK_SEC)
                shells.append(eid); eid += 1
                a = _poly_area(pts)
                A_tot += a
                for n in ns:
                    area_share[n] = area_share.get(n, 0.0) + a / 4.0
        m_k = E.floor_w(cfg, k) / E.g
        if A_tot <= 0.0:                                     # no framed panel: spread over the level's grid nodes
            pts_ = list(grid_.values()) or [n for n in members if n in tags]
            area_share = {n: 1.0 for n in pts_}
            A_tot = float(len(pts_)) or 1.0
            for n in pts_:
                crd[n] = ops.nodeCoord(n)[:2]
        inv = {v: kk for kk, v in keyed.items()}
        for n, a in area_share.items():
            mass_nodes[n] = (("deck", k) + tuple(inv.get(n, ("n", n))), k, m_k * a / A_tot, crd[n][0], crd[n][1])
        deck[k] = {"panels": len(cells), "shells": len(shells), "mass_t": m_k, "area_mm2": A_tot if cells else 0.0,
                   "nodes": len(area_share), "no_panel": not cells, "grid_nodes": dict(grid_)}
    model["deck"] = deck
    model["mass_nodes"] = mass_nodes
    model["stiffness"] = stiff
    return model


def _assign_masses(model):
    import engine3d as E
    mn = model["mass_nodes"]
    mmin = min([v[2] for v in mn.values() if v[2] > 0] or [1.0])
    tiny = 1e-8 * mmin
    for t in ops.getNodeTags():
        ops.mass(t, tiny, tiny, tiny, tiny, tiny, tiny)
    for t, (_key, _k, m, _x, _y) in mn.items():
        ops.mass(t, m + tiny, m + tiny, tiny, tiny, tiny, tiny)
    return tiny


def _eigen(cfg, nseg, stiff, nev):
    import contextlib
    import os as _os
    model = build_flexible(cfg, "Linear", nseg, stiff)
    _assign_masses(model)
    # SparseGeneral + RCM: ~10x faster than UmfPack / band storage for the many deck DOF (identical modes)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("SparseGeneral")

    @contextlib.contextmanager
    def _quiet():
        try:
            devnull = open(_os.devnull, "w"); old = _os.dup(2); _os.dup2(devnull.fileno(), 2)
        except Exception:
            yield
            return
        try:
            yield
        finally:
            try:
                _os.dup2(old, 2); _os.close(old); devnull.close()
            except Exception:
                pass
    with _quiet():
        try:
            w2 = ops.eigen("-genBandArpack", nev)
        except Exception:
            w2 = ops.eigen("-fullGenLapack", nev)
    mn = model["mass_nodes"]
    phi = []
    for n in range(1, len(w2) + 1):
        phi.append({mn[t][0]: tuple(ops.nodeEigenvector(t, n)[:2]) for t in mn})
    return model, list(w2), phi


def modal_flexible(cfg, nseg=2, stiff=None, nev=None):
    """Modes of the flexible model with >= 90 % modal mass per direction where reachable (7.7.5.2).
    Returns {w2, T, phi {mode: {key: (ux, uy)}}, mass {key: (level, m, x, y)}, modes [...], Mtot}."""
    if stiff is None:
        stiff, err = diaphragm_stiffness(cfg)
        if err:
            raise FlexibleDiaphragmError(err)
    NF = len(cfg["heights"])
    nev = nev or max(12, 4 * NF)
    while True:
        model, w2, phi = _eigen(cfg, nseg, stiff, nev)
        mn = model["mass_nodes"]
        mass = {v[0]: (v[1], v[2], v[3], v[4]) for v in mn.values()}
        Mt = sum(v[1] for v in mass.values())
        modes = []
        for n, ph in enumerate(phi):
            Mn = sum(mass[k_][1] * (ph[k_][0] ** 2 + ph[k_][1] ** 2) for k_ in mass)
            Lx = sum(mass[k_][1] * ph[k_][0] for k_ in mass)
            Ly = sum(mass[k_][1] * ph[k_][1] for k_ in mass)
            modes.append({"mode": n + 1, "T": 2 * math.pi / math.sqrt(max(w2[n], 1e-12)), "Mn": Mn,
                          "Gx": Lx / Mn if Mn else 0.0, "Gy": Ly / Mn if Mn else 0.0,
                          "mass_x": Lx * Lx / Mn / Mt if Mn else 0.0, "mass_y": Ly * Ly / Mn / Mt if Mn else 0.0})
        cx = sum(m["mass_x"] for m in modes); cy = sum(m["mass_y"] for m in modes)
        cap = min(2 * len(mass) - 1, 150)
        if (cx >= 0.90 and cy >= 0.90) or nev >= cap:
            break
        nev = min(2 * nev, cap)
    deck = {k: {kk: vv for kk, vv in d.items() if kk != "grid_nodes"} for k, d in model["deck"].items()}
    return {"w2": w2, "T": [m["T"] for m in modes], "phi": phi, "mass": mass, "modes": modes, "Mtot": Mt,
            "cum_x": cx, "cum_y": cy, "nev": nev, "deck": deck, "stiffness": stiff}


def rsa_flexible(cfg, nseg=6, zeta=0.05):
    """IS 1893 7.7.5 RSA of the flexible-diaphragm model (same spectrum, CQC, 7.7.3.1 scaling to V-bar_B per
    direction as engine3d.rsa_analysis).  Returns the rsa_analysis-shaped dict {'X', 'Y', 'modes', 'elements'} plus
    'deck', 'stiffness', 'cum_x/y'.  Raises FlexibleDiaphragmError when the deck stiffness is not declared."""
    import numpy as np
    import engine3d as E
    import india_seismic as IS
    import static_model as SM
    stiff, err = diaphragm_stiffness(cfg)
    if err:
        raise FlexibleDiaphragmError(err)
    prm = E.india_seismic_params(cfg)
    vrec = {d: E.VBbar_record(cfg, d) for d in ("X", "Y")}
    key = hashlib.md5(repr((E._model_key(cfg), sorted(stiff.items(), key=str), sorted(prm.items(), key=str),
                            [round(vrec[d]["used_N"], 3) for d in ("X", "Y")], nseg, zeta)).encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    md = modal_flexible(cfg, nseg=2 if stiff["mesh"] == 2 else 1, stiff=stiff)
    mass = md["mass"]
    nm = len(md["T"])
    Ad = {d: [IS.design_Ah(prm["Z"], prm["I"], prm["R_" + d.lower()], T, prm["soil"], "RSA") for T in md["T"]]
          for d in ("X", "Y")}
    w = [math.sqrt(max(x, 1e-12)) for x in md["w2"]]
    rho = np.array([[IS.cqc_rho(w[i], w[j], zeta) for j in range(nm)] for i in range(nm)])
    model = build_flexible(cfg, "Linear", nseg, stiff)
    bykey = {v[0]: t for t, v in model["mass_nodes"].items()}
    miss = [k_ for k_ in mass if k_ not in bykey]
    if miss:
        raise FlexibleDiaphragmError("flexible model: %d mass nodes of the modal model not in the response model" % len(miss))
    # one pattern per mode on a Path series that is 1.0 only at pseudo-time n + 1: step n solves mode n alone, and
    # the domain never changes between the steps, so the linear system is factorised once (-factorOnce)
    for n in range(nm):
        ph = md["phi"][n]
        vals = [0.0] * (nm + 2)
        vals[n + 1] = 1.0
        ops.timeSeries("Path", 500 + n, "-dt", 1.0, "-values", *vals)
        ops.pattern("Plain", 500 + n, 500 + n)
        for k_, (lv, m, _x, _y) in mass.items():
            ops.load(bykey[k_], E.g * m * ph[k_][0], E.g * m * ph[k_][1], 0.0, 0.0, 0.0, 0.0)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("SparseGeneral")    # factorised once
    ops.test("NormDispIncr", 1e-9, 10); ops.algorithm("Linear", "-factorOnce")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static")
    unit = []
    for n in range(nm):
        if ops.analyze(1) != 0:
            raise FlexibleDiaphragmError("flexible RSA: unit modal load %d did not solve" % (n + 1))
        unit.append(SM._responses(model))
    tags = list(unit[0].keys())
    NF = len(cfg["heights"])
    out = {"modes": [], "elements": {}, "method": "IS 1893 7.7.5 RSA, CQC (7.7.5.3), zeta 0.05, flexible diaphragm",
           "params": prm, "deck": md["deck"], "stiffness": stiff, "nev": md["nev"]}
    for n, m_ in enumerate(md["modes"]):
        out["modes"].append({"mode": n + 1, "T": m_["T"], "Sa_g": IS.sa_over_g(m_["T"], prm["soil"], "RSA"),
                             "Ak_x": Ad["X"][n], "Ak_y": Ad["Y"][n], "mass_x": m_["mass_x"], "mass_y": m_["mass_y"]})
    for d in ("X", "Y"):
        ci = 0 if d == "X" else 1
        coef = np.array([md["modes"][n]["G" + d.lower()] * Ad[d][n] for n in range(nm)])
        Vn = np.array([coef[n] * E.g * sum(m * md["phi"][n][k_][ci] for k_, (lv, m, _x, _y) in mass.items())
                       for n in range(nm)])
        VB = float(math.sqrt(max(Vn @ rho @ Vn, 0.0)))
        Vst = []
        for k in range(1, NF + 1):
            vk = np.array([coef[n] * E.g * sum(m * md["phi"][n][k_][ci] for k_, (lv, m, _x, _y) in mass.items() if lv >= k)
                           for n in range(nm)])
            Vst.append(float(math.sqrt(max(vk @ rho @ vk, 0.0))))
        Vbar = vrec[d]["used_N"]
        scale = max(1.0, Vbar / VB) if VB > 0 else 1.0
        E_ = {}
        for t in tags:
            Rm = np.array([unit[n][t] * coef[n] for n in range(nm)])
            E_[t] = scale * np.sqrt(np.maximum(np.einsum("ic,ij,jc->c", Rm, rho, Rm), 0.0))
        cum = sum(m_["mass_" + d.lower()] for m_ in md["modes"])
        out[d] = {"VB_rsa_N": VB, "VBbar_N": Vbar, "scale": scale, "VB_scaled_N": VB * scale,
                  "R": prm["R_" + d.lower()], "mass_participation": cum, "storey_shear_N": Vst,
                  "storey_shear_scaled_N": [v * scale for v in Vst], "VBbar_record": vrec[d],
                  "cite": "IS 1893 7.7.3.1 (Amd 2): force responses x V-bar_B/VB when VB < V-bar_B"}
        out["elements"][d] = E_
    _CACHE[key] = out
    return out


# ---------------------------------------------------------------------------------------------------------------
# drift and 7.6.4 on the flexible model (static design forces, gamma 1.0)
# ---------------------------------------------------------------------------------------------------------------
def _level_fields(model):
    lv = {}
    for t, (key, k, m, x, y) in model["mass_nodes"].items():
        lv.setdefault(k, []).append((t, m, x, y))
    return lv


def _lateral_loads(lv_nodes, Fd, mz):
    """Storey force Fd = (fx, fy) spread by nodal mass, plus a torque mz as the mass-proportional rotational field
    f = mz m (-(y - yc), (x - xc)) / sum(m r^2) about the level's mass centre."""
    M = sum(m for (_t, m, _x, _y) in lv_nodes) or 1.0
    xc = sum(m * x for (_t, m, x, _y) in lv_nodes) / M
    yc = sum(m * y for (_t, m, _x, y) in lv_nodes) / M
    Jp = sum(m * ((x - xc) ** 2 + (y - yc) ** 2) for (_t, m, x, y) in lv_nodes)
    out = {}
    for (t, m, x, y) in lv_nodes:
        fx = Fd[0] * m / M; fy = Fd[1] * m / M
        if mz and Jp > 0:
            fx += -mz * m * (y - yc) / Jp
            fy += mz * m * (x - xc) / Jp
        out[t] = (fx, fy)
    return out


def drift_and_764(cfg, eccentricity=None, support_nodes=None):
    """IS 1893 7.11.1.1 storey drift at every column line of the flexible model (1.0 DL + 1.0 LL P-Delta gravity
    state, design ESM storey forces spread by mass + the 7.8.2 torsion variants, both signs; linear increments about
    the gravity state) and the 7.6.4 in-plane deformation per level: max deviation of the deck-node displacement from
    the chord (rigid-body plane motion fitted to the lateral-load-resisting nodes of the level) vs the average storey
    drift and vs the average displacement of the entire diaphragm."""
    import engine3d as E
    import india_combos as IC
    import india_loads as IL
    import india_diaphragm as DIA
    import static_model as SM
    stiff, err = diaphragm_stiffness(cfg)
    if err:
        raise FlexibleDiaphragmError(err)
    plan = cfg.get("load_plan") or {}
    if eccentricity is None:
        eccentricity = E.design_eccentricities(cfg)
    sc = IL._story_force_scale(plan)
    NF = len(cfg["heights"])
    dex = set(int(k) for k in (cfg.get("drift_exempt_stories") or {}))
    model = build_flexible(cfg, "PDelta", 2 if stiff["mesh"] == 2 else 1, stiff)
    lv = _level_fields(model)
    present = model["present"]
    tags = set(ops.getNodeTags())
    gnodes = {(i, j, k): E.ntag(i, j, k) for k in range(NF + 1) for (i, j) in present.get(k, set())
              if E.ntag(i, j, k) in tags}
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    E._apply_nodal_gravity(cfg, {"NF": NF, "present": {k: {(i, j) for (i, j, kk) in gnodes if kk == k}
                                                       for k in range(NF + 1)}}, 1.0, 1.0)
    if SM._solve_newton() != 0:
        raise FlexibleDiaphragmError("flexible drift gravity state did not converge")
    uG = {t: tuple(ops.nodeDisp(t)[:2]) for t in tags}
    SM._to_linear_increments()
    out = {"drift": {}, "d764": {}, "clause": "IS 1893 7.11.1.1 / 7.8.2 / 7.6.4 (flexible-diaphragm model)"}
    ptag = 900
    for d in ("X", "Y"):
        F = E.india_story_forces(cfg, d)
        if not F:
            continue
        di = 0 if d == "X" else 1
        tor = IC.torsion_moments(plan, cfg, d, eccentricity)
        worst = [0.0] * NF
        for v in (None, "a", "b"):
            ptag += 1
            ops.pattern("Plain", ptag, 77)
            for k in range(1, NF + 1):
                fx, fy, mz = F.get(k, (0.0, 0.0, 0.0))
                if v:
                    mz += float((tor.get(v) or {}).get(k, 0.0)) * sc
                for t, (px, py) in _lateral_loads(lv.get(k, []), (fx, fy), mz).items():
                    ops.load(t, px, py, 0.0, 0.0, 0.0, 0.0)
            if ops.analyze(1) != 0:
                raise FlexibleDiaphragmError("flexible drift analysis %s/%s failed" % (d, v))
            uL = {t: ops.nodeDisp(t)[di] - uG[t][di] for t in tags}
            ops.remove("loadPattern", ptag)
            ops.analyze(1)
            for sgn in (1.0, -1.0):
                for k in range(1, NF + 1):
                    if k in dex:
                        continue
                    h = cfg["heights"][k - 1]
                    for (i, j, kk), t in gnodes.items():
                        if kk != k:
                            continue
                        tb = gnodes.get((i, j, k - 1))
                        if tb is None:
                            continue
                        dr = abs((uG[t][di] + sgn * uL[t]) - (uG[tb][di] + sgn * uL[tb])) / h
                        worst[k - 1] = max(worst[k - 1], dr)
            if v is None:
                recs, prev_avg = [], 0.0
                for k in range(1, NF + 1):
                    nodes = lv.get(k, [])
                    if not nodes:
                        continue
                    sup = [(t, x, y) for (t, m, x, y) in nodes
                           if support_nodes is None or t in support_nodes]
                    if len(sup) < 2:
                        sup = [(t, x, y) for (t, m, x, y) in nodes if t in model["deck"][k]["grid_nodes"].values()]
                    xs = sum(x for _t, x, _y in sup) / len(sup); ys = sum(y for _t, _x, y in sup) / len(sup)
                    # least-squares plane rigid motion (ux = a - th (y - ys), uy = b + th (x - xs)) on the supports;
                    # only the component along the force enters (the chord of Fig. 6 in the loaded direction)
                    num = den = 0.0
                    aa = bb = 0.0
                    for (t, x, y) in sup:
                        u = uL[t]
                        if d == "X":
                            aa += u
                        else:
                            bb += u
                    aa /= len(sup); bb /= len(sup)
                    for (t, x, y) in sup:
                        u = uL[t]
                        if d == "X":
                            num += -(y - ys) * (u - aa); den += (y - ys) ** 2
                        else:
                            num += (x - xs) * (u - bb); den += (x - xs) ** 2
                    th = num / den if den > 0 else 0.0
                    dev = [abs(uL[t] - ((aa - th * (y - ys)) if d == "X" else (bb + th * (x - xs))))
                           for (t, m, x, y) in nodes]
                    M = sum(m for (_t, m, _x, _y) in nodes) or 1.0
                    avg = sum(m * uL[t] for (t, m, _x, _y) in nodes) / M
                    sd = abs(avg - prev_avg)
                    cl = DIA.classify_7_6_4(delta_max_from_chord_mm=max(dev), delta_avg_mm=sd or None)
                    recs.append({"level": k, "delta_max_from_chord_mm": max(dev), "delta_avg_diaphragm_mm": abs(avg),
                                 "avg_storey_drift_mm": sd, "ratio": (max(dev) / sd) if sd else None,
                                 "ratio_vs_avg_displacement": (max(dev) / abs(avg)) if avg else None, "limit": 1.2,
                                 "classification": cl.get("classification"), "flexible": cl.get("flexible"),
                                 "chord": "plane rigid-body motion fitted to the level's lateral-load-resisting nodes"
                                          if support_nodes else "plane rigid-body motion fitted to the level's grid nodes"})
                    prev_avg = avg
                out["d764"][d] = recs
        out["drift"][d] = worst
    out["basis"] = ("storey drift (gamma 1.0) at every column line of the flexible model: 1.0 DL + 1.0 LL P-Delta "
                    "gravity state + ESM design storey forces spread by floor mass, 7.8.2 torsion variants (a, b) as a "
                    "mass-proportional rotational field, +F and -F (linear increments about the gravity state)")
    out["cite_7_6_4"] = Q_7_6_4
    out["basis_7_6_4"] = ("in-plane deformation = max deviation of the deck displacement (no torsion variant, lateral "
                          "only) from the chord; 'ratio' = deviation / average storey drift of the diaphragm (the "
                          "conservative reading), 'ratio_vs_avg_displacement' = deviation / average displacement of "
                          "the entire diaphragm (7.6.4 literal); classification on 'ratio' (limit 1.2)")
    return out


# ---------------------------------------------------------------------------------------------------------------
# envelope of the rigid and flexible combination records
# ---------------------------------------------------------------------------------------------------------------
def merge_records(per_case, per_case_flex):
    """In place: per EQ combination and member, each record component = the larger |value| of the rigid and flexible
    runs (sign of the larger kept; Mmaj_sag_max = the larger signed value).  Returns the count of components where
    the flexible run exceeds the rigid run by more than 1 % and the number of merged (combination, member) records."""
    n_flex = n_rec = 0
    for lab, resf in per_case_flex.items():
        if lab.startswith("_") or lab not in per_case:
            continue
        resr = per_case[lab]
        for fs, rf in resf.items():
            rr = resr.get(fs)
            if rr is None:
                continue
            m = []
            for q, (a, b) in enumerate(zip(rr, rf)):
                if q == _SAG:
                    take_f = b > a
                else:
                    take_f = abs(b) > abs(a) * (1.0 + 1e-9) + 1e-9
                m.append(b if take_f else a)
                n_flex += int(abs(b) > abs(a) * 1.01 + 1.0)
            if len(rr) > len(m):
                m += list(rr[len(m):])
            resr[fs] = tuple(m)
            n_rec += 1
    return n_flex, n_rec


def group_ratios(per_case_rigid, per_case_flex, role_of_fs, labels):
    """{role: {field: {rigid, flexible, ratio}}}: the largest |value| over the EQ combinations and the members of the
    group in each run (N, N-mm) and flexible / rigid (None when the rigid value is ~0, e.g. beam axial force under
    a rigid diaphragm without collectors).  Fields N, N_LAT, V_LAT, Mmaj, Mmin."""
    import static_model as SM
    idx = {f: SM.REC_FIELDS.index(f) for f in ("N", "N_LAT", "V_LAT", "Mmaj", "Mmin")}
    acc = {}
    for lab in labels:
        rr, rf = per_case_rigid.get(lab) or {}, per_case_flex.get(lab) or {}
        for fs, a in rr.items():
            b = rf.get(fs)
            role = role_of_fs.get(fs)
            if b is None or role is None:
                continue
            g = acc.setdefault(role, {f: [0.0, 0.0] for f in idx})
            for f, q in idx.items():
                if q < len(a) and q < len(b):
                    g[f][0] = max(g[f][0], abs(a[q])); g[f][1] = max(g[f][1], abs(b[q]))
    return {role: {f: {"rigid": round(v[0], 1), "flexible": round(v[1], 1),
                       "ratio": (round(v[1] / v[0], 3) if v[0] > 1.0 else None)} for f, v in g.items()}
            for role, g in acc.items()}
