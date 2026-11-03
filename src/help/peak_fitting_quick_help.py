# src/help/peak_fitting_quick_help.py
"""The short texts of the orange "?" buttons in the Peak Fitting window: one
per part of the window, each with a link to its section of the full help
(peak_fitting_help.py)."""

QUICK_HELP = {
    'peaks': ("Quick help – the peaks to fit", 'adding-peaks', """
<p><b>Auto-Detect Peaks</b> finds the bands of the shown spectrum and fills the table with a
starting position, height and width for each. Check the list: remove what you do not want
(select rows, <b>Remove Selected Peak(s)</b>) and add what is missing.</p>
<p><b>Add via Click</b>: click on the top of a band in the plot - a Gaussian peak is added there,
its width taken from the band under the click. With several spectra shown it goes to the
shown one (Overlay), or to the one clicked on (Waterfall: its band; Grid: its small plot). To zoom or pan, simply choose Zoom or Pan in the
plot's toolbar: that switches Add via Click off (tick it again to add more peaks).</p>
<p>The table: <b>Model</b> (the peak shape), <b>Center</b> (position of the top), <b>Height</b>
(of the top), <b>Width</b> and <b>Extra</b>. Every value can be edited (double-click). Drag the
line between two headings to make a column wider.
<b>Width</b> is &sigma; for Gaussian and Voigt, &gamma; for Lorentzian, the FWHM for
Pseudo-Voigt; <b>Extra</b> is &gamma; for Voigt, &eta; (0&ndash;1) for Pseudo-Voigt (shown only
when a peak has it). Hold the mouse over a column heading to see this.</p>
<p><b>Right-click a value</b> to <b>fix</b> it (kept, not fitted - grey, [fixed]) or to
<b>link</b> it to another peak (light blue): the same width ([=P1]), a fixed distance between
the centres ([P1+12]), a fixed height ratio ([P1&times;0.5]). E.g. two overlapping bands of
the same width: Width of peak 2 &rsaquo; The same width as peak &rsaquo; Peak 1.</p>
"""),
    'peaks-mode': ("Quick help \u2013 the peaks of several spectra", 'peaks-mode', """
<p>With several spectra <b>every spectrum has its own peaks</b>, and everything acts only on
the spectra <b>selected in the list</b> beside the plot:</p>
<ul>
<li>The table shows the peaks of the shown spectrum (name in its title). Adding a peak by a click
on the plot, changing a value and Remove change only these (and its fit counts as not fitted
yet). The shown spectrum changes only when you select one spectrum alone.</li>
<li><b>Clear All Peaks - N spectra</b>: the peaks (and fits) of the selected spectra.</li>
<li><b>Auto-Detect Peaks - N spectra</b>: the peaks of each selected spectrum, each its own.</li>
<li><b>Copy peaks of &hellip;</b> (the shown spectrum), select others, <b>Paste peaks of &hellip;
to the selected spectra</b> - for a series of similar spectra.</li>
<li><b>Fit Peaks - N selected spectra</b>: each from its own peaks; spectra without peaks are
left out (unless <i>Spectra without peaks: start from the fit before them</i> is ticked).</li>
<li>In the list: green dot = has peaks, grey = no peaks yet; &#10003; fitted, &#9888; poor fit,
&#10007; failed.</li>
</ul>
"""),
    'fitting': ("Quick help – getting a good fit", 'converge', """
<p><b>Fit Peaks</b> adjusts all peaks together until their sum matches the data - for the
spectra selected in the list beside the plot (its text says how many). It starts from the
values in the table, so it works best when they are already close:</p>
<ul>
<li>One peak per band you can see; no two peaks at almost the same position.</li>
<li>Remove peaks much broader than the bands, or lying on flat baseline.</li>
<li>For spectra that only go up (Raman, IR absorbance, fluorescence) choose <b>Amplitude
Constraint: Positive Peaks Only</b> - otherwise the fit may use large positive and negative
peaks cancelling each other.</li>
<li>Spectra of different kinds selected together: tick <b>Each spectrum its own</b> next to the
constraint and set it for each group (select it in the list, choose the constraint).</li>
<li><b>Background</b>: <i>Automatic</i> (default) chooses for each spectrum and shows it in
brackets - <i>None</i> when the data come back to zero (CD, baseline-corrected spectra),
<i>Linear</i> when they sit on an offset (raw Raman counts). It is fitted with the peaks, their
heights are above it. A curved baseline: correct it first (Baseline Correction).</li>
<li>Check the residual: it should be small noise around zero. A wave left in it means a peak is
missing there.</li>
<li>After the fit each value has its uncertainty, e.g. <b>3432 &plusmn; 10</b>: large for noisy
data or overlapping bands; <i>n/a</i> when the data cannot determine it (e.g. two peaks at the
same place).</li>
</ul>
"""),
    'series': ("Quick help – a whole series", 'series', """
<p>Fit one spectrum well first: select it alone, set its peaks (<b>Auto-Detect Peaks</b>,
<b>Add via Click</b>, or correct them in the table) and click <b>Fit Peaks - 1 spectrum</b>. Then
give the other spectra a start (below), select them in the list beside the plot (<b>All</b> for
the whole series) and click <b>Fit Peaks - N selected spectra</b>.</p>
<p><b>Every selected spectrum needs a start</b> - if none has one, the button is greyed and the
orange line under it says what to do.</p>
<p>Each selected spectrum starts from <b>its own peaks</b>; spectra without peaks are left out -
or, with <b>Spectra without peaks: start from the fit before them</b> ticked, start from the fit
of the selected spectrum before it (in the order of the list). So:</p>
<ul>
<li>a band that shifts along a series - peaks on the first spectrum only, tick it, select All,
Fit;</li>
<li>the same peaks for all - Copy peaks, select All, Paste, Fit (several cores, faster);</li>
<li>different spectra - select All, Auto-Detect Peaks - N spectra, Fit.</li>
</ul>
<p><b>Several spectra: Together</b> (in the box Fitting) fits all selected spectra at once
from the peaks of the shown spectrum - the same positions and widths (or only the same widths)
for all, each spectrum its own heights and background. Much more stable for a noisy series
(temperature, titration).</p>
<p>The results are in the tab <b>Series results</b>.</p>
<p>The button next to Fit Peaks copies for Excel what the tab shows: on the tab Peaks
<b>Copy table - &hellip;</b> (the peaks of the shown spectrum: start values, or after Fit Peaks
the fitted values); on the tab Series results e.g. <b>Copy peak 1 - N spectra</b>.</p>
"""),
    'series-results': ("Quick help – Series results", 'series-results', """
<p>The results of the spectra <b>selected in the list</b> (All = the whole series), with
<b>Show</b>: <b>By peak</b> - one peak at a time (&#9664; &#9654;), a row per spectrum;
<b>By spectrum</b> - each spectrum with its peaks; <b>All in one table</b> - a row per spectrum
with all peaks. R&sup2; 1 = perfect fit.</p>
<p>A poor fit: select that spectrum alone, correct its peaks in the tab Peaks and click Fit
Peaks - only it changes.</p>
<p><b>Copy &hellip;</b> next to Fit Peaks copies what is shown; <b>Export…</b> for Excel;
<b>Open in the Data table</b> to plot e.g. a position against temperature.</p>
"""),
    'view': ("Quick help – the plot", 'viewing', """
<p>The list beside the plot works as in the main window: <b>one</b> spectrum selected - it alone
with its fit, single peaks and residual; <b>several</b> (Ctrl/Shift+click, All, Fitted) - shown
together as chosen in <b>Several selected</b>: Overlay, Waterfall or Grid. Each spectrum has its
colour: data thin, fit thick. &#9664; &#9654; (Alt+Left / Alt+Right) go to the previous or
next spectrum. The <b>shown spectrum</b> (its peaks are in the table) has an <b>orange frame</b>
in the list; with several selected, &#9664; &#9654; move the frame among them (all stay
selected). In the plot it is drawn stronger (Overlay), or framed in orange (Waterfall, Grid).</p>
<p><b>Residual</b> and <b>Legend</b> hide the residual plot and the legend (for one spectrum;
the legend also in Overlay and Waterfall). <b>Data</b>: the measured data as Points (default)
or as a Line (also with several spectra). <b>&minus; background</b>: the data and the fit drawn without the background,
the peaks from zero (only the drawing changes).</p>
<p>The y axis shows the range of the data; the peaks are drawn on the background (black
dash-dot line).</p>
"""),
    'uncertainty': ("Quick help – the uncertainties (\u00b1)", 'uncertainty', """
<p>After Fit Peaks every value has its uncertainty, e.g. Center <b>3432 &plusmn; 10</b>: measured
again, the value would scatter by about this much. Large for noisy data, small bands or
overlapping bands; <i>n/a</i> when the data cannot determine the value.</p>
<p><b>&plusmn; shown as</b>: <b>1 &sigma;</b> (default, the standard error) - the true value lies
within &plusmn; in about 2 of 3 cases (68 %); <b>2 &sigma;</b> - in 19 of 20 cases (95 %),
e.g. for a confidence interval in a paper; <b>3 &sigma;</b> - in 997 of 1000 (99.7 %). Only
the shown and copied &plusmn; change (their columns are then named e.g. <i>Center
&plusmn;2&sigma;</i>), not the fit.</p>
<p>The &plusmn; do not tell whether a peak is needed - that is the column <b>Needed?</b>
(yes / probably / no): the spectrum is fitted once more without the peak and the two fits
are compared (&Delta;BIC).</p>
<p>The uncertainties assume independent noise: after smoothing they come out too small.</p>
"""),
    'needed': ("Quick help – is a peak needed? (the column Needed?)", 'needed', """
<p>After <b>Fit Peaks</b> the column <b>Needed?</b> says for each peak whether the data really
need it: the spectrum is fitted <b>once more without that peak</b>, and the two fits are
compared.</p>
<ul>
<li><b>yes</b> - without the peak the fit is clearly worse: keep it;</li>
<li><b>probably</b> - somewhat worse: probably keep it;</li>
<li><b>no</b> (orange) - just as good: remove it and fit again.</li>
</ul>
<p><i>not fitted</i> (grey): the values are start values - click Fit Peaks.</p>
<p><b>When several peaks could each be left out</b> (e.g. two peaks on one band - either one
is enough), they are taken out one at a time - the least certain one first - and the rest
checked again each time. So only the peaks marked <b>no</b> are left out, and they can all be
removed together; the others stay needed.</p>
<p><b>The number</b> (hold the mouse over the word): &Delta;BIC, how much better the fit is with
the peak, after a penalty for its three values. It means: the fit with the peak is about
e<sup>&Delta;BIC/2</sup> times more probable than without it -</p>
<table cellspacing="0" cellpadding="2">
<tr><td>&Delta;BIC 2</td><td>&rarr; about 3 times</td></tr>
<tr><td>&Delta;BIC 6</td><td>&rarr; about 20 times</td></tr>
<tr><td>&Delta;BIC 10</td><td>&rarr; about 150 times</td></tr>
<tr><td>&Delta;BIC 0</td><td>&rarr; equally probable</td></tr>
<tr><td>below 0</td><td>&rarr; without the peak more probable</td></tr>
</table>
<p>So: above 10 <b>yes</b>, 2 to 10 <b>probably</b>, below 2 <b>no</b>.</p>
"""),
    'output': ("Quick help – what OK keeps", 'ok-behavior', """
<p>The fit itself changes nothing in your spectra. <b>OK</b> adds new spectra only for the
ticked options: the total fit, the residual, or each peak on its own.</p>
<p>With a series, <b>Add for</b> chooses for which spectra: all fitted spectra, or only the
fitted ones selected in the list beside the plot.</p>
<p>The peaks and fits are remembered: open Peak Fitting again with the same spectra and they are
back.</p>
"""),
}
