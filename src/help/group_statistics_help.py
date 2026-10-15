# src/help/group_statistics_help.py
"""Help for Analysis & Visualization -> Data Analysis -> Group Statistics."""

import os
import struct
from pathlib import Path
from string import Template

from src.modules.utils.resource_path import resource_path

_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "group_statistics")

# Shown only once the file exists (inserted as $<KEY>_FIGURE, empty if missing).
_OPTIONAL_FIGURES = {
    "GS_DIALOG": ("group_statistics_dialog.png", "Group Statistics window",
                  "The Group Statistics window: groups on the left, the value and the test "
                  "on the right, the plot below."),
    "GS_NAMES": ("groups_from_names.png", "Groups from spectrum names",
                 "Groups from the spectrum names: a text the names contain, or a part of "
                 "the name."),
    "GS_TEST": ("test_tab.png", "Test results",
                "The Test tab: the overall test and, for three or more groups, every pair "
                "with Holm-corrected p-values."),
}
_MAX_IMG_WIDTH = 700


def _png_size(path):
    with open(path, "rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(path)
    return struct.unpack(">II", header[16:24])


def _figures():
    values = {}
    for key, (filename, alt, caption) in _OPTIONAL_FIGURES.items():
        path = resource_path(os.path.join(_SCREENSHOT_DIR, filename))
        if not os.path.isfile(path):
            values[f"{key}_FIGURE"] = ''
            continue
        try:
            w, h = _png_size(path)
            dw = min(w, _MAX_IMG_WIDTH)
            dh = round(h * dw / w)
        except (OSError, ValueError):
            dw, dh = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)
        values[f"{key}_FIGURE"] = (
            f'<div class="screenshot"><img src="{Path(path).as_uri()}" width="{dw}" '
            f'height="{dh}" alt="{alt}" /><p class="caption">{caption}</p></div>')
    return values


def get_group_statistics_help_title():
    return "Group Statistics – Help"


def get_group_statistics_help_content():
    from src.help.help_figures import figure_substitutions
    values = _figures()
    values.update(figure_substitutions())
    return Template(_HTML).safe_substitute(values)


_HTML = """
<html>
<head>
<style>
    body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; max-width: 950px; }
    h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
    h3 { color: #1976D2; margin-top: 1.4em; }
    .tip { background-color: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin-top: 10px; }
    .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin-top: 10px; }
    table { border-collapse: collapse; }
    th, td { text-align: left; padding: 4px 8px; border: 1px solid #ccc; vertical-align: top; }
    .screenshot { margin: 10px 0; }
    .caption { font-size: 9pt; color: #555; }
</style>
</head>
<body>
<h1>Group Statistics</h1>
<p><b>Analysis &amp; Visualization &rarr; Data Analysis &rarr; Group Statistics</b> compares
groups of spectra &mdash; for example treated against control, or several samples &mdash; on
<b>one value per spectrum</b>, and tells you whether the groups differ more than chance
would explain, and by how much. It works on the selected spectra; they may have different
x-axes.</p>
$GS_DIALOG_FIGURE

<h2>1. Give the spectra their groups</h2>
<p>The table lists the selected spectra with a <b>Group</b> column. A spectrum without a group
is left out. Ways to fill it, which can be combined:</p>
<ul>
<li><b>Like a spreadsheet:</b>
  <ul>
  <li>click a Group cell and type (Enter or double-click edits it);</li>
  <li><b>fill handle:</b> select one or more Group cells and drag the small <b>green square</b>
  at the bottom-right corner of the selection down (or up): the value is repeated into all
  rows you drag over; several selected cells are repeated as a pattern (e.g.
  <i>A, B, A, B, &hellip;</i>). While dragging below the visible rows the table scrolls;</li>
  <li><b>Ctrl+D</b> (fill down): the top selected value goes into all selected rows;</li>
  <li><b>Ctrl+V</b> pastes a column of values, e.g. copied from Excel, starting at the first
  selected row; one copied value pasted into several selected rows fills them all;</li>
  <li><b>Ctrl+C</b>, <b>Ctrl+X</b>, <b>Delete</b> copy, cut and clear; <b>Ctrl+Z</b> undoes the
  last change (also a fill, paste or Clear);</li>
  <li>right-click: the same actions, plus <b>Select spectra&hellip;</b> (by name, range or every
  n-th, as in the main window) to select rows before giving them a group.</li>
  </ul></li>
<li><b>Set group of selected rows&hellip;</b> &mdash; select rows (click, Shift+click,
Ctrl+click) and give them one group name.</li>
<li><b>From names&hellip;</b> &mdash; from the spectrum names:
  <ul>
  <li><i>Common root name</i> (selected when the window opens; the same rule as in Select
  spectra / Rename): the group is the name without its numbering, in one click. E.g.
  <code>CD_spectra_TBA : 0019</code> &rarr; <code>CD_spectra_TBA</code>,
  <code>Glenodinium [r001_c001]</code> &rarr; <code>Glenodinium</code>,
  <code>Chlorella [r24_c14]</code> &rarr; <code>Chlorella</code>,
  <code>sample_012</code> &rarr; <code>sample</code>,
  <code>CD_melt_1_heating : CD [mdeg] T=45.00C</code> &rarr; <code>CD_melt_1_heating</code>
  (the file part before &ldquo; : &rdquo;). Ideal for spectra from several
  maps or files;</li>
  <li><i>Name contains a text:</i> one rule per line, <code>text = group</code>, e.g.
  <code>ctrl = Control</code> and <code>treat = Treated</code>. The first matching rule wins;
  upper/lower case is ignored. Just <code>ctrl</code> makes the group "ctrl".</li>
  <li><i>A part of the name:</i> split the name at a separator and use one part, e.g. with
  <code>_</code> and part 2, <code>cellA_day3_01</code> belongs to group <code>day3</code>
  (&minus;1 is the last part).</li>
  </ul>
  A preview shows the groups and their sizes before you press OK; the window's
  <b>Help</b> button explains the three ways with examples.</li>
<li><b>From table file&hellip;</b> &mdash; a text/CSV or Excel file with two columns, spectrum
name and group (a header row "name, group" is recognised). In a text file the two may be
separated by a tab, comma, semicolon or space, and the names may contain spaces (e.g.
<code>run : temp_01 group1</code>): the spectrum names in the window are recognised at the
start of each line. The message afterwards says how many spectra were found and lists table
names that match no spectrum. Useful for larger studies: keep the
table with your data and reuse it.</li>
<li><b>Clear</b> removes all groups.</li>
</ul>
<p>The groups are remembered for the rest of the session (by spectrum name), so you can close
the window and come back. The window can be maximized, and the widths of the
<b>Spectrum</b> and <b>Group</b> columns can be changed by dragging the border between
their headers.</p>
$GS_NAMES_FIGURE

<h2>2. Choose the value</h2>
<p>The <b>Value</b> list has three parts. The one-band and two-band values work for any spectra
(also with different x-axes); the whole-spectrum values need spectra with the same x-axis and
are greyed out otherwise. A grey line under the choice says what the chosen value is.</p>

$GROUP_VALUES_FIGURE

<h3>One band (one range)</h3>
<p>The same metrics as in the 2D Map and Band Ratio:</p>
<table>
<tr><th>Value</th><th>What it is</th></tr>
<tr><td>Intensity at x</td><td>The intensity at one x-value. <i>value:</i> the interpolated
point (one noisy point can decide it), the <b>average over x &plusmn; w</b>, or a <b>polynomial
fitted over x &plusmn; w</b> and read at x (smooths the noise, keeps the shape). w is the
half-width of the window.</td></tr>
<tr><td>Area (integral) over a range</td><td>Area under the spectrum from exactly the start to
exactly the end of the range, e.g. the area of a band (includes any background).</td></tr>
<tr><td>Baseline-corrected area</td><td>Area above the straight line joining the spectrum at
the two range edges: the band without a sloping background.</td></tr>
<tr><td>Mean over a range</td><td>The average height of the spectrum over the range (area /
width) &mdash; less noisy than one point.</td></tr>
<tr><td>Maximum (peak intensity) in a range</td><td>The highest intensity in the range.</td></tr>
<tr><td>Peak position</td><td>The x-position of the top of the band &mdash; compares band
shifts between groups.</td></tr>
<tr><td>FWHM</td><td>Width of the dominant band at half its height.</td></tr>
<tr><td>Variance in a range</td><td>Spread of the intensities within the range.</td></tr>
<tr><td>Fitted peak position / FWHM / height / area, Fit quality (R&sup2;)</td><td>One peak
plus a background is fitted to the range in every spectrum &mdash; the same fit as the 2D Map's
peak-fit maps (<b>Fit settings&hellip;</b>: shape, background, rejection rules; shared with the
2D Map). The position can lie between measured points and noise matters much less. A spectrum
whose fit is rejected gets no value.</td></tr>
</table>
<p><b>Peak top</b> (for Maximum and Peak position): <i>the highest point</i> (a noise spike can
win; the position is always a measured x) or <i>top of a parabola through the highest
points</i> (a parabola is fitted to the top 30&nbsp;% of the band found on a lightly smoothed
copy; noise matters less and the position can lie between measured points).</p>

<h3>Two bands (A and B)</h3>
<p>Range A and Range B, each with its own metric from the list above (e.g. fitted peak height
of A and area of B), combined by <b>Combine</b>:</p>
<table>
<tr><th>Combine</th><th>Meaning</th><th>A = 6, B = 3</th><th>A = 3, B = 6</th></tr>
<tr><td>A / B</td><td>ratio &mdash; independent of the overall intensity (focus,
concentration, path length)</td><td>2</td><td>0.5</td></tr>
<tr><td>A &minus; B</td><td>difference (e.g. of two peak positions: their distance)</td><td>3</td><td>&minus;3</td></tr>
<tr><td>A + B</td><td>sum</td><td>9</td><td>9</td></tr>
<tr><td>A &times; B</td><td>product</td><td>18</td><td>18</td></tr>
<tr><td>(A &minus; B) / (A + B)</td><td>normalised difference, always between &minus;1 and 1</td><td>0.33</td><td>&minus;0.33</td></tr>
<tr><td>log&#8322;(A / B)</td><td>log ratio: doubling and halving are equally large
(+1 / &minus;1), which suits tests better than A / B</td><td>1</td><td>&minus;1</td></tr>
</table>
<p>A combination that is undefined (division by zero, logarithm of a negative ratio) gives no
value. With both metrics <i>Integral</i> and <i>A / B</i> this is the classic band ratio.</p>

<h3>Whole spectrum (same x-axis needed)</h3>
<p>Optionally only within a range (<i>Use only the range below</i>).</p>
<table>
<tr><th>Value</th><th>What it is</th></tr>
<tr><td>PCA score</td><td>The score of each spectrum on principal component 1, 2, &hellip; of
the grouped spectra (mean-centred): do the groups differ along a main direction of
variation? The line below the results says how much of the variation the component
describes. The sign of a component is arbitrary (the test result does not depend on it).</td></tr>
<tr><td>SVD coefficient</td><td>The same without mean-centring; component 1 mostly follows the
overall intensity.</td></tr>
<tr><td>Correlation with a reference group</td><td>Pearson correlation of each spectrum with
the mean spectrum of the chosen reference group (e.g. control): 1 = the same shape. A
spectrum of the reference group itself is compared with the mean of the group's
<i>other</i> spectra, so it is not compared with itself.</td></tr>
<tr><td>Distance from a reference group</td><td>Root-mean-square difference between each
spectrum and the mean spectrum of the reference group (0 = identical), leave-one-out for the
reference group as above.</td></tr>
</table>
<p>The value, ranges and options are remembered for the rest of the session.</p>
<p><b>Starting values</b> (change them to your band): the window looks at the x-range that
<i>all</i> selected spectra share (e.g. 200&ndash;330 nm). <i>Intensity at x</i> starts in its
middle; one-band values start with the whole shared range; <i>Two bands</i> start
with two neighbouring ranges, each &#8539; of the shared range wide, just left and right of the
middle. A range you typed yourself is kept when you switch the value.</p>
<p>A spectrum that does not <b>completely</b> cover the x-value or range gets no value and is
left out; the red line below the results names it. (A value from only the part of the range a
spectrum has would look like a real, just smaller value, and comparing it with the others would
be meaningless.) If the selected spectra have <b>no x-range in common</b> (e.g. some 200&ndash;250 nm,
others 270&ndash;330 nm), a warning is shown under the value: one range cannot give all of them
a value, so the ones outside it are left out. If a <b>whole group</b> has no value, the line
below the results turns red and names it, and the plot title says it is not in the test
(the test then compares only the other groups).</p>

<h2 id="different-axes">Spectra with different x-axes or intensity scales</h2>
<p>What happens when the spectra were measured differently &mdash; with a different point
spacing, over a different x-range, or on a different intensity scale:</p>
<table>
<tr><th>Situation</th><th>One band / two bands</th><th>Whole spectrum (PCA, SVD, reference
group)</th></tr>
<tr><td><b>Different point spacing</b></td>
<td>No problem: every spectrum is computed on its own x-axis, nothing is resampled. Areas run
from exactly the start to exactly the end of the range, the mean is area / width (denser
points do not count more), the peak fit and the parabola use the spectrum's own points.</td>
<td rowspan="2">Need <b>the same x-axis</b> (the same points, apart from tiny rounding
differences): these values compare the spectra point by point, and points at different
x-positions would compare different things. Otherwise the four choices are <b>greyed out</b>
(the tooltip says why). To use them anyway, first bring all spectra onto one grid:
<i>Spectra Processing &rarr; Define Spectral Range</i>, the same X-min / X-max and
<i>Apply linearisation</i> with one X-step.</td></tr>
<tr><td><b>Different x-ranges</b></td>
<td>A spectrum that does not <b>completely</b> cover the range (or the x-value, or the
x &plusmn; w window) gets no value and is left out; the red line below the results names it.
No x-range in common at all: an orange warning under the value. A whole group without
values: named in red, and the plot title says it is not in the test.</td></tr>
<tr><td><b>Different intensity scales</b> (e.g. counts from one instrument, normalised data
from another)</td>
<td colspan="2">The program cannot detect this (the intensity numbers carry no units).
<b>Depend on the scale</b> &mdash; normalise first (<i>Spectra Processing &rarr;
Normalization</i>), or the groups differ only because of the scale: area, baseline-corrected
area, mean, maximum, variance, fitted height and area, SVD coefficient, distance from a
reference group.<br>
<b>Do not depend on the scale</b> &mdash; usable without normalising: peak position, FWHM,
fitted position and FWHM, fit quality (R&sup2;), correlation with a reference group, and the
two-band ratios A / B, (A &minus; B)/(A + B) and log&#8322;(A/B).</td></tr>
</table>

<h2>3. Choose the test and Compute</h2>
<table>
<tr><th></th><th>Two groups</th><th>Three or more groups</th></tr>
<tr><td><b>Parametric</b> (compares means)</td><td>Welch t-test (does not assume equal
spread in the groups)</td><td>One-way ANOVA, then every pair with a Welch t-test</td></tr>
<tr><td><b>Non-parametric</b> (compares ranks)</td><td>Mann&ndash;Whitney U test</td>
<td>Kruskal&ndash;Wallis test, then every pair with a Mann&ndash;Whitney U test</td></tr>
</table>
<p><b>Which one?</b> The parametric tests are the usual choice and the most sensitive when the
values in each group are roughly bell-shaped. Use the non-parametric ones when a group
contains outliers or clearly skewed values, or with very small groups (fewer than about 5);
they only use the order of the values.</p>
<p><b>Several groups:</b> testing every pair separately would find "significant" differences
by chance far too often (with 5 groups there are 10 pairs). The pair p-values are therefore
<b>Holm-corrected</b>; use the corrected p (column "p (Holm)").</p>
$GS_TEST_FIGURE

<h2>Reading the results</h2>
<ul>
<li><b>Plot</b> &mdash; choose above the plot (remembered for the session); <b>Save
plot&hellip;</b> writes it as PNG, TIFF (300 dpi), SVG or PDF. Every spectrum is a dot in all
three:
  <ul>
  <li><i>Box plot</i> (default): the box spans the middle half of the values, the black line
  is the median, the orange line the mean, the whiskers reach the furthest values within 1.5
  box lengths.</li>
  <li><i>Violin plot</i>: the shape of each group's values, estimated from the dots &mdash;
  shows e.g. a group that falls into two clusters (two sub-populations), which a box hides;
  that is a reason to use the non-parametric test. Black line: median, orange: mean. With
  fewer than about 10 values a group's shape is mostly guesswork; a note under the plot names
  such groups. A group with fewer than 2 different values gets no violin.</li>
  <li><i>Points with mean &plusmn; 95&nbsp;% CI</i>: the mean (orange) and its 95&nbsp;%
  confidence interval (black bar, from the t distribution: mean &plusmn; t &middot; SD /
  &radic;n) &mdash; the range in which the true group mean probably lies. It matches the
  t-test and ANOVA, and is preferred to bar charts by many journals.</li>
  </ul></li>
<li><b>Summary:</b> n, mean, standard deviation (SD), median, minimum and maximum per group.</li>
<li><b>p-value:</b> the probability of seeing a difference at least this large if the groups
were really the same. p below 0.05 is usually called statistically significant. A small p does
<i>not</i> mean the difference is large &mdash; with many spectra even tiny differences become
"significant".</li>
<li><b>Effect size</b> &mdash; how large the difference is, independent of the number of spectra:
  <ul>
  <li><i>Hedges' g</i> (two groups, parametric): the difference of the means in units of the
  standard deviation; about 0.2 small, 0.5 medium, 0.8 large.</li>
  <li><i>rank-biserial r</i> (Mann&ndash;Whitney): from &minus;1 to 1; 0 means no tendency,
  &plusmn;1 that every value of one group is larger than every value of the other.</li>
  <li><i>eta squared</i> (ANOVA) and <i>epsilon squared</i> (Kruskal&ndash;Wallis): the share of
  the variation explained by the groups, 0 to 1; about 0.01 small, 0.06 medium, 0.14 large.</li>
  </ul></li>
<li><b>Values:</b> the value of every spectrum, with its group.</li>
</ul>
<div class="warning"><b>Independent samples.</b> The tests assume that the spectra are
independent measurements. Many spectra of the <i>same</i> sample (e.g. points of one map) are
not independent of each other: comparing two maps pixel by pixel makes almost any difference
"significant". Compare per sample (e.g. the mean of each map) when you want to generalise to
samples.</div>

<h2>Export</h2>
<p><b>Export&hellip;</b> saves an Excel workbook with three sheets (Values, Summary, Tests) or a
CSV file with the three tables one below the other.</p>

<h2>Technical details</h2>
<ul>
<li>Values are computed from each spectrum's own x-axis: interpolation for <i>Intensity at
x</i>; areas by the trapezoid rule from exactly the lower to exactly the upper limit (the
spectrum is interpolated at the limits), mean = area / width, maximum from the points with x
between the limits. Shared with the 2D Map and Band Ratio
(<code>src/modules/utils/band_integration.py</code>); the values are in
<code>group_values.py</code>.
$AREA_OVER_A_RANGE_FIGURE</li>
<li>Intensity at x &mdash; fitted: <code>numpy.polyfit</code> of degree 2 to the points within
x &plusmn; w (at least 3), evaluated at x. Peak top &mdash; parabola: 5-point moving average,
its maximum, the connected points above 70&nbsp;% of the way from the minimum to that maximum
(at least 5), a degree-2 fit; the vertex is used if the parabola opens downwards and its
vertex lies within those points, otherwise the highest point. FWHM as in the 2D Map
(half-maximum crossings relative to the minimum of the range, linear interpolation; no value
if the band does not fall to half height on both sides).</li>
<li>PCA: singular value decomposition of the mean-centred matrix of the grouped spectra
(rows = spectra); score = U<sub>k</sub>&middot;s<sub>k</sub>; the sign is fixed so that the
largest loading is positive; explained share = s<sub>k</sub>&sup2; / &Sigma;s&sup2;. SVD: the
same without centring.</li>
<li>Tests: <code>scipy.stats.ttest_ind(equal_var=False)</code>, <code>f_oneway</code>,
<code>mannwhitneyu(alternative="two-sided")</code>, <code>kruskal</code>; all two-sided.
Groups with fewer than two values are left out of the tests (named below the results).</li>
<li>Holm&ndash;Bonferroni: p-values sorted ascending, the k-th multiplied by (m &minus; k + 1),
made non-decreasing, capped at 1.</li>
<li>Hedges' g = (mean<sub>A</sub> &minus; mean<sub>B</sub>) / pooled SD &times;
(1 &minus; 3 / (4(n<sub>A</sub>+n<sub>B</sub>) &minus; 9)); rank-biserial r = 2U/(n<sub>A</sub>n<sub>B</sub>)
&minus; 1; &eta;&sup2; = SS<sub>between</sub>/SS<sub>total</sub>; &epsilon;&sup2; = H/(n &minus; 1).</li>
</ul>
<h3>References</h3>
<ul>
<li>Welch, B. L. (1947). The generalization of "Student's" problem when several different
population variances are involved. <i>Biometrika</i> 34, 28&ndash;35.</li>
<li>Mann, H. B., Whitney, D. R. (1947). On a test of whether one of two random variables is
stochastically larger than the other. <i>Ann. Math. Stat.</i> 18, 50&ndash;60.</li>
<li>Kruskal, W. H., Wallis, W. A. (1952). Use of ranks in one-criterion variance analysis.
<i>J. Am. Stat. Assoc.</i> 47, 583&ndash;621.</li>
<li>Holm, S. (1979). A simple sequentially rejective multiple test procedure.
<i>Scand. J. Stat.</i> 6, 65&ndash;70.</li>
<li>Hedges, L. V. (1981). Distribution theory for Glass's estimator of effect size and related
estimators. <i>J. Educ. Stat.</i> 6, 107&ndash;128.</li>
</ul>
</body>
</html>
"""
