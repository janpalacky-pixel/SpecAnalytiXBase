# src/help/group_statistics_tutorial_help.py
"""Step-by-step tutorial for Group Statistics on the four demo datasets
(Help -> Test datasets -> Synthetic -> Group Statistics).

Every number quoted here is checked by tests/test_group_statistics_tutorial.py;
the screenshots are made by dev_notes/make_group_statistics_tutorial_figures.py.
"""

import os
import struct
from pathlib import Path
from string import Template

from src.modules.utils.resource_path import resource_path

_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots",
                               "group_statistics_tutorial")
_MAX_IMG_WIDTH = 760

# key -> (file, caption); inserted as $FIG_<key>, empty if the file is missing
_FIGURES = {
    "l1_opened": ("l1_opened.png", "The window right after opening: the Group column is "
                  "already filled in (green line under the table)."),
    "l1_why_normalize": ("l1_why_normalize.png", "Top left: three raw spectra (one per "
                         "group) - the weakly measured high-dose spectrum looks lowest. Top "
                         "right: the same spectra divided by their 1450 band. Bottom: the mean "
                         "of each group (12 spectra) divided by the 1450 band - the 1655 band "
                         "grows with the dose, and the 1585 band moves slightly to the right."),
    "l1_area": ("l1_area.png", "Lesson 1, the band alone: the dots of the groups overlap."),
    "l1_ratio": ("l1_ratio.png", "Lesson 1, the ratio of two bands: three clearly separated "
                 "groups."),
    "l1_ratio_test": ("l1_ratio_test.png", "The Test tab: the overall test and every pair."),
    "l1_checks": ("l1_checks.png", "Further down in the Test tab: the checks, the possible "
                  "outliers and the results sentence."),
    "l1_outliers": ("l1_outliers.png", "Mark outliers: control_05 is circled."),
    "l1_pc2": ("l1_pc2.png", "PCA score, component 2: the treatment effect."),
    "l2_violin": ("l2_violin.png", "Lesson 2, violin plot: most cells have little lipid, a "
                  "few have a lot (a long tail upwards)."),
    "l2_checks": ("l2_checks.png", "The checks: neither group is bell-shaped."),
    "l2_log": ("l2_log.png", "log₂(A / B): the long tail is gone, the t-test now sees "
               "the difference."),
    "l3_warning": ("l3_warning.png", "Lesson 3, one value per spectrum: a tiny p-value and "
                   "the red warning."),
    "l3_per_sample": ("l3_per_sample.png", "One value per sample: 3 cells against 3 cells."),
    "l4_unpaired": ("l4_unpaired.png", "Lesson 4, ordinary test: the differences between the "
                    "samples hide the change."),
    "l4_paired_test": ("l4_paired_test.png", "Paired t-test: the change is found clearly."),
    "l5_raw": ("l5_raw.png", "Lesson 5, raw spectra: no region differs (the random intensity "
               "hides everything)."),
    "l5_band": ("l5_band.png", "Divided by the maximum of the 1450 band: the 1655 band and "
                "both sides of the 1585 band differ."),
    "l5_area": ("l5_area.png", "Unit area: most of the spectrum comes out 'different'."),
    "l5_cells_warning": ("l5_cells_warning.png", "Cells demo, one value per spectrum: a "
                         "'difference' at 1655 and the red warning."),
    "l6_map": ("l6_map.png", "Lesson 6: the DNA-band map of one cell with two ROI regions "
               "(ellipse: nucleus, rectangle: cytoplasm); right: the spectrum of a nucleus "
               "pixel."),
    "l6_names": ("l6_names.png", "Naming the regions."),
    "l6_ratio": ("l6_ratio.png", "Group Statistics with the regions as groups: the DNA band "
                 "(770\u2013800 / 1420\u20131480)."),
    "l6_spectra_raw": ("l6_spectra_raw.png", "Spectra tab, raw: almost everything 'differs' "
                       "(the intensity drift across the map)."),
    "l6_spectra_band": ("l6_spectra_band.png", "Divided by the 1450 band: only the DNA bands "
                        "remain (785, 1095, 1578)."),
}


def _png_size(path):
    with open(path, "rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(path)
    return struct.unpack(">II", header[16:24])


def _figures():
    values = {}
    for key, (filename, caption) in _FIGURES.items():
        path = resource_path(os.path.join(_SCREENSHOT_DIR, filename))
        if not os.path.isfile(path):
            values[f"FIG_{key}"] = ''
            continue
        try:
            w, h = _png_size(path)
            dw = min(w, _MAX_IMG_WIDTH)
            dh = round(h * dw / w)
        except (OSError, ValueError):
            dw, dh = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)
        values[f"FIG_{key}"] = (
            f'<div class="screenshot"><img src="{Path(path).as_uri()}" width="{dw}" '
            f'height="{dh}" alt="{caption}" /><p class="caption">{caption}</p></div>')
    return values


def get_group_statistics_tutorial_help_title():
    return "Group Statistics – Tutorial"


def get_group_statistics_tutorial_help_content():
    return Template(_HTML).safe_substitute(_figures())


_HTML = """
<html>
<head>
<meta charset="utf-8">
<style>
    body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; max-width: 950px; }
    h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
    h3 { color: #1976D2; margin-top: 1.4em; }
    .tip { background-color: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin-top: 10px; }
    .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin-top: 10px; }
    .lesson { background-color: #e3f2fd; padding: 10px; border-left: 4px solid #1976D2; margin-top: 10px; }
    table { border-collapse: collapse; }
    th, td { text-align: left; padding: 4px 8px; border: 1px solid #ccc; vertical-align: top; }
    .screenshot { margin: 10px 0; }
    .caption { font-size: 9pt; color: #555; }
    .set { font-family: Consolas, monospace; background: #f4f4f4; padding: 1px 4px; }
</style>
</head>
<body>
<h1>Group Statistics &ndash; Tutorial</h1>
<p>Six short lessons, each with an artificial (synthetic) dataset whose true answer is known,
so you can see what the tool finds and why. Together they take about 45 minutes. The full
reference is the <a href="help://group_statistics">Group Statistics help</a>.</p>

<table>
<tr><th>Lesson</th><th>Dataset</th><th>You learn</th></tr>
<tr><td><a href="#l1">1</a></td><td>Three treatment groups</td>
<td>the basic steps; choosing a good value; reading the results; checks; outliers; other
values (peak position, PCA score)</td></tr>
<tr><td><a href="#l2">2</a></td><td>Skewed values (lipid in cells)</td>
<td>when the t-test misses an effect: non-parametric test or a logarithm</td></tr>
<tr><td><a href="#l3">3</a></td><td>Cells with several pixels</td>
<td>many spectra of one sample are not independent: the Sample column</td></tr>
<tr><td><a href="#l4">4</a></td><td>Paired before / after</td>
<td>the same samples measured twice: paired tests</td></tr>
<tr><td><a href="#l5">5</a></td><td>Three treatment groups, cells</td>
<td><i>where</i> along the spectrum the groups differ (Spectra tab); normalization</td></tr>
<tr><td><a href="#l6">6</a></td><td>Map of one cell</td>
<td>regions drawn on a 2D map as groups (nucleus vs cytoplasm)</td></tr>
</table>
<p>At the end: <a href="#which">which test when</a> and
<a href="#own">using your own data</a>.</p>

<h2 id="open">How to open a demo dataset (the same for every lesson)</h2>
<ol>
<li><b>Help &rarr; Test datasets &rarr; Synthetic &rarr; Group Statistics</b> and choose the
dataset.</li>
<li>The Import dialog opens with the file already chosen; press <b>Import</b>. If other spectra
are loaded, choose <b>Replace all</b> &mdash; one dataset at a time keeps it simple.</li>
<li>Select all spectra in the spectra list (click one, then Ctrl+A).</li>
<li><b>Analysis &amp; Visualization &rarr; Data Analysis &rarr; Group Statistics.</b></li>
</ol>
<p>The Group column (and in lessons 3 and 4 the Sample column) is <b>already filled in</b>: every
demo workbook has a sheet <i>Groups</i>, which the window reads by itself. A green line under
the table says so. (If you opened the window with these spectra before, the groups are simply
remembered and the green line does not appear.)</p>
$FIG_l1_opened
<p>The orange <b>?</b> buttons in the window explain each part. Numbers below are rounded; you
should see the same ones.</p>

<h2 id="l1">Lesson 1 &ndash; Three treatment groups: the basic steps</h2>
<p><b>Dataset:</b> <i>Group Statistics &mdash; three treatment groups</i> (36 spectra).
<b>Story:</b> cells grown without a drug (<i>control</i>), with a low dose and with a high dose,
12 cells each, one spectrum per cell. The drug makes the band at 1655&nbsp;cm&#8315;&sup1; grow
with the dose <b>relative to the other bands</b> (e.g. the CH&#8322; band at
1450&nbsp;cm&#8315;&sup1;), and shifts the band at 1585&nbsp;cm&#8315;&sup1; by about
1.5&nbsp;cm&#8315;&sup1;. Every spectrum also has a random overall intensity (focus, laser
power; &plusmn;30&nbsp;%) &mdash; as in real measurements. One control cell (control_05) is
unusual.</p>
<div class="warning"><b>You will not see the dose effect if you just plot a few spectra.</b> A
high-dose spectrum that happened to be measured 40&nbsp;% weaker looks <i>lower</i> than a
control spectrum, although its 1655 band is larger relative to its 1450 band. Normalize the
spectra to the 1450 band (maximum in the range 1420&ndash;1480) and plot them again: then the
1655 band grows control &lt; low dose &lt; high dose. This is exactly the problem that steps 1
and 2 below show &mdash; and solve &mdash; in Group Statistics.</div>
$FIG_l1_why_normalize

<h3>Step 1 &ndash; the band alone</h3>
<p>Value <span class="set">Area (integral) over a range</span>, Range
<span class="set">1620</span> to <span class="set">1690</span>. Leave the test at
<span class="set">Parametric: Welch t-test / one-way ANOVA</span> and press <b>Compute</b>.</p>
$FIG_l1_area
<p>The plot shows each spectrum as a dot; the box holds the middle half of the group, the
black line is the median, the orange line the mean. A dot's <i>height</i> is its value; it is
moved sideways only so that it does not cover another dot (the sideways position means
nothing; <span class="set">Dots</span> next to the plot type offers other ways). The values
of the three groups overlap a lot. The title says
<b>p = 0.03</b>, but the pairs in the Test tab are confusing: control vs low dose p &asymp;
0.03, control vs high dose p &asymp; 0.07, low vs high dose p &asymp; 0.88 &mdash; as if the
high dose did no more than the low dose.</p>
<div class="lesson"><b>Why?</b> The area depends on the overall intensity of each spectrum. The
random intensity (&plusmn;30&nbsp;%) is larger than the effect of the drug and hides it.</div>

<h3>Step 2 &ndash; two bands: cancel the intensity</h3>
<p>Value <span class="set">Two bands A and B (e.g. area A / area B)</span>; Range A
<span class="set">1620&ndash;1690</span> <span class="set">Integral</span>, Range B
<span class="set">1420&ndash;1480</span> <span class="set">Integral</span>, Combine
<span class="set">A / B</span>. <b>Compute.</b></p>
$FIG_l1_ratio
<p>Now the three groups are clearly apart, in the order of the dose: <b>p &lt; 0.0001</b>, and
every pair p &lt; 0.0001.</p>
<div class="lesson"><b>Lesson:</b> when the overall intensity of your spectra varies (it almost
always does), compare a <b>ratio</b> to a band that the treatment does not change (here the
CH&#8322; band at 1450&nbsp;cm&#8315;&sup1;) instead of a raw height or area. Normalizing the
spectra first does the same job.</div>

<h3>Step 3 &ndash; read the Test tab</h3>
$FIG_l1_ratio_test
<ul>
<li><b>One-way ANOVA</b> &mdash; the test used for three or more groups (for two groups it is the
Welch t-test). <b>p &lt; 0.0001</b>: a difference this large would almost never appear by
chance if the groups were really the same.</li>
<li><b>eta squared = 0.82</b> &mdash; the effect size: 82&nbsp;% of the variation of the values
is explained by the group. (p says <i>whether</i> there is a difference, the effect size
<i>how large</i> it is.)</li>
<li><b>Pairs</b> &mdash; every pair of groups. <i>Difference of means</i>: control is 0.135 lower
than low dose, and so on. <i>p (Holm)</i>: the p-value corrected because three comparisons
were made (more comparisons = more chances for a false positive); use this column.
<i>Hedges' g</i>: the difference in units of the spread within the groups; about 0.2 is
small, 0.5 medium, 0.8 or more large. Here it is &minus;2.7 to &minus;4.0: very large.</li>
</ul>

<h3>Step 4 &ndash; the checks</h3>
<p>Scroll down in the Test tab:</p>
$FIG_l1_checks
<ul>
<li><b>Bell-shaped? Shapiro&ndash;Wilk p</b>: the ANOVA assumes roughly bell-shaped values.
Control has p &asymp; 0.0005 &mdash; not bell-shaped, because of control_05.</li>
<li><b>Same spread? Brown&ndash;Forsythe p &asymp; 0.013</b>: the high-dose cells vary more than
the others (built into this dataset).</li>
<li>The advice suggests <span class="set">Unequal spread: Welch t-test / Welch ANOVA +
Games&ndash;Howell</span>. Choose it and press Compute: still <b>p &lt; 0.0001</b> for the
whole test and every pair.</li>
</ul>
<div class="lesson"><b>Lesson:</b> the checks are information, not a verdict. If the
recommended test gives the same answer, the conclusion is safe. Never try tests until one
gives p &lt; 0.05 &mdash; choose the test from the nature of the data (see
<a href="#which">which test when</a>), ideally before you look at the result.</div>

<h3>Step 5 &ndash; outliers</h3>
<p>Plot tab: tick <span class="set">Mark outliers</span>.</p>
$FIG_l1_outliers
<p>control_05 is circled (also named in the Test tab under <i>Possible outliers</i>). The tool
never removes it. Look at that spectrum: remove a spectrum only for a real reason (a
measurement error, a different sample), never just because it does not fit.</p>

<h3>Step 6 &ndash; other values</h3>
<ul>
<li><span class="set">Fitted peak position</span>, Range
<span class="set">1560&ndash;1610</span> (test back to Parametric): the band position of each
spectrum from a peak fit. The Summary tab gives the means 1584.9 / 1585.6 / 1586.4&nbsp;cm&#8315;&sup1;
&mdash; exactly the shift built into the data; p &lt; 0.0001. A shift of 1.5&nbsp;cm&#8315;&sup1;
is far below the point spacing (1&nbsp;cm&#8315;&sup1;) but the fit finds it.</li>
<li><span class="set">PCA score</span> (whole spectrum), Component
<span class="set">1</span>: p &asymp; 0.34, and the note says component 1 describes 89&nbsp;% of
the variation &mdash; that is the random intensity, not the treatment. Component
<span class="set">2</span> (10&nbsp;%): <b>p &lt; 0.0001</b>.</li>
</ul>
$FIG_l1_pc2
<div class="lesson"><b>Lesson:</b> the largest variation in the spectra is not always the
interesting one. Try several components.</div>

<h3>Step 7 &ndash; report the result</h3>
<p><b>Copy results sentence</b> (Test tab) puts a sentence like this on the clipboard, ready for
a paper:<br><i>Welch ANOVA: F(2, 17.4) = 52.6, p &lt; 0.0001, omega squared (est.) = 0.74;
n = 12 vs 12 vs 12.</i><br><b>Export&hellip;</b> saves all values, the summary, the tests and a
report to Excel.</p>

<h2 id="l2">Lesson 2 &ndash; Skewed values: when the t-test misses an effect</h2>
<p><b>Dataset:</b> <i>Group Statistics &mdash; skewed values (lipid in cells)</i> (30 spectra).
<b>Story:</b> lipid in algal cells, 15 control and 15 nitrogen-starved cells. Starved cells
store about <b>3 times more lipid</b> (band at 1745&nbsp;cm&#8315;&sup1;). But lipid varies
enormously from cell to cell: most cells have little, a few have a lot. Amounts and
concentrations often behave like this ("skewed", log-normal).</p>
<h3>Step 1 &ndash; the usual test</h3>
<p>Value <span class="set">Two bands A and B</span>; A <span class="set">1715&ndash;1775</span>
<span class="set">Baseline-corrected integral</span>, B
<span class="set">1420&ndash;1480</span> <span class="set">Baseline-corrected integral</span>,
Combine <span class="set">A / B</span>; test <span class="set">Parametric</span>. Compute:
<b>p &asymp; 0.074</b> &mdash; "not significant". Choose the plot
<span class="set">Violin plot</span>:</p>
$FIG_l2_violin
<p>The shape of each group: a heap of low values and a long tail upwards. The few very high
values make the mean and the spread large, and the t-test loses its power.</p>
$FIG_l2_checks
<p>The checks say it too: neither group is bell-shaped (Shapiro&ndash;Wilk p &lt; 0.0001 and
0.0045), and the advice suggests a non-parametric test.</p>
<h3>Step 2 &ndash; two ways out</h3>
<ul>
<li>Test <span class="set">Non-parametric: Mann&ndash;Whitney U / Kruskal&ndash;Wallis</span>:
<b>p &asymp; 0.006</b>. It compares the order (ranks) of the values, so a few very high
values do not dominate.</li>
<li>Or keep <span class="set">Parametric</span> and set Combine to
<span class="set">log&#8322;(A / B)</span>: <b>p &asymp; 0.005</b>, and now both groups are
bell-shaped (Shapiro&ndash;Wilk p &asymp; 0.91). A logarithm turns "3 times more" into "a
fixed step up".</li>
</ul>
$FIG_l2_log
<div class="lesson"><b>Lesson:</b> for amounts, concentrations and ratios that vary over a wide
range, use a non-parametric test or log&#8322;(A / B). The "possible outliers" named here are not
mistakes &mdash; they are the long tail and must stay in.</div>

<h2 id="l3">Lesson 3 &ndash; Cells with several pixels: what counts as a replicate</h2>
<p><b>Dataset:</b> <i>Group Statistics &mdash; cells with several pixels (samples)</i> (90
spectra). <b>Story:</b> wild type and mutant, 3 cells each; every cell was measured at 15 points
(pixels of a map), so 15 spectra per cell and 45 per group. The truth: there is <b>no
difference</b> between wild type and mutant &mdash; but the cells differ from each other, and
the 15 spectra of one cell are very similar. Here both the Group and the <b>Sample</b> column
(which cell) are filled in.</p>
<h3>Step 1 &ndash; one value per spectrum</h3>
<p>Value <span class="set">Two bands A and B</span>; A <span class="set">1620&ndash;1690</span>
<span class="set">Integral</span>, B <span class="set">1420&ndash;1480</span>
<span class="set">Integral</span>, <span class="set">A / B</span>. Compute:
<b>p &lt; 0.0001</b> &mdash; and a <b>red warning</b>.</p>
$FIG_l3_warning
<p>The test believes it has 45 independent measurements per group. In fact it has 3 cells per
group, each counted 15 times. With only 3 cells it is easy for the 3 wild-type cells to be a
bit higher by chance, and 15 copies of each make that look certain.</p>
<h3>Step 2 &ndash; one value per sample</h3>
<p>Tick <span class="set">One value per sample (average its spectra)</span> and Compute
again: the spectra of each cell are averaged first, n = 3 vs 3, <b>p &asymp; 0.26</b> &mdash;
no significant difference, which is the truth.</p>
$FIG_l3_per_sample
<div class="lesson"><b>Lesson:</b> the n that counts is the number of <b>independent
samples</b> (cells, cultures, patients, maps), not the number of spectra. Fill the Sample column
and tick <i>One value per sample</i> whenever several spectra come from one sample. With so few
samples the test has little power: "not significant" does not prove "no difference" &mdash;
measure more cells.</div>

<h2 id="l4">Lesson 4 &ndash; Paired before / after</h2>
<p><b>Dataset:</b> <i>Group Statistics &mdash; paired before / after</i> (16 spectra).
<b>Story:</b> 8 samples, each measured before and after heating. The samples differ a lot from
each other (band 1655&nbsp;cm&#8315;&sup1; between about 0.6 and 1.4), and heating lowers the
band by only 0.05 &mdash; but in every sample. The Sample column (s1 &hellip; s8) says which
spectra belong together.</p>
<h3>Step 1 &ndash; the ordinary test</h3>
<p>Value <span class="set">Maximum (peak intensity) in a range</span>,
<span class="set">1630&ndash;1680</span>, test <span class="set">Parametric</span>. Compute:
<b>p &asymp; 0.64</b>. The differences between the samples are much larger than the change, so
the two groups look the same.</p>
$FIG_l4_unpaired
<h3>Step 2 &ndash; the paired test</h3>
<p>Test <span class="set">Paired (same samples): paired t-test</span>. Compute: <b>p &lt;
0.0001</b>. The paired test looks at the change <i>within</i> each sample (s1 after minus s1
before, &hellip;), so the differences between the samples no longer matter. The difference
before &minus; after is 0.048 with 95&nbsp;% confidence interval 0.034 to 0.062: the true
change (0.05) lies inside.</p>
$FIG_l4_paired_test
<p>The non-parametric version, <span class="set">Paired (same samples): Wilcoxon signed-rank
test</span>, gives p &asymp; 0.008 &mdash; with 8 pairs the smallest possible value, because the
band went down in all 8 samples.</p>
<div class="lesson"><b>Lesson:</b> if the same samples were measured in both groups, use a
paired test &mdash; it can find small changes that the ordinary test misses. The Sample column
must give each sample the same name in both groups.</div>

<h2 id="l5">Lesson 5 &ndash; Where along the spectrum do the groups differ?</h2>
<p>Lessons 1&ndash;4 compared <b>one value</b> per spectrum, which you had to choose. The
<b>Spectra</b> tab instead compares the groups at <b>every point</b> of the spectrum and shows
where they differ &mdash; useful when you do not know yet which band matters.</p>
<h3>Step 1 &ndash; raw spectra</h3>
<p>Open <i>three treatment groups</i> again (Lesson 1) and Group Statistics. The Spectra tab
uses the test of box 3, so set it back to <span class="set">Parametric: Welch t-test /
one-way ANOVA</span> and untick <i>One value per sample</i> (the window remembers your choices
from the earlier lessons). Tab <b>Spectra</b>: leave Normalize at
<span class="set">None</span> and press <b>Compare spectra</b>.</p>
$FIG_l5_raw
<p>Upper plot: the mean spectrum of each group with a band of &plusmn; one SD. Lower plot: the
corrected p-value at every point (&minus;log<sub>10</sub>: above the red line = p &lt; 0.05).
Result: <b>no region</b> differs &mdash; the random overall intensity of the spectra (Lesson 1)
is larger than the effect. The first line, <i>Whole spectrum (PERMANOVA)</i>, tests the whole
spectra at once: p &asymp; 0.08, not significant either.</p>
<h3>Step 2 &ndash; normalize to a band that does not change</h3>
<p>Normalize <span class="set">Divide by the maximum in a band</span>,
<span class="set">1420</span> to <span class="set">1480</span>; Compare spectra.</p>
$FIG_l5_band
<p>PERMANOVA: p = 0.0001 (the smallest possible). Three regions are shaded yellow: <b>1620&ndash;1689</b> (the 1655 band, strongest
difference) and <b>1573&ndash;1584</b> and <b>1587&ndash;1598</b> &mdash; the two sides of the
1585 band, because the band <b>shifts</b> (its top, ~1585, does not differ; its flanks do).
"Plus 4 shorter ones": single points that are most likely chance findings &mdash; about
5&nbsp;% of the shaded points may be false with the FDR correction, so read regions, not
points.</p>
<h3>Step 3 &ndash; other normalizations</h3>
<p>Normalize <span class="set">Unit area</span>: about 60&nbsp;% of the spectrum comes out
"different", and the note explains why: dividing by the total area means that a larger 1655
band makes every other point smaller. Same with SNV.</p>
$FIG_l5_area
<div class="lesson"><b>Lesson:</b> the Spectra tab finds the bands that differ without choosing
them first, but only after a sensible normalization. Divide by a band that the treatment does
not change.</div>
<h3>Step 4 &ndash; replicates matter here too</h3>
<p>Open <i>cells with several pixels</i> (Lesson 3), Spectra tab, the same normalization
(1420&ndash;1480), Compare spectra: the region <b>1629&ndash;1684</b> "differs" (PERMANOVA
p = 0.0001), with the red warning. Tick <span class="set">One value per sample</span> and
Compare again: <b>no region</b>, PERMANOVA p &asymp; 0.10 &mdash; as in Lesson 3, the 45 pixels
per group are only 3 cells.</p>
$FIG_l5_cells_warning
<p><b>Export table&hellip;</b> saves the mean, SD and n of each group and the p-values at every
point, for your own plots.</p>

<h2 id="l6">Lesson 6 &ndash; Regions of a 2D map as groups</h2>
<p><b>Dataset:</b> <i>Group Statistics &mdash; map of one cell (ROI regions as groups)</i> (a
Raman map, 40 &times; 30 = 1200 spectra). <b>Story:</b> one cell; the cytoplasm contains
protein, the nucleus protein and DNA (bands at 785, 1095 and 1578&nbsp;cm&#8315;&sup1;). The
overall intensity drifts from left to right across the map (focus).</p>
<h3>Step 1 &ndash; the map and the regions</h3>
<ol>
<li>Import the dataset, select all 1200 spectra, <b>Analysis &amp; Visualization &rarr;
Visualization &rarr; 2D map</b> (the size 30 &times; 40 is read from the file).</li>
<li><span class="set">Intensity metric</span>, Metric <span class="set">Baseline-corrected
integral</span>, <b>Configure Band&hellip;</b> 770&ndash;800 (the DNA band): the nucleus
lights up.</li>
<li><b>ROI &rarr; Add ROI ellipse&hellip;</b> and draw an ellipse inside the nucleus; then
<b>ROI &rarr; Add ROI rectangle&hellip;</b> and draw a rectangle in the cytoplasm (right of the
nucleus, inside the cell).</li>
</ol>
$FIG_l6_map
<h3>Step 2 &ndash; open them in Group Statistics</h3>
<p><b>ROI &rarr; Compare ROI regions in Group Statistics&hellip;</b>. Name the regions
<span class="set">nucleus</span> and <span class="set">cytoplasm</span> and press OK.</p>
$FIG_l6_names
<p>Group Statistics opens with the pixels of the two regions as groups. The green note under
the table reminds you that they are pixels of <b>one</b> map. (Test: Parametric, as in
Lesson 5.)</p>
<p>Value <span class="set">Two bands A and B</span>; A <span class="set">770&ndash;800</span>,
B <span class="set">1420&ndash;1480</span>, both <span class="set">Baseline-corrected
integral</span>, <span class="set">A / B</span>; Compute: <b>p &lt; 0.0001</b>, the nucleus
far higher. Change A to <span class="set">990&ndash;1015</span> (phenylalanine, protein):
<b>p &asymp; 0.87</b> &mdash; the protein signal relative to the CH&#8322; band is the same in both
regions.</p>
$FIG_l6_ratio
<h3>Step 3 &ndash; the whole spectrum</h3>
<p>Spectra tab, Normalize <span class="set">None</span>, Compare spectra: almost the
<b>whole spectrum</b> differs &mdash; the cytoplasm rectangle lies where the map is measured
more strongly (the drift). With <span class="set">Divide by the maximum in a band</span>
1420&ndash;1480 only <b>774&ndash;798</b>, <b>1082&ndash;1108</b> and <b>1566&ndash;1590</b>
remain: exactly the three DNA bands.</p>
$FIG_l6_spectra_raw
$FIG_l6_spectra_band
<div class="lesson"><b>Lesson:</b> ROI regions make it easy to compare parts of a map, but the
result describes <b>this map only</b>: "in this cell, the nucleus has more DNA signal". To say
something about nuclei in general, measure several cells and compare one value per cell
(Lesson 3). Maps often have intensity drifts &mdash; normalize, or use ratios of two
bands.</div>

<h2 id="which">Which test when &ndash; a summary</h2>
<table>
<tr><th>Your data</th><th>Choose</th><th>Lesson</th></tr>
<tr><td>Different samples in the groups, values roughly bell-shaped</td>
<td>Parametric: Welch t-test / one-way ANOVA</td><td>1</td></tr>
<tr><td>&hellip; three or more groups with clearly different spread</td>
<td>Unequal spread: Welch ANOVA + Games&ndash;Howell</td><td>1</td></tr>
<tr><td>Skewed values (amounts, a long tail), or a few extreme values</td>
<td>Non-parametric: Mann&ndash;Whitney U / Kruskal&ndash;Wallis (+ Dunn for the pairs), or
log&#8322;(A / B), or the permutation test</td><td>2</td></tr>
<tr><td>Several spectra from each sample (map pixels, repeated scans)</td>
<td>fill the Sample column and tick <i>One value per sample</i></td><td>3</td></tr>
<tr><td>The same samples measured in both groups (before / after)</td>
<td>Paired: paired t-test or Wilcoxon signed-rank</td><td>4</td></tr>
<tr><td>You do not know which band differs</td>
<td>the Spectra tab, after normalizing to a band that does not change</td><td>5</td></tr>
<tr><td>Parts of one map (nucleus, cytoplasm, &hellip;)</td>
<td>ROI regions in the 2D Map &rarr; Compare ROI regions in Group Statistics (describes this
map only)</td><td>6</td></tr>
</table>
<p>And always: report the <b>effect size</b> and the <b>confidence interval</b>, not only p
(the results sentence contains them). p &lt; 0.05 means "unlikely to be chance"; it does not
say the difference is large or important. p &gt; 0.05 means "not shown", not "no
difference".</p>

<h2 id="own">Using your own data</h2>
<p>Give the groups by hand (type, <i>Set group of selected rows&hellip;</i>, <i>From
names&hellip;</i>) or, like the demos, prepare them once next to the data:</p>
<ul>
<li>in your Excel workbook add a sheet named <b>Groups</b>, or</li>
<li>next to your data file <code>measurement.txt</code> put a file
<code>measurement_groups.csv</code>.</li>
</ul>
<p>Columns: spectrum name (the column name in your data file, e.g. <code>control_01</code>),
group, and optionally sample:</p>
<pre>Spectrum;Group;Sample
control_01;control;
control_02;control;
treated_01;treated;</pre>
<p>When you open Group Statistics with these spectra and no groups are set yet, the columns are
filled in by themselves. Details: <a href="help://group_statistics">Group Statistics help</a>.</p>
</body>
</html>
"""
