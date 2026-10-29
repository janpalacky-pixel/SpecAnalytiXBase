# src/help/peak_fitting_quick_help.py
"""The short texts of the orange "?" buttons in the Peak Fitting window: one
per part of the window, each with a link to its section of the full help
(peak_fitting_help.py)."""

QUICK_HELP = {
    'peaks': ("Quick help – the peaks to fit", 'adding-peaks', """
<p><b>Auto-Detect Peaks</b> finds the bands of the shown spectrum and fills the table with a
starting position, height and width for each. Check the list: remove what you do not want
(select rows, Delete) and add what is missing.</p>
<p><b>Add via Click</b>: click on the top of a band in the plot - a Gaussian peak is added there,
its width taken from the band under the click. To zoom or pan, simply choose Zoom or Pan in the
plot's toolbar: that switches Add via Click off (tick it again to add more peaks).</p>
<p>Every value in the table can be edited (double-click). <b>Width</b> is &sigma; for Gaussian
and Voigt, &gamma; for Lorentzian, the FWHM for Pseudo-Voigt.</p>
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
<li><b>Copy peaks</b> of the shown spectrum, select others, <b>Paste peaks to the selected
spectra</b> - for a series of similar spectra.</li>
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
<li>Correct the baseline first (Baseline Correction): the peaks have no baseline of their own.</li>
<li>Check the residual: it should be small noise around zero. A wave left in it means a peak is
missing there.</li>
</ul>
"""),
    'series': ("Quick help – a whole series", 'series', """
<p>Fit one spectrum well first. Then select the spectra in the list beside the plot (<b>All</b>
for the whole series) and click <b>Fit Peaks - N selected spectra</b>.</p>
<p>Each selected spectrum starts from <b>its own peaks</b>; spectra without peaks are left out -
or, with <b>Spectra without peaks: start from the fit before them</b> ticked, start from the fit
of the selected spectrum before it (in the order of the list). So:</p>
<ul>
<li>a band that shifts along a series - peaks on the first spectrum only, tick it, select All,
Fit;</li>
<li>the same peaks for all - Copy peaks, select All, Paste, Fit (several cores, faster);</li>
<li>different spectra - select All, Auto-Detect Peaks - N spectra, Fit.</li>
</ul>
<p>The results are in the tab <b>Series results</b>.</p>
"""),
    'series-results': ("Quick help – Series results", 'series-results', """
<p>One row per spectrum: position, FWHM, height and area of each peak, and R&sup2; (1 = perfect
fit). An empty row: that fit failed or the spectrum is not fitted yet.</p>
<p>Click a row to see that spectrum with its fit; select several rows to see them together.
A poor fit: correct its peaks in the tab Peaks and click Fit Peaks - only its row changes.</p>
<p><b>Copy</b> / <b>Export…</b> for Excel; <b>Open in the Data table</b> to plot e.g. a
position against temperature.</p>
"""),
    'view': ("Quick help – the plot", 'viewing', """
<p>The list beside the plot works as in the main window: <b>one</b> spectrum selected - it alone
with its fit, single peaks and residual; <b>several</b> (Ctrl/Shift+click, All, Fitted) - shown
together as chosen in <b>Several selected</b>: Overlay, Waterfall or Grid. Each spectrum has its
colour: data thin, fit thick. &#9664; &#9654; go to the previous or next spectrum.</p>
<p><b>Residual</b> and <b>Legend</b> hide the residual plot and the legend (for one spectrum;
the legend also in Overlay and Waterfall).</p>
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
