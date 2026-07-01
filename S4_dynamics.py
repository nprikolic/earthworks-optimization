"""
S4_dynamics.py - execution-dynamics layer for the manuscript

    "Earthworks Planning through Dynamically Clustered Cut-and-Fill Sequencing"

Pure-numpy primitives (no dependency beyond numpy/pandas):

    (a) drainage_check(gridstep_df)        -> per-cell drains? + global bool
    (b) adjacent_dh_guard(gridstep_df, ..) -> flag adjacent dH > max_dh
    (c) face_advance_order(cells, ...)     -> drainage-safe face advance
        (ADOPTED ordering: opens the cut at its daylight end and advances the
        working face uphill; every intermediate surface drains by construction)
        with serpentine_order_3d / hilbert_order_3d / row_major_order /
        random_order as evaluated alternatives
    (d) top_down_passes(cells, ...)        -> downhill parallel machine passes

Endpoint convention of the transport table (differs from the manuscript's
Eq. 4 sign choice): in S3_tools.py, SUM = FILL + CUT/bulk with CUT stored
negative, so cut cells have SUM < 0. calc_qtt() takes supply = max(SUM, 0),
i.e. the SUPPLY rows are the FILL cells, and build_transports() writes supply
coordinates to start_x/start_y. Therefore start_* = FILL cell and
end_* = CUT cell; cluster_cut_cells() below uses end_*.

Run `python reproduce_dynamics.py` to regenerate the sequencing and per-step
drainage results reported in the paper (Fig. 3).
"""

import numpy as np

GRID_STEP = 25.0  # m, the Zlatibor grid spacing (uniform in X and Y)


# =============================================================================
# Grid bookkeeping helpers (pure numpy)
# =============================================================================
def _cell_index(gridstep_df, step=GRID_STEP):
    """Map (X, Y) cell centres onto integer (col, row) lattice indices."""
    X = gridstep_df["X"].to_numpy(dtype=float)
    Y = gridstep_df["Y"].to_numpy(dtype=float)
    ix = np.rint((X - X.min()) / step).astype(int)
    iy = np.rint((Y - Y.min()) / step).astype(int)
    return ix, iy, int(ix.max()) + 1, int(iy.max()) + 1


def _build_grid_lookup(gridstep_df, step=GRID_STEP):
    """Return (ix, iy, Z, occupied2d, z2d) where the 2-D arrays are nx*ny."""
    ix, iy, nx, ny = _cell_index(gridstep_df, step)
    Z = gridstep_df["Z"].to_numpy(dtype=float)
    occupied = np.zeros((nx, ny), dtype=bool)
    z2d = np.full((nx, ny), np.nan, dtype=float)
    occupied[ix, iy] = True
    z2d[ix, iy] = Z
    return ix, iy, Z, occupied, z2d


# =============================================================================
# (a) Drainage check
# =============================================================================
def drainage_check(gridstep_df, step=GRID_STEP, z_override=None):
    """
    For every grid cell, verify at least one of its four orthogonal (N/S/E/W)
    neighbours is STRICTLY lower than the cell, i.e. surface water has a path
    off the cell and no ponding occurs.

    A cell with no in-grid neighbour at all (isolated) trivially drains to the
    boundary and is treated as passing. The lowest cell(s) on the boundary also
    drain off the site boundary; only an INTERIOR cell whose four neighbours
    are all present and all >= its elevation is flagged as a sink (ponding).

    Returns (per_cell_pass bool array, global_pass bool).
    """
    ix, iy, _, occupied, _ = _build_grid_lookup(gridstep_df, step)
    nx, ny = occupied.shape
    Z = (gridstep_df["Z"].to_numpy(dtype=float)
         if z_override is None else np.asarray(z_override, dtype=float))

    z2d = np.full((nx, ny), np.nan, dtype=float)
    z2d[ix, iy] = Z

    per_cell_pass = np.ones(len(Z), dtype=bool)
    for k in range(len(Z)):
        cx, cy, cz = ix[k], iy[k], Z[k]
        if not np.isfinite(cz):
            continue  # undefined elevation: skip (no surface to drain)
        neigh_present = False
        drains = False
        boundary = False
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            mx, my = cx + dx, cy + dy
            if not (0 <= mx < nx and 0 <= my < ny) or not occupied[mx, my]:
                boundary = True  # neighbour off-grid => an edge of the site
                continue
            nz = z2d[mx, my]
            if not np.isfinite(nz):
                boundary = True
                continue
            neigh_present = True
            if nz < cz - 1e-9:  # strictly lower neighbour
                drains = True
                break
        per_cell_pass[k] = drains or boundary or (not neigh_present)
    return per_cell_pass, bool(per_cell_pass.all())


# =============================================================================
# (b) Adjacent elevation-difference guard
# =============================================================================
def adjacent_dh_guard(gridstep_df, max_dh, step=GRID_STEP, rock_mask=None,
                      z_override=None):
    """
    Flag adjacent-cell elevation differences (between orthogonal neighbours)
    that exceed `max_dh` (untrafficable working faces). A pair where either
    cell is flagged as rock is exempt.

    Returns (flagged_pairs, per_cell_flag, max_observed_dh).
    """
    ix, iy, _, occupied, _ = _build_grid_lookup(gridstep_df, step)
    nx, ny = occupied.shape
    Z = (gridstep_df["Z"].to_numpy(dtype=float)
         if z_override is None else np.asarray(z_override, dtype=float))
    if rock_mask is None:
        rock_mask = np.zeros(len(Z), dtype=bool)
    rock_mask = np.asarray(rock_mask, dtype=bool)

    pos_to_row = -np.ones((nx, ny), dtype=int)
    pos_to_row[ix, iy] = np.arange(len(Z))

    flagged_pairs = []
    per_cell_flag = np.zeros(len(Z), dtype=bool)
    max_observed = 0.0
    for k in range(len(Z)):
        cx, cy, cz = ix[k], iy[k], Z[k]
        if not np.isfinite(cz):
            continue
        for dx, dy in ((1, 0), (0, 1)):  # +x and +y only -> each pair once
            mx, my = cx + dx, cy + dy
            if not (0 <= mx < nx and 0 <= my < ny) or not occupied[mx, my]:
                continue
            nrow = pos_to_row[mx, my]
            nz = Z[nrow]
            if not np.isfinite(nz):
                continue
            dh = abs(cz - nz)
            max_observed = max(max_observed, dh)
            if dh > max_dh + 1e-9 and not (rock_mask[k] or rock_mask[nrow]):
                flagged_pairs.append(((k, nrow), float(dh)))
                per_cell_flag[k] = True
                per_cell_flag[nrow] = True
    return flagged_pairs, per_cell_flag, float(max_observed)


# =============================================================================
# (c) 2-D Hilbert curve mapping (implemented from scratch) + orderings
# =============================================================================
def hilbert_d2xy(order, d):
    """Map a 1-D Hilbert distance `d` to (x, y) on a 2**order square grid."""
    n = 1 << order
    x = y = 0
    t = int(d)
    s = 1
    while s < n:
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s <<= 1
    return x, y


def hilbert_xy2d(order, x, y):
    """Inverse of hilbert_d2xy: (x, y) -> Hilbert distance d."""
    n = 1 << order
    rx = ry = 0
    d = 0
    s = n >> 1
    x = int(x)
    y = int(y)
    while s > 0:
        rx = 1 if (x & s) > 0 else 0
        ry = 1 if (y & s) > 0 else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        s >>= 1
    return d


def hilbert_order_3d(cells, step=GRID_STEP, z_descending=True,
                     lift_thickness=None):
    """
    Order a set of cut cells along a 3-D Hilbert-like space-filling curve
    (evaluated alternative). The vertical axis is processed top-down in
    horizontal LIFTS; within each lift the cells are ordered by a 2-D Hilbert
    curve, alternating direction between lifts so the 3-D path is continuous.

    Returns (order_idx, lift_id).
    """
    X = np.asarray(cells["X"], dtype=float)
    Y = np.asarray(cells["Y"], dtype=float)
    Z = np.asarray(cells["Z"], dtype=float)
    n = len(X)

    ix = np.rint((X - X.min()) / step).astype(int)
    iy = np.rint((Y - Y.min()) / step).astype(int)

    extent = max(ix.max(), iy.max()) + 1
    order = int(np.ceil(np.log2(max(extent, 2))))  # Hilbert curve order

    hdist = np.array([hilbert_xy2d(order, x, y) for x, y in zip(ix, iy)])

    zmin, zmax = Z.min(), Z.max()
    if lift_thickness is None:
        n_lifts = max(2, int(round(np.sqrt(n))))
        edges = np.linspace(zmin, zmax, n_lifts + 1)
    else:
        n_lifts = max(1, int(np.ceil((zmax - zmin) / lift_thickness)))
        edges = zmin + lift_thickness * np.arange(n_lifts + 1)
        edges[-1] = max(edges[-1], zmax + 1e-9)
    band = np.clip(np.digitize(Z, edges[1:-1]), 0, n_lifts - 1)
    if z_descending:
        band = (n_lifts - 1) - band

    order_idx = []
    lift_id = []
    populated = 0
    for lift in range(n_lifts):
        members = np.where(band == lift)[0]
        if members.size == 0:
            continue
        members = members[np.argsort(hdist[members], kind="stable")]
        if populated % 2 == 1:
            members = members[::-1]
        order_idx.extend(members.tolist())
        lift_id.extend([lift] * members.size)
        populated += 1
    return np.array(order_idx, dtype=int), np.array(lift_id, dtype=int)


def serpentine_order_3d(cells, step=GRID_STEP, z_descending=True,
                        lift_thickness=None):
    """
    Top-down boustrophedon (serpentine) sweep (evaluated alternative).
    Identical lift banding to hilbert_order_3d so the two orderings are
    directly comparable; within each lift the cells are swept row by row with
    alternating row direction, and every other populated lift is traversed in
    reverse.

    Returns (order_idx, lift_id).
    """
    X = np.asarray(cells["X"], dtype=float)
    Y = np.asarray(cells["Y"], dtype=float)
    Z = np.asarray(cells["Z"], dtype=float)
    n = len(X)

    ix = np.rint((X - X.min()) / step).astype(int)
    iy = np.rint((Y - Y.min()) / step).astype(int)

    zmin, zmax = Z.min(), Z.max()
    if lift_thickness is None:
        n_lifts = max(2, int(round(np.sqrt(n))))
        edges = np.linspace(zmin, zmax, n_lifts + 1)
    else:
        n_lifts = max(1, int(np.ceil((zmax - zmin) / lift_thickness)))
        edges = zmin + lift_thickness * np.arange(n_lifts + 1)
        edges[-1] = max(edges[-1], zmax + 1e-9)
    band = np.clip(np.digitize(Z, edges[1:-1]), 0, n_lifts - 1)
    if z_descending:
        band = (n_lifts - 1) - band

    order_idx = []
    lift_id = []
    populated = 0
    for lift in range(n_lifts):
        members = np.where(band == lift)[0]
        if members.size == 0:
            continue
        lift_seq = []
        for r, row in enumerate(sorted(np.unique(iy[members]))):
            k = members[iy[members] == row]
            k = k[np.argsort(ix[k], kind="stable")]
            if r % 2 == 1:
                k = k[::-1]
            lift_seq.extend(k.tolist())
        if populated % 2 == 1:
            lift_seq = lift_seq[::-1]
        order_idx.extend(lift_seq)
        lift_id.extend([lift] * len(lift_seq))
        populated += 1
    return np.array(order_idx, dtype=int), np.array(lift_id, dtype=int)


def face_advance_order(cells, gs, z_state0, z_design, gs_xy, step=GRID_STEP,
                       drainage_filter=True):
    """
    Drainage-safe face-advance excavation ordering (ADOPTED).

    Models how a cut is opened in practice: excavation starts at the cut's
    downhill (daylight) end and the working face advances uphill. At every
    step the next cell excavated is one that, once lowered to design grade,
    immediately drains into the already-open cut or the surrounding lower
    ground (i.e. has at least one strictly lower orthogonal neighbour on the
    CURRENT intermediate surface). Among all drainable candidates the one
    nearest the machine's current position is chosen, keeping repositioning
    travel short. Because surfaces only ever descend, cells that drain keep
    draining, so every intermediate state passes the drainage check by
    construction (violations, if geometrically unavoidable, are reported).

    Parameters
    ----------
    cells : DataFrame with X, Y, Z (design/working elevations) of the cluster.
    gs : full-site gridstep DataFrame.
    z_state0 : ndarray -- initial full-site surface (pre-cut).
    z_design : ndarray -- design (final) full-site surface.
    gs_xy : dict -- (round(x,3), round(y,3)) -> row index into gs / z arrays.
    step : float -- grid spacing.
    drainage_filter : bool -- if False, the drainability test is skipped and
        the rule degenerates to plain greedy nearest-neighbor from the same
        (lowest) seed cell: the unconstrained control reported in the paper.

    Returns (order_idx, n_forced) where n_forced = number of steps where no
    drainable candidate existed (0 = the whole sequence is drainage-safe).
    """
    X = np.asarray(cells["X"], dtype=float)
    Y = np.asarray(cells["Y"], dtype=float)
    n = len(X)
    rows = np.array([gs_xy[(round(x, 3), round(y, 3))] for x, y in zip(X, Y)])
    z_state = z_state0.copy()

    def nbr_rows(x, y):
        out = []
        for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step)):
            r = gs_xy.get((round(x + dx, 3), round(y + dy, 3)))
            if r is not None:
                out.append(r)
        return out

    nbrs = [nbr_rows(x, y) for x, y in zip(X, Y)]

    def drains_if_cut(k):
        if not drainage_filter:
            return True
        zk = z_design[rows[k]]
        nb = nbrs[k]
        if len(nb) < 4:          # grid-boundary cell: drains off-site (exempt)
            return True
        return any(z_state[r] < zk - 1e-9 for r in nb)

    remaining = set(range(n))
    order = []
    n_forced = 0
    Zd = np.array([z_design[rows[k]] for k in range(n)])
    seed_cands = [k for k in remaining if drains_if_cut(k)]
    if seed_cands:
        cur = min(seed_cands, key=lambda k: Zd[k])
    else:
        cur = int(np.argmin(Zd))
        n_forced += 1
    order.append(cur)
    remaining.discard(cur)
    z_state[rows[cur]] = z_design[rows[cur]]
    cx, cy = X[cur], Y[cur]

    while remaining:
        cands = [k for k in remaining if drains_if_cut(k)]
        forced = not cands
        if forced:
            cands = list(remaining)
            n_forced += 1
        cur = min(cands, key=lambda k: (np.hypot(X[k] - cx, Y[k] - cy), Zd[k]))
        order.append(cur)
        remaining.discard(cur)
        z_state[rows[cur]] = z_design[rows[cur]]
        cx, cy = X[cur], Y[cur]
    return np.array(order, dtype=int), int(n_forced)


# =============================================================================
# (d) Top-down downhill parallel passes (dozer / scraper)
# =============================================================================
def top_down_passes(cells, step=GRID_STEP, pass_axis="auto"):
    """
    Generate downhill parallel machine passes such that the LOADED machine
    never travels uphill within a lane. Returns (order_idx, lane_id,
    uphill_loaded_legs) with uphill_loaded_legs expected to be 0.
    """
    X = np.asarray(cells["X"], dtype=float)
    Y = np.asarray(cells["Y"], dtype=float)
    Z = np.asarray(cells["Z"], dtype=float)

    ix = np.rint((X - X.min()) / step).astype(int)
    iy = np.rint((Y - Y.min()) / step).astype(int)

    if pass_axis == "auto":
        pass_axis = "x" if (ix.max() - ix.min()) >= (iy.max() - iy.min()) else "y"

    if pass_axis == "x":
        lane_key = iy
    else:
        lane_key = ix

    order_idx = []
    lane_id = []
    uphill = 0
    lane_counter = 0
    for L in sorted(np.unique(lane_key)):
        members = np.where(lane_key == L)[0]
        if members.size == 0:
            continue
        members = members[np.argsort(-Z[members], kind="stable")]
        zseq = Z[members]
        uphill += int(np.sum(np.diff(zseq) > 1e-9))
        order_idx.extend(members.tolist())
        lane_id.extend([lane_counter] * members.size)
        lane_counter += 1
    return np.array(order_idx, dtype=int), np.array(lane_id, dtype=int), int(uphill)


# =============================================================================
# Travel-cost helpers
# =============================================================================
def path_length(cells, order_idx, step=GRID_STEP):
    """Total Euclidean travel along the ordered visiting sequence (m)."""
    X = np.asarray(cells["X"], dtype=float)[order_idx]
    Y = np.asarray(cells["Y"], dtype=float)[order_idx]
    if len(order_idx) < 2:
        return 0.0
    return float(np.sum(np.hypot(np.diff(X), np.diff(Y))))


def row_major_order(cells, step=GRID_STEP):
    """Naive raster order: sort by (row, col) -> lawn-mower with row returns."""
    X = np.asarray(cells["X"], dtype=float)
    Y = np.asarray(cells["Y"], dtype=float)
    ix = np.rint((X - X.min()) / step).astype(int)
    iy = np.rint((Y - Y.min()) / step).astype(int)
    return np.lexsort((ix, iy))


def random_order(cells, rng):
    n = len(cells["X"])
    idx = np.arange(n)
    rng.shuffle(idx)
    return idx


def cluster_cut_cells(P, cluster_id):
    """
    Build a cells DataFrame (X, Y, Z) of the unique CUT cells of a given
    cluster, with Z taken from the gridstep surface.

    See the module docstring for the endpoint convention: start_* = FILL cell
    and end_* = CUT cell in the transport table.
    """
    import pandas as pd
    dt = P["df_transports"]
    gs = P["df_gridstep"]
    sub = dt[dt["cluster"] == cluster_id]
    cuts = sub[["end_x", "end_y"]].drop_duplicates().to_numpy()
    zmap = {(round(r.X, 3), round(r.Y, 3)): r.Z for r in gs.itertuples()}
    rows = [(x, y, zmap[(round(x, 3), round(y, 3))]) for x, y in cuts]
    return pd.DataFrame(rows, columns=["X", "Y", "Z"])
