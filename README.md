# Earthworks Optimization

Supplementary materials for the manuscript **"Optimal Earthworks Planning through Dynamically Clustered Cut-and-Fill Sequencing"**, submitted to the ASCE *Journal of Construction Engineering and Management*.

N. Milovanović, D. Gavran, S. Fric, V. Ilić, F. Trpčevski, S. Vranjevac, M. Lukić
Faculty of Civil Engineering, University of Belgrade

## Contents

| File | Description |
|------|-------------|
| `S1_pointvol.csv` | Example POINTVOL data (grid point pairs with elevations, Zlatibor Airport case) |
| `S2_gridcell.csv` | Example GRIDCELL data (cut/fill volumes and areas per grid cell) |
| `S3_tools.py` | Python source code implementing the methodology |

## Methodology overview

The code extends the classical linear programming approach to earthwork allocation with a dynamic execution component:

1. **Data import** — reads POINTVOL and GRIDCELL blocks from AutoCAD (volumes computed with GCM++) via `pyautocad`
2. **Cost function** — bilinear cost model for two parallel machinery configurations (short-haul dozer / long-haul scraper + dozer)
3. **Allocation** — linear programming solution of the transportation problem
4. **Clustering** — k-means grouping of individual transports into spatially coherent work packages
5. **Sequencing** — gridstep terrain model with 3D Hilbert curve traversal; prevents local depressions and water accumulation at every step

## Usage

```python
import S3_tools as tools

example = tools.Grid("example")
example.load_from_acad()
example.apply_bulking_factor(b_factor=1.25)
example.calc_dist()
example.calc_qtt(cost_func='bilinear')
example.build_transports()
example.cluster_transports()
example.calc_gridstep()
```

## Requirements

- Python 3.x with `numpy`, `pandas`, `scipy`, `scikit-learn`, `pyautocad`
- AutoCAD with GCM++ (for volume computation from terrain surfaces; example outputs S1/S2 are provided so the optimization steps can be run without it)

## Citation

If you use this code, please cite the paper (full reference will be added upon publication).

## Acknowledgments

Supported by the RESAFE project No. 7051, funded by the Science Fund of the Republic of Serbia under the PRISMA program (2024–2026).
