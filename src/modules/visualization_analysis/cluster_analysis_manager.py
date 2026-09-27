# src/modules/visualization_analysis/cluster_analysis_manager.py

import numpy as np
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_samples
import pandas as pd
import os
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
logger = get_logger(__name__)

class ClusterAnalysisManager:
    """Business logic for cluster analysis operations on spectra."""
    
    def __init__(self):
        self.reset()

    def reset(self):
        """Clear all previous results. Called when a new dialog is opened
        for a (possibly entirely different) set of spectra — without this,
        results from a previous, unrelated spectra set would persist and
        could be displayed (e.g. switching straight to PCA 3D) before the
        user ever clicks Run Clustering for the current selection."""
        # Clustering results
        self.cluster_labels = None
        self.n_clusters = None
        self.method = None
        self.linkage = 'ward'   # stored linkage method for dendrogram
        self.x_axis = None
        self.spectrum_labels = None
        self.data_matrix = None
        self.scaled_data = None
        self.pca_components = None
        self.explained_variance_ratio = None
        
        # Silhouette analysis results
        self.silhouette_avg_score = None
        self.silhouette_sample_scores = None

        # Human-readable reason the last compute_clustering() call
        # returned False, for the dialog to show instead of a generic
        # "Clustering failed" -- see compute_clustering's own use of this.
        self.last_error = None
        

    def compute_clustering(self, spectra, method='kmeans', n_clusters=3, progress_callback=None, **kwargs):
        """
        Perform cluster analysis on spectra.
        
        Args:
            spectra: List of spectrum dictionaries with 'x_scale', 'y_scale', 'label'
            method: Clustering method ('kmeans', 'hierarchical', 'dbscan')
            n_clusters: Number of clusters (for kmeans and hierarchical)
            progress_callback: optional callable(step, total_steps, label) called at
                each real stage boundary (data prep / clustering fit / PCA /
                silhouette). There's no way to get finer-grained progress than
                this: the clustering fit, PCA, and silhouette scoring are each
                a single opaque call into scikit-learn with no internal
                progress hooks, so anything claiming to animate smoothly
                *during* one of those calls would be faking it. Reporting the
                real stage boundaries instead is the honest version of a
                progress indicator here — same approach already used by
                compute_elbow_curve below.
            **kwargs: Additional method-specific parameters
            
        Returns:
            bool: True if clustering was successful
        """
        logger.debug(f"DEBUG: =================== CLUSTERING START ===================")
        logger.debug(f"DEBUG: compute_clustering called with:")
        logger.debug(f"DEBUG: method = '{method}'")
        logger.debug(f"DEBUG: n_clusters = {n_clusters}")
        logger.debug(f"DEBUG: kwargs = {kwargs}")
        logger.debug(f"DEBUG: spectra count = {len(spectra) if spectra else 0}")
        
        if not spectra:
            logger.debug("DEBUG: No spectra provided for clustering")
            self.last_error = "No spectra selected."
            return False

        self.last_error = None

        # Real case a user hit in practice: asking for more clusters than
        # there are spectra to put in them (e.g. 3 clusters for 2 selected
        # spectra) is mathematically impossible and sklearn correctly
        # refuses it -- but that refusal used to be swallowed by the
        # generic except block below and reported to the user as a bare
        # "Clustering failed", with the actual reason only visible in the
        # log file. Check it up front instead, with a message that says
        # what to actually do about it.
        if method in ('kmeans', 'hierarchical') and n_clusters is not None                 and n_clusters > len(spectra):
            msg = (f"Can't create {n_clusters} clusters from only "
                   f"{len(spectra)} selected spectra -- select at least "
                   f"{n_clusters} spectra, or lower the number of clusters.")
            logger.debug(f"DEBUG: {msg}")
            self.last_error = msg
            return False

        total_steps = 4

        def _report(step, label):
            if progress_callback is not None:
                progress_callback(step, total_steps, label)

        try:
            logger.debug(f"DEBUG: Computing {method} clustering with {n_clusters} clusters")
            _report(0, 'Preparing data…')
            
            # Extract data
            x_scales = [spectrum['x_scale'] for spectrum in spectra]
            y_scales = [spectrum['y_scale'] for spectrum in spectra]
            
            logger.debug(f"DEBUG: Extracted {len(y_scales)} spectra for clustering")
            logger.debug(f"DEBUG: First spectrum has {len(y_scales[0])} data points")
            
            # Check x-axis consistency. Uses axes_match (tolerance-aware,
            # scaled to the data) rather than exact np.array_equal — an
            # exact check here would be STRICTER than the controller's own
            # up-front validate_common_x_axis check that already ran
            # before this dialog was allowed to open. Two axes that are
            # physically identical but differ in float round-off (e.g.
            # one rebuilt arithmetically via Data Range linearisation)
            # would pass that promise and then fail here with a confusing
            # "clustering failed" the user has no way to explain.
            first_x = x_scales[0]
            for i, x in enumerate(x_scales):
                if not axes_match(first_x, x):
                    logger.error(
                        "Cluster analysis: %s",
                        describe_axis_mismatch(spectra[0], spectra[i], 'cluster analysis')
                        .replace('\n', ' ')
                    )
                    return False
                    
            logger.debug("DEBUG: All spectra have identical x-axes")
            
            # Construct data matrix (spectra x wavelengths)
            self.x_axis = first_x
            self.data_matrix = np.row_stack(y_scales)
            self.spectrum_labels = [spectrum['label'] for spectrum in spectra]
            self.method = method
            self.n_clusters = n_clusters
            
            logger.debug(f"DEBUG: Data matrix shape: {self.data_matrix.shape}")
            logger.debug(f"DEBUG: Storing method as: '{self.method}'")
            logger.debug(f"DEBUG: Storing n_clusters as: {self.n_clusters}")
            
            # Standardize data
            scaler = StandardScaler()
            self.scaled_data = scaler.fit_transform(self.data_matrix)
            logger.debug(f"DEBUG: Data standardized, scaled_data shape: {self.scaled_data.shape}")
            
            # Perform clustering
            logger.debug(f"DEBUG: ========== CLUSTERING ALGORITHM SELECTION ==========")
            
            if method == 'kmeans':
                logger.debug("DEBUG: Selected K-Means clustering algorithm")
                logger.debug(f"DEBUG: Creating KMeans with n_clusters={n_clusters}, random_state=42")
                clusterer = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, **kwargs)
                
            elif method == 'hierarchical':
                logger.debug("DEBUG: Selected Hierarchical clustering algorithm")
                linkage = kwargs.get('linkage', 'ward')
                self.linkage = linkage   # store for dendrogram
                logger.debug(f"DEBUG: Creating AgglomerativeClustering with n_clusters={n_clusters}, linkage='{linkage}'")
                clusterer = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage)
                
            elif method == 'dbscan':
                logger.debug("DEBUG: Selected DBSCAN clustering algorithm")
                eps = kwargs.get('eps', 0.5)
                min_samples = kwargs.get('min_samples', 2)
                logger.debug(f"DEBUG: Creating DBSCAN with eps={eps}, min_samples={min_samples}")
                clusterer = DBSCAN(eps=eps, min_samples=min_samples)
                
            else:
                logger.error(f"ERROR: Unknown clustering method: {method}")
                return False
            
            logger.info(f"DEBUG: Clusterer created: {type(clusterer).__name__}")
            logger.debug(f"DEBUG: Running fit_predict on scaled data...")
            _report(1, f'Running {method} clustering…')
            
            self.cluster_labels = clusterer.fit_predict(self.scaled_data)
            
            logger.debug(f"DEBUG: ========== CLUSTERING RESULTS ==========")
            logger.debug(f"DEBUG: Raw cluster_labels: {self.cluster_labels}")
            logger.debug(f"DEBUG: Cluster labels shape: {self.cluster_labels.shape}")
            logger.debug(f"DEBUG: Unique clusters found: {np.unique(self.cluster_labels)}")
            logger.debug(f"DEBUG: Number of unique clusters: {len(np.unique(self.cluster_labels))}")
            
            # Print cluster assignments
            for i, (label, cluster) in enumerate(zip(self.spectrum_labels, self.cluster_labels)):
                logger.debug(f"DEBUG: Spectrum '{label}' -> Cluster {cluster}")
            
            # Compute PCA for visualization
            logger.debug(f"DEBUG: Computing PCA for visualization...")
            _report(2, 'Computing PCA for visualization…')
            pca = PCA(n_components=min(3, len(spectra)))
            self.pca_components = pca.fit_transform(self.scaled_data)
            self.explained_variance_ratio = pca.explained_variance_ratio_
            
            logger.debug(f"DEBUG: PCA components shape: {self.pca_components.shape}")
            logger.debug(f"DEBUG: PCA explained variance ratio: {self.explained_variance_ratio}")
            
            # Compute silhouette analysis
            logger.debug(f"DEBUG: Computing silhouette analysis...")
            _report(3, 'Computing silhouette analysis…')
            self.compute_silhouette_analysis()
            _report(4, 'Done')
            
            logger.debug(f"DEBUG: Clustering complete - {len(np.unique(self.cluster_labels))} clusters found")
            logger.debug(f"DEBUG: =================== CLUSTERING END ===================")
            return True
            
        except Exception as e:
            logger.error(f"ERROR: Clustering failed: {e}")
            logger.exception("Traceback:")
            self.last_error = str(e)
            return False

    def compute_silhouette_analysis(self):
        """
        Compute silhouette analysis for clustering quality assessment.
        
        The silhouette analysis measures how similar a data point is to its own 
        cluster compared to other clusters. Values range from -1 to +1:
        - Near +1: Well separated from neighboring clusters
        - Near 0: On or very close to decision boundary between clusters  
        - Near -1: May have been assigned to wrong cluster
        """
        if self.cluster_labels is None or self.scaled_data is None:
            logger.debug("DEBUG: Cannot compute silhouette - no clustering results")
            self.silhouette_avg_score = None
            self.silhouette_sample_scores = None
            return
            
        # Check if we have at least 2 clusters (excluding noise points for DBSCAN)
        unique_labels = np.unique(self.cluster_labels)
        
        # For DBSCAN, exclude noise points (label -1) from silhouette analysis
        if self.method == 'dbscan' and -1 in unique_labels:
            valid_mask = self.cluster_labels != -1
            valid_labels = self.cluster_labels[valid_mask]
            valid_data = self.scaled_data[valid_mask]
            unique_valid_labels = np.unique(valid_labels)
            
            # sklearn's silhouette_samples requires 2 <= n_labels <=
            # n_samples - 1 -- not just "at least 2". Bug found in
            # practice: with few enough non-noise points, DBSCAN can end
            # up with every one of them in its own cluster (n_labels ==
            # n_valid_points), which passed this "< 2" check but then
            # raised ValueError inside silhouette_samples ("Number of
            # labels is N. Valid values are 2 to n_samples - 1") --
            # caught by compute_clustering's outer try/except, which
            # logged it and returned False for the whole clustering run
            # instead of just skipping this diagnostic. Silhouette score
            # is optional/diagnostic; the actual cluster labels are still
            # valid and useful even when there are too few points per
            # cluster to score them meaningfully, so skip gracefully
            # instead of failing the whole run.
            if len(unique_valid_labels) < 2 or len(unique_valid_labels) > len(valid_labels) - 1:
                logger.debug("DEBUG: Insufficient clusters for silhouette analysis (DBSCAN)")
                self.silhouette_avg_score = None
                self.silhouette_sample_scores = None
                return
                
            logger.debug(f"DEBUG: Computing silhouette for DBSCAN: {len(valid_labels)} points, {len(unique_valid_labels)} clusters")
            
            # Compute silhouette scores only for non-noise points. sklearn's
            # silhouette_score(X, labels) is literally
            # float(np.mean(silhouette_samples(X, labels))) internally (no
            # sampling here, since we never pass sample_size) — so calling
            # both separately, as this used to do, ran the same O(n^2)
            # pairwise-distance computation twice for an identical result.
            # For larger datasets this was easily the single most expensive
            # step in the whole clustering pipeline; computing it once and
            # deriving the average from it halves that cost.
            sample_scores_valid = silhouette_samples(valid_data, valid_labels)
            self.silhouette_avg_score = float(np.mean(sample_scores_valid))
            
            # Create full sample scores array with NaN for noise points
            self.silhouette_sample_scores = np.full(len(self.cluster_labels), np.nan)
            self.silhouette_sample_scores[valid_mask] = sample_scores_valid
            
        else:
            # Same upper-bound bug as the DBSCAN branch above: K-Means/
            # Hierarchical with n_clusters set equal to (or, degenerate
            # cases aside, close to) the number of selected spectra can
            # leave every point in its own cluster -- e.g. 3 clusters
            # requested for 3 selected spectra. That passed this "< 2"
            # check but crashed inside silhouette_samples, which requires
            # 2 <= n_labels <= n_samples - 1, taking down the whole
            # clustering run instead of just skipping this diagnostic.
            if len(unique_labels) < 2 or len(unique_labels) > len(self.cluster_labels) - 1:
                logger.debug("DEBUG: Insufficient clusters for silhouette analysis")
                self.silhouette_avg_score = None
                self.silhouette_sample_scores = None
                return
                
            logger.debug(f"DEBUG: Computing silhouette: {len(self.cluster_labels)} points, {len(unique_labels)} clusters")
            
            # Compute silhouette scores once (see the DBSCAN branch above for
            # why calling silhouette_score() as well would just repeat the
            # same expensive pairwise-distance computation for no reason).
            self.silhouette_sample_scores = silhouette_samples(self.scaled_data, self.cluster_labels)
            self.silhouette_avg_score = float(np.mean(self.silhouette_sample_scores))
        
        logger.debug(f"DEBUG: Silhouette average score: {self.silhouette_avg_score:.3f}")
        
        # Print per-cluster average scores
        for cluster_id in unique_labels:
            if self.method == 'dbscan' and cluster_id == -1:
                continue  # Skip noise points
            cluster_mask = self.cluster_labels == cluster_id
            if np.any(cluster_mask):
                cluster_scores = self.silhouette_sample_scores[cluster_mask]
                # Filter out NaN values for DBSCAN
                cluster_scores = cluster_scores[~np.isnan(cluster_scores)]
                if len(cluster_scores) > 0:
                    avg_score = np.mean(cluster_scores)
                    logger.debug(f"DEBUG: Cluster {cluster_id} average silhouette: {avg_score:.3f}")

    def get_silhouette_data(self):
        """
        Get silhouette analysis data for visualization.
        
        Returns:
            dict: Dictionary containing silhouette scores and metadata, or None if not available
        """
        if self.silhouette_avg_score is None or self.silhouette_sample_scores is None:
            return None
            
        return {
            'avg_score': self.silhouette_avg_score,
            'sample_scores': self.silhouette_sample_scores,
            'cluster_labels': self.cluster_labels,
            'spectrum_labels': self.spectrum_labels,
            'method': self.method
        }

    def export_cluster_members(self, filepath):
        """
        Export detailed cluster membership information to CSV.
        
        Args:
            filepath (str): Path to save the CSV file
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        if self.cluster_labels is None or self.spectrum_labels is None:
            logger.error("ERROR: No clustering data available for export")
            return False
            
        try:
            logger.debug(f"DEBUG: Exporting cluster members to {filepath}")
            
            # Create detailed membership data
            export_data = []
            
            for idx, (spectrum_label, cluster_id) in enumerate(zip(self.spectrum_labels, self.cluster_labels)):
                row_data = {
                    'Spectrum_Name': spectrum_label,
                    'Spectrum_Index': idx,
                    'Cluster_ID': cluster_id,
                    'Cluster_Name': f'Cluster_{cluster_id}' if cluster_id != -1 else 'Noise',
                    'Clustering_Method': self.method.upper(),
                }
                
                # Add silhouette score if available
                if self.silhouette_sample_scores is not None:
                    sil_score = self.silhouette_sample_scores[idx]
                    if not np.isnan(sil_score):
                        row_data['Silhouette_Score'] = round(sil_score, 4)
                        row_data['Silhouette_Quality'] = self._interpret_silhouette_score(sil_score)
                    else:
                        row_data['Silhouette_Score'] = 'N/A'
                        row_data['Silhouette_Quality'] = 'N/A (Noise)'
                
                # Add PCA coordinates if available
                if self.pca_components is not None:
                    n_components = self.pca_components.shape[1]
                    for comp_idx in range(n_components):
                        row_data[f'PC{comp_idx+1}'] = round(self.pca_components[idx, comp_idx], 4)
                
                export_data.append(row_data)
            
            # Convert to DataFrame and sort by cluster then by spectrum name
            df = pd.DataFrame(export_data)
            
            # Sort: noise points (-1) last, then by cluster ID, then by spectrum name
            df['sort_cluster'] = df['Cluster_ID'].apply(lambda x: 999 if x == -1 else x)
            df = df.sort_values(['sort_cluster', 'Spectrum_Name'])
            df = df.drop('sort_cluster', axis=1)
            
            # Export to CSV
            df.to_csv(filepath, index=False)
            
            # Generate summary statistics
            cluster_stats = self._generate_cluster_summary_stats()
            
            # Also save a summary file alongside the detailed export
            summary_filepath = filepath.replace('.csv', '_summary.csv')
            cluster_stats.to_csv(summary_filepath, index=False)
            
            logger.info(f"DEBUG: Successfully exported {len(export_data)} cluster members")
            logger.debug(f"DEBUG: Detailed file: {filepath}")
            logger.debug(f"DEBUG: Summary file: {summary_filepath}")
            
            return True
            
        except Exception as e:
            logger.error(f"ERROR: Failed to export cluster members: {e}")
            logger.exception("Traceback:")
            return False
    
    def _interpret_silhouette_score(self, score):
        """
        Provide text interpretation of silhouette score.
        
        Args:
            score (float): Silhouette coefficient
            
        Returns:
            str: Text interpretation
        """
        if score > 0.7:
            return "Excellent"
        elif score > 0.5:
            return "Good"
        elif score > 0.3:
            return "Moderate"
        elif score > 0:
            return "Weak"
        else:
            return "Poor"
    
    def _generate_cluster_summary_stats(self):
        """
        Generate summary statistics for each cluster.
        
        Returns:
            pd.DataFrame: Summary statistics
        """
        if self.cluster_labels is None:
            return pd.DataFrame()
        
        unique_labels = np.unique(self.cluster_labels)
        summary_data = []
        
        for cluster_id in unique_labels:
            cluster_mask = self.cluster_labels == cluster_id
            cluster_size = np.sum(cluster_mask)
            
            row_data = {
                'Cluster_ID': cluster_id,
                'Cluster_Name': f'Cluster_{cluster_id}' if cluster_id != -1 else 'Noise',
                'Size': cluster_size,
                'Percentage': round(100 * cluster_size / len(self.cluster_labels), 1)
            }
            
            # Add silhouette statistics if available
            if self.silhouette_sample_scores is not None:
                cluster_silhouettes = self.silhouette_sample_scores[cluster_mask]
                # Filter out NaN values
                cluster_silhouettes = cluster_silhouettes[~np.isnan(cluster_silhouettes)]
                
                if len(cluster_silhouettes) > 0:
                    row_data['Avg_Silhouette'] = round(np.mean(cluster_silhouettes), 4)
                    row_data['Min_Silhouette'] = round(np.min(cluster_silhouettes), 4)
                    row_data['Max_Silhouette'] = round(np.max(cluster_silhouettes), 4)
                    row_data['Std_Silhouette'] = round(np.std(cluster_silhouettes), 4)
                    row_data['Quality_Assessment'] = self._interpret_silhouette_score(np.mean(cluster_silhouettes))
                else:
                    row_data['Avg_Silhouette'] = 'N/A'
                    row_data['Min_Silhouette'] = 'N/A'
                    row_data['Max_Silhouette'] = 'N/A'
                    row_data['Std_Silhouette'] = 'N/A'
                    row_data['Quality_Assessment'] = 'N/A (Noise)'
            
            # Get spectrum names for this cluster
            cluster_spectra = [self.spectrum_labels[i] for i in range(len(self.spectrum_labels)) if cluster_mask[i]]
            row_data['Member_Spectra'] = '; '.join(sorted(cluster_spectra))
            
            summary_data.append(row_data)
        
        # Create DataFrame and add overall statistics
        df = pd.DataFrame(summary_data)
        
        # Add overall statistics row
        if self.silhouette_avg_score is not None:
            overall_row = {
                'Cluster_ID': 'OVERALL',
                'Cluster_Name': 'All Clusters',
                'Size': len(self.cluster_labels),
                'Percentage': 100.0,
                'Avg_Silhouette': round(self.silhouette_avg_score, 4),
                'Min_Silhouette': '',
                'Max_Silhouette': '',
                'Std_Silhouette': '',
                'Quality_Assessment': self._interpret_silhouette_score(self.silhouette_avg_score),
                'Member_Spectra': f'Method: {self.method.upper()}, Total Spectra: {len(self.cluster_labels)}'
            }
            
            # Convert to DataFrame with single row and concatenate
            overall_df = pd.DataFrame([overall_row])
            df = pd.concat([df, overall_df], ignore_index=True)
        
        return df

    def get_cluster_info(self):
        """Get clustering information including silhouette score."""
        if self.cluster_labels is None:
            return None
        
        unique_labels = np.unique(self.cluster_labels)
        cluster_sizes = [np.sum(self.cluster_labels == label) for label in unique_labels]
        
        info = {
            'n_clusters': len(unique_labels),
            'cluster_sizes': cluster_sizes,
            'cluster_labels': unique_labels.tolist(),
            'method': self.method
        }
        
        # Add silhouette score if available
        if self.silhouette_avg_score is not None:
            info['silhouette_score'] = self.silhouette_avg_score
            
        return info
    
    def get_cluster_members(self, cluster_id):
        """Get spectrum indices belonging to a cluster."""
        if self.cluster_labels is None:
            return []
        return np.where(self.cluster_labels == cluster_id)[0].tolist()
    
    def get_cluster_centroid(self, cluster_id):
        """Get average spectrum for a cluster."""
        if self.cluster_labels is None or self.data_matrix is None:
            return None, None
        
        members = self.get_cluster_members(cluster_id)
        if not members:
            return None, None
        
        centroid = np.mean(self.data_matrix[members, :], axis=0)
        return self.x_axis, centroid

    def compute_elbow_curve(self, spectra, max_clusters=10, progress_callback=None):
        """Compute within-cluster sum of squares for elbow plot.

        progress_callback, if given, is called as progress_callback(i, total)
        after each k value's fit completes — this loop runs up to 9 separate
        K-Means fits (each with 10 internal restarts via n_init=10), which can
        take a real, noticeable amount of time for many spectra.
        """
        if not spectra:
            return None, None
            
        try:
            # Prepare data - only need y_scales for clustering
            y_scales = [s['y_scale'] for s in spectra]
            data_matrix = np.row_stack(y_scales)
            
            # Standardize data
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(data_matrix)
            
            # Limit max_clusters to number of samples
            max_clusters = min(max_clusters, len(spectra) - 1)
            
            wcss = []
            k_values = list(range(2, max_clusters + 1))
            
            for i, k in enumerate(k_values):
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
                kmeans.fit(scaled_data)
                wcss.append(kmeans.inertia_)
                if progress_callback is not None:
                    if progress_callback(i + 1, len(k_values)) is False:
                        return None, None  # cancelled
            
            return k_values, wcss
            
        except Exception as e:
            logger.error(f"Error computing elbow curve: {e}")
            return None, None
    
    def _autofit_excel_columns(self, writer, sheet_name, df):
        """Widen each column enough to show its full header on first
        open — same fix applied to PCA/SVD/NMF's Excel export."""
        from openpyxl.utils import get_column_letter
        worksheet = writer.sheets[sheet_name]
        for i, col in enumerate(df.columns):
            width = max(len(str(col)) + 2, 10)
            worksheet.column_dimensions[get_column_letter(i + 1)].width = width

    def save_results_excel(self, filepath):
        """Save clustering results to Excel including silhouette analysis."""
        if self.cluster_labels is None:
            raise ValueError("No clustering data available")
        
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Cluster assignments with silhouette scores
                assignments_data = {
                    'Spectrum': self.spectrum_labels,
                    'Cluster': self.cluster_labels
                }
                
                # Add silhouette scores if available
                if self.silhouette_sample_scores is not None:
                    assignments_data['Silhouette_Score'] = self.silhouette_sample_scores
                    
                assignments_df = pd.DataFrame(assignments_data)
                assignments_df.to_excel(writer, sheet_name='Cluster_Assignments', index=False)
                self._autofit_excel_columns(writer, 'Cluster_Assignments', assignments_df)
                
                # PCA components if available
                if self.pca_components is not None:
                    n_components = self.pca_components.shape[1]
                    pca_data = {'Spectrum': self.spectrum_labels}
                    for i in range(n_components):
                        pca_data[f'PC{i+1}'] = self.pca_components[:, i]
                    pca_df = pd.DataFrame(pca_data)
                    pca_df.to_excel(writer, sheet_name='PCA_Components', index=False)
                    self._autofit_excel_columns(writer, 'PCA_Components', pca_df)
                
                # Cluster centroids
                unique_clusters = np.unique(self.cluster_labels)
                centroid_data = {'x_axis': self.x_axis}
                for cluster_id in unique_clusters:
                    _, centroid = self.get_cluster_centroid(cluster_id)
                    if centroid is not None:
                        centroid_data[f'Cluster_{cluster_id}_centroid'] = centroid
                
                centroid_df = pd.DataFrame(centroid_data)
                centroid_df.to_excel(writer, sheet_name='Cluster_Centroids', index=False)
                self._autofit_excel_columns(writer, 'Cluster_Centroids', centroid_df)
                
                # Silhouette analysis summary
                if self.silhouette_avg_score is not None:
                    silhouette_summary = []
                    silhouette_summary.append(['Overall_Average_Score', self.silhouette_avg_score])
                    
                    # Per-cluster averages
                    for cluster_id in unique_clusters:
                        cluster_mask = self.cluster_labels == cluster_id
                        if np.any(cluster_mask):
                            cluster_scores = self.silhouette_sample_scores[cluster_mask]
                            # Filter out NaN values for DBSCAN noise points
                            cluster_scores = cluster_scores[~np.isnan(cluster_scores)]
                            if len(cluster_scores) > 0:
                                avg_score = np.mean(cluster_scores)
                                silhouette_summary.append([f'Cluster_{cluster_id}_Average', avg_score])
                    
                    silhouette_df = pd.DataFrame(silhouette_summary, columns=['Metric', 'Value'])
                    silhouette_df.to_excel(writer, sheet_name='Silhouette_Analysis', index=False)
                    self._autofit_excel_columns(writer, 'Silhouette_Analysis', silhouette_df)
            
            return True
        except Exception as e:
            logger.error(f"Error saving clustering results: {e}")
            return False