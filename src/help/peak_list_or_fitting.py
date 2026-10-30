# src/help/peak_list_or_fitting.py
"""The section "Peak list or Peak Fitting?" - the same in the help of the
Peaks window (peak_detection_help.py) and of Peak Fitting
(peak_fitting_help.py): what each one is for, with a picture of two
overlapping bands. No '$' in it: Peak Fitting's help is a string.Template."""


def section_html(page):
    """page: 'peaks' or 'fitting' - the link goes to the other help."""
    other = ('<a href="help://peak_fitting#list-or-fitting">Peak Fitting help</a>'
             if page == 'peaks' else
             '<a href="help://peak_detection#list-or-fitting">Peaks help</a>')
    return _SECTION.replace('@@OTHER@@', other)


_SECTION = """
        <h2 id="list-or-fitting">Peak list or Peak Fitting?</h2>
        <p>Both give positions, heights and widths of peaks, but they answer different questions.
        The <b>Peak list</b> (the Peaks window) <i>measures the peaks you can see</i>;
        <b>Peak Fitting</b> <i>splits a spectrum into the bands it is made of</i>. (The same
        section is in the @@OTHER@@.)</p>
        <table style="border-collapse:collapse; margin:8px 0;">
            <tr style="background:#E8EEF7;"><th style="padding:4px 8px; text-align:left;"></th>
                <th style="padding:4px 8px; text-align:left;">Peak list (Peaks window)</th>
                <th style="padding:4px 8px; text-align:left;">Peak Fitting</th></tr>
            <tr><td style="padding:4px 8px;"><b>Question</b></td>
                <td style="padding:4px 8px;">Where are the peaks, how high and how wide?</td>
                <td style="padding:4px 8px;">Which bands make up the spectrum &mdash; also hidden or
                overlapping ones?</td></tr>
            <tr><td style="padding:4px 8px;"><b>How</b></td>
                <td style="padding:4px 8px;">Finds every top automatically and reads its values from
                the measured points.</td>
                <td style="padding:4px 8px;">You choose the peaks (how many, which shape); all are
                adjusted together until their sum matches the whole spectrum.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Overlapping bands</b></td>
                <td style="padding:4px 8px;">A hump of two bands gives <b>one</b> peak, wider than
                each band. <i>Refine by fitting</i> fits one band to the points around that one top,
                so it cannot split the hump either.</td>
                <td style="padding:4px 8px;">Two peaks give <b>two</b> bands, each with its own
                position, width, height and area. A shoulder becomes a band of its own.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Effort</b></td>
                <td style="padding:4px 8px;">Fast, almost no setting up: many spectra in
                seconds.</td>
                <td style="padding:4px 8px;">Setting up (peaks, shape, constraint) and checking
                (residual, R&sup2;); slower.</td></tr>
            <tr><td style="padding:4px 8px;"><b>You get</b></td>
                <td style="padding:4px 8px;">A table of all peaks, the Band table, a plot of a value
                through a series, red marks on the plot.</td>
                <td style="padding:4px 8px;">The fitted values, the residual, and new spectra: the
                total fit, the residual, each band alone.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Typical use</b></td>
                <td style="padding:4px 8px;">An overview, a quick check, following clear peaks
                through a series.</td>
                <td style="padding:4px 8px;">Overlapping bands (e.g. the parts of the amide I band),
                CD or UV-Vis bands, the area of each band.</td></tr>
        </table>
        <p><b>Example: two bands that overlap.</b> Two bands at 1640 and 1660&nbsp;cm&#8315;&#185;,
        each 23.5 wide (FWHM), merge into one hump:</p>
        <svg viewBox="0 0 900 270" xmlns="http://www.w3.org/2000/svg" style="width:100%; max-width:860px; height:auto; display:block; margin:8px auto; font-family:Arial,sans-serif;">
            <defs>
                <marker id="lfA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#C62828"/></marker>
            </defs>
            <rect x="10" y="10" width="430" height="250" rx="10" fill="#F5F9FF" stroke="#1F77B4"/>
            <rect x="460" y="10" width="430" height="250" rx="10" fill="#F6FBF5" stroke="#2E7D32"/>
            <text x="225" y="34" font-size="15" font-weight="bold" fill="#0D47A1" text-anchor="middle">Peak list: one peak</text>
            <text x="675" y="34" font-size="15" font-weight="bold" fill="#1B5E20" text-anchor="middle">Peak Fitting with two peaks: two bands</text>
            <line x1="50" y1="200" x2="390" y2="200" stroke="#90A4AE"/>
            <line x1="500" y1="200" x2="840" y2="200" stroke="#90A4AE"/>
            <path d="M 50.0 200.0 L 52.4 200.0 L 54.9 200.0 L 57.3 200.0 L 59.7 200.0 L 62.1 200.0 L 64.6 200.0 L 67.0 200.0 L 69.4 200.0 L 71.9 200.0 L 74.3 200.0 L 76.7 200.0 L 79.1 200.0 L 81.6 200.0 L 84.0 200.0 L 86.4 200.0 L 88.9 200.0 L 91.3 200.0 L 93.7 200.0 L 96.1 200.0 L 98.6 200.0 L 101.0 199.9 L 103.4 199.9 L 105.9 199.9 L 108.3 199.8 L 110.7 199.7 L 113.1 199.6 L 115.6 199.5 L 118.0 199.3 L 120.4 199.0 L 122.9 198.7 L 125.3 198.2 L 127.7 197.6 L 130.1 196.9 L 132.6 195.9 L 135.0 194.7 L 137.4 193.3 L 139.9 191.5 L 142.3 189.3 L 144.7 186.7 L 147.1 183.7 L 149.6 180.2 L 152.0 176.2 L 154.4 171.6 L 156.9 166.5 L 159.3 160.8 L 161.7 154.7 L 164.1 148.0 L 166.6 141.0 L 169.0 133.7 L 171.4 126.1 L 173.9 118.5 L 176.3 111.0 L 178.7 103.6 L 181.1 96.5 L 183.6 89.9 L 186.0 83.8 L 188.4 78.5 L 190.9 73.8 L 193.3 70.0 L 195.7 67.0 L 198.1 64.8 L 200.6 63.4 L 203.0 62.6 L 205.4 62.5 L 207.9 62.9 L 210.3 63.7 L 212.7 64.8 L 215.1 66.1 L 217.6 67.5 L 220.0 69.0 L 222.4 70.4 L 224.9 71.9 L 227.3 73.3 L 229.7 74.8 L 232.1 76.3 L 234.6 78.0 L 237.0 79.9 L 239.4 82.2 L 241.9 84.7 L 244.3 87.8 L 246.7 91.2 L 249.1 95.2 L 251.6 99.7 L 254.0 104.6 L 256.4 110.0 L 258.9 115.7 L 261.3 121.7 L 263.7 127.9 L 266.1 134.2 L 268.6 140.4 L 271.0 146.6 L 273.4 152.6 L 275.9 158.2 L 278.3 163.6 L 280.7 168.6 L 283.1 173.1 L 285.6 177.2 L 288.0 180.9 L 290.4 184.2 L 292.9 187.0 L 295.3 189.4 L 297.7 191.4 L 300.1 193.2 L 302.6 194.6 L 305.0 195.8 L 307.4 196.7 L 309.9 197.5 L 312.3 198.1 L 314.7 198.6 L 317.1 198.9 L 319.6 199.2 L 322.0 199.4 L 324.4 199.6 L 326.9 199.7 L 329.3 199.8 L 331.7 199.9 L 334.1 199.9 L 336.6 199.9 L 339.0 200.0 L 341.4 200.0 L 343.9 200.0 L 346.3 200.0 L 348.7 200.0 L 351.1 200.0 L 353.6 200.0 L 356.0 200.0 L 358.4 200.0 L 360.9 200.0 L 363.3 200.0 L 365.7 200.0 L 368.1 200.0 L 370.6 200.0 L 373.0 200.0 L 375.4 200.0 L 377.9 200.0 L 380.3 200.0 L 382.7 200.0 L 385.1 200.0 L 387.6 200.0 L 390.0 200.0" fill="none" stroke="#1F77B4" stroke-width="2.4"/>
            <circle cx="204.7" cy="62.5" r="5" fill="#D62728"/>
            <text x="192.7" y="58.5" font-size="13" fill="#B71C1C" text-anchor="end">1644</text>
            <line x1="169.7" y1="131.2" x2="264.9" y2="131.2" stroke="#C62828" stroke-width="1.6" marker-start="url(#lfA)" marker-end="url(#lfA)"/>
            <text x="276.9" y="135.2" font-size="13" fill="#B71C1C">FWHM 39</text>
            <text x="225" y="226" font-size="12.5" fill="#37474F" text-anchor="middle">two bands merged into one hump (1580 – 1720 cm⁻¹)</text>
            <text x="225" y="246" font-size="12.5" fill="#37474F" text-anchor="middle">one top is found; its width includes both bands</text>
            <path d="M 500.0 200.0 L 502.4 200.0 L 504.9 200.0 L 507.3 200.0 L 509.7 200.0 L 512.1 200.0 L 514.6 200.0 L 517.0 200.0 L 519.4 200.0 L 521.9 200.0 L 524.3 200.0 L 526.7 200.0 L 529.1 200.0 L 531.6 200.0 L 534.0 200.0 L 536.4 200.0 L 538.9 200.0 L 541.3 200.0 L 543.7 200.0 L 546.1 200.0 L 548.6 200.0 L 551.0 199.9 L 553.4 199.9 L 555.9 199.9 L 558.3 199.8 L 560.7 199.7 L 563.1 199.6 L 565.6 199.5 L 568.0 199.3 L 570.4 199.0 L 572.9 198.7 L 575.3 198.2 L 577.7 197.6 L 580.1 196.9 L 582.6 195.9 L 585.0 194.7 L 587.4 193.3 L 589.9 191.5 L 592.3 189.3 L 594.7 186.7 L 597.1 183.7 L 599.6 180.2 L 602.0 176.2 L 604.4 171.6 L 606.9 166.5 L 609.3 160.8 L 611.7 154.7 L 614.1 148.0 L 616.6 141.0 L 619.0 133.7 L 621.4 126.1 L 623.9 118.5 L 626.3 111.0 L 628.7 103.6 L 631.1 96.5 L 633.6 89.9 L 636.0 83.8 L 638.4 78.5 L 640.9 73.8 L 643.3 70.0 L 645.7 67.0 L 648.1 64.8 L 650.6 63.4 L 653.0 62.6 L 655.4 62.5 L 657.9 62.9 L 660.3 63.7 L 662.7 64.8 L 665.1 66.1 L 667.6 67.5 L 670.0 69.0 L 672.4 70.4 L 674.9 71.9 L 677.3 73.3 L 679.7 74.8 L 682.1 76.3 L 684.6 78.0 L 687.0 79.9 L 689.4 82.2 L 691.9 84.7 L 694.3 87.8 L 696.7 91.2 L 699.1 95.2 L 701.6 99.7 L 704.0 104.6 L 706.4 110.0 L 708.9 115.7 L 711.3 121.7 L 713.7 127.9 L 716.1 134.2 L 718.6 140.4 L 721.0 146.6 L 723.4 152.6 L 725.9 158.2 L 728.3 163.6 L 730.7 168.6 L 733.1 173.1 L 735.6 177.2 L 738.0 180.9 L 740.4 184.2 L 742.9 187.0 L 745.3 189.4 L 747.7 191.4 L 750.1 193.2 L 752.6 194.6 L 755.0 195.8 L 757.4 196.7 L 759.9 197.5 L 762.3 198.1 L 764.7 198.6 L 767.1 198.9 L 769.6 199.2 L 772.0 199.4 L 774.4 199.6 L 776.9 199.7 L 779.3 199.8 L 781.7 199.9 L 784.1 199.9 L 786.6 199.9 L 789.0 200.0 L 791.4 200.0 L 793.9 200.0 L 796.3 200.0 L 798.7 200.0 L 801.1 200.0 L 803.6 200.0 L 806.0 200.0 L 808.4 200.0 L 810.9 200.0 L 813.3 200.0 L 815.7 200.0 L 818.1 200.0 L 820.6 200.0 L 823.0 200.0 L 825.4 200.0 L 827.9 200.0 L 830.3 200.0 L 832.7 200.0 L 835.1 200.0 L 837.6 200.0 L 840.0 200.0" fill="none" stroke="#B0BEC5" stroke-width="5"/>
            <path d="M 500.0 200.0 L 502.4 200.0 L 504.9 200.0 L 507.3 200.0 L 509.7 200.0 L 512.1 200.0 L 514.6 200.0 L 517.0 200.0 L 519.4 200.0 L 521.9 200.0 L 524.3 200.0 L 526.7 200.0 L 529.1 200.0 L 531.6 200.0 L 534.0 200.0 L 536.4 200.0 L 538.9 200.0 L 541.3 200.0 L 543.7 200.0 L 546.1 200.0 L 548.6 200.0 L 551.0 199.9 L 553.4 199.9 L 555.9 199.9 L 558.3 199.8 L 560.7 199.7 L 563.1 199.6 L 565.6 199.5 L 568.0 199.3 L 570.4 199.0 L 572.9 198.7 L 575.3 198.2 L 577.7 197.6 L 580.1 196.9 L 582.6 195.9 L 585.0 194.7 L 587.4 193.3 L 589.9 191.5 L 592.3 189.3 L 594.7 186.8 L 597.1 183.8 L 599.6 180.3 L 602.0 176.3 L 604.4 171.7 L 606.9 166.6 L 609.3 161.0 L 611.7 155.0 L 614.1 148.5 L 616.6 141.6 L 619.0 134.5 L 621.4 127.2 L 623.9 120.0 L 626.3 112.9 L 628.7 106.1 L 631.1 99.8 L 633.6 94.1 L 636.0 89.2 L 638.4 85.3 L 640.9 82.4 L 643.3 80.6 L 645.7 80.0 L 648.1 80.6 L 650.6 82.4 L 653.0 85.3 L 655.4 89.2 L 657.9 94.1 L 660.3 99.8 L 662.7 106.1 L 665.1 112.9 L 667.6 120.0 L 670.0 127.2 L 672.4 134.5 L 674.9 141.6 L 677.3 148.5 L 679.7 155.0 L 682.1 161.0 L 684.6 166.6 L 687.0 171.7 L 689.4 176.3 L 691.9 180.3 L 694.3 183.8 L 696.7 186.8 L 699.1 189.3 L 701.6 191.5 L 704.0 193.3 L 706.4 194.7 L 708.9 195.9 L 711.3 196.9 L 713.7 197.6 L 716.1 198.2 L 718.6 198.7 L 721.0 199.0 L 723.4 199.3 L 725.9 199.5 L 728.3 199.6 L 730.7 199.7 L 733.1 199.8 L 735.6 199.9 L 738.0 199.9 L 740.4 199.9 L 742.9 200.0 L 745.3 200.0 L 747.7 200.0 L 750.1 200.0 L 752.6 200.0 L 755.0 200.0 L 757.4 200.0 L 759.9 200.0 L 762.3 200.0 L 764.7 200.0 L 767.1 200.0 L 769.6 200.0 L 772.0 200.0 L 774.4 200.0 L 776.9 200.0 L 779.3 200.0 L 781.7 200.0 L 784.1 200.0 L 786.6 200.0 L 789.0 200.0 L 791.4 200.0 L 793.9 200.0 L 796.3 200.0 L 798.7 200.0 L 801.1 200.0 L 803.6 200.0 L 806.0 200.0 L 808.4 200.0 L 810.9 200.0 L 813.3 200.0 L 815.7 200.0 L 818.1 200.0 L 820.6 200.0 L 823.0 200.0 L 825.4 200.0 L 827.9 200.0 L 830.3 200.0 L 832.7 200.0 L 835.1 200.0 L 837.6 200.0 L 840.0 200.0" fill="none" stroke="#FF7F0E" stroke-width="2"/>
            <path d="M 500.0 200.0 L 502.4 200.0 L 504.9 200.0 L 507.3 200.0 L 509.7 200.0 L 512.1 200.0 L 514.6 200.0 L 517.0 200.0 L 519.4 200.0 L 521.9 200.0 L 524.3 200.0 L 526.7 200.0 L 529.1 200.0 L 531.6 200.0 L 534.0 200.0 L 536.4 200.0 L 538.9 200.0 L 541.3 200.0 L 543.7 200.0 L 546.1 200.0 L 548.6 200.0 L 551.0 200.0 L 553.4 200.0 L 555.9 200.0 L 558.3 200.0 L 560.7 200.0 L 563.1 200.0 L 565.6 200.0 L 568.0 200.0 L 570.4 200.0 L 572.9 200.0 L 575.3 200.0 L 577.7 200.0 L 580.1 200.0 L 582.6 200.0 L 585.0 200.0 L 587.4 200.0 L 589.9 200.0 L 592.3 200.0 L 594.7 200.0 L 597.1 200.0 L 599.6 200.0 L 602.0 199.9 L 604.4 199.9 L 606.9 199.9 L 609.3 199.8 L 611.7 199.7 L 614.1 199.6 L 616.6 199.4 L 619.0 199.2 L 621.4 198.9 L 623.9 198.6 L 626.3 198.1 L 628.7 197.5 L 631.1 196.7 L 633.6 195.8 L 636.0 194.6 L 638.4 193.2 L 640.9 191.5 L 643.3 189.4 L 645.7 187.0 L 648.1 184.2 L 650.6 181.0 L 653.0 177.4 L 655.4 173.3 L 657.9 168.8 L 660.3 164.0 L 662.7 158.8 L 665.1 153.3 L 667.6 147.6 L 670.0 141.8 L 672.4 136.0 L 674.9 130.3 L 677.3 124.9 L 679.7 119.8 L 682.1 115.3 L 684.6 111.4 L 687.0 108.2 L 689.4 105.9 L 691.9 104.5 L 694.3 104.0 L 696.7 104.5 L 699.1 105.9 L 701.6 108.2 L 704.0 111.4 L 706.4 115.3 L 708.9 119.8 L 711.3 124.9 L 713.7 130.3 L 716.1 136.0 L 718.6 141.8 L 721.0 147.6 L 723.4 153.3 L 725.9 158.8 L 728.3 164.0 L 730.7 168.8 L 733.1 173.3 L 735.6 177.4 L 738.0 181.0 L 740.4 184.2 L 742.9 187.0 L 745.3 189.4 L 747.7 191.5 L 750.1 193.2 L 752.6 194.6 L 755.0 195.8 L 757.4 196.7 L 759.9 197.5 L 762.3 198.1 L 764.7 198.6 L 767.1 198.9 L 769.6 199.2 L 772.0 199.4 L 774.4 199.6 L 776.9 199.7 L 779.3 199.8 L 781.7 199.9 L 784.1 199.9 L 786.6 199.9 L 789.0 200.0 L 791.4 200.0 L 793.9 200.0 L 796.3 200.0 L 798.7 200.0 L 801.1 200.0 L 803.6 200.0 L 806.0 200.0 L 808.4 200.0 L 810.9 200.0 L 813.3 200.0 L 815.7 200.0 L 818.1 200.0 L 820.6 200.0 L 823.0 200.0 L 825.4 200.0 L 827.9 200.0 L 830.3 200.0 L 832.7 200.0 L 835.1 200.0 L 837.6 200.0 L 840.0 200.0" fill="none" stroke="#2E7D32" stroke-width="2"/>
            <path d="M 500.0 200.0 L 502.4 200.0 L 504.9 200.0 L 507.3 200.0 L 509.7 200.0 L 512.1 200.0 L 514.6 200.0 L 517.0 200.0 L 519.4 200.0 L 521.9 200.0 L 524.3 200.0 L 526.7 200.0 L 529.1 200.0 L 531.6 200.0 L 534.0 200.0 L 536.4 200.0 L 538.9 200.0 L 541.3 200.0 L 543.7 200.0 L 546.1 200.0 L 548.6 200.0 L 551.0 199.9 L 553.4 199.9 L 555.9 199.9 L 558.3 199.8 L 560.7 199.7 L 563.1 199.6 L 565.6 199.5 L 568.0 199.3 L 570.4 199.0 L 572.9 198.7 L 575.3 198.2 L 577.7 197.6 L 580.1 196.9 L 582.6 195.9 L 585.0 194.7 L 587.4 193.3 L 589.9 191.5 L 592.3 189.3 L 594.7 186.7 L 597.1 183.7 L 599.6 180.2 L 602.0 176.2 L 604.4 171.6 L 606.9 166.5 L 609.3 160.8 L 611.7 154.7 L 614.1 148.0 L 616.6 141.0 L 619.0 133.7 L 621.4 126.1 L 623.9 118.5 L 626.3 111.0 L 628.7 103.6 L 631.1 96.5 L 633.6 89.9 L 636.0 83.8 L 638.4 78.5 L 640.9 73.8 L 643.3 70.0 L 645.7 67.0 L 648.1 64.8 L 650.6 63.4 L 653.0 62.6 L 655.4 62.5 L 657.9 62.9 L 660.3 63.7 L 662.7 64.8 L 665.1 66.1 L 667.6 67.5 L 670.0 69.0 L 672.4 70.4 L 674.9 71.9 L 677.3 73.3 L 679.7 74.8 L 682.1 76.3 L 684.6 78.0 L 687.0 79.9 L 689.4 82.2 L 691.9 84.7 L 694.3 87.8 L 696.7 91.2 L 699.1 95.2 L 701.6 99.7 L 704.0 104.6 L 706.4 110.0 L 708.9 115.7 L 711.3 121.7 L 713.7 127.9 L 716.1 134.2 L 718.6 140.4 L 721.0 146.6 L 723.4 152.6 L 725.9 158.2 L 728.3 163.6 L 730.7 168.6 L 733.1 173.1 L 735.6 177.2 L 738.0 180.9 L 740.4 184.2 L 742.9 187.0 L 745.3 189.4 L 747.7 191.4 L 750.1 193.2 L 752.6 194.6 L 755.0 195.8 L 757.4 196.7 L 759.9 197.5 L 762.3 198.1 L 764.7 198.6 L 767.1 198.9 L 769.6 199.2 L 772.0 199.4 L 774.4 199.6 L 776.9 199.7 L 779.3 199.8 L 781.7 199.9 L 784.1 199.9 L 786.6 199.9 L 789.0 200.0 L 791.4 200.0 L 793.9 200.0 L 796.3 200.0 L 798.7 200.0 L 801.1 200.0 L 803.6 200.0 L 806.0 200.0 L 808.4 200.0 L 810.9 200.0 L 813.3 200.0 L 815.7 200.0 L 818.1 200.0 L 820.6 200.0 L 823.0 200.0 L 825.4 200.0 L 827.9 200.0 L 830.3 200.0 L 832.7 200.0 L 835.1 200.0 L 837.6 200.0 L 840.0 200.0" fill="none" stroke="#C62828" stroke-width="1.4" stroke-dasharray="5 3"/>
            <text x="616.6" y="110.0" font-size="13" fill="#E65100" text-anchor="end">1640</text>
            <text x="616.6" y="126.0" font-size="13" fill="#E65100" text-anchor="end">FWHM 23.5</text>
            <text x="725.9" y="110.0" font-size="13" fill="#1B5E20">1660</text>
            <text x="725.9" y="126.0" font-size="13" fill="#1B5E20">FWHM 23.5</text>
            <text x="675" y="226" font-size="12.5" fill="#37474F" text-anchor="middle">grey: the data, red dashed: the sum of the fitted bands</text>
            <text x="675" y="246" font-size="12.5" fill="#37474F" text-anchor="middle">each band with its own position, width, height and area</text>
        </svg>
        <ul>
            <li><b>Peak list</b>: one peak, at 1644, with FWHM 39 &mdash; the width of both bands
            together. <i>Refine by fitting</i> does not change that: it fits one band to the points
            around that top (no other peak is found to stop it), and gives one band at 1648 with
            FWHM 37 &mdash; with R&sup2; 0.99, which looks good, although it is two bands.</li>
            <li><b>Peak Fitting</b> with two peaks: 1640 and 1660, each FWHM 23.5, each with its own
            area &mdash; so you can see, for example, that the 1660 band grows with the
            temperature.</li>
        </ul>
        <p><b>Which one?</b> Separate, clear peaks: the Peak list is enough and faster.
        Overlapping bands, shoulders, or the area of each band: Peak Fitting. Often both: the Peak
        list first, to see what is there and how it changes through the series; then Peak Fitting
        of the region that matters.</p>
"""
