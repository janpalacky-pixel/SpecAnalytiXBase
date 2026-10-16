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
    "GS_SPECTRA": ("spectra_tab.png", "Spectra tab",
                   "The Spectra tab (three treatment groups, divided by the maximum of the "
                   "1450 band): mean \u00b1 SD of each group, the corrected p-value along x, "
                   "and in yellow the regions where the groups differ."),
    "GS_MAP": ("map_roi_regions.png", "ROI regions on a 2D map",
               "Two ROI regions on the demo map of one cell (DNA band 770\u2013800): an "
               "ellipse on the nucleus and a rectangle in the cytoplasm."),
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
<p>The small orange <b>?</b> buttons in the window explain the part next to them (groups and
samples, the value, the test, one value per sample, the plot, the Test tab). The
<a href="#spectra"><b>Spectra</b> tab</a> compares the groups at every point along x, and in
the 2D Map <a href="#map-regions">ROI regions can be the groups</a>. New to the tool?
The <a href="help://group_statistics_tutorial"><b>step-by-step tutorial</b></a> walks through
four <a href="#demos">demo datasets</a> with a known answer: which value to set, which test to
choose and how to read the results.</p>
$GS_DIALOG_FIGURE

<h2>1. Give the spectra their groups</h2>
<p>The table lists the selected spectra with a <b>Group</b> column and an optional
<b>Sample</b> column (which independent sample each spectrum comes from &mdash; see
<a href="#replicates">Replicates</a>; it works like the Group column, also with the fill handle
and copy / paste). A spectrum without a group is left out. Ways to fill the Group column, which
can be combined:</p>
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
  last change (also a fill, paste or "Clear all groups"), from anywhere in the window;</li>
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
name and group (a header row "name, group" is recognised), and optionally a third column, the
<b>sample</b>, which then fills the Sample column too (in a text file the three columns must
be separated by a tab, semicolon or comma). In an Excel workbook the sheet named
<i>Groups</i> is used if there is one, otherwise the first sheet. In a text file the two may be
separated by a tab, comma, semicolon or space, and the names may contain spaces (e.g.
<code>run : temp_01 group1</code>): the spectrum names in the window are recognised at the
start of each line. The message afterwards says how many spectra were found and lists table
names that match no spectrum. Useful for larger studies: keep the
table with your data and reuse it.</li>
<li><b>Clear all groups</b> removes the groups of all spectra. To remove only some, select
their rows and press <b>Delete</b> (or right-click &rarr; <i>Remove group of selected
rows</i>); in the Sample column the same clears the samples.</li>
<li><b>Automatically</b> &mdash; when the window opens and no spectrum has a group yet, it looks
for a group table that belongs to the spectra's own data file: a sheet named <i>Groups</i> in
the Excel workbook they were imported from, or a file <code>&lt;data file name&gt;_groups.csv</code>
(or <code>.txt</code> / <code>.xlsx</code>) next to the data file, e.g.
<code>measurement_groups.csv</code> next to <code>measurement.txt</code>. Same columns as for
<i>From table file</i>. The spectra may be named by their column name in the data file
(<code>control_01</code>) or by their full name in the window
(<code>measurement : control_01</code>). A green line under the table says where the groups came
from; one Ctrl+Z (or right-click &rarr; Undo) removes them again. So you can prepare the groups once, next to the
data, and they are there every time you open the tool.</li>
</ul>
<p>When the groups, the samples or the value are changed after Compute, an orange line under
the results says so and the Compute button turns orange until you press it &mdash; the results
on screen then still belong to the old settings. The same after <b>Compare spectra</b> in the
Spectra tab: when the groups or samples change, the orange line says so and the Compare spectra
button turns orange. Group names that differ only in upper/lower
case or spaces ("Control" and "control") are flagged in red under the table: they count as
separate groups.</p>
<p>The Group cells are tinted with the group's colour in the plot (and the Spectra tab); the
Sample cells get a light colour per sample, so the spectra of one sample &mdash; or the two
measurements of a pair &mdash; are easy to spot. The group names under the table and in the
Summary and Values tabs use the same colours.</p>
<p>The groups and samples are remembered for the rest of the session (and in a snapshot), so
you can close the window and come back. They belong to the spectra themselves, not to their
names: a renamed spectrum keeps its group, while data imported again (even the same file) are
new spectra and start without the old groups. The window can be maximized, and the widths of the
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
<tr><td><b>Unequal spread</b> (compares means)</td><td>Welch t-test</td>
<td><b>Welch ANOVA</b>, then every pair with the <b>Games&ndash;Howell</b> test (with a 95&nbsp;%
confidence interval of each difference)</td></tr>
<tr><td><b>Non-parametric + Dunn</b></td><td>Mann&ndash;Whitney U test</td>
<td>Kruskal&ndash;Wallis test, then <b>Dunn's test</b> for every pair (Holm-corrected)</td></tr>
<tr><td><b>Permutation test</b> (no distribution assumed)</td><td>difference of the means,
10&nbsp;000 random relabellings</td><td>F statistic, 10&nbsp;000 relabellings; pairs by
permutation, Holm-corrected</td></tr>
<tr><td><b>Paired</b> (same samples in two groups)</td><td>paired t-test or Wilcoxon
signed-rank test</td><td>&mdash; (exactly two groups)</td></tr>
</table>
<p>The first two choices work exactly as in earlier versions; the others are for more specific
cases:</p>
<ul>
<li><b>Unequal spread</b> &mdash; when the groups clearly differ in spread (the check
"Same spread in all groups?" in the Test tab, Brown&ndash;Forsythe p &lt; 0.05). Classic ANOVA
assumes equal spread; Welch ANOVA and Games&ndash;Howell do not. With two groups it is the same
Welch t-test as "Parametric".</li>
<li><b>Non-parametric + Dunn</b> &mdash; Dunn's test is the standard follow-up of
Kruskal&ndash;Wallis: it compares the groups on the same ranks as the overall test.</li>
<li><b>Permutation test</b> &mdash; shuffles the group labels 10&nbsp;000 times and counts how
often a difference at least as large appears by chance. Needs no bell shape; good for small
groups and for any kind of value. The p-value can change in the 4th decimal place between
choices of random numbers; the program uses a fixed seed, so it is reproducible.</li>
<li><b>Paired</b> &mdash; the <i>same</i> samples measured in both groups, e.g. before / after
heating, or two conditions on each specimen. Fill the <b>Sample</b> column with the same name
for the two measurements of one sample (several spectra of one sample in a group are averaged
first). Pairing removes the differences <i>between</i> samples, so a small but consistent
change is found that the unpaired test misses. Paired t-test: Cohen's d<sub>z</sub> and the
95&nbsp;% interval of the mean difference; Wilcoxon: matched-pairs rank-biserial r. The paired
tests can only be chosen when there are exactly two groups and at least 3 samples appear in
both of them (greyed out otherwise, the tooltip says why; if one was chosen, the window switches
to Parametric and says so). The note under the plot says how many pairs were used and which
samples were left out because they have no partner with the same name in the other group
(e.g. &ldquo;6 pairs. Left out: s5, s6 (only in &lsquo;before&rsquo;); s66 (only in
&lsquo;after&rsquo;)&rdquo;).</li>
</ul>
<p><b>Which one?</b> The parametric tests are the usual choice and the most sensitive when the
values in each group are roughly bell-shaped. Use the non-parametric ones when a group
contains outliers or clearly skewed values, or with very small groups (fewer than about 5);
they only use the order of the values.</p>
<p><b>Several groups:</b> testing every pair separately would find "significant" differences
by chance far too often (with 5 groups there are 10 pairs). The pair p-values are therefore
<b>Holm-corrected</b>; use the corrected p (column "p (Holm)").</p>
<p><b>Compute and changing the test:</b> press <b>Compute</b> after choosing the groups and the
value. Afterwards, changing the test or <i>One value per sample</i> recomputes the results by
itself (the values of the spectra are kept, so this is fast even for peak fits of many
spectra); the Spectra tab too, if it shows a result.</p>
<p><b>Very small p-values</b> are shown as "p &lt; 0.0001" (the usual way to report them), with
the exact value in brackets in the Test tab, e.g. "p &lt; 0.0001 (p = 6.1 &times; 10&#8315;&#8312;)",
so different tests can be told apart. For the permutation test the smallest possible p is 1 /
10&nbsp;001. Note: when many spectra come from few samples (see
<a href="#replicates">replicates</a>), every test gives a tiny p &mdash; the problem is then the
data, not the test.</p>
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
<li><b>Values:</b> the value of every spectrum, with its group (and sample).</li>
<li><b>How large is the difference?</b> (Test tab, two groups) &mdash; the difference of the
means with its <b>95&nbsp;% confidence interval</b> (Welch), and Hedges' g with a 95&nbsp;%
bootstrap interval (2&nbsp;000 resamplings). If the interval of the difference does not include
0, the difference is significant at 5&nbsp;%; its width shows how precisely it is known.
With three or more groups (Unequal spread), every pair has its interval.</li>
<li><b>Checks of the test's assumptions</b> (information only, the test is always computed):
per group, is it roughly bell-shaped (Shapiro&ndash;Wilk p; below 0.05 = probably not), and do
the groups have the same spread (Brown&ndash;Forsythe p), with plain advice which test is safer.
With fewer than about 8 values these checks have little power: a large p is no proof.</li>
<li><b>Possible outliers</b> &mdash; values outside 1.5&nbsp;&times; the interquartile range
(Tukey's rule) are named in the Test tab and circled in red with <b>Mark outliers</b> above the
plot. They are never removed automatically: check the spectrum (a spike, a bad measurement?)
and leave it out by clearing its group if there is a reason.</li>
<li><b>Results sentence</b> &mdash; e.g. <i>"Welch t-test: t(17.3) = 4.21, p = 0.0006,
Hedges' g = 1.90 [95&nbsp;% CI 0.80; 3.00]; difference of means 0.12 [95&nbsp;% CI 0.05; 0.19];
n = 10 vs 10."</i> &mdash; <b>Copy results sentence</b> (Test tab) puts it on the clipboard
for the paper. Export&hellip; adds a <b>Report</b> sheet with the intervals, the checks and the
sentence.</li>
</ul>

<h2 id="replicates">Replicates: spectra of one sample are not independent</h2>
<p>The tests assume that every value is an <b>independent</b> measurement. Many spectra of the
<i>same</i> sample &mdash; the pixels of one map, the temperatures of one melt, repeated scans
of one cuvette &mdash; are not: they share everything that makes that sample special. Testing
500 pixels of one map against 500 pixels of another gives a tiny p-value although only one
sample per group was measured &mdash; the test then compares two maps, not two treatments
("pseudoreplication", Hurlbert 1984). This is the most common statistical mistake in
spectroscopy papers.</p>
<ul>
<li>The optional <b>Sample</b> column says which independent sample (specimen, culture,
cuvette, map, &hellip;) each spectrum comes from. Fill it like the Group column, with
<b>Set sample of selected rows&hellip;</b> or <b>Samples from names&hellip;</b> (e.g. the
common root name = the file or map).</li>
<li>Tick <b>One value per sample</b> (box 3): the spectra of each sample are averaged first,
so the test uses one value per independent sample. The plot, the summary and n then count
samples. Spectra without a sample count as their own sample.</li>
<li>When this is not ticked and the Sample column gives several spectra of a group the same
sample name (e.g. 15 spectra of one cell), a red warning names them: the program takes them as
measurements of one sample, but the test counts every spectrum as a separate sample. The
warning comes from the names only &mdash; it does not check the spectra or the p-value. With
real repeated measurements of one sample the test is usually too sure (the p-value too small);
if the spectra are in fact different samples, just give them different names. The same name
in <i>different</i> groups (s7 before / s7 after) is fine and gives no warning: it marks one
sample measured in both groups (used by the paired tests). With an
empty Sample column there is no such warning &mdash; the window works exactly as without this
feature.</li>
<li>With few samples per group the test has little power &mdash; a warning says so. Then a
non-significant result does not show that there is no difference; measure more samples.</li>
</ul>
<p>Comparing pixels of <i>one</i> map (e.g. two regions of one cell) is fine when the question
is about that one map; the p-value then says nothing about other cells or samples.</p>

<h2 id="spectra">Comparing along the whole spectrum (Spectra tab)</h2>
<p>One value per spectrum answers <i>whether</i> a chosen band differs. The <b>Spectra</b> tab
asks <i>where</i> along x the groups differ: it compares the groups at <b>every point</b> of
the spectrum.</p>
$GS_SPECTRA_FIGURE
<ul>
<li>The upper plot shows the mean spectrum of each group with a band: <i>mean &plusmn; SD</i>
(how much the spectra vary) or <i>mean &plusmn; 95&nbsp;% CI</i> (how precisely the mean is
known). The lower plot shows the corrected p-value at each point as
&minus;log<sub>10</sub>: 1.3 is p = 0.05 (red dashed line), 2 is 0.01, 3 is 0.001. Regions where
the groups differ significantly are shaded yellow and listed above the plot.</li>
<li><b>Whole spectrum (PERMANOVA)</b>: first, one overall answer to "do the spectra of the
groups differ at all?" &mdash; a permutation test on the distances between whole spectra
(Euclidean, 10&nbsp;000 permutations; not for the paired tests). Like ANOVA it also reacts to
groups that differ only in their spread.</li>
<li><b>Test</b> and <b>One value per sample</b> come from box 3 (changing them recomputes the
tab; Welch t-test / ANOVA, Welch
ANOVA, Mann&ndash;Whitney U / Kruskal&ndash;Wallis, permutation, paired t-test, Wilcoxon).</li>
<li><b>Normalize</b>: compare raw spectra only if their overall intensity is comparable.
<i>Divide by the maximum in a band</i> that does not change (e.g. the CH&#8322; band at
1450&nbsp;cm&#8315;&sup1;; it may lie outside the compared range) is usually clearest.
<i>Unit area</i> and <i>SNV</i> also remove the intensity, but a change of one band then
shifts all the other points too, so much of the spectrum may come out "different".</li>
<li><b>Correction</b>: hundreds of points are tested, and at 5&nbsp;% about one point in twenty
would be "significant" by chance. <i>FDR</i> (false discovery rate, Benjamini&ndash;Hochberg,
default) keeps the share of chance findings among the shaded points at about 5&nbsp;%;
<i>Holm</i> keeps the chance of even one false point at 5&nbsp;% (stricter). Neighbouring points
are strongly related, so read <b>regions</b>, not single points: an isolated point is often a
chance finding (they are counted, not listed).</li>
<li>A band that only <b>shifts</b> appears as two regions, one on each side of the band, with
no difference at its top.</li>
<li>Rank and permutation tests cannot give very small p-values with few spectra (e.g. with 8
pairs the Wilcoxon test gives at least p = 0.0078); after the correction for hundreds of
points they may find nothing. Use a narrower range, or the t-test / ANOVA.</li>
<li>Spectra on different x-axes are interpolated onto the points of the coarsest one, within
the x-range they all share.</li>
<li><b>Save plot&hellip;</b>; <b>Export table&hellip;</b> saves x, the mean, SD and n of every
group, p and the corrected p (Excel or CSV).</li>
</ul>

<h2 id="map-regions">Regions of a 2D map as groups</h2>
<p>In the <b>2D Map</b> window, draw two or more ROI regions (ROI &rarr; Add ROI rectangle /
ellipse / Paint ROI lasso), then <b>ROI &rarr; Compare ROI regions in Group
Statistics&hellip;</b>. A small window asks for a name for each region (regions with the same
name form one group; optionally the rest of the map is one more group), and Group Statistics
opens with the pixel spectra of the regions as groups. A pixel in two regions counts for the
first.</p>
$GS_MAP_FIGURE
<div class="warning">The regions are pixels of <b>one</b> map. The test compares these regions
within this map (e.g. "in this cell, the nucleus has more DNA signal than the cytoplasm"); it
says nothing about other cells or samples. To compare cells, measure several cells and compare
one value per cell (Sample column, <a href="#replicates">replicates</a>). A note under the table
says so.</div>
<p>The map's overall intensity often drifts (focus): normalize in the Spectra tab, and use
ratios of two bands as values.</p>

<h2 id="demos">Demo datasets</h2>
<p><b>Help &rarr; Test datasets &rarr; Synthetic &rarr; Group Statistics</b> opens five
artificial datasets whose true effects are known. Each workbook has a <i>Groups</i> sheet, so
after the import select all spectra and open Group Statistics: the groups (and samples) are
already filled in. The <i>Info</i> sheet of each workbook tells the story and what to try;
the <a href="help://group_statistics_tutorial"><b>tutorial</b></a> goes through them step by
step.</p>
<table>
<tr><th>Dataset</th><th>What it shows</th></tr>
<tr><td>Three treatment groups<br>(36 spectra, Group only)</td>
<td>control / low dose / high dose. The area of the 1655 band alone (1620&ndash;1690) shows
the effect only weakly (p &asymp; 0.03), because every spectrum has a random intensity scale; the
<i>Two bands</i> value A / B (integral 1620&ndash;1690 over integral 1420&ndash;1480) cancels
the scale and separates the three groups clearly (p &lt; 0.0001). The high-dose group has a larger spread
(Brown&ndash;Forsythe check; try the Welch ANOVA + Games&ndash;Howell test),
<i>Fitted peak position</i> 1560&ndash;1610 shows the shift of the 1585 band, and
<i>Mark outliers</i> circles control_05.</td></tr>
<tr><td>Cells with several pixels<br>(90 spectra, Group + Sample)</td>
<td>wild type / mutant, 3 cells each, 15 pixels per cell; there is <b>no</b> true difference.
Testing the 45 against 45 pixels gives a tiny p-value and the red
<i>not independent replicates</i> warning; with <i>One value per sample</i> it is 3 against 3
cells and not significant &mdash; the honest answer.</td></tr>
<tr><td>Paired before / after<br>(16 spectra, Group + Sample)</td>
<td>8 samples measured before and after heating, which lowers the 1655 band by 0.05 in every
sample. The ordinary test finds nothing (the samples differ much more than that); the
<i>paired t-test</i> pairs each sample with itself and finds the change clearly.</td></tr>
<tr><td>Skewed values (lipid in cells)<br>(30 spectra, Group only)</td>
<td>control / nitrogen starved, 15 cells each; starved cells have about 3 times more lipid
(band at 1745), but the amounts vary enormously from cell to cell (log-normal). The t-test
misses it (p &asymp; 0.07); Mann&ndash;Whitney U (p &asymp; 0.006) or the t-test on
log&#8322;(A / B) (p &asymp; 0.005) find it.</td></tr>
<tr><td>Map of one cell<br>(.mat, 40 &times; 30 pixels; no Groups sheet)</td>
<td>a Raman map of one cell: cytoplasm (protein) and nucleus (protein + DNA bands at 785 and
1095&nbsp;cm&#8315;&sup1;); the intensity drifts across the map. Open it in the 2D Map, draw a
region on the nucleus and one in the cytoplasm, and compare them: the DNA band differs
strongly, the protein band (1003) does not; in the Spectra tab the raw spectra differ almost
everywhere (the drift), divided by the 1450 band only the DNA bands remain.</td></tr>
</table>

<h2>Export</h2>
<p><b>Export&hellip;</b> saves an Excel workbook with three sheets (Values, Summary, Tests) or a
CSV file with the three tables one below the other. Both also get a <b>Report</b> part with
the confidence intervals, the checks and the results sentence (a fourth sheet / table).</p>

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
<li>Welch ANOVA: weights w<sub>i</sub> = n<sub>i</sub>/s<sub>i</sub>&sup2;, F = [&Sigma;w<sub>i</sub>(m<sub>i</sub>
&minus; m<sub>w</sub>)&sup2;/(k&minus;1)] / [1 + 2(k&minus;2)/(k&sup2;&minus;1)&middot;&Lambda;],
&Lambda; = &Sigma;(1&minus;w<sub>i</sub>/W)&sup2;/(n<sub>i</sub>&minus;1), df = (k&minus;1, (k&sup2;&minus;1)/(3&Lambda;));
effect: estimated &omega;&sup2; = df<sub>1</sub>(F&minus;1)/(df<sub>1</sub>(F&minus;1)+N). Games&ndash;Howell:
t = difference / &radic;(s<sub>i</sub>&sup2;/n<sub>i</sub> + s<sub>j</sub>&sup2;/n<sub>j</sub>), Welch df, p from
the studentized range distribution with q = |t|&radic;2. Dunn: z from the mean ranks of the
pooled ranking with tie correction, two-sided p, Holm. Checked against pingouin,
scikit-posthocs and statsmodels.</li>
<li>Permutation: |difference of means| (two groups) or the ANOVA F (more groups), 10&nbsp;000
relabellings, p = (count &ge; observed + 1)/(10&nbsp;001), seed 0. Bootstrap interval of
Hedges' g: percentile, 2&nbsp;000 resamplings of each group, seed 0; with fewer than 10
values in a group the bootstrap is unreliable, so there the usual approximation
SE = &radic;((n<sub>A</sub> + n<sub>B</sub>)/(n<sub>A</sub>n<sub>B</sub>) + g&sup2;/(2(n<sub>A</sub> + n<sub>B</sub>)))
is used (Hedges &amp; Olkin 1985). Difference of means:
Welch interval. Paired: scipy <code>ttest_rel</code>, <code>wilcoxon</code>; d<sub>z</sub> = mean / SD of
the differences.</li>
<li>Spectra tab (<code>group_spectra.py</code>): the spectra on one grid (the common x-axis,
or linear interpolation onto the points of the spectrum with the fewest points in the common
range); normalization per spectrum (maximum in the band over the whole common range; area by
the trapezoid rule, SNV over the compared range); the chosen test at every point
(<code>ttest_ind(equal_var=False)</code>, <code>f_oneway</code>, the Welch ANOVA above,
<code>mannwhitneyu</code>, <code>kruskal</code>, <code>ttest_rel</code>, <code>wilcoxon</code>;
permutation with 2&nbsp;000 relabellings, seed 0); Benjamini&ndash;Hochberg:
q<sub>(i)</sub> = min<sub>j&ge;i</sub> p<sub>(j)</sub>&middot;m/j, capped at 1 (valid for
positively dependent tests, as neighbouring points are); regions = runs of points with
q &lt; 0.05. PERMANOVA (Anderson 2001): pseudo-F = [SS<sub>between</sub>/(k&minus;1)] /
[SS<sub>within</sub>/(N&minus;k)] from squared Euclidean distances (computed from the group
means, which is the same for this distance), p = (count of permuted F &ge; observed + 1) /
10&nbsp;000, 9&nbsp;999 random relabellings, seed 0. For very large data (more than 10 million
numbers = spectra &times; points, e.g. every pixel of a big map) 1&nbsp;999, above 50 million
999 relabellings (fixed by the size, so the result is the same on every computer; the text
says how many); the relabellings run in batches as one matrix product, so even 20&nbsp;000
spectra of 1&nbsp;600 points take a few seconds.</li>
<li>Checks: <code>scipy.stats.shapiro</code> (3 &le; n &le; 5000), <code>levene(center="median")</code>
(Brown&ndash;Forsythe); outliers: Tukey's fences Q1 &minus; 1.5&nbsp;IQR, Q3 + 1.5&nbsp;IQR (n &ge; 4).
Module: <code>group_tests.py</code>.</li>
<li>Holm&ndash;Bonferroni: p-values sorted ascending, the k-th multiplied by (m &minus; k + 1),
made non-decreasing, capped at 1.</li>
<li>Hedges' g = (mean<sub>A</sub> &minus; mean<sub>B</sub>) / pooled SD &times;
(1 &minus; 3 / (4(n<sub>A</sub>+n<sub>B</sub>) &minus; 9)); rank-biserial r = 2U/(n<sub>A</sub>n<sub>B</sub>)
&minus; 1; &eta;&sup2; = SS<sub>between</sub>/SS<sub>total</sub>; &epsilon;&sup2; = H/(n &minus; 1).</li>
</ul>
<h3>References</h3>
<ul>
<li>Welch, B. L. (1951). On the comparison of several mean values: an alternative approach.
<i>Biometrika</i> 38, 330&ndash;336.</li>
<li>Games, P. A., Howell, J. F. (1976). Pairwise multiple comparison procedures with unequal
n's and/or variances. <i>J. Educ. Stat.</i> 1, 113&ndash;125.</li>
<li>Dunn, O. J. (1964). Multiple comparisons using rank sums. <i>Technometrics</i> 6,
241&ndash;252.</li>
<li>Shapiro, S. S., Wilk, M. B. (1965). An analysis of variance test for normality.
<i>Biometrika</i> 52, 591&ndash;611.</li>
<li>Brown, M. B., Forsythe, A. B. (1974). Robust tests for the equality of variances.
<i>J. Am. Stat. Assoc.</i> 69, 364&ndash;367.</li>
<li>Hurlbert, S. H. (1984). Pseudoreplication and the design of ecological field experiments.
<i>Ecol. Monogr.</i> 54, 187&ndash;211.</li>
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
<li>Hedges, L. V., Olkin, I. (1985). <i>Statistical Methods for Meta-Analysis.</i> Academic
Press.</li>
<li>Anderson, M. J. (2001). A new method for non-parametric multivariate analysis of
variance. <i>Austral Ecol.</i> 26, 32&ndash;46.</li>
<li>Benjamini, Y., Hochberg, Y. (1995). Controlling the false discovery rate: a practical and
powerful approach to multiple testing. <i>J. R. Stat. Soc. B</i> 57, 289&ndash;300.</li>
<li>Benjamini, Y., Yekutieli, D. (2001). The control of the false discovery rate in multiple
testing under dependency. <i>Ann. Stat.</i> 29, 1165&ndash;1188.</li>
</ul>
</body>
</html>
"""
