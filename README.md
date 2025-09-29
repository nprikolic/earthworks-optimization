# Earthworks Grid Transport Planner

This Python project provides tools for modeling, analyzing, and optimizing earthworks transport between grid cells. It integrates AutoCAD data, CSV input/output, and visualization of transport flows, clusters, and 3D terrain surfaces.

## Features

- **Data Import/Export**
  - Load grid cells and elevation points from CSV files or directly from AutoCAD.
  - Save results, including transport quantities and distances, to CSV.

- **Distance & Quantity Calculations**
  - Compute distance matrices between grid cells.
  - Calculate optimal fill/cut transport quantities using linear programming.
  - Supports linear and bilinear cost functions.

- **Visualization**
  - Heatmaps of fill/cut quantities.
  - Arrows representing transport flows.
  - Clustering of transport flows with KMeans.
  - 3D surface plots and contour maps (izopahijete).
  - Step-wise cluster visualization showing progressive earthworks.

- **Cost Functions**
  - Linear: proportional to distance.
  - Bilinear: includes fixed cost and distance thresholds.

## Usage

```python
from tools import *

# Initialize and load data
grid = Grid(name="test")
grid.load_from_csv()        # or grid.load_from_acad()

# Calculate distances and optimal quantities
grid.calc_dist()
qtt = grid.calc_qtt(cost_func='bilinear')

# Build and visualize transport flows
df_transports = grid.build_transports()
grid.plot_arrows()

# Cluster transport flows
df_clusters = grid.cluster_transports(n_clusters=3)
grid.plot_clusters()

# Surface and step visualization
grid.calc_gridstep()
grid.plot_grid_surface()
grid.plot_cluster_steps()


