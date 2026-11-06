"""Search a tool by name or by what it does (Qt-free).

The search field next to the drop-down lists of Spectra Processing and
Spectra Analysis & Visualization: the user types a part of a tool's name or a
word for what it does ("baseline", "smooth", "pca", "normalise") and gets the
closest tools first. A small typo is forgiven ("smoting" -> SG-smoothing).
"""
from difflib import SequenceMatcher
import re

# Words for what each tool does (besides its name and its group): what a
# user might type when looking for it.
KEYWORDS = {
    # Spectra Processing
    "Manual baseline": "baseline background points polynomial spline",
    "Automated Baseline": "baseline background automatic asls airpls arpls polynomial",
    "SNIP Baseline": "baseline background snip clipping",
    "SVD background": "baseline background svd singular value",
    "SG-smoothing": "smooth smoothing savitzky golay savgol derivative noise",
    "FFT Denoising": "denoise noise smooth fourier fft filter",
    "Data range": "range crop cut trim region limits x range",
    "Combine Spectra": "combine average mean sum merge",
    "Interactive subtraction": "subtract subtraction difference minus solvent buffer",
    "X-axis alignment": "align alignment shift x axis calibrate",
    "SVD Interpolation": "interpolate interpolation svd missing new spectra",
    "Spectral Calculator": "calculator formula math absorbance transmittance log ratio "
                           "derivative arithmetic",
    "Normalization": "normalize normalise normalization normalisation snv msc area maximum "
                     "max scale",
    "CD Unit Conversion": "cd circular dichroism units mdeg ellipticity delta epsilon mre",
    "X-axis Unit Conversion": "x axis units wavenumber wavelength nm cm-1 raman shift ev "
                              "convert",
    "Mean-Center Spectra (Dataset)": "mean center centre centering subtract mean dataset",
    "Spike removal": "spike spikes cosmic ray remove",
    "Cosmic ray removal": "cosmic ray rays spike spikes remove",
    "Resolution enhancement": "resolution sharpen deconvolution narrow bands",
    "Run Batch Pipeline": "batch pipeline many files automatic steps",
    # Spectra Analysis & Visualization
    "SVD analysis": "svd singular value decomposition components",
    "PCA Scores & Loadings": "pca principal component analysis scores loadings",
    "NMF": "nmf non negative matrix factorization factorisation components",
    "MCR-ALS": "mcr als multivariate curve resolution unmixing components",
    "Cluster analysis": "cluster clustering kmeans k-means hierarchical dendrogram groups",
    "SOM": "som self organizing organising map kohonen",
    "2D map": "map 2d image imaging hyperspectral raman map",
    "2D Correlation": "2d correlation noda synchronous asynchronous",
    "PLS / PLS-DA": "pls plsda regression calibration classification predict",
    "Peak Fitting": "peak peaks fit fitting deconvolution gaussian lorentzian voigt bands",
    "Band Ratio": "band ratio intensity ratio",
    "Reference Matching": "reference library match matching identify search",
    "Melting Curve Analysis": "melting melt thermal denaturation tm temperature curve",
    "Isosbestic Point Detection": "isosbestic point",
    "Kinetics Fitting": "kinetics kinetic time rate exponential",
    "QC / Outlier Detection": "qc quality outlier outliers check",
    "Group Statistics": "group groups statistics t-test anova compare",
    "Data table": "data table spreadsheet excel values",
    "Mixture analysis": "mixture components quantify amount least squares",
}


def _words(text):
    return [w for w in re.split(r"[^a-z0-9\-]+", str(text).lower()) if w]


def _score_word(word, name, words):
    """How well one typed word fits a tool: its name, its group and its
    keywords (`words`). 0 when not at all."""
    name_l = name.lower()
    if name_l.startswith(word):
        return 100
    if any(w.startswith(word) for w in _words(name)):
        return 90
    if word in name_l:
        return 80
    if any(w.startswith(word) for w in words):
        return 60
    if len(word) >= 3 and any(word in w for w in words):
        return 50
    # a typo: the closest word (only for words of 4 letters or more)
    if len(word) >= 4:
        best = max((SequenceMatcher(None, word, w).ratio() for w in _words(name) + words),
                   default=0.0)
        if best >= 0.75:
            return int(40 * best)
    return 0


def search(query, categories, limit=8):
    """The tools that fit `query` best, best first. `categories`: [(group,
    [tool, ...])] (the drop-down list's tree). Every typed word must fit."""
    typed = _words(query)
    if not typed:
        return []
    found = []
    order = 0
    for group, tools in categories:
        for tool in tools:
            words = _words(group) + _words(KEYWORDS.get(tool, ""))
            scores = [_score_word(w, tool, words) for w in typed]
            if all(scores):
                found.append((-sum(scores), order, tool))
            order += 1
    found.sort()
    return [tool for _, _, tool in found[:limit]]
