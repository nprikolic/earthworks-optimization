import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.optimize import linprog
from sklearn.cluster import KMeans
from mpl_toolkits.mplot3d import Axes3D

class Grid:
    def __init__(self, name=""):
        self.name = name
        self.df_gridcell = None
        self.df_pointvol = None
        self._dist_df = None
        self.qtt = None
        self.df_transports = None
        self.df_transports_sorted = None
        self.df_gridstep = None
        self.d_break = Cost.bilinear.__defaults__[0]
        
    def load_from_csv(self):
        """Učitava ćelije i visinske tačke iz .csv fajla."""
        self.df_gridcell = pd.read_csv(f"{self.name}_gridcell.csv")
        self.df_pointvol = pd.read_csv(f"{self.name}_pointvol.csv")
    
    def load_from_acad(self):
        """Učitava ćelije i visinske tačke iz aktivnog AutoCad modela."""

        from pyautocad import Autocad
        import win32com.client
        import math

        acad = Autocad()
        acad_app = win32com.client.Dispatch("AutoCAD.Application")
        
        try:
            doc = acad_app.ActiveDocument
        except Exception as e:
            raise RuntimeError("Nema otvorenog dokumenta u AutoCAD-u!") from e

        gridcell_data = []
        pointvol_data = []

        for obj in acad.iter_objects("AcDbBlockReference"):
            handle = obj.Handle
            block = doc.HandleToObject(handle)

            x, y, z = map(float, block.InsertionPoint)
            sx, sy, sz = float(block.XScaleFactor), float(block.YScaleFactor), float(block.ZScaleFactor)
            rotation_deg = float(math.degrees(block.Rotation))

            attrs = {}
            try:
                for att in block.GetAttributes():
                    try:
                        attrs[att.TagString] = float(att.TextString)
                    except:
                        attrs[att.TagString] = att.TextString
            except:
                pass

            row = {
                "Name": block.Name,
                "X": x,
                "Y": y,
                "Z": z,
                "ScaleX": sx,
                "ScaleY": sy,
                "ScaleZ": sz,
                "Rotation": rotation_deg,
                **attrs
            }

            if block.Name.upper() == "GRIDCELL":
                gridcell_data.append(row)
            elif block.Name.upper() == "POINTVOL":
                pointvol_data.append(row)

        df_gridcell = pd.DataFrame(gridcell_data)
        df_pointvol = pd.DataFrame(pointvol_data)

        try:
            df_gridcell["SUM"]=df_gridcell["FILL"]+df_gridcell["CUT"]
        except:
            print('Podaci nisu učitani!')

        self.df_gridcell = df_gridcell
        self.df_pointvol = df_pointvol

    def save_to_csv(self):
        """Čuva čelije i visinske tačke u .csv fajl."""
        if self.df_gridcell is not None:
            self.df_gridcell.to_csv(f"{self.name}_gridcell.csv",
                                    index=False)
        if self.df_pointvol is not None:
            self.df_pointvol.to_csv(f"{self.name}_pointvol.csv", 
                                    index=False)
    
    def calc_dist(self):
        """Izraunava matricu distanci među svim ćelijama"""

        if self.df_gridcell is None:
            raise ValueError("Nisu učitani ulazni podaci.")
        
        if self._dist_df is not None:
            return self._dist_df  # već je izračunato
        
        X = self.df_gridcell["X"].to_numpy()
        Y = self.df_gridcell["Y"].to_numpy()

        x_dist = np.abs(X[:, None] - X[None, :])
        y_dist = np.abs(Y[:, None] - Y[None, :])
        
        dist_matrix = np.sqrt(x_dist**2 + y_dist**2)
        self._dist_df = pd.DataFrame(dist_matrix, 
                                     index=self.df_gridcell.index, 
                                     columns=self.df_gridcell.index)
        return self._dist_df
    
    def grid_heatmap(self):
        """Prikazuje heatmapu vrednosti po grid ćelijama."""

        if self.df_gridcell is None:
            raise ValueError("Nisu učitani ulazni podaci.")

        sns.set_theme()
        f, ax = plt.subplots(figsize=(9, 9))

        #Izbacuje iz skupa ćelije čiji je "ScaleZ" = 0 
        #sa idejom da se tako podešavaju ćelije za pozajmišta i deponije
        help=self.df_gridcell[self.df_gridcell['ScaleZ'] != 0]

        gridcell_ = help.pivot(index="Y", columns="X", values="SUM")

        sns.heatmap(
            gridcell_,
            annot=True,
            fmt=".1f",
            linewidths=0.5,
            annot_kws={"fontsize": 8},
            ax=ax,
            cmap="coolwarm",
            xticklabels=True,
            yticklabels=True
        )

        ax.set_xticklabels([f"{x:.1f}" for x in gridcell_.columns], rotation=45)
        ax.set_yticklabels([f"{y:.1f}" for y in gridcell_.index], rotation=0)
        ax.invert_yaxis()
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_title("QTT Heatmap", fontsize=12)
        plt.show()
        return None
    
    def calc_qtt(self, cost_func='bilinear', **kwargs):
        """Računanje optimalnih količina linearnim programiranjem."""
        
        if self.df_gridcell is None:
            raise ValueError("Podaci nisu učitani")

        sum_ = self.df_gridcell["SUM"].to_numpy()
        supply = np.maximum(sum_, 0)
        demand = np.maximum(-sum_, 0)

        total_supply = supply.sum()
        total_demand = demand.sum()

        dist = self.calc_dist().values

        #Dodaje dummy ćelije ako se količine nasipa i useka ne poklapaju
        dummy_added = False
        if total_supply != total_demand:
            supply = np.insert(supply, 0, max(0, total_demand - total_supply))
            demand = np.insert(demand, 0, max(0, total_supply - total_demand))
            dist = np.pad(dist, ((1,0),(1,0)), 'constant', constant_values=0)
            dummy_added = True

        n = len(supply)

        cost_obj = Cost()
        if cost_func == 'bilinear':
            self.d_break = kwargs.get("d_break", cost_obj.bilinear.__defaults__[0])
            c_matrix = cost_obj.bilinear(dist, **kwargs)
        elif cost_func == 'linear':
            c_matrix = cost_obj.linear(dist)
        else:
            raise ValueError("Nepoznata cost funkcija")

        c = c_matrix.flatten()

        # Ograničenja
        A_eq = []
        b_eq = []

        # Supply ograničenja
        for i in range(n):
            row = np.zeros(n*n)
            row[i*n:(i+1)*n] = 1
            A_eq.append(row)
            b_eq.append(supply[i])

        # Demand ograničenja
        for j in range(n):
            col = np.zeros(n*n)
            col[j::n] = 1
            A_eq.append(col)
            b_eq.append(demand[j])

        A_eq = np.array(A_eq)
        b_eq = np.array(b_eq)

        # Rešenje LP
        res = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=(0, None), method='highs')
        qtt = res.x.reshape((n, n))

        # Ukloni dummy ćeliju ako postoji
        if dummy_added:
            qtt = qtt[1:, 1:]
            dist = dist[1:, 1:]

        self.qtt = qtt
        return self.qtt

    def build_transports(self, threshold=0):
        """
        Pravi DataFrame sa transportima na osnovu qtt matrice.
        
        Parametri:
        -----------
        threshold : int ili float
            Granica ispod koje se transporti ignorišu.
        
        Rezultat:
        ---------
        self.df_transports : pandas.DataFrame
            Tabela sa kolonama: start_x, start_y, end_x, end_y, qtt, distance
        """
        # Koordinate svih ćelija
        X = self.df_gridcell["X"].to_numpy()
        Y = self.df_gridcell["Y"].to_numpy()

        # Nalazimo indekse gde je qtt veći od minimalne granice
        rows, cols = np.nonzero(self.qtt > threshold)

        # Pravi DataFrame direktno
        self.df_transports = pd.DataFrame({
            "start_x": X[rows],
            "start_y": Y[rows],
            "end_x": X[cols],
            "end_y": Y[cols],
            "qtt": self.qtt[rows, cols]
        })

        # Računa rastojanje između start i end tačaka
        self.df_transports["distance"] = np.sqrt(
            (self.df_transports["end_x"] - self.df_transports["start_x"])**2 +
            (self.df_transports["end_y"] - self.df_transports["start_y"])**2
        )

        return self.df_transports

    def save_results(self, qtt, dist, prefix=""):
        """
        Eksportuje rezultate u CSV fajlove.

        Parametri:
        - qtt: transportne količine (n x n matrica)
        - dist: matrica rastojanja (n x n matrica)
        - prefix: opcioni prefiks za ime fajlova
        """
        if self.df_gridcell is None:
            raise ValueError("Podaci nisu učitani")

        # Ako je dat prefiks dodaj ga ispred imena
        qtt_file = f"{prefix}qtt.csv"
        dist_file = f"{prefix}dist.csv"
        grid_file = f"{prefix}gridcell_data.csv"

        # Kreiranje DataFrame sa indeksima i kolonama kao u df_gridcell
        qtt_df = pd.DataFrame(qtt,
                              index=self.df_gridcell.index,
                              columns=self.df_gridcell.index)
        dist_df_labeled = pd.DataFrame(dist,
                                       index=self.df_gridcell.index,
                                       columns=self.df_gridcell.index)

        # Čuvanje u CSV fajlove
        qtt_df.to_csv(qtt_file, index=False)
        dist_df_labeled.to_csv(dist_file, index=False)
        self.df_gridcell.to_csv(grid_file, index=False)

        print(f"Rezultati su sačuvani u fajlove:\n - {qtt_file}\n - {dist_file}\n - {grid_file}")

    def plot_arrows(self, qtt, threshold=0.05):
        """
        Prikazuje transportne tokove između grid ćelija pomoću strelica.

        Parametri:
        - qtt: matrica transportnih količina (n x n)
        - threshold: prag ispod kojeg se strelice ne crtaju (relativno u odnosu na max qtt)
        """
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyArrowPatch
        import matplotlib.cm as cm
        import numpy as np

        if self.df_gridcell is None:
            raise ValueError("Podaci nisu učitani")

        # Koordinate centara ćelija
        X = self.df_gridcell["X"].to_numpy()
        Y = self.df_gridcell["Y"].to_numpy()
        n = len(self.df_gridcell)

        # Normalizacija količina za širinu i boju strelica
        qtt_norm = qtt / qtt.max()

        # Veličine čvorova proporcionalne SUM vrednosti
        sizes = np.abs(self.df_gridcell["SUM"].to_numpy())
        sizes = sizes / sizes.max() * 300  # skaliranje za veličinu markera

        # Kolormap za strelice
        cmap = cm.Reds

        plt.figure(figsize=(12, 10))
        plt.scatter(X, Y, s=sizes, c='blue', alpha=0.6, zorder=5)

        # Crtanje strelica
        for i in range(n):
            for j in range(n):
                if qtt[i, j] / qtt.max() > threshold:
                    arrow = FancyArrowPatch(
                        (X[i], Y[i]), (X[j], Y[j]),
                        arrowstyle='-|>', 
                        mutation_scale=5 + 10*qtt_norm[i, j],   # veličina vrha strelice
                        color=cmap(qtt_norm[i, j]), alpha=0.7,
                        linewidth=0.5 + 3*qtt_norm[i, j],       # širina strelice
                        connectionstyle="arc3,rad=0.2"          # mala zakrivljenost
                    )
                    plt.gca().add_patch(arrow)

        # Dodavanje oznaka za indekse ćelija
        for i in range(n):
            plt.text(X[i], Y[i], str(i), color='black', fontsize=8, ha='center', va='center')

        plt.xlabel("X")
        plt.ylabel("Y")
        plt.title("Transportne strelice između grid ćelija")
        plt.axis('equal')
        plt.grid(True)
        plt.show()
    

    def cluster_transports(
        self,
        n_clusters,
        state,
        d_break=None,
        short_clusters=None,
        long_clusters=None,
        allocation_metric="count"
    ):
        """
        Grupisanje prevoza pomocu KMeans algoritma.

        Parametri:
        n_clusters : int
            Broj klastera (grupa) u koje se prevozi dele.
        short_clusters, long_clusters : int, optional
            Eksplicitno zadavanje broja klastera za kratke (<= d_break)
            odnosno duge (> d_break) prevoze. Ako je zadat samo jedan od
            ova dva parametra, drugi se racuna kao razlika do n_clusters.
            Ako nijedan nije zadat, broj klastera se odredjuje automatski.
        allocation_metric : {'count', 'qtt'}
            Metod kojim se automatski raspodeljuje broj klastera izmedu
            kratkih i dugih prevoza. 'count' koristi broj prevoza, dok
            'qtt' koristi zbirnu kolicinu qtt.

        Napomena:
        Klasteri ne smeju da sadrze kombinaciju prevoza sa distancom manjom
        i vecom od `d_break` (prelomna tacka iz bilinearne cost funkcije).

        Rezultat:

        df_clusters : pandas.DataFrame
            Tabela sa prosecnim koordinatama pocetka i kraja svakog prevoza
            u okviru klastera, kao i zbirnom kolicinom prevoza (qtt).
        """
        if self.df_transports is None or self.df_transports.empty:
            raise ValueError("Nema transporta za klasterovanje. Pozovite build_transports().")

        if n_clusters < 1:
            raise ValueError("Broj klastera mora biti najmanje 1.")

        total_transports = len(self.df_transports)
        if n_clusters > total_transports:
            raise ValueError("Broj klastera ne moze biti veci od broja transporta.")

        # Pravi prag za bilinearnu funkciju
        if d_break is None:
            threshold = getattr(self, "d_break", Cost.bilinear.__defaults__[0])
        else:
            threshold = float(d_break)
            self.d_break = threshold

        feature_cols = ["start_x", "start_y", "end_x", "end_y", "distance"]

        short_mask = self.df_transports["distance"] <= threshold
        long_mask = self.df_transports["distance"] > threshold

        short_count = int(short_mask.sum())
        long_count = int(long_mask.sum())

        if short_count and long_count and n_clusters < 2:
            raise ValueError("Za kombinaciju kratkih i dugih transporta potrebno je najmanje 2 klastera.")

        if allocation_metric not in {"count", "qtt"}:
            raise ValueError("allocation_metric mora biti 'count' ili 'qtt'.")

        def allocate_clusters(total_clusters, short_cnt, long_cnt):
            if short_cnt == 0:
                return 0, min(total_clusters, long_cnt)
            if long_cnt == 0:
                return min(total_clusters, short_cnt), 0

            if allocation_metric == "count":
                short_score = short_cnt
                long_score = long_cnt
            else:
                short_score = self.df_transports.loc[short_mask, "qtt"].sum()
                long_score = self.df_transports.loc[long_mask, "qtt"].sum()

            if short_score == 0 and long_score == 0:
                return min(total_clusters, short_cnt), min(total_clusters, long_cnt)

            short_ratio = short_score / (short_score + long_score) if (short_score + long_score) else 0.0
            n_short = max(1, round(total_clusters * short_ratio))
            n_long = max(1, total_clusters - n_short)

            if n_short + n_long != total_clusters:
                adjustment = total_clusters - (n_short + n_long)
                n_long += adjustment

            if n_short == 0:
                n_short = 1
                n_long = max(1, n_long - 1)
            if n_long == 0:
                n_long = 1
                n_short = max(1, n_short - 1)

            n_short = min(n_short, short_cnt)
            n_long = min(n_long, long_cnt)

            assigned = n_short + n_long
            leftover = total_clusters - assigned

            while leftover > 0:
                short_capacity = short_cnt - n_short
                long_capacity = long_cnt - n_long

                if short_capacity <= 0 and long_capacity <= 0:
                    break

                if short_capacity >= long_capacity and short_capacity > 0:
                    n_short += 1
                elif long_capacity > 0:
                    n_long += 1
                leftover -= 1

                if n_short > short_cnt:
                    n_short = short_cnt
                if n_long > long_cnt:
                    n_long = long_cnt

            return n_short, n_long

        if short_clusters is not None or long_clusters is not None:
            if short_clusters is None:
                long_clusters = int(long_clusters)
                short_clusters = n_clusters - long_clusters
            elif long_clusters is None:
                short_clusters = int(short_clusters)
                long_clusters = n_clusters - short_clusters
            else:
                short_clusters = int(short_clusters)
                long_clusters = int(long_clusters)

            if short_clusters < 0 or long_clusters < 0:
                raise ValueError("Broj klastera ne moze biti negativan.")
            if short_clusters + long_clusters != n_clusters:
                raise ValueError("Zbir short_clusters i long_clusters mora biti jednak n_clusters.")

            if short_count == 0 and short_clusters > 0:
                raise ValueError("Nema kratkih transporta, short_clusters mora biti 0.")
            if long_count == 0 and long_clusters > 0:
                raise ValueError("Nema dugih transporta, long_clusters mora biti 0.")

            n_short = min(short_clusters, short_count)
            n_long = min(long_clusters, long_count)

            if n_short + n_long < n_clusters:
                raise ValueError("Nije moguce raspodeliti zadati broj klastera na osnovu dostupnih transporta.")
        else:
            n_short, n_long = allocate_clusters(n_clusters, short_count, long_count)

        # Priprema nove kolone sa podrazumevanom vrednoscu
        self.df_transports = self.df_transports.copy()
        self.df_transports["cluster"] = -1

        assignments = []
        cluster_offset = 0

        def run_kmeans(mask, n_group_clusters, rs):
            nonlocal cluster_offset
            if n_group_clusters == 0:
                return
            idx = self.df_transports.index[mask]
            if len(idx) == 0:
                return

            features = self.df_transports.loc[idx, feature_cols].to_numpy()
            if len(idx) <= n_group_clusters or n_group_clusters == 1:
                labels = np.zeros(len(idx), dtype=int)
            else:
                kmeans = KMeans(n_clusters=n_group_clusters, random_state=rs, n_init="auto")
                labels = kmeans.fit_predict(features)

            assignments.append(pd.Series(labels + cluster_offset, index=idx))
            cluster_offset += n_group_clusters

        run_kmeans(short_mask, n_short, state)
        long_state = state if state is None else state + 1
        run_kmeans(long_mask, n_long, long_state)

        if assignments:
            combined_clusters = pd.concat(assignments).astype(int)
            self.df_transports.loc[combined_clusters.index, "cluster"] = combined_clusters

        if (self.df_transports["cluster"] < 0).any():
            raise RuntimeError("Neki transporti nisu dobili klaster. Proverite ulazne podatke.")

        cluster_dist_sum = self.df_transports.groupby("cluster")["distance"].sum()
        # Kreiranje mapiranja: stari label -> novi label (0 najmanja suma, ... n_clusters-1 najveca)
        sorted_labels = cluster_dist_sum.sort_values().index.tolist()
        label_map = {old_label: new_label for new_label, old_label in enumerate(sorted_labels)}
        # Primena novog redosleda
        self.df_transports["cluster"] = self.df_transports["cluster"].map(label_map)

        # Tabela sa rezultatima po klasterima
        df_clusters = (
            self.df_transports
            .groupby("cluster")
            .agg({
                "start_x": "mean",
                "start_y": "mean",
                "end_x": "mean",
                "end_y": "mean",
                "qtt": "sum"
            })
            .reset_index(drop=True)
        )

        self.df_transports_sorted = (
            self.df_transports
            .sort_values(by=["cluster", "distance"])
            .reset_index(drop=True)
        )

        # Provera da li postoji mesanje kratkih i dugih distanci u bilo kom klasteru
        def has_mix(group):
            le = (group <= threshold).any()
            gt = (group > threshold).any()
            return le and gt

        violations = self.df_transports.groupby("cluster")["distance"].apply(has_mix)
        bad_clusters = violations[violations].index.tolist()
        if bad_clusters:
            raise RuntimeError(
                f"Klasteri {bad_clusters} sadrze razdaljine i ispod i iznad d_break={threshold}. "
                "Povecajte broj klastera ili proverite ulazne podatke."
            )

        return df_clusters

    def plot_clusters(self):
        plt.figure(figsize=(12, 10))
        
        df_transports = self.df_transports_sorted
        palette = sns.color_palette("tab10", n_colors=df_transports["cluster"].nunique())

        sns.scatterplot(
            data=df_transports, x="start_x", y="start_y",
            hue="cluster", size="qtt", marker="^",
            palette=palette, edgecolor="black", linewidth=0.5, alpha=0.8,
            sizes=(100, 1000)  
        )

        sns.scatterplot(
            data=df_transports, x="end_x", y="end_y",
            hue="cluster", size="qtt", marker="o",
            palette=palette, edgecolor="black", linewidth=0.5, alpha=0.8,
            sizes=(100, 1000) 
        )

        plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
        plt.title("Start vs End Coordinates by Cluster")
        plt.axis("equal")
        plt.show()
    
    def plot_grid_surface(self, surfn='ELEV1'):

        X = self.df_pointvol["X"].to_numpy()
        Y = self.df_pointvol["Y"].to_numpy()
        Z = self.df_pointvol[surfn].to_numpy()

        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111, projection='3d')

        surf = ax.plot_trisurf(X, Y, Z, cmap='viridis', edgecolor='grey', alpha=0.9)
        ax.scatter(X, Y, Z, color='red', s=20)

        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.set_title("3D Surface "+surfn)

        fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10, label='Z')

        plt.show()
    
    def plot_izopahijete(self):

        X = self.df_pointvol["X"].to_numpy()
        Y = self.df_pointvol["Y"].to_numpy()
        Z = self.df_pointvol["DELEV"].to_numpy()

        plt.figure(figsize=(12, 8))

        contour = plt.tricontour(X, Y, Z, levels=10, colors='blue', linewidths=1)
        plt.clabel(contour, inline=True, fontsize=8, fmt="%.2f")

        plt.scatter(X, Y, c='black', s=20, label='Data points')

        plt.xlabel("X")
        plt.ylabel("Y")
        plt.title("Izopahijete")
        plt.legend()
        plt.axis('equal')
        plt.grid(True)
        plt.show()

    def calc_gridstep(self):

        df_gridstep=pd.DataFrame()
        df_gridstep['X']=self.df_gridcell['X']
        df_gridstep['Y']=self.df_gridcell['Y']
         
        point_lookup = {(round(row.X, 3), round(row.Y, 3)): row.ELEV2 for row in self.df_pointvol.itertuples()}

        records = []
        for row in self.df_gridcell.itertuples():
            x, y = row.X, row.Y
            dx, dy = row.ScaleX, row.ScaleY

            neighbors = [
                (round(x - dx/2, 3), round(y - dy/2, 3)),
                (round(x - dx/2, 3), round(y + dy/2, 3)),
                (round(x + dx/2, 3), round(y - dy/2, 3)),
                (round(x + dx/2, 3), round(y + dy/2, 3)),
            ]

            elevs = [point_lookup.get(pt) for pt in neighbors]

            if None not in elevs:
                z = np.mean(elevs)
            else:
                z = np.nan

            records.append((x, y, z))

        self.df_gridstep = pd.DataFrame(records, columns=["X", "Y", "Z"])

        return self.df_gridstep
  
    def plot_cluster_steps(self, baseline=-20):
        dx = float(self.df_pointvol.loc[self.df_pointvol["X"] != 0, "X"].min())
        dy = float(self.df_pointvol.loc[self.df_pointvol["Y"] != 0, "Y"].min())
        base_area = dx * dy

        Z_current = self.df_gridstep["Z"].to_numpy().copy()
        n_cells = len(self.df_gridstep)

        color_init = '#4CAF50' 
        color_start = '#FF6EC7'  
        color_end = '#00CED1'   
        color_prev = "#347036"     
        cell_colors = np.full(n_cells, color_init, dtype=object)

        unique_clusters = sorted(self.df_transports_sorted["cluster"].unique())
        df_snapshots = []
        prev_changed_indices = set()

        df_snapshots.append(pd.DataFrame({
            "X": self.df_gridstep["X"],
            "Y": self.df_gridstep["Y"],
            "Z": Z_current.copy(),
            "color": cell_colors.copy(),
            "cluster": "Initial"
        }))

        for step_idx, cluster_id in enumerate(unique_clusters):
            cluster_transports = self.df_transports_sorted[self.df_transports_sorted["cluster"] == cluster_id]
            newly_changed_indices = set()

            for _, step in cluster_transports.iterrows():
                delta_z = step.qtt / base_area

                start_idx = self.df_gridstep.index[
                    (self.df_gridstep["X"] == step.start_x) & (self.df_gridstep["Y"] == step.start_y)
                ].tolist()
                end_idx = self.df_gridstep.index[
                    (self.df_gridstep["X"] == step.end_x) & (self.df_gridstep["Y"] == step.end_y)
                ].tolist()

                Z_current[start_idx] += delta_z
                Z_current[end_idx] -= delta_z
                newly_changed_indices.update(start_idx)
                newly_changed_indices.update(end_idx)

            if step_idx == 0:
                for _, step in cluster_transports.iterrows():
                    start_idx = self.df_gridstep.index[
                        (self.df_gridstep["X"] == step.start_x) & (self.df_gridstep["Y"] == step.start_y)
                    ].tolist()
                    end_idx = self.df_gridstep.index[
                        (self.df_gridstep["X"] == step.end_x) & (self.df_gridstep["Y"] == step.end_y)
                    ].tolist()
                    cell_colors[start_idx] = color_start
                    cell_colors[end_idx] = color_end
            else:
                for idx in prev_changed_indices:
                    cell_colors[idx] = color_prev
                for _, step in cluster_transports.iterrows():
                    start_idx = self.df_gridstep.index[
                        (self.df_gridstep["X"] == step.start_x) & (self.df_gridstep["Y"] == step.start_y)
                    ].tolist()
                    end_idx = self.df_gridstep.index[
                        (self.df_gridstep["X"] == step.end_x) & (self.df_gridstep["Y"] == step.end_y)
                    ].tolist()
                    cell_colors[start_idx] = color_start
                    cell_colors[end_idx] = color_end

            prev_changed_indices.update(newly_changed_indices)

            snapshot = pd.DataFrame({
                "X": self.df_gridstep["X"],
                "Y": self.df_gridstep["Y"],
                "Z": Z_current.copy(),
                "color": cell_colors.copy(),
                "cluster": cluster_id
            })
            df_snapshots.append(snapshot)

        final_colors = np.full(n_cells, color_init, dtype=object)
        final_colors[list(prev_changed_indices)] = color_prev
        df_snapshots.append(pd.DataFrame({
            "X": self.df_gridstep["X"],
            "Y": self.df_gridstep["Y"],
            "Z": Z_current.copy(),
            "color": final_colors,
            "cluster": "Final"
        }))

        n_clusters = len(df_snapshots)
        nrows = int(np.ceil(np.sqrt(n_clusters)))
        ncols = int(np.ceil(n_clusters / nrows))

        fig = plt.figure(figsize=(4*ncols, 4*nrows))
        for i, df_snap in enumerate(df_snapshots):
            ax = fig.add_subplot(nrows, ncols, i+1, projection='3d')

            X = df_snap["X"].to_numpy()
            Y = df_snap["Y"].to_numpy()
            Z = df_snap["Z"].to_numpy()
            colors = df_snap["color"].to_numpy()
            dz = Z - baseline

            ax.bar3d(
                X - dx/2,
                Y - dy/2,
                np.full_like(Z, baseline),
                dx, dy, dz,
                shade=True,
                color=colors,
                alpha=0.85,
                edgecolor='k',
                linewidth=0.3
            )

            ax.set_title(f"{df_snap['cluster'].iloc[0]}", fontsize=10, fontweight='medium')
            ax.view_init(elev=35, azim=-60)
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            ax.set_zlabel("Z")
            ax.set_zlim(baseline, Z.max() + 0.5)
            ax.grid(False)
            ax.axis('off')

        plt.tight_layout()
        plt.show()



class Cost:
    """Klasa sadrži različite Cost funkcije."""
    def __init__(self):
        pass

    def linear(self, distance):
        """Linearna Cost funckcija, prosto vraća distancu ćelija"""
        return np.array(distance)  
          
    def bilinear(self, distance, d_break=20, C1=0.03, C2=0.05, C3=5):
        """
        Bilinearna cost funkcija.

        Parametri:
        distance : array-like ili pandas DataFrame
            Udaljenosti između ćelija
        d_break : float
            Prelomna tačka bilinearne funkcije
        C1 : float
            Koeficijent pre prelomne tačke (kratke distance)
        C2 : float
            Koeficijent posle prelomne tačke (duge distance)
        C3 : float
            Fiksni trošak posle prelomne tačke

        Povratna vrednost:
        cost : istog tipa kao distance
        """
        return np.where(distance <= d_break,
                        C1 * distance,
                        C3 + C1*d_break + C2*(distance - d_break))
    
    def plot_cost(self, func, distance_range=(0, 200), **kwargs):
        """Plotuje graf date cost funkcije."""
        distances = np.linspace(distance_range[0], distance_range[1], 300)

        costs = func(distances, **kwargs)
        plt.figure(figsize=(8,5))
        plt.plot(distances, costs, label=f'{func.__name__} cost')
        plt.xlabel("Distance (m)")
        plt.ylabel("Cost")
        plt.title(f"{func.__name__.capitalize()} transport cost function")
        plt.grid(True)
        plt.legend()
        plt.show()





            
