# src/help/mean_centering_help.py


def get_mean_centering_help_title():
    return 'Mean-Center Spectra (Dataset) — help'


def get_mean_centering_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            .cat    { background: #f5f5f5; padding: 10px 14px; margin: 6px 0; border-radius: 5px; }
            .tip    { background: #E8F5E9; border-left: 4px solid #2E7D32;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note   { background: #E3F2FD; border-left: 4px solid #1565C0;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn   { background: #FFF8E1; border-left: 4px solid #F9A825;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm     { font-family: monospace; background: #ececec;
                      padding: 1px 5px; border-radius: 3px; }
            .back-link { font-size: 11px; color: #888; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
            hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
        </style>
    </head>
    <body>
    <a name="top"></a>

    <h1>Mean-Center Spectra (Dataset)</h1>

    <p>Computes the <strong>ensemble average spectrum</strong> across a
    selected batch &mdash; the per-wavelength mean, one value per
    wavelength, averaged across every spectrum in the selection &mdash;
    and subtracts it from every spectrum in that batch. This is exactly
    the same preprocessing step the
    <a href="help://pca_scores">PCA / SVD Scores &amp; Loadings</a> and
    <a href="help://svd_analysis">SVD Analysis</a> dialogs perform
    internally when their own "Mean-center spectra before SVD" checkbox
    is on, exposed here as its own standalone operation &mdash;
    independent of running any decomposition.</p>

    <div class="tip">
    <p><strong>Why you might want this on its own:</strong> to visually
    inspect per-wavelength deviations from the group average directly
    (a quick exploratory-differences view, before committing to a full
    PCA/SVD run), to reproduce exactly what those dialogs did to a
    dataset for use in another tool, or simply to export pre-centered
    data.</p>
    </div>

    <hr>
    <h2 id="not-normalization">This is NOT the same as Normalization's "Mean Centering" mode</h2>

    <p>Normalization already has modes called <strong>Mean Centering</strong>
    and <strong>Z-score</strong> &mdash; it is easy to assume this operation
    duplicates one of those. It does not:</p>

    <table>
        <tr><th></th><th>Normalization's Mean Centering / Z-score</th><th>This operation</th></tr>
        <tr>
            <td><strong>What gets subtracted</strong></td>
            <td>Each spectrum's own scalar mean (or the mean of a chosen region within it)</td>
            <td>The ensemble average spectrum &mdash; one vector, shared across the whole batch</td>
        </tr>
        <tr>
            <td><strong>Depends on other spectra?</strong></td>
            <td>No &mdash; every spectrum is processed completely independently</td>
            <td>Yes &mdash; every output depends on every spectrum in the selection</td>
        </tr>
        <tr>
            <td><strong>Direction</strong></td>
            <td>Row-wise (within one spectrum, across wavelengths)</td>
            <td>Column-wise (within one wavelength, across spectra)</td>
        </tr>
    </table>

    <p>In short: Normalization's mode asks "how far is this point from
    <em>this spectrum's own</em> average?" This operation asks "how far is
    this point from what <em>the whole group</em> looks like here?" &mdash;
    the second question is the one PCA/SVD mean-centering answers, and the
    two are not interchangeable.</p>

    <hr>
    <h2 id="requirements">Requirements</h2>
    <p>Every selected spectrum must share an identical x-axis (same
    wavelengths, same order) &mdash; the same requirement as PCA, SVD
    Analysis, and SVD Background Correction, since averaging "the same
    wavelength across spectra" is only meaningful when that wavelength is
    actually the same for all of them. A spectrum with a mismatched x-axis
    is rejected with a message naming it, rather than silently averaged
    against unrelated wavelengths.</p>

    <div class="warn">
    <p><strong>Select at least two spectra.</strong> With only one spectrum
    selected, its "average" is itself, and the centered result is exactly
    zero everywhere &mdash; not useful. The dialog warns about this case
    but does not block it.</p>
    </div>

    <hr>
    <h2 id="settings">Settings</h2>
    <p>There is only one: <strong>"Also add the ensemble mean spectrum as
    a new spectrum."</strong> When checked, the computed average (the one
    subtracted from everything else) is added to the spectrum list as its
    own new spectrum, labeled <span class="fm">Mean_of_N_spectra</span>
    &mdash; useful as a reference or QC artifact. This extra spectrum is
    always <em>added</em>, regardless of whether you choose Apply
    (replace) or Add as New for the centered results themselves, since it
    has no single source spectrum of its own to replace.</p>

    <hr>
    <h2 id="technical-background">Technical background</h2>
    <p>For the full mathematical rationale behind mean-centering &mdash;
    why this particular centering makes SVD/PCA components uncorrelated
    (not just orthogonal), the exact equivalence between mean-centered SVD
    and PCA, and why per-wavelength <em>standardizing</em> (dividing each
    wavelength by its own standard deviation) is deliberately never
    offered anywhere in this application &mdash; see the
    <a href="help://pca_scores#technical-background">Technical background</a>
    section of the PCA / SVD Scores &amp; Loadings help page. Everything
    said there about the centering step applies identically here, since
    this operation performs the exact same calculation.</p>

    <hr>
    <h2 id="faq">Frequently asked questions</h2>

    <h3>Can I mean-center a dataset that's already been mean-centered?</h3>
    <p>Yes, mechanically &mdash; but centering an already-centered dataset
    a second time has no further effect beyond floating-point noise, since
    the ensemble mean of already-centered data is (by construction) itself
    approximately zero. Every application IS recorded in Operations
    History, like any other operation in this application, so you can
    check whether a dataset has already been through this step.</p>

    <h3>Does this affect x-axis values?</h3>
    <p>No. Only the y-values (intensities) change; the x-axis is copied
    through unchanged.</p>

    <h3>How is this different from just running PCA/SVD with mean-centering on?</h3>
    <p>PCA/SVD with mean-centering on centers the data internally as
    part of computing the decomposition (scores, loadings, singular
    values) &mdash; the centered spectra themselves are not saved back to
    your spectrum list. This operation does the identical centering step
    but stops there: the centered spectra become new (or replaced) entries
    in your spectrum list, without running any decomposition at all.</p>

    <hr>
    <p class="back-link"><a href="#top">Back to top</a></p>
    </body>
    </html>
    """
