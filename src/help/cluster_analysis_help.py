# src/help/cluster_analysis_help.py

def get_cluster_analysis_help_title():
    return "Cluster Analysis — Help"

def get_cluster_analysis_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            h4    { color: #4A148C; margin-top: 10px; margin-bottom: 2px; }
            .cat  { background: #f5f5f5; padding: 10px 14px; margin: 6px 0; border-radius: 5px; }
            .detail { background: #FAFAFA; border-left: 4px solid #E65100;
                      padding: 10px 14px; margin: 6px 0 14px 0; border-radius: 3px; }
            .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note { background: #E3F2FD; border-left: 4px solid #1565C0;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn { background: #FFF8E1; border-left: 4px solid #F9A825;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm   { font-family: monospace; background: #ececec;
                    padding: 1px 5px; border-radius: 3px; }
            .det-link { font-size: 11px; color: #1565C0; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
            hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
        </style>
    </head>
    <body>

    <h1>Cluster Analysis</h1>

    <p>Cluster analysis groups similar spectra together based on their full spectral profiles.
    It is a <em>post-processing visualization tool</em> — apply it to already preprocessed spectra
    (baseline-corrected, normalized, etc.) to discover patterns and relationships.</p>

    <div class="note">
        <strong>Requirement:</strong> All selected spectra must share an identical x-axis
        (same wavenumber/wavelength points and same range). Use the <em>Data Range</em>
        step to harmonize spectra if needed.
    </div>

    <h2>Workflow</h2>
    <ol>
        <li>Select and preprocess spectra (baseline, normalization, smoothing).</li>
        <li>Choose <em>Cluster Analysis</em> from the visualization menu and click Run.</li>
        <li>Select a clustering method and set parameters.</li>
        <li>Click <strong>Run Clustering</strong>.</li>
        <li>Inspect results in different visualization modes.</li>
        <li>Check the <strong>Silhouette Analysis</strong> to assess cluster quality.</li>
        <li>Save results to Excel if needed.</li>
    </ol>

    <hr>
    <h2>Data preprocessing inside the algorithm</h2>

    <p>Before any clustering is performed, all spectra are automatically
    <strong>standardized</strong> using scikit-learn's <span class="fm">StandardScaler</span>:</p>
    <ul>
        <li>Each wavenumber channel is independently rescaled to zero mean and unit variance
            across all spectra: <span class="fm">x_scaled = (x &minus; mean) / std</span>.</li>
        <li>This ensures that high-intensity bands do not dominate the distance calculations
            simply because of their magnitude.</li>
        <li>Clustering and silhouette scores are computed in this standardized space.</li>
        <li>Centroids displayed in the <em>Centroids</em> view are computed from the
            <em>original</em> (unscaled) spectra so they are physically interpretable.</li>
    </ul>

    <div class="tip">
        <strong>Implication:</strong> If you have already normalized your spectra before
        clustering, standardization effectively re-weights all bands equally by their
        variability across the dataset. This is usually desirable — it means the clustering
        finds groups based on spectral <em>shape differences</em>, not absolute intensity.
    </div>

    <hr>
    <h2>Clustering methods</h2>

    <!-- K-Means -->
    <div class="cat">
        <h3>K-Means</h3>
        <p>Partitions spectra into K non-overlapping clusters by minimizing the
        within-cluster sum of squares (WCSS). Best when you expect roughly spherical,
        similarly sized groups and have an idea of how many clusters to expect.</p>
        <a class="det-link" href="#det-kmeans">&#9660; algorithm details</a>
    </div>

    <!-- Hierarchical -->
    <div class="cat">
        <h3>Hierarchical (Agglomerative)</h3>
        <p>Builds a tree of merges starting from individual spectra.
        The dendrogram shows which spectra merged at each step and at what distance.
        Does not require knowing K in advance — you cut the tree at any level.</p>
        <a class="det-link" href="#det-hierarchical">&#9660; algorithm details</a>
    </div>

    <!-- DBSCAN -->
    <div class="cat">
        <h3>DBSCAN</h3>
        <p>Density-based clustering — finds clusters as dense regions separated by sparse
        regions. Automatically determines the number of clusters and labels low-density
        spectra as <em>noise</em> (label &minus;1). Best when clusters have irregular shapes
        or the dataset contains genuine outliers.</p>
        <a class="det-link" href="#det-dbscan">&#9660; algorithm details</a>
    </div>

    <hr>
    <h2>Visualization modes</h2>

    <div class="cat">
        <h3>PCA 2D / PCA 3D</h3>
        <p>Projects all spectra into the first 2 or 3 principal components and plots
        them coloured by cluster. The percentage labels on each axis show how much
        spectral variance that component explains.</p>
        <div class="warn">
            <strong>Important:</strong> PCA is computed only for <em>visualization</em>;
            clustering and silhouette scores are computed in the full high-dimensional
            standardized space. A PCA plot that looks poorly separated does not necessarily
            mean the clusters are bad — it may simply mean the relevant variation is spread
            across many components beyond the first two or three.
        </div>
        <p>Click on any point (interactive mode) to highlight all members of that cluster.</p>
    </div>

    <div class="cat">
        <h3>Spectra view</h3>
        <p>Plots all raw spectra coloured by cluster membership. Useful for seeing the
        actual spectral differences that drove the grouping.</p>
    </div>

    <div class="cat">
        <h3>Centroids</h3>
        <p>Shows the mean spectrum of each cluster computed from the original
        (unscaled) intensities. Noise points (DBSCAN label &minus;1) are excluded.
        Useful for identifying the characteristic spectral signature of each group.</p>
    </div>

    <div class="cat">
        <h3>Silhouette Analysis</h3>
        <p>Primary tool for assessing cluster quality. See the
        <a href="#sil-section">Silhouette Analysis</a> section below.</p>
    </div>

    <div class="cat">
        <h3>Dendrogram <em>(Hierarchical only)</em></h3>
        <p>Shows the full merge tree. The y-axis is the linkage distance at which two
        groups merged — a large jump indicates a natural cluster boundary.
        The dendrogram uses the same linkage method you selected in the dialog.</p>
    </div>

    <div class="cat">
        <h3>Elbow Plot <em>(K-Means only)</em></h3>
        <p>Plots WCSS versus number of clusters k = 2&hellip;10. Look for the
        "elbow" — the point where adding more clusters gives diminishing returns.
        Use this together with the silhouette score to choose K.</p>
        <p>This means running K-Means up to 9 additional times (each with 10 internal
        restarts), which can take a while for many spectra — a progress dialog shows
        how far through it is, with a Cancel option. The result is cached: switching
        away from this view and back without re-running clustering reuses the cached
        plot instead of recomputing.</p>
    </div>

    <hr>
    <a name="sil-section"></a>
    <h2>Silhouette Analysis</h2>

    <p>The silhouette coefficient for a single spectrum i is:</p>
    <p>&nbsp;&nbsp;<span class="fm">s(i) = (b(i) &minus; a(i)) / max(a(i), b(i))</span></p>
    <ul>
        <li><span class="fm">a(i)</span> = mean distance from spectrum i to all other spectra
            in the <em>same</em> cluster (cohesion).</li>
        <li><span class="fm">b(i)</span> = mean distance from spectrum i to all spectra in the
            <em>nearest other</em> cluster (separation).</li>
        <li>Range: &minus;1 to +1. Values near +1 mean the spectrum is well inside its cluster
            and far from others; near 0 means it is on the boundary; negative means it is
            probably in the wrong cluster.</li>
    </ul>

    <p>The <strong>average silhouette score</strong> is the mean of s(i) over all
    (non-noise) spectra. Interpretation:</p>
    <table>
        <tr><th>Score</th><th>Interpretation</th></tr>
        <tr><td>&gt; 0.7</td><td>Excellent — clusters are well separated</td></tr>
        <tr><td>0.5 – 0.7</td><td>Good — reasonable cluster structure</td></tr>
        <tr><td>0.3 – 0.5</td><td>Moderate — overlapping but distinguishable clusters</td></tr>
        <tr><td>0 – 0.3</td><td>Weak — poor separation; consider adjusting parameters</td></tr>
        <tr><td>&lt; 0</td><td>Poor — spectra likely assigned to wrong clusters</td></tr>
    </table>

    <div class="note">
        <strong>Implementation note:</strong> Silhouette is computed in the standardized
        high-dimensional space using Euclidean distances — the same space used for clustering.
        DBSCAN noise points (label &minus;1) are excluded from both the average score and
        the silhouette plot.
    </div>

    <hr>
    <h2>Quick method selection guide</h2>
    <table>
        <tr><th>Situation</th><th>Recommended method</th></tr>
        <tr><td>Expected number of groups is known</td><td>K-Means or Hierarchical</td></tr>
        <tr><td>Want to explore the cluster hierarchy</td><td>Hierarchical + Dendrogram</td></tr>
        <tr><td>Unknown number of groups, outliers expected</td><td>DBSCAN</td></tr>
        <tr><td>Large dataset (&gt; 100 spectra)</td><td>K-Means (fastest)</td></tr>
        <tr><td>Small dataset with complex shapes</td><td>Hierarchical or DBSCAN</td></tr>
        <tr><td>Need to find optimal K</td><td>K-Means + Elbow Plot + Silhouette</td></tr>
    </table>

    <hr>
    <!-- ALGORITHM DETAILS -->
    <h2>Algorithm details</h2>

    <div class="detail">
        <a name="det-kmeans"></a>
        <h3>K-Means — algorithm</h3>
        <p><strong>Objective:</strong> minimise the within-cluster sum of squares (WCSS =
        <span class="fm">inertia</span> in scikit-learn):</p>
        <p>&nbsp;&nbsp;<span class="fm">WCSS = &sum;<sub>k</sub> &sum;<sub>i &isin; C<sub>k</sub></sub> &Vert;x<sub>i</sub> &minus; &mu;<sub>k</sub>&Vert;&sup2;</span></p>
        <p><strong>Implementation:</strong> <span class="fm">sklearn.cluster.KMeans</span> with
        <span class="fm">n_init=10</span> (10 random initialisations, best result kept) and
        <span class="fm">random_state=42</span> for reproducibility.</p>
        <p><strong>Initialisation:</strong> k-means++ by default — seeds centroids to be
        spread across the data, which greatly reduces the chance of a poor local minimum
        compared to random initialisation.</p>
        <p><strong>Elbow plot:</strong> WCSS is plotted for k = 2&hellip;10. The "elbow"
        is the k where the rate of decrease sharply flattens.</p>
        <p><strong>Limitations:</strong> assumes spherical, similarly sized clusters;
        sensitive to outliers; result depends on random initialisation (mitigated by n_init=10).</p>
    </div>

    <div class="detail">
        <a name="det-hierarchical"></a>
        <h3>Hierarchical (Agglomerative) — algorithm</h3>
        <p><strong>Implementation:</strong> <span class="fm">sklearn.cluster.AgglomerativeClustering</span>
        for cluster labels; <span class="fm">scipy.cluster.hierarchy.linkage</span> for the
        dendrogram (same linkage method used for both).</p>
        <p><strong>Linkage methods — how inter-cluster distance is defined:</strong></p>
        <ul>
            <li><strong>Ward</strong> — merges the pair that minimises the increase in total
                within-cluster variance. Tends to produce compact, similarly sized clusters.
                Recommended default.</li>
            <li><strong>Complete</strong> — distance between clusters = maximum distance between
                any two members. Produces tightly bounded clusters, sensitive to outliers.</li>
            <li><strong>Average</strong> — distance = mean distance between all pairs of members
                across the two clusters. A compromise between Ward and Complete.</li>
            <li><strong>Single</strong> — distance = minimum distance between any pair. Can
                produce elongated "chaining" clusters; rarely useful for spectroscopic data.</li>
        </ul>
        <p><strong>Dendrogram y-axis:</strong> the linkage distance at which two groups merged.
        A large gap between successive merge distances is evidence of a natural cluster boundary.</p>
        <p><strong>Note:</strong> the dendrogram uses the same linkage method you selected —
        it is not always Ward.</p>
    </div>

    <div class="detail">
        <a name="det-dbscan"></a>
        <h3>DBSCAN — algorithm</h3>
        <p><strong>Implementation:</strong> <span class="fm">sklearn.cluster.DBSCAN</span>.</p>
        <p><strong>Two parameters:</strong></p>
        <ul>
            <li><span class="fm">epsilon (&epsilon;)</span> — neighbourhood radius. A point q
                is a neighbour of p if their Euclidean distance in the standardised space is
                &le; &epsilon;.</li>
            <li><span class="fm">min_samples</span> — minimum number of neighbours
                (including self) for p to be a <em>core point</em>.</li>
        </ul>
        <p><strong>Labelling:</strong></p>
        <ul>
            <li><em>Core point:</em> has &ge; min_samples neighbours within &epsilon;.</li>
            <li><em>Border point:</em> within &epsilon; of a core point but has fewer
                neighbours itself.</li>
            <li><em>Noise point (label &minus;1):</em> neither core nor border — excluded from
                all silhouette calculations and centroid computations.</li>
        </ul>
        <p><strong>Choosing &epsilon;:</strong> DBSCAN operates in the standardised
        high-dimensional space. For spectral data with hundreds of wavenumber channels, typical
        inter-point distances are much larger than 1.0. A practical starting point is
        &epsilon; = 3&ndash;5; increase if too many noise points appear, decrease if all
        spectra end up in one cluster. The <em>k-distance plot</em> (not yet implemented) is
        the classical method for choosing &epsilon;.</p>
        <p><strong>Advantage over K-Means / Hierarchical:</strong> does not require specifying
        the number of clusters and naturally identifies outlier spectra as noise.</p>
    </div>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    plot point labels, dendrogram leaf labels, and cluster-member lists.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    </body>
    </html>
    """
