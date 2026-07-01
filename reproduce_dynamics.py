"""
reproduce_dynamics.py - regenerate the execution-dynamics results (Fig. 3)
of the manuscript

    "Earthworks Planning through Dynamically Clustered Cut-and-Fill Sequencing"

directly from the released example data (S1_pointvol.csv, S2_gridcell.csv) and
code (S3_tools.py, S4_dynamics.py). No AutoCAD / GCM++ is required.

The driver
  1. solves the allocation and clusters the transports exactly as
     reproduce.py does (same locked parameters),
  2. builds the gridstep working surface and checks site-wide drainage and
     the adjacent-face guard,
  3. sequences the largest (deepest-cut, long-haul) cluster with the ADOPTED
     drainage-safe face-advance rule and with the evaluated alternatives
     (row-major, serpentine, Hilbert, random),
  4. re-runs the drainage check after every excavation step of every
     ordering, and
  5. verifies that every loaded cut-to-fill haul of the cluster descends.

Run:
    python reproduce_dynamics.py
"""

import numpy as np
import pandas as pd

import S3_tools as tools
import S4_dynamics as dyn

# Locked case parameters (see manuscript and reproduce.py) --------------------
D_BREAK = 100          # bilinear break distance [m]
C1, C2, C3 = 0.03, 0.05, 5
BULK = 1.25            # bank -> compacted conversion (bulking) factor
K_CLUSTERS = 5
SHORT_CLUSTERS, LONG_CLUSTERS = 3, 2
RANDOM_STATE = 0       # KMeans determinism
MAX_DH = 12.5          # trafficability guard [m] (1:2 face over the 25 m grid)
N_RANDOM = 200         # random-ordering replicates (fixed seed)


def load_solved_grid():
    g = tools.Grid("zlatibor")
    g.df_gridcell = pd.read_csv("S2_gridcell.csv")
    g.df_pointvol = pd.read_csv("S1_pointvol.csv")
    # common (compacted) volume basis: SUM = FILL + CUT/bulk (CUT is negative)
    g.df_gridcell["SUM"] = g.df_gridcell["FILL"] + g.df_gridcell["CUT"] / BULK
    g.calc_dist()
    g.calc_qtt(cost_func="bilinear", d_break=D_BREAK, C1=C1, C2=C2, C3=C3)
    g.build_transports()
    g.cluster_transports(K_CLUSTERS, RANDOM_STATE, d_break=D_BREAK,
                         short_clusters=SHORT_CLUSTERS,
                         long_clusters=LONG_CLUSTERS)
    g.calc_gridstep()
    return g


def main():
    g = load_solved_grid()
    gs = g.df_gridstep
    dt = g.df_transports
    P = {"df_gridcell": g.df_gridcell, "df_gridstep": gs, "df_transports": dt}

    print("=" * 64)
    print("Execution dynamics on the solved Zlatibor grid")
    print("=" * 64)

    # ---- site-wide checks on the design surface -----------------------------
    pcp, ok = dyn.drainage_check(gs)
    print(f"Drainage (design surface): {int(pcp.sum())}/{len(pcp)} cells "
          f"drain, global_pass={ok}")
    flagged, _, max_dh = dyn.adjacent_dh_guard(gs, max_dh=MAX_DH)
    print(f"Adjacent-dH guard (max {MAX_DH} m): {len(flagged)} pairs flagged, "
          f"max observed dH = {max_dh:.2f} m")

    # ---- the demonstration cluster (largest volume = deepest cut) ----------
    deep_id = int(dt.groupby("cluster")["qtt"].sum().idxmax())
    cut_cells = dyn.cluster_cut_cells(P, deep_id)
    print(f"\nCluster index {deep_id} (1-based 'cluster {deep_id + 1}'), "
          f"{len(cut_cells)} cut cells, "
          f"qtt={dt[dt['cluster'] == deep_id]['qtt'].sum():.0f} m^3, "
          f"design Z[{cut_cells.Z.min():.1f}, {cut_cells.Z.max():.1f}] m")

    # ---- full-site surface model (pre-cut state) ----------------------------
    cell_area = dyn.GRID_STEP * dyn.GRID_STEP
    cutdepth = {(round(r.X, 3), round(r.Y, 3)): -r.SUM / cell_area
                for r in g.df_gridcell.itertuples() if r.SUM < 0}
    z_design = gs["Z"].to_numpy(dtype=float).copy()
    gs_xy = {(round(r.X, 3), round(r.Y, 3)): i
             for i, r in enumerate(gs.itertuples())}
    worked_rows = np.array([gs_xy[(round(x, 3), round(y, 3))]
                            for x, y in zip(cut_cells["X"], cut_cells["Y"])])
    z_precut = z_design.copy()
    for k, (x, y) in enumerate(zip(cut_cells["X"], cut_cells["Y"])):
        z_precut[worked_rows[k]] += cutdepth.get((round(x, 3), round(y, 3)), 0.0)

    # ---- orderings ----------------------------------------------------------
    fa_order, fa_forced = dyn.face_advance_order(cut_cells, gs, z_precut,
                                                 z_design, gs_xy)
    sp_order, _ = dyn.serpentine_order_3d(cut_cells)
    h_order, _ = dyn.hilbert_order_3d(cut_cells)
    rm_order = dyn.row_major_order(cut_cells)
    td_order, _, td_uphill = dyn.top_down_passes(cut_cells)
    rng = np.random.default_rng(0)
    rand_L = [dyn.path_length(cut_cells, dyn.random_order(cut_cells, rng))
              for _ in range(N_RANDOM)]

    L_face = dyn.path_length(cut_cells, fa_order)
    L_rm = dyn.path_length(cut_cells, rm_order)
    L_sp = dyn.path_length(cut_cells, sp_order)
    L_h = dyn.path_length(cut_cells, h_order)
    L_rand, S_rand = float(np.mean(rand_L)), float(np.std(rand_L))

    print(f"\nMachine repositioning travel (within-cluster ordering):")
    print(f"  face advance (ADOPTED)   : {L_face:9.1f} m "
          f"(forced steps: {fa_forced})")
    print(f"  row-major (naive raster) : {L_rm:9.1f} m")
    print(f"  serpentine top-down      : {L_sp:9.1f} m")
    print(f"  Hilbert top-down         : {L_h:9.1f} m")
    print(f"  random (mean+-std of {N_RANDOM}): {L_rand:9.1f} +- {S_rand:.1f} m")
    print(f"  face advance vs row-major: "
          f"{100.0 * (L_rm - L_face) / L_rm:+5.1f} %")
    print(f"  face advance vs random   : "
          f"{100.0 * (L_rand - L_face) / L_rand:+5.1f} %")

    # ---- per-step drainage for every ordering -------------------------------
    def perstep(order_idx):
        z_state = z_precut.copy()
        oks = [dyn.drainage_check(gs, z_override=z_state)[1]]
        for k in order_idx:
            z_state[worked_rows[k]] = z_design[worked_rows[k]]
            oks.append(dyn.drainage_check(gs, z_override=z_state)[1])
        return int(np.sum(oks)), len(oks)

    print("\nPer-step drainage (snapshots passing / total):")
    for name, order in [("face advance (ADOPTED)", fa_order),
                        ("row-major", rm_order),
                        ("serpentine top-down", sp_order),
                        ("Hilbert top-down", h_order),
                        ("top-down passes", td_order)]:
        npass, ntot = perstep(order)
        print(f"  {name:24s}: {npass}/{ntot}  all_pass={npass == ntot}")

    # ---- loaded-haul direction check (cut -> fill must descend) ------------
    sub_t = dt[dt["cluster"] == deep_id]
    uphill_hauls = 0
    for t in sub_t.itertuples():
        zc = z_design[gs_xy[(round(t.end_x, 3), round(t.end_y, 3))]]
        zf = z_design[gs_xy[(round(t.start_x, 3), round(t.start_y, 3))]]
        if zc < zf - 1e-9:
            uphill_hauls += 1
    print(f"\nLoaded cut->fill hauls descending: "
          f"{len(sub_t) - uphill_hauls}/{len(sub_t)} "
          f"(uphill loaded hauls: {uphill_hauls})")
    print(f"Top-down parallel passes uphill loaded legs: {td_uphill}")


if __name__ == "__main__":
    main()
