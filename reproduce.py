"""
reproduce.py - regenerate Tables 1 and 2 of the manuscript

    "Earthworks Planning through Dynamically Clustered Cut-and-Fill Sequencing"

directly from the released example data (S1_pointvol.csv, S2_gridcell.csv) and
code (S3_tools.py). No AutoCAD / GCM++ is required: the example GRIDCELL volumes
are provided so the optimization, clustering and baseline comparison can be run
stand-alone.

Bulking / common volume basis
-----------------------------
GCM++ reports CUT as an in-place (bank) volume and FILL as a compacted volume.
To allocate cut to fill on a single consistent basis, the bank cut is converted
to its compacted equivalent through the 1.25 bulking factor, i.e.

    SUM = FILL + CUT / 1.25            (CUT is stored as a negative quantity)

On this common basis cut and fill balance to within ~4 % for the Zlatibor case,
so only a small residual is sent to disposal and no borrow is required.

Run:
    python reproduce.py
"""

import numpy as np
import pandas as pd
from scipy.optimize import linprog

import S3_tools as tools

# Locked case parameters (see manuscript) ------------------------------------
D_BREAK = 100          # bilinear break distance [m]
C1, C2, C3 = 0.03, 0.05, 5
BULK = 1.25            # bank -> compacted conversion (bulking) factor
K_CLUSTERS = 5
SHORT_CLUSTERS, LONG_CLUSTERS = 3, 2
RANDOM_STATE = 0       # KMeans determinism
RATE = 40.0            # illustrative unit rate [$/m^3] (Table 1, col 5)


def load_grid():
    g = tools.Grid("zlatibor")
    g.df_gridcell = pd.read_csv("S2_gridcell.csv")
    g.df_pointvol = pd.read_csv("S1_pointvol.csv")
    # common (compacted) volume basis
    g.df_gridcell["SUM"] = g.df_gridcell["FILL"] + g.df_gridcell["CUT"] / BULK
    return g


# --- Transportation problem (mirrors S3_tools.Grid.calc_qtt bookkeeping) -----
def build_problem(df):
    sum_ = df["SUM"].to_numpy(float)
    keep = sum_ != 0.0
    sub = df.loc[keep]
    s = sub["SUM"].to_numpy(float)
    X = sub["X"].to_numpy(float); Y = sub["Y"].to_numpy(float)
    dist = np.sqrt((X[:, None] - X[None, :]) ** 2 + (Y[:, None] - Y[None, :]) ** 2)
    supply = np.maximum(s, 0.0); demand = np.maximum(-s, 0.0)
    ts, td = supply.sum(), demand.sum()
    off = 0
    if not np.isclose(ts, td):
        supply = np.insert(supply, 0, max(0.0, td - ts))
        demand = np.insert(demand, 0, max(0.0, ts - td))
        dist = np.pad(dist, ((1, 0), (1, 0)), "constant", constant_values=0)
        off = 1
    cost = tools.Cost().bilinear(dist, d_break=D_BREAK, C1=C1, C2=C2, C3=C3)
    return dict(supply=supply, demand=demand, dist=dist, cost=cost, off=off)


def _metrics(q, p):
    o = p["off"]; rq = q[o:, o:]; rd = p["dist"][o:, o:]; rc = p["cost"][o:, o:]
    return (rq * rd).sum(), (rq * rc).sum(), int((rq > 1e-9).sum())


def lp_allocate(p):
    s, d, c = p["supply"], p["demand"], p["cost"]; n = len(s)
    A, b = [], []
    for i in range(n):
        r = np.zeros(n * n); r[i * n:(i + 1) * n] = 1; A.append(r); b.append(s[i])
    for j in range(n):
        col = np.zeros(n * n); col[j::n] = 1; A.append(col); b.append(d[j])
    res = linprog(c.flatten(), A_eq=np.array(A), b_eq=np.array(b),
                  bounds=(0, None), method="highs")
    return res.x.reshape((n, n))


def nearest_fill_allocate(p):
    s = p["supply"].copy(); d = p["demand"].copy(); dist = p["dist"]; n = len(s)
    q = np.zeros((n, n)); tol = 1e-9
    for i in np.argsort(-s):
        if s[i] <= tol:
            continue
        for j in np.argsort(dist[i, :]):
            if s[i] <= tol:
                break
            if d[j] <= tol:
                continue
            m = min(s[i], d[j]); q[i, j] += m; s[i] -= m; d[j] -= m
    return q


def greedy_allocate(p):
    s = p["supply"].copy(); d = p["demand"].copy(); dist = p["dist"]; n = len(s)
    q = np.zeros((n, n)); tol = 1e-9
    si = np.where(s > tol)[0]; di = np.where(d > tol)[0]
    pairs = sorted(((dist[i, j], i, j) for i in si for j in di), key=lambda x: x[0])
    for _, i, j in pairs:
        if s[i] <= tol or d[j] <= tol:
            continue
        m = min(s[i], d[j]); q[i, j] += m; s[i] -= m; d[j] -= m
    return q


def main():
    g = load_grid()

    # --- Table 1: clustered work plan (uses S3_tools pipeline) ---------------
    g.calc_dist()
    g.calc_qtt(cost_func="bilinear", d_break=D_BREAK, C1=C1, C2=C2, C3=C3)
    g.build_transports()
    g.cluster_transports(K_CLUSTERS, RANDOM_STATE, d_break=D_BREAK,
                         short_clusters=SHORT_CLUSTERS, long_clusters=LONG_CLUSTERS)
    t = g.df_transports_sorted
    colors = {0: "blue", 1: "orange", 2: "green", 3: "red", 4: "purple"}
    print("=" * 64)
    print("TABLE 1 - Work plan overview by clusters")
    print("=" * 64)
    print(f"{'ID':>2} {'color':>7} {'avg dist (m)':>13} {'qty (m3)':>13} {'cost (M$)':>10}")
    tot = 0.0
    for c in sorted(t["cluster"].unique()):
        sub = t[t["cluster"] == c]; q = sub["qtt"].sum()
        wm = (sub["qtt"] * sub["distance"]).sum() / q
        print(f"{c+1:>2} {colors.get(c, ''):>7} {wm:>13.1f} {q:>13.1f} {q*RATE/1e6:>10.1f}")
        tot += q
    print(f"{'Total':>10} {'':>13} {tot:>13.1f} {tot*RATE/1e6:>10.1f}")

    # --- Table 2: LP vs greedy heuristics on the same problem ---------------
    p = build_problem(g.df_gridcell)
    print("\n" + "=" * 64)
    print("TABLE 2 - Optimal LP allocation vs two greedy heuristics")
    print("=" * 64)
    print(f"{'Method':>14} {'haul (1e6 m3.m)':>16} {'wcost (1e6)':>12} {'transports':>11}")
    out = {}
    for name, fn in [("LP (optimal)", lp_allocate),
                     ("Nearest-fill", nearest_fill_allocate),
                     ("Greedy", greedy_allocate)]:
        haul, wc, ntr = _metrics(fn(p), p)
        out[name] = (haul, wc); print(f"{name:>14} {haul/1e6:>16.1f} {wc/1e6:>12.2f} {ntr:>11d}")
    lph, lpw = out["LP (optimal)"]; nh, nw = out["Nearest-fill"]; gh, gw = out["Greedy"]
    print(f"\nLP haul reduction : {(1-lph/nh)*100:.1f}% vs nearest, {(1-lph/gh)*100:.1f}% vs greedy")
    print(f"LP wcost reduction: {(1-lpw/nw)*100:.1f}% vs nearest, {(1-lpw/gw)*100:.1f}% vs greedy")


if __name__ == "__main__":
    main()
