# Earthworks Optimization

Supplementary materials for the manuscript **"Earthworks Planning through Dynamically Clustered Cut-and-Fill Sequencing"**, submitted to the ASCE *Journal of Construction Engineering and Management*.

N. Milovanović, D. Gavran, S. Fric, V. Ilić, F. Trpčevski, S. Vranjevac, M. Lukić
Faculty of Civil Engineering, University of Belgrade

## Contents

| File | Description |
|------|-------------|
| `S1_pointvol.csv` | Example POINTVOL data (grid point pairs with elevations, Zlatibor Airport case) |
| `S2_gridcell.csv` | Example GRIDCELL data (cut/fill volumes and areas per grid cell) |
| `S3_tools.py` | Python source implementing the methodology (`Grid`, `Cost`) |
| `reproduce.py` | Turn-key driver that regenerates Table 1 and Table 2 from S1/S2/S3 |

## Reproducing the paper's results

```bash
pip install numpy pandas scipy scikit-learn
python reproduce.py
```

This regenerates, from the released example data alone (no AutoCAD/GCM++ needed):

* **Table 1** — the clustered work plan (5 clusters, per-cluster haul distance, quantity and indicative cost), and
* **Table 2** — the optimal LP allocation versus the nearest-fill and greedy heuristics.

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
5. **Sequencing** — gridstep terrain model with a 3-D Hilbert top-down traversal and a per-step
   drainage check (execution-dynamics layer; available from the corresponding author on request).

## Requirements

Python 3.x with `numpy`, `pandas`, `scipy`, `scikit-learn`.

## Citation

If you use this code, please cite the paper (full reference will be added upon publication).

## Acknowledgments

Supported by the RESAFE project No. 7051, funded by the Science Fund of the Republic of Serbia under the PRISMA program (2024–2026).
