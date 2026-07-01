# Earthworks Optimization

Supplementary materials for the manuscript **"Earthworks Planning through Dynamically Clustered Cut-and-Fill Sequencing"**, submitted to the ASCE *Journal of Construction Engineering and Management*.

N. Milovanović, D. Gavran, S. Fric, V. Ilić, F. Trpčevski, S. Vranjevac, M. Lukić
Faculty of Civil Engineering, University of Belgrade

## Contents

| File | Description |
|------|-------------|
| `S1_pointvol.csv` | Example POINTVOL data (grid point pairs with elevations, Zlatibor Airport case) |
| `S2_gridcell.csv` | Example GRIDCELL data (cut/fill volumes and areas per grid cell) |
| `S3_tools.py` | Python source implementing the allocation/clustering methodology (`Grid`, `Cost`) |
| `S4_dynamics.py` | Python source implementing the execution-dynamics layer (drainage check, face-advance and alternative orderings) |
| `reproduce.py` | Turn-key driver that regenerates Table 1 and Table 2 from S1/S2/S3 |
| `reproduce_dynamics.py` | Turn-key driver that regenerates the sequencing and per-step drainage results (Fig. 3) from S1/S2/S3/S4 |

## Reproducing the paper's results

```bash
pip install numpy pandas scipy scikit-learn
python reproduce.py            # Tables 1 and 2
python reproduce_dynamics.py   # sequencing + per-step drainage (Fig. 3)
```

This regenerates, from the released example data alone (no AutoCAD/GCM++ needed):

* **Table 1** — the clustered work plan (5 clusters, per-cluster haul distance, quantity and indicative cost),
* **Table 2** — the optimal LP allocation versus the nearest-fill and greedy heuristics, and
* **Fig. 3 numbers** — the drainage-safe face-advance sequencing of the largest cluster versus row-major, serpentine, Hilbert and random orderings (machine repositioning travel, per-step drainage pass rates, loaded-haul direction check).

Locked case parameters: `d_break = 100` m, `C1 = 0.03`, `C2 = 0.05`, `C3 = 5`, `k = 5`
clusters (3 short + 2 long), `random_state = 0`, illustrative unit rate `$40/m^3`.

### Cut/fill volume basis (bulking)

GCM++ reports `CUT` as an **in-place (bank)** volume and `FILL` as a **compacted**
volume. To allocate cut to fill on one consistent basis, the bank cut is converted
to its compacted equivalent through the 1.25 bulking factor:

```
SUM = FILL + CUT / 1.25     # CUT is stored as a negative quantity
```

On this common basis cut and fill balance to within about 4 % for the Zlatibor
case, so only a small residual is sent to disposal and no borrow is required.

## Methodology overview

1. **Data import** — POINTVOL/GRIDCELL volumes computed with GCM++ (example outputs
   S1/S2 are provided so the optimization steps run without AutoCAD).
2. **Cost function** — bilinear weighting for two parallel machinery configurations
   (short-haul dozer / long-haul scraper + dozer).
3. **Allocation** — linear-programming solution of the transportation problem (globally optimal).
4. **Clustering** — k-means grouping of individual transports into spatially coherent work packages.
5. **Sequencing** — gridstep terrain model with a drainage-safe face-advance excavation
   ordering steered by a per-step drainage check (`S4_dynamics.py`); serpentine, Hilbert,
   row-major and random orderings are evaluated alternatives.

## Requirements

Python 3.x with `numpy`, `pandas`, `scipy`, `scikit-learn`.

## Citation

If you use this code, please cite the paper (full reference will be added upon publication).

## Acknowledgments

Supported by the RESAFE project No. 7051, funded by the Science Fund of the Republic of Serbia under the PRISMA program (2024–2026).
