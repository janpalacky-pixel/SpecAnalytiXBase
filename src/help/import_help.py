# src/help/import_help.py

def get_import_help_title():
    return "Import Spectra — Help"


def get_import_help_content():
    """Return HTML content for the Import Spectra dialog help."""
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h3 { color: #1976D2; margin-top: 1.5em; }
            .tip     { background-color: #d4edda; padding: 10px;
                       border-left: 4px solid #28a745; margin-top: 10px; }
            .info    { background-color: #e3f2fd; padding: 10px;
                       border-left: 4px solid #1e88e5; margin-top: 10px; }
            .warning { background-color: #fff3cd; padding: 10px;
                       border-left: 4px solid #ffc107; margin-top: 10px; }
            code { background-color: #f1f1f1; padding: 2px 4px;
                   border-radius: 3px; font-family: monospace; }
            table { border-collapse: collapse; width: 100%; margin-top: 8px; }
            th { background: #e3f2fd; padding: 6px 10px;
                 border: 1px solid #bbb; text-align: left; }
            td { padding: 5px 10px; border: 1px solid #ddd; vertical-align: top; }
            li { margin-bottom: 5px; }
            pre { background:#f5f5f5; padding:8px; border-radius:4px;
                  font-family: monospace; font-size: 9pt; }
        </style>
    </head>
    <body>

    <h1>Import Spectra — Help</h1>

    <h2>Overview</h2>
    <p>
        The Import dialog lets you load one or more spectrum files at once.
        After selecting your files in the OS file picker, the dialog opens
        automatically with settings pre-filled by auto-detection and a live
        preview of the first file, so you can verify everything looks correct
        before committing to the import.
    </p>

    <h2>How This App Represents Your Data — Worth Understanding</h2>
    <p>
        Internally, this application always stores spectra the same way:
        one X-axis and one column of Y-values per spectrum. It doesn't
        matter whether your original file had spectra in columns, in rows,
        or interlaced — whichever Layout you choose, the file is converted
        into this same internal shape the moment it's read in. You don't
        need to think about this for everyday importing and viewing; it
        matters for two reasons below.
    </p>
    <p>
        <b>1. Choosing the wrong Layout doesn't error out — it just gives
        wrong numbers.</b> If you tell the importer "Row-oriented" for a
        file that's actually laid out in columns (or the other way round),
        it will usually still produce spectra that <em>look</em> plausible
        — but the values will be nonsense: a wavelength axis might get read
        as intensity data, or several unrelated spectra might get merged
        into one. There's nothing in the file itself that can tell the
        importer your intent was wrong — only you know what the rows and
        columns of your particular file actually represent, which is why
        it's worth checking the preview table carefully before importing,
        not just trusting Auto-detection blindly.
    </p>
    <p>
        <b>2. Row-vs-column convention isn't universal — it differs by
        field.</b> Interestingly:
    </p>
    <ul>
        <li>
            In statistics and machine learning, the standard convention
            (often called "tidy data," or a design matrix) is <b>one row
            per observation, one column per variable</b> — a dataset of
            100 spectra measured at 500 wavelengths would typically be
            stored as 100 rows × 500 columns there.
        </li>
        <li>
            In everyday spreadsheet use, and in a lot of instrument export
            software, the more common convention is the <b>opposite</b> —
            one column per sample, with a shared axis running down the
            rows. That's this app's own internal representation, which is
            also why "spectra in columns" is the default Standard layout.
        </li>
    </ul>
    <p>
        Neither convention is more "correct" — they're just different
        traditions from different fields. That's exactly why the Layout
        choice exists: to tell the importer which convention your
        particular file follows.
    </p>
    <div class="warning">
        <b>Why this matters for PCA and similar analyses:</b> Principal
        Component Analysis (and related multivariate methods) treats rows
        and columns fundamentally differently — one axis is treated as
        "the observations," the other as "the variables." Transposing your
        data before running PCA — swapping which axis is rows and which is
        columns — doesn't just reformat the output, it changes what
        question is being answered:
        <ul>
            <li>
                With spectra as <b>observations</b> (one spectrum per row),
                PCA produces <b>scores</b> — one summary number per
                spectrum, describing how that spectrum differs from the
                others.
            </li>
            <li>
                Transpose that, and PCA instead compares how individual
                <b>wavelengths</b> behave across the set of spectra — the
                roles that "scores" and "loadings" play effectively swap
                between the two orientations.
            </li>
        </ul>
        Neither result is wrong on its own terms — they answer genuinely
        different questions — but they are not interchangeable, and
        running an analysis with the wrong orientation produces a result
        that looks reasonable while answering a question you didn't mean
        to ask. If you use this app's PCA or other multivariate tools,
        make sure you know which orientation that specific tool expects
        before drawing conclusions from the result.
    </div>

    <h2>Supported File Formats</h2>
    <div class="info">
        <ul>
            <li>
                <b>Plain-text files</b> — <code>.txt</code>, <code>.csv</code>,
                <code>.dat</code> and any other text file containing numeric
                columns separated by a consistent delimiter.
                Multiple encodings are tried automatically
                (UTF-8, Latin-1, CP1252).
            </li>
            <li>
                <b>Excel files</b> — <code>.xlsx</code>, <code>.xls</code>,
                <code>.xlsm</code>.
                Numbers are read directly from the workbook cells so there is
                no delimiter or decimal-separator ambiguity.
                By default, the sheet named <b>spectra</b> is used when
                present (this is the sheet written by the Save function);
                otherwise the first sheet is used. A <b>Sheet</b> picker
                appears for Excel files to choose a different sheet
                explicitly — see below.
                <br><br>
                Tick <b>Import several sheets</b> and that picker becomes a
                checkable list: every sheet you tick is imported in one pass.
                Spectra carry the sheet name in their label
                (<code>&lt;file&gt; [&lt;sheet&gt;] : &lt;column&gt;</code>) so
                two sheets using the same column names stay distinct.
                <br><br>
                <b>Each sheet keeps its own settings.</b> Different sheets are
                usually different tables — a different layout, different metadata
                columns to exclude, a different header row. <b>Click a sheet in
                the list</b> (highlight it, as distinct from ticking it) to
                configure that sheet: the preview and every setting below then
                refer to it. Tick = "import this one"; click = "configure this
                one".
                <br><br>
                <b>A sheet you haven't clicked into yet defaults to Auto,</b>
                not to whatever the previously-configured sheet had set —
                unlike navigating between separate <i>files</i> (see Import
                Profile / Apply to All Other Files below), where a manual
                override does carry forward as a starting point. Clicking a
                sheet that was already left on Auto genuinely re-detects
                delimiter, decimal separator and header from that sheet's own
                data, rather than silently inheriting a choice made for a
                different sheet's layout. This matters because an inherited
                setting that's wrong for a normal-looking sheet gives no
                warning — it just quietly misreads that sheet.
                <br><br>
                <b>Apply to All Sheets</b> (button below the sheet list, once
                <b>Import several sheets</b> is ticked and the workbook has
                more than one sheet) is the explicit, opt-in version of that
                same convenience: it copies everything about the
                sheet you're currently configuring — layout, separators,
                header row, column pickers — onto every other sheet in the
                workbook, after asking for confirmation. Use it when several
                sheets genuinely do share one non-default format, instead of
                configuring each one by hand.
            </li>
            <li>
                <b>SPE files</b> — <code>.spe</code>, from Princeton
                Instruments / Teledyne cameras. Both <b>LightField 3.x</b>
                and legacy <b>WinSpec 2.x</b> files are supported, and the
                format is auto-detected — see the dedicated section below.
                Every stored frame becomes one spectrum with a raw,
                <b>uncalibrated</b> pixel-index x-axis. No settings apply
                to this format at all.
            </li>
            <li>
                <b>SPC files</b> — <code>.spc</code>, the Thermo/GRAMS
                Universal Data Format (SpectraCalc, LabCalc, GRAMS/32 and
                everything descended from them). Both the legacy
                <b>old-format</b> and the modern <b>new-format</b> headers
                are supported, and the format is auto-detected — see the
                dedicated section below. Unlike SPE, SPC carries a real,
                <b>calibrated</b> x-axis (wavenumber, nanometers, etc., as
                recorded in the file). No settings apply to this format
                either.
            </li>
            <li>
                <b>JWS files</b> — <code>.jws</code>, JASCO SpectraManager's
                native binary format (e.g. from a J-815 CD spectropolarimeter).
                Carries a real, <b>calibrated</b> wavelength x-axis. A single
                file can hold several co-recorded channels sharing that same
                axis — most commonly <b>CD [mdeg]</b>, sometimes also
                <b>HT [V]</b> (photomultiplier dynode voltage) and/or
                <b>Absorbance [AU]</b> — see the dedicated section below for
                how to pick which ones to import.
            </li>
            <li>
                <b>JWB files</b> &mdash; <code>.jwb</code>, JASCO SpectraManager's
                <b>temperature (interval) scan</b>, e.g. a CD melting
                experiment: one spectrum recorded at every temperature while
                the sample is heated or cooled. Same container and the same
                channels as JWS, but every channel you tick is imported as
                <b>one spectrum per temperature</b>, each labelled with its
                temperature &mdash; see the dedicated section below.
            </li>
            <li>
                <b>MAT files</b> — <code>.mat</code>, a hyperspectral Raman/IR
                map exported by WITec's <b>Project FIVE</b> software (the
                Eigenvector "dataset object" struct layout). Every pixel of
                the map's row &times; col grid becomes one spectrum, all
                sharing the map's own calibrated x-axis — see the dedicated
                section below. No settings apply to this format at all; row,
                column, and (when the file records them) physical &micro;m
                coordinates are attached to every imported spectrum's
                metadata.
            </li>
            <li>
                <b>SpecOrd row-per-measurement CSV</b> — a <code>.csv</code>
                export straight off a SpecOrd spectrometer's own software,
                with tick <b>SpecOrd row-per-measurement CSV</b> checked.
                Structurally different from every other <code>.csv</code>
                this app reads: one row per (condition, temperature-step)
                measurement rather than one column per spectrum. Detected
                automatically from the file's header row; see the dedicated
                section below.
            </li>
        </ul>
    </div>

    <div class="info">
        <b>File with an unrecognized extension?</b> Import doesn't reject it
        on the name alone. If its content looks like numeric columns — the
        same check used for plain text above — you're asked whether to read
        it as text data; only files whose content genuinely doesn't look
        numeric are turned away outright. This matters for instrument
        exports and collaborator files saved under some other extension
        (<code>.bcw</code>, <code>.dat1</code>, whatever the source software
        happened to choose) that are otherwise ordinary x/y columns —
        picking <b>All Files</b> in the file-picker's format dropdown (or
        dragging the file onto the window) reaches them the same way any
        <code>.txt</code> file would be. Binary formats (SPE/SPC/JWS/JWB/MAT) and
        Excel aren't affected by this — those always need their real
        extension, since sniffing binary bytes as text would be meaningless.
    </div>

    <h2>SPE Files (LightField &amp; WinSpec legacy)</h2>
    <p>
        SPE is the binary format written by Princeton Instruments /
        Teledyne cameras for CCD/CMOS acquisitions — Raman, CD, or any
        other spectroscopic detector reading through that hardware. Two
        structurally different formats share the <code>.spe</code>
        extension, and both are handled automatically:
    </p>
    <ul>
        <li>
            <b>LightField 3.x</b> — identified by an XML footer at the end
            of the file. Written by LightField, the successor to WinSpec.
        </li>
        <li>
            <b>WinSpec 2.x (legacy)</b> — an older, fixed binary header
            with no XML footer, written by WinSpec/WinView prior to
            LightField.
        </li>
    </ul>
    <p>
        You don't need to know which one a given file is — the importer
        checks for the XML footer and reads the file accordingly. Either
        way, every stored frame in the file becomes one spectrum — a
        multi-frame acquisition of, say, 120 frames produces 120 spectra,
        numbered <code>0001</code>, <code>0002</code>, … the same way a
        headerless text file would be.
    </p>
    <div class="info">
        <b>Calibrated x-axis — legacy WinSpec files only, opt-in.</b>
        WinSpec can record an x-axis calibration (a polynomial mapping
        pixel number to a real physical unit) directly in the file's
        header at acquisition time. When the currently-previewed file is a
        legacy WinSpec <code>.spe</code> with a valid calibration, a
        <b>Use calibrated x-axis (&lt;unit&gt;)</b> checkbox appears above
        the preview — <b>unchecked by default</b>. Ticking it switches
        that file to its recorded axis; leaving it unticked (or any file
        with no recorded calibration at all) gives the plain pixel-index
        x-axis (0, 1, 2, …), same as always. This is a per-file choice,
        remembered the same way every other per-file import setting is: it
        survives switching between files and back within one Import
        session, but isn't saved beyond that.
    </div>
    <div class="note">
        <b>Why pixel index rather than calibrated is the default:</b> a
        large class of real SPE files have no calibration to offer at all
        (see LightField below), and even where WinSpec did record one,
        it's whatever axis the instrument software happened to use at
        acquisition time — commonly wavelength (nm) — which is not
        necessarily the unit you actually want to work in (e.g. Raman
        shift, derived from wavelength and the laser line). Pixel index is
        the one axis every SPE file can always produce consistently, so
        it stays the default; the calibrated axis remains one click away
        whenever a specific file's recorded calibration is exactly what's
        needed.
    </div>
    <div class="warning">
        <b>LightField 3.x files: pixel index only, no calibration
        option.</b> The checkbox never appears for LightField files —
        reading LightField's own calibration data isn't currently
        supported (LightField stores it differently from legacy WinSpec,
        in its XML footer rather than a fixed binary struct, and this
        app's LightField reader hasn't been verified against a real
        calibrated sample file — see the codebase's own conservative
        "don't guess at an unverified layout" policy). If your workflow
        calibrates the x-axis separately for LightField data (e.g. a
        dedicated calibration procedure producing calibrated text files),
        import those calibrated files normally through the
        Standard/Row-oriented/Interlaced layouts described above — SPE
        import and text-file import are two independent paths into the
        same spectrum list.
    </div>
    <div class="warning">
        <b>Only single-region, single-row (fully vertically-binned)
        acquisitions are supported</b> — i.e. 1D spectra, not 2D images or
        multi-ROI acquisitions. A file that doesn't match this (a 2D image
        frame, or more than one region-of-interest per frame) gives a
        clear error explaining why, rather than attempting to read it
        incorrectly.
    </div>
    <p>
        Almost none of the usual text/Excel settings apply to SPE files —
        no delimiter, decimal separator, header, Layout, or column
        pickers, since none of those concepts exist for this format. The
        dialog reflects this: those settings groups are hidden for an SPE
        file, replaced with a short summary (format, frame count, pixel
        count) and a preview of the first few frames. The one SPE-specific
        setting that does exist — the calibrated-axis choice for legacy
        WinSpec files — is described above. <b>Zero Padding</b> is the one
        general setting that still applies, exactly as it does for
        text/Excel imports: it controls the digit width of the
        <code>0001</code>, <code>0002</code>, … numbering given to each
        frame's spectrum, and stays visible and live for SPE files — see
        <a href="#zero-padding">Zero Padding</a> below.
    </p>

    <h2>SPC Files (Thermo/GRAMS)</h2>
    <p>
        SPC is the Thermo/GRAMS Universal Data Format — a long-lived
        binary format used across a wide range of spectroscopy software
        (SpectraCalc, LabCalc, GRAMS/32 and its descendants, and many
        instrument vendors' own export options). As with SPE, two
        structurally different header layouts share the <code>.spc</code>
        extension, distinguished by a single byte in the file and handled
        automatically:
    </p>
    <ul>
        <li>
            <b>Old format</b> — the legacy SpectraCalc/LabCalc header. No
            multifile or log-block support.
        </li>
        <li>
            <b>New format</b> — the modern GRAMS/32-era header, with
            optional multifile and log-block support.
        </li>
    </ul>
    <p>
        Again, you don't need to know which one a given file is — it's
        detected automatically. <b>Unlike SPE, SPC carries a real,
        calibrated x-axis</b> — wavenumber, nanometers, or whatever unit
        the instrument recorded — read directly from the file, along with
        its axis labels. Most SPC files contain exactly one spectrum
        (one "subfile"); a file with several subfiles (e.g. a short time
        series stored in one file) produces one spectrum per subfile,
        numbered the same way multi-frame SPE files are.
    </p>
    <div class="warning">
        A few genuinely rarer SPC variants aren't currently supported —
        explicit per-point X arrays stored separately for each subfile,
        4D/W-plane files, and new-format files in MSB byte order (vanishingly
        rare in practice). Any of these give a clear, specific error
        rather than attempting to read them incorrectly.
    </div>
    <p>
        As with SPE, almost no settings apply to SPC files — the dialog
        shows a short summary (format, subfile count, point count, and the
        file's own axis labels) and a preview of the first few subfiles,
        the same way it does for SPE. <b>Zero Padding</b> again applies:
        when a file has several subfiles, it controls the digit width of
        the auto-generated <code>0001</code>, <code>0002</code>, …
        numbering — see <a href="#zero-padding">Zero Padding</a> below.
    </p>

    <h2>JWS Files (JASCO SpectraManager)</h2>
    <p>
        JWS is the native binary format written by JASCO's spectroscopy
        instruments — most commonly CD spectropolarimeters (the J-815 and
        similar models). It is not a published format; support here was
        built by examining real sample files directly rather than from a
        specification. A JWS file is, internally, a Microsoft OLE2
        compound-file container (the same structured-storage format
        historically used for old <code>.doc</code>/<code>.xls</code>
        files) holding a fixed set of named data blocks, read without any
        third-party library.
    </p>
    <p>
        <b>Channels.</b> A single scan can record more than one quantity
        at once, all sharing the same calibrated wavelength x-axis:
    </p>
    <ul>
        <li><b>CD [mdeg]</b> — the circular dichroism signal itself, in millidegrees. Present in every JWS file seen so far.</li>
        <li><b>HT [V]</b> — the photomultiplier dynode ("high tension") voltage. Only present when the instrument was set to record it alongside CD.</li>
        <li><b>Absorbance [AU]</b> — the sample's ordinary UV/Vis absorbance, recorded simultaneously with CD on the same optical path. Very commonly present even when not deliberately requested.</li>
    </ul>
    <p>
        Unlike SPE/SPC, a JWS file's channels are <b>not</b> all imported
        unconditionally: opening a <code>.jws</code> file shows a
        <b>Channels to import</b> table, one row per channel found, with an
        <b>Include</b> checkbox (all ticked by default), a <b>Type</b>
        column, and each channel's value <b>range</b>. Untick a channel to
        leave it out of the import — e.g. to bring in only CD from a file
        that also carries HT.
    </p>
    <div class="warning">
        JWS does not store a channel-type label anywhere recoverable from
        the file — the <b>Type</b> shown is this app's own guess, based on
        each channel's value range (CD straddles zero and stays small; HT
        is always positive and large, typically hundreds of volts;
        Absorbance is always positive and small). This is reliable in
        every sample file tested, but it <i>is</i> a guess rather than
        something read directly from the file, so double-check it for
        unusual data — a CD spectrum with an unusually large positive
        offset, for instance, could conceivably be misread as Absorbance.
        The <b>Type</b> column is an editable dropdown for exactly this
        reason: correct it there if it looks wrong, before clicking Import.
    </div>
    <p>
        No other settings apply to JWS files — no delimiter, decimal,
        header, or Layout concept, same as SPE/SPC.
    </p>

    <h2>JWB Files (JASCO Temperature Scans)</h2>
    <p>
        JWB is the sibling of JWS: the file JASCO SpectraManager writes for an
        <b>interval (temperature) scan</b> &mdash; most commonly a <b>CD melting
        experiment</b>, in which the spectropolarimeter records one complete
        spectrum at each temperature while the sample is heated or cooled.
        Internally it is the same OLE2 container as a JWS file and is read the
        same way, without any third-party library. Like JWS it is not a
        published format; support here was built from real scans (15&ndash;17
        temperatures each, heating and cooling) and checked against an
        independent reader, which gave identical temperatures and identical
        values for every channel.
    </p>
    <p>
        <b>What is imported.</b> A JWS file gives one spectrum per channel; a
        JWB file gives <b>one spectrum per channel and per temperature</b>. A
        scan with 17 temperatures and two channels (CD and Absorbance) can
        therefore produce 34 spectra. The dialog works exactly as for JWS: a
        <b>Channels to import</b> table lists the channels, with an
        <b>Include</b> checkbox, an editable <b>Type</b> and each channel's value
        <b>range</b>. Untick a channel to leave it out &mdash; for a melting
        experiment you will usually want only <b>CD [mdeg]</b>, or only
        <b>Absorbance [AU]</b>. The summary line above the table shows how many
        temperatures the file holds, the temperature range, the direction
        (<i>heating</i> or <i>cooling</i>, read from the first and last
        temperature), and the free-text sample name and comment that were typed
        at the instrument, if any.
    </p>
    <p>
        <b>Labels.</b> Every spectrum is labelled with the file name, the channel
        and its temperature, in the same style as SpecOrd CSV imports:
    </p>
    <p style="text-align:center;">
        <code>2026_09_21-1-Cell 5 : CD [mdeg] T=45.00C</code>
    </p>
    <p>
        Having the temperature in the label is deliberate: <b>Melting Curve
        Analysis</b> guesses each spectrum's temperature from the numbers in its
        label, and picks the one that actually changes between the selected
        spectra &mdash; so for a JWB import the Temperature column is normally
        filled in correctly without any editing (still worth a glance). If the
        instrument recorded the same temperature twice, the later spectra get a
        trailing <code>#2</code>, <code>#3</code>, &hellip; so that no label repeats
        (a repeated label would silently overwrite the earlier spectrum).
        Importing several JWB files at once &mdash; for example a heating and a
        cooling run &mdash; is fine: each spectrum carries its own file name.
    </p>
    <p>
        <b>Metadata.</b> Besides the usual file information, every spectrum stores
        <code>temperature_C</code>, <code>direction</code> (<code>heating</code> or
        <code>cooling</code>), the instrument's free-text <code>jasco_sample_name</code>
        and <code>jasco_comment</code>, and the channel and position within the scan
        (<code>import_parameters</code>) &mdash; open any imported spectrum's
        Metadata dialog to see them.
    </p>
    <div class="note">
        <b>Practical notes.</b>
        <ul>
            <li>The <b>Type</b> of each channel is the same value-range guess as for
            JWS (see the warning in that section), judged on the values of all
            temperatures together. Correct it in the dropdown if it looks wrong.</li>
            <li>The x-axis is stored in scan order (for example 480 &rarr; 220 nm);
            like every import, the spectra are re-sorted into ascending order on the
            way in.</li>
            <li>CD of a sample in buffer is usually mostly noise at the shortest
            wavelengths of a scan (the detector voltage is high there). Crop the range
            afterwards with the <b>Data Range</b> operation if it disturbs your
            analysis.</li>
            <li>No delimiter, decimal, header, Layout or Zero Padding settings apply
            &mdash; spectra are named by temperature, not numbered.</li>
        </ul>
    </div>

    <p>
        <b>Try it with sample data.</b> Three real CD melting scans ship with the
        application: <b>Help &rarr; Test datasets &rarr; Real (measured) &rarr; CD
        melting (JASCO .jwb)</b> &mdash; two heating runs and one cooling run.
        Open one, keep only <b>CD [mdeg]</b>, then run <b>Melting Curve
        Analysis</b>: it reads each spectrum's temperature from its name.
    </p>

    <h2>MAT Files (WITec/Project FIVE Hyperspectral Maps)</h2>
    <p>
        MAT files of this kind are hyperspectral <b>maps</b>, not single
        spectra: an instrument scans a rectangular grid of points across a
        sample, recording one full spectrum at every point. WITec's
        <b>Project FIVE</b> software (and other packages built on the same
        Eigenvector "dataset object" convention) exports this as a single
        <code>.mat</code> file holding the map's row &times; col size, every
        pixel's spectrum, the shared spectral x-axis and its unit (e.g.
        <code>rel. 1/cm</code> for Raman shift), and — when recorded — the
        physical spacing between pixels in &micro;m.
    </p>
    <p>
        Importing one of these files creates <b>one spectrum per pixel</b>,
        labelled <code>&lt;file&gt; [rNN_cNN]</code> — row/column numbers
        1-based (the map's first row/column is <code>r1_c1</code>, not
        <code>r0_c0</code>) and zero-padded to the map's own grid size —
        all sharing that one spectral x-axis. Nothing needs to be
        configured — the row/col grid size, spectral axis, and pixel
        coordinates all come from the file itself.
    </p>
    <p>
        Every imported spectrum's <code>import_parameters</code> metadata
        carries <code>map_n_rows</code> / <code>map_n_cols</code> (the
        map's full grid size), <code>pixel_row</code> / <code>pixel_col</code>
        (that spectrum's own position in it), and — when the file recorded
        physical spacing — <code>spatial_x</code> / <code>spatial_y</code> in
        <code>spatial_unit</code>. Unlike the label, these are <b>0-based</b>
        array indices (the first row/column is <code>0</code>, not
        <code>1</code>) — this is what lets the map's spatial structure be
        reconstructed afterwards — the <b>2-D Map</b> dialog reads
        <code>map_n_rows</code> &times; <code>map_n_cols</code> straight
        from the imported spectra and fills them in automatically, reshaping
        back into the original spatial grid for visualization with no manual
        dimension entry needed.
    </p>
    <div class="warning">
        Support for this format was built and verified against real
        Project FIVE 5.1 exports rather than a published specification —
        variants from other Eigenvector-dataset-object-exporting software,
        or older/newer Project FIVE versions, may use a slightly different
        internal layout. A file that doesn't match what this reader expects
        is always rejected with a specific reason (e.g. a missing field, or
        a declared grid size that doesn't match the actual pixel count) —
        never silently misread.
    </div>
    <p>
        <b>Preview table columns.</b> Rather than the first few pixels in
        file order &mdash; which for a map stored row by row would put
        every sampled column in the same handful of map rows and say
        nothing about the map's actual extent &mdash; the preview's
        columns are nine pixels chosen by position: each of the first,
        middle, and last row, crossed with each of the first, middle, and
        last column (fewer than nine on a very small map, where some of
        those coincide). They're listed in that grid's own natural
        reading order &mdash; every column from the first sampled row,
        then every column from the middle row, then every column from the
        last row &mdash; which is why the header order (e.g., 1-based
        like the imported labels: <code>r1_c1, r1_c72, r1_c144, r58_c1,
        &hellip;</code>) can look non-sequential: it's a spatial sample,
        not a walk through the file's own flat pixel order. Hovering over the table repeats this
        same explanation. The <b>Rows to show</b> spin box above the
        table controls how many spectral points are listed (default 20);
        changing it just redraws the already-loaded preview, it never
        re-reads the file. Next to it, a small orange <b>?</b> button
        opens a reminder of the actual post-import workflow &mdash;
        selecting the imported spectra and opening the <b>2-D Map</b>
        dialog &mdash; since nothing else on this page explains it.
    </p>
    <p>
        <b>Spatial preview.</b> Below the usual points/values table, a
        MAT file's preview also shows a raw, unprocessed spatial heatmap
        — every pixel's own intensity at one spectral point, placed at
        its actual row/col position. A slider picks which spectral point
        is shown (defaulting to the middle of the range); dragging it is
        the fastest way to confirm the file's row/col geometry decoded
        correctly before importing — a real map looks like a coherent
        shape, a wrong reshape looks like noise. This heatmap always
        reflects the file's own data, unprocessed — it's a sanity check,
        not an analysis view (that's what the app's 2-D Map dialog is
        for, after import). <b>Preserve aspect ratio</b> (checked by
        default) keeps each map pixel square in the preview, matching
        its real physical shape on the sample; uncheck it for a map so
        elongated in one direction that an equal-aspect view leaves it a
        thin sliver.
    </p>
    <p>
        No other settings apply to MAT files — no delimiter, decimal,
        header, Layout, or Zero Padding concept, same as SPE/SPC/JWS/JWB.
    </p>

    <h2>SpecOrd Row-per-Measurement CSV</h2>
    <p>
        Some instrument software exports one row per (condition,
        temperature-step) <i>measurement</i> instead of one column per
        <i>spectrum</i> — confirmed on real files from a SpecOrd
        spectrometer running a pH-titration UV-melting series, but nothing
        about the parsing is SpecOrd-specific beyond the exact column names
        it happens to use. Each row's header line looks like:
    </p>
    <p style="text-align:center;">
        <code>No.;Type;Name;Date/Time;Note;Temperature;Temperature;230,0;231,0;&hellip;;330,0;</code>
    </p>
    <p>
        i.e. semicolon-delimited, comma-as-decimal (European locale) — 7
        metadata columns (<b>Type</b> is <code>Blank</code> or
        <code>Sample</code>; <b>Name</b> is the condition, e.g.
        <code>pH 7.5</code>) followed by one column per wavelength. This
        layout has no Standard/Interlaced/Row-oriented equivalent — it
        mixes per-row metadata with a shared wavelength axis in a way none
        of those three options can express — so it gets its own dedicated
        reader rather than a Layout choice.
    </p>
    <p>
        <b>Auto-detection.</b> A <code>.csv</code> file whose first three
        header columns read exactly <code>No.</code>, <code>Type</code>,
        <code>Name</code> is recognized automatically, and the
        <b>SpecOrd row-per-measurement CSV</b> checkbox appears pre-ticked
        with a summary of what was found (conditions, total spectra,
        wavelength range, temperature range). Untick it to fall back to
        importing the file as an ordinary CSV instead (e.g. if this was a
        false match); the checkbox is offered for every <code>.csv</code>
        file, not just auto-detected ones, so any file sharing this layout
        can be told to use this reader by hand.
    </p>
    <p>
        <b>What each row becomes.</b> Every row in the file becomes one
        spectrum (wavelengths as x, absorbance as y). Rows for the same
        condition (<b>Name</b>) repeat once per temperature step in a fixed
        cycle through every condition in the file, tracing out that
        condition's full heating/cooling temperature trajectory — run
        boundaries (heating vs. cooling, run 1 vs. run 2, &hellip;) are
        found automatically from direction reversals in each condition's
        own temperature sequence, not assumed to always be exactly 4 runs.
        Each spectrum's label embeds the condition, run/direction, and
        temperature, e.g.:
    </p>
    <p style="text-align:center;">
        <code>250224 dC5U3 : pH_7.5 run2_cooling T=45.20C</code>
    </p>
    <p>
        The same values are also stored as structured metadata
        (<code>condition_label</code>, <code>condition_value</code>,
        <code>run_index</code>, <code>direction</code>,
        <code>temperature_C</code>, <code>measurement_type</code>) — open
        any imported spectrum's Metadata dialog to see them. Embedding
        temperature directly in the label, specifically, is deliberate: the
        <b>Melting Curve Analysis</b> tool (see its own Help) guesses each
        selected spectrum's temperature from the numbers in its label,
        preferring whichever number actually <i>varies</i> across the
        selected batch — since condition/run/direction stay fixed within
        one such series and only temperature changes, it reads the right
        number automatically. Select all the spectra from one condition's
        run/direction, open Melting Curve Analysis, and the temperature
        column populates itself correctly without manual editing (though
        it's always editable afterward, the same as for any other import).
    </p>
    <div class="warning">
        The file's header carries <b>two</b> columns both literally named
        <code>Temperature</code>. They differ by up to roughly 0.3&deg;C on
        real files — likely a setpoint/actual-reading pair, but nothing in
        the exported file documents which is which. Rather than guess, each
        row's canonical temperature is the <b>average</b> of the two. If
        you need one specific column instead, that's not currently
        selectable — the discrepancy is small enough that it hasn't
        mattered for melting-curve Tm fitting on real data so far, but ask
        if a genuine use case needs to distinguish them.
    </div>
    <p>
        No other settings apply to SpecOrd CSV files — no delimiter,
        decimal, header, Layout, or column-picker concept, same as
        SPE/SPC/JWS/JWB. Zero Padding is likewise unused (every spectrum
        already has a unique label from its own condition/run/temperature).
    </p>

    <h2>Expected Data Layout</h2>
    <p><small>(Standard, Interlaced, and Row-oriented — the three
    text/Excel layouts. SPE, SPC, JWS, and JWB files, described above, don't use
    any of these.)</small></p>

    <h3>Standard layout (default)</h3>
    <p>
        The <b>first column</b> is the shared X-scale (e.g. wavenumber or
        wavelength). Every subsequent column is a separate spectrum (Y-scale).
        An optional header row in the first row provides spectrum labels.
    </p>
    <pre>
x_scale    spectrum_A    spectrum_B    spectrum_C
100.0      1.23          4.56          7.89
102.0      1.31          4.61          7.92
&hellip;</pre>

    <h3>Interlaced layout</h3>
    <p>
        Each spectrum has its <b>own X-scale column</b>, alternating with its
        Y-scale: x<sub>1</sub>, y<sub>1</sub>, x<sub>2</sub>, y<sub>2</sub>, &hellip;
        Use this when spectra were measured on different grids.
    </p>
    <pre>
x_A      spectrum_A    x_B      spectrum_B
100.0    1.23          200.0    5.67
102.0    1.31          202.0    5.71
&hellip;</pre>
    <div class="warning">
        <b>Note:</b> The Interlaced format option is a per-file setting — it
        resets to off automatically after each import so it does not affect
        subsequent files.
    </div>
    <div class="warning">
        <b>Applies to every layout, and every file format — not just Interlaced:</b>
        when a spectrum's x-values are not already increasing, import re-sorts that
        spectrum into ascending x order, and if the same x-value appears more than
        once it <b>merges those points into one by averaging their y-values</b>.
        This happens at one single point every import passes through on its way in
        — Standard, Interlaced, Row-oriented, Excel, SPE, SPC, JWS, JWB, all of it — so the
        same rule applies no matter which file or layout you're importing.
        <br><br>
        The sorting is harmless — it is a pure reordering, every y stays attached to
        its own x, and nothing is lost. <b>The merging is not harmless: it destroys
        data</b> in the sense that two separate measurements become one averaged
        point. If the same x legitimately recurs with a different y — a
        forward/reverse voltage sweep, a repeated cycle — the two measurements are
        averaged together and the difference between them, often the very thing being
        measured, is gone from the spectrum you see and analyse.
        <br><br>
        Nothing is silently thrown away, though: whenever a merge happens, the
        original, pre-merge x/y values are kept in that spectrum's own metadata
        (<b>Show Metadata → duplicate_x_merge</b>), so the discarded points can
        always be recovered later even though they're not part of the working
        spectrum. And whenever any merging actually happens, you're told about it
        <b>twice</b>: as a warning block in the <b>Import Results</b> summary shown
        right after import (naming the spectrum and how many points were merged), and
        as an entry in the application log for a permanent record. If you see it and
        the recurring x-values are meaningful in your experiment — not noise or a
        genuine duplicate — treat the affected spectra as needing a closer look before
        drawing conclusions from them.
    </div>

    <h3>Repeated-scan data: split instead of merge</h3>
    <p>
        Averaging away every duplicate is the right default, but there is one
        common case it's wrong for: a file that is really <b>several scans
        stacked in one long x/y column pair</b> — a forward sweep followed by
        a reverse sweep sharing the same x-axis, or N spectra concatenated
        one after another instead of laid out as separate columns. There,
        the "duplicate" x-values aren't noise at all; they're N different
        measurements at the same x, and merging throws away exactly the
        thing you imported the file to see.
    </p>
    <p>
        Import now recognizes this shape automatically: if most of a
        spectrum's distinct x-values repeat the <b>same number of times</b>
        S (2 or more), that's a strong signal of S co-registered scans
        rather than a handful of coincidental duplicates, and you're asked,
        once per file, right when it's detected:
    </p>
    <ul>
        <li><b>Split into S spectra</b> &mdash; keeps every scan as its own
        spectrum instead of averaging them together. Any x-values that don't
        fit the pattern cleanly (a stray turning point at the ends of a
        sweep, for example) are left out of the split spectra — the dialog
        tells you how many, so you can judge whether that's acceptable.</li>
        <li><b>Merge (default)</b> &mdash; the ordinary behavior described
        above, completely unchanged.</li>
    </ul>
    <p>
        This only ever asks when the repeat pattern is strong (the large
        majority of x-values share the same repeat count) — the ordinary
        case of a file with no such structure, or just one or two stray
        duplicates, is <b>never</b> affected: it's merged silently (with the
        usual warning) exactly as it always has been. Scan identity is
        recovered from each x-value's position in the file, not from
        assuming the repeats sit in tidy contiguous blocks, so a genuine
        round-trip sweep (where the reverse leg runs through the same
        x-values in the opposite direction) still splits into the right two
        scans.
    </p>

    <h3>Row-oriented layout</h3>
    <p>
        The <b>first row</b> is the shared X-scale — the mirror image of the
        standard layout. Every subsequent row is a separate spectrum
        (Y-scale). An optional header <b>column</b> (the first column)
        provides spectrum labels, the same way the first row does in the
        standard layout.
    </p>
    <pre>
label         100.0    200.0    300.0    400.0
spectrum_A    1.1      2.2      3.3      4.4
spectrum_B    5.5      6.6      7.7      8.8
&hellip;</pre>
    <p>
        Use this for files where instrument software writes one spectrum per
        row instead of per column.
    </p>
    <div class="warning">
        <b>Note:</b> Row-oriented is a per-file setting, just like Interlaced
        — it resets to off automatically after each import. Row-oriented and
        Interlaced are mutually exclusive; a file can only use one layout at
        a time.
    </div>

    <h2>The Dialog Step by Step</h2>
    <ol>
        <li>
            <b>Select files</b> in the OS file picker (File → Import data →
            new / add), or skip the menu entirely and <b>drag files from
            your file manager and drop them onto the application
            window</b> — either way opens the same dialog below with the
            same files selected. You can select multiple files at once
            using Ctrl+click, Shift+click, or by dragging several files
            together.
        </li>
        <li>
            The dialog opens. A bold label above the settings always shows
            <b>which file you're currently configuring</b> (e.g. "Now
            configuring file 2 of 5: spectra.txt"). If more than one file
            was selected, a scrollable <b>list of every selected file</b> is
            shown — click any row to jump the preview straight to that file
            — alongside <b>&#9664; &#9654; navigation arrows</b> for
            flipping through them in order.
        </li>
        <li>
            Check the <b>Preview table</b> — if the cyan-highlighted row or
            column is the X-axis and the rest look like spectra, the settings
            are correct.
        </li>
        <li>
            If the preview looks wrong, adjust the settings and watch the
            preview update instantly. <b>Every setting in this dialog —
            Layout, separators, header, column pickers, everything — can be
            different for each file.</b> Switching to another file in the
            list shows that file's own settings, not the one you just left.
        </li>
        <li>
            Once every file looks right, click <b>Import</b>.
        </li>
    </ol>

    <h2>Drag and Drop</h2>
    <p>
        Instead of using File → Import data, you can drag one or more
        spectrum files straight from your file manager and drop them
        anywhere on the application window. This opens the exact same
        Import dialog described above, with those files already
        selected — it's a shortcut to the same place, not a different
        import path, so everything on this page still applies.
    </p>
    <p>
        Supported extensions: <code>.txt</code>, <code>.csv</code>,
        <code>.dat</code>, <code>.xlsx</code>, <code>.xls</code>,
        <code>.xlsm</code>, <code>.spe</code>, <code>.spc</code>,
        <code>.jws</code>, <code>.jwb</code>, <code>.mat</code>. Dropping
        a file with an unsupported extension (or dropping something that
        isn't a file at all) is simply ignored.
    </p>
    <div class="note">
        <b>Add or Replace?</b> If spectra are already loaded, drag-and-drop
        asks first: <b>Add</b> (keep what's loaded and add the new spectra
        alongside) or <b>Replace all</b> (discard the loaded spectra first).
        <b>Add</b> is the default — a passive drag gesture is never treated as
        licence to discard your work, and nothing is ever thrown away unless
        you say so. If nothing is loaded yet the question is skipped, since Add
        and Replace would do the same thing.
        <br><br>
        The same prompt appears when you open one of the built-in datasets from
        <b>Help → Test datasets</b>. Only the <b>File → Import data → add /
        new</b> menu makes the choice up-front instead of asking.
    </div>

    <h2>Importing Multiple Files</h2>
    <p>
        You can select multiple files at once in the OS file picker using
        Ctrl+click or Shift+click. All selected files are imported in a
        single operation — but each one is imported with <em>its own</em>
        settings, not one shared configuration applied to the whole batch.
        This means a batch can freely mix, say, one Standard-layout file,
        one Interlaced file, and one Row-oriented file, each with its own
        delimiter and header settings, all imported together.
    </p>
    <p>
        A file's settings are captured the moment you preview it, and
        remembered for the rest of the dialog session — click away to
        another file and back, and everything you set is exactly as you
        left it. A file you never click into at all is still imported using
        whatever Auto-detection produced for it; you only need to visit the
        files that actually need a manual adjustment.
    </p>
    <p>
        When <b>Value separator</b> and <b>Decimal separator</b> are left on
        <b>Auto</b>, each file is auto-detected <em>independently</em> —
        always, regardless of how many files you're importing. This means
        you can import a dot-decimal file and a comma-decimal file together
        and both will be read correctly.
    </p>
    <p>
        If you <em>manually</em> override a separator (or any other setting)
        while viewing one file, that choice becomes the starting point
        offered for the <em>next file you preview for the first time</em> —
        a convenience so you don't have to re-set the same override
        repeatedly for a batch of similar files. But it is only ever a
        starting suggestion: changing it for one file never retroactively
        changes a file you've already configured, and going back to an
        earlier file always restores exactly what you set for it,
        regardless of what you've done to other files since.
    </p>

    <h3>Reset to Auto-detected</h3>
    <p>
        Discards any manual changes you've made to the currently-previewed
        file and re-runs auto-detection fresh, exactly as if that file had
        never been previewed at all — including, for Excel files, the
        Sheet choice: it resets to Auto and re-reads the preview from the
        auto-selected sheet, not whichever sheet happened to be manually
        picked before. Available for single-file imports too — a quick way
        to undo tweaks without closing and reopening the dialog.
    </p>

    <h3>Apply to All Other Files  <small>(multi-file imports only)</small></h3>
    <p>
        Copies the currently-previewed file's settings — Layout,
        separators, header, every column picker — onto <em>every other
        file</em> in the batch, including ones you haven't previewed yet
        and ones you've already customized differently. Asks for
        confirmation first, since overwriting other files' individual
        settings is exactly what it does.
    </p>
    <p>
        Use this when a whole batch shares the same non-default format —
        e.g. 50 files that are all Row-oriented with the same label column
        — instead of repeating the same manual setup 50 times.
    </p>

    <h3>Apply to All Sheets  <small>(multi-sheet Excel imports only)</small></h3>
    <p>
        The per-sheet equivalent of Apply to All Other Files above: copies
        the settings of the sheet you're currently configuring — Layout,
        separators, header row, every column picker — onto every
        <em>other</em> sheet in the same workbook, including sheets you
        haven't clicked into yet and ones already customized differently.
        Asks for confirmation first. Appears once <b>Import several
        sheets</b> is ticked and the workbook has more than one sheet.
    </p>
    <p>
        Use this when several sheets genuinely share one non-default format
        — otherwise, leave sheets alone: each one defaults to Auto on its
        own the first time you click into it, rather than inheriting
        whatever a previously-configured sheet had set (see "Each sheet
        keeps its own settings" above).
    </p>
    <div class="warning">
        <b>Column-index settings carry over literally.</b> Label column,
        X-scale column, and Exclude columns are copied as raw column
        indices. This is exactly right when every file in the batch shares
        the same column layout — the intended use case. If a target file
        happens to have fewer columns than an index refers to, that
        specific picker silently falls back to Auto the next time you
        preview that file, or — if you never preview it again — surfaces
        as a clear "index out of range" failure for that file in the
        Import Results summary, rather than a silent misread.
    </div>

    <h3>Import Profile</h3>
    <p>
        Where "Apply to All Other Files" only reaches the other files in
        <em>this</em> batch, an Import Profile is a full settings snapshot
        saved under a name and stored on disk — it's still there the next
        time you open Import, in a future session, for a completely
        different set of files. Use it for a recurring instrument export
        format you import repeatedly across projects.
    </p>
    <ul>
        <li>
            <b>Save Current as Profile…</b> saves the currently-displayed
            file's full settings — Layout, separators, header, every
            column picker, Sheet — under a name you choose. Saving under
            an existing name overwrites it, after confirming.
        </li>
        <li>
            Selecting a profile from the <b>Import profile</b> dropdown
            immediately applies it to the currently-previewed file, the
            same way "Apply to All Other Files" applies settings to a
            file. The dropdown keeps showing the profile's name afterward
            as confirmation it applied — this is still a one-shot copy,
            not an ongoing link, so further edits to the settings below
            do not get saved back into the profile. Switching to a
            different file clears the dropdown back to the placeholder,
            since the shown name would otherwise no longer describe that
            new file's settings.
        </li>
        <li>
            <b>Delete</b> removes the selected profile permanently.
        </li>
    </ul>
    <div class="warning">
        <b>Same column-index and Sheet caveats as Apply to All Other
        Files</b> — and more so here, since a profile is explicitly meant
        to be reused across different files, possibly from entirely
        different projects. Label column, X-scale column, and Exclude
        columns are saved as raw indices; Sheet is saved as a literal
        name. Applying a profile to a file with a different column count,
        or an Excel file without a matching sheet name, falls back to
        Auto for that specific setting rather than corrupting anything —
        worth a glance at the preview after applying, same as any other
        setting change.
    </div>

    <h2>Settings Explained</h2>

    <h3>Sheet  <small>(Excel files only)</small></h3>
    <p>
        Which worksheet to read. Only shown when the currently-previewed
        file is an Excel file (<code>.xlsx</code>/<code>.xls</code>/<code>.xlsm</code>)
        — hidden entirely for plain-text files. The dropdown lists every
        sheet actually present in that specific file.
    </p>
    <p>
        <b>Auto</b> prefers a sheet named <code>spectra</code> (the
        sheet this app's own Save function writes), otherwise the first
        sheet. Changing the sheet re-reads the preview immediately, the
        same as changing any other setting.
    </p>
    <div class="warning">
        <b>Note:</b> if you pick an explicit sheet name and then use
        <b>Apply to All Other Files</b> in a multi-file batch, files that
        don't happen to have a sheet with that exact name silently fall
        back to Auto for that one file, rather than raising an error —
        worth a quick check if your batch mixes workbooks with different
        sheet names.
    </div>

    <h3>Value Separator  <small>(plain-text files only)</small></h3>
    <p>
        The character that separates columns. Auto-detection works for the
        vast majority of files — only change this if the preview looks garbled.
    </p>
    <table>
        <tr><th>Option</th><th>Character</th><th>Typical use</th></tr>
        <tr><td><b>Auto</b></td><td>Detected from file</td>
            <td>Start here — works for most files</td></tr>
        <tr><td><b>tab</b></td><td><code>\t</code></td>
            <td>Files exported from Excel or instrument software</td></tr>
        <tr><td><b>;</b></td><td>Semicolon</td>
            <td>European CSV files (where comma is the decimal separator)</td></tr>
        <tr><td><b>,</b></td><td>Comma</td>
            <td>Standard CSV (only when the decimal separator is a dot)</td></tr>
        <tr><td><b>|</b></td><td>Pipe</td>
            <td>Less common; some instrument exports</td></tr>
        <tr><td><b>space</b></td><td>Whitespace</td>
            <td>Space-separated text files</td></tr>
    </table>
    <div class="warning">
        <b>Ambiguous case:</b> If your file uses a comma as <em>both</em> the
        decimal separator and the column separator, auto-detection will fail.
        Export the file with a semicolon or tab as the column separator instead.
    </div>

    <h3>Decimal Separator  <small>(plain-text files only)</small></h3>
    <table>
        <tr><th>Option</th><th>Meaning</th></tr>
        <tr><td><b>Auto</b></td>
            <td>Detected from the file — works for almost all files</td></tr>
        <tr><td><b>.</b></td>
            <td>Dot — standard in English-locale files</td></tr>
        <tr><td><b>,</b></td>
            <td>Comma — standard in European-locale files
                (German, Czech, French, &hellip;)</td></tr>
    </table>
    <p>
        For <b>Excel files</b> both separator settings are disabled and
        greyed out — numbers are read as native floats directly from the
        workbook so no separator detection is needed.
    </p>

    <h3>Header Row</h3>
    <table>
        <tr><th>Option</th><th>Behaviour</th></tr>
        <tr><td><b>Auto</b></td>
            <td>First looks for where the real table actually starts,
                discarding any preamble above it (an instrument banner,
                operator notes, a multi-line title) exactly as <b>Row N</b>
                would — then, on that row, decides header vs. data the usual
                way: mostly non-numeric text is used as a header and its
                values become spectrum labels, fully numeric is treated as
                data.</td></tr>
        <tr><td><b>No header</b></td>
            <td>Always treat the first row as data.
                Spectra are numbered automatically
                (<code>0001</code>, <code>0002</code>, &hellip;).</td></tr>
        <tr><td><b>Row N</b></td>
            <td>Row <i>N</i> is the header — <b>everything above it is
                discarded</b>. Pick this by hand when a file's preamble is
                long or unusual enough that Auto doesn't find the right row
                on its own. <b>Row 1</b> is the same as the old <b>Yes</b>.</td></tr>
    </table>

    <div class="note">
        <b>Auto skips preamble on its own, within reason.</b> It compares
        each candidate line's column count against the table's real width
        (learned from the rows further down) and discards anything that
        doesn't look like it belongs — but deliberately tolerates a header
        that is exactly <b>one</b> column narrower than the data (the common
        convention of leaving the X column unlabeled), so that pattern is
        never mistaken for junk and discarded by accident. This only looks
        within the first couple hundred lines of the file; a preamble longer
        than that, or junk that happens to match the table's column count,
        can still fool it — pick <b>Row N</b> by hand if Auto gets a
        particular file wrong.
    </div>

    <div class="note">
        <b>Row numbers count the rows you can actually see in the preview.</b>
        Completely blank lines are dropped when the file is read, so the numbering
        in the picker always matches the preview — pick the row where the real
        table starts and that is exactly what gets used.
    </div>

    <div class="note">
        <b>In Row-oriented layout there is no header <i>row</i>.</b> The spectrum
        names come from a label <i>column</i> (see <b>Label column</b>). There,
        <b>Row N</b> means &ldquo;the table starts at row N&rdquo; — that row
        becomes the shared X-scale row and anything above it is discarded. It is
        the same idea (&ldquo;skip the preamble&rdquo;), applied to the layout
        you have chosen.
    </div>

    <div class="note">
        <b>Independent per Excel sheet.</b> When <b>Import several sheets</b> is
        ticked, each sheet remembers its own Header Row choice — pick
        <b>Row 3</b> for a sheet with a banner above its table, <b>No header</b>
        for a sheet with none, click to another sheet, and clicking back
        restores exactly what that sheet had. A sheet you have not clicked into
        yet starts from whatever the previously-configured sheet was showing
        (the same convenience the Import Profile / Apply to All Other Files
        features use — most sheets in one workbook tend to share a layout) —
        it is not silently reset to Auto, so if a particular sheet's layout is
        genuinely different, click it and set its Header Row (and any other
        setting) explicitly.
    </div>

    <h3>Header Threshold  <small>(only used when Header row = Auto)</small></h3>
    <p>
        Controls how the <b>Auto</b> header decision is made. The candidate
        header line is split into tokens; if at least this percentage of
        tokens fail to parse as a number, the line is classified as a
        header. Default: <b>50%</b>.
    </p>
    <div class="info">
        <b>Example:</b> a line with 14 tokens where only 2 are non-numeric
        text (18%) will <em>not</em> be classified as a header at the
        default 50% threshold — it's treated as data instead. Lowering the
        threshold to, say, 15% would flip that decision.
    </div>
    <p>
        Lower it if a genuine header is being missed because a few of its
        tokens happen to look numeric (e.g. a header cell that's just a
        number, or a mostly-text row with one stray numeric-looking value).
        Raise it if an ordinary data line is being mistaken for a header
        because it happens to contain a few text values (e.g. a units row,
        or a data row with an occasional text flag).
    </p>
    <p>
        This threshold applies everywhere a header/label line is
        auto-detected — Standard, Interlaced, and Row-oriented layouts all
        use it consistently.
    </p>

    <h3>Layout</h3>
    <p>
        Choose which of the three layouts described above matches your file:
    </p>
    <table>
        <tr><th>Option</th><th>Behaviour</th></tr>
        <tr><td><b>Standard</b></td>
            <td>First column is a single shared X-scale; every other column
                is a spectrum.</td></tr>
        <tr><td><b>Interlaced</b></td>
            <td>Columns alternate x, y, x, y &hellip; — each spectrum has its
                own X-scale column. In the preview, X-columns are highlighted
                in <b style="color:#006699;">cyan</b> and Y-columns in white
                so you can immediately verify the pairing is correct.</td></tr>
        <tr><td><b>Row-oriented</b></td>
            <td>First row is a single shared X-scale; every other row is a
                spectrum. In the preview, the cyan highlighting moves to the
                first row instead of the first column.</td></tr>
    </table>
    <p>
        Only one layout can be active at a time — Interlaced and Row-oriented
        are mutually exclusive.
    </p>

    <h3>Label Column  <small>(Row-oriented only)</small></h3>
    <p>
        By default, Row-oriented layout uses the <b>first column</b> of the
        raw file as the source of spectrum labels — the row-oriented mirror
        of the header row in Standard layout. If your file has several
        metadata columns before or alongside the actual spectral data (an
        ID number, a sample type, a name, a timestamp, &hellip;), the field
        you actually want as the label might not be that first column.
    </p>
    <p>
        Use <b>Label column</b> to pick a different column instead. The
        dropdown lists every column detected in the currently-previewed
        file, shown as <code>Column N: &lt;first value&gt;</code> — the
        index is included so that columns with duplicate or missing names
        (for example two columns both literally called
        <code>Temperature</code>) can still be selected unambiguously.
    </p>
    <div class="warning">
        <b>Note:</b> Like Layout, Label Column is a per-file setting — it
        resets to <b>Auto (first column)</b> after every import.
    </div>

    <h3>X-scale Column  <small>(Standard layout only)</small></h3>
    <p>
        By default, Standard layout uses the <b>first column</b> of the
        file as the shared X-scale. If your file has metadata columns
        (an ID number, a sample type, a timestamp, &hellip;) before the
        real X-scale column, that first column won't be numeric and the
        import will misread it as X — every value garbled or treated as
        invalid.
    </p>
    <p>
        Use <b>X-scale column</b> to point at the real one instead. Same
        dropdown format as Label Column: <code>Column N: &lt;first
        value&gt;</code>. In the preview, the cyan highlighting moves to
        whichever column you pick, so you can confirm it's the right one
        before importing.
    </p>
    <div class="warning">
        <b>Note:</b> Standard layout only distinguishes "the X-scale column"
        from "everything else is a spectrum" — on its own, it has no
        concept of a metadata column that should be ignored entirely. If
        you redirect X-scale to a column other than column 0, whatever was
        originally in column 0 does not automatically disappear — it would
        become an extra, bogus spectrum, plotted against the new X-scale,
        <b>unless</b> you also list it under <b>Exclude columns</b> below.
    </div>
    <div class="warning">
        <b>Note:</b> Like Layout and Label Column, X-scale Column is a
        per-file setting — it resets to <b>Auto (first column)</b> after
        every import.
    </div>

    <h3>Exclude Columns  <small>(Standard layout only)</small></h3>
    <p>
        Tick any columns that are neither the X-scale nor a real spectrum
        — an ID number, sample type, timestamp, or any other metadata
        column your file happens to include. Excluded columns are removed
        from the data entirely before parsing, so unlike X-scale Column
        alone, they never turn into bogus spectra.
    </p>
    <p>
        Shown as a checklist, same <code>Column N: &lt;first value&gt;</code>
        format as the other column pickers, listing every column detected
        in the currently-previewed file.
    </p>
    <div class="note">
        <b>Columns with no header name are listed too</b>, as
        <code>Column N: (no name)</code>. A column that the header row doesn't
        name still holds real data and still needs to be selectable, so the
        column list is built from the widest row in the file rather than from
        the header row. (Previously such columns were missing from the list
        entirely — you could see them in the preview but had no way to exclude
        them.)
    </div>
    <p>
        When <b>X-scale column</b> is left on <b>Auto</b>, "Auto" means
        "the first column remaining after exclusion" — not literally
        column 0 if column 0 happens to be one of the excluded ones. So if
        your real X-scale is already the first non-excluded column, you
        often don't need to also set X-scale Column explicitly; excluding
        the metadata columns in front of it is enough.
    </p>
    <div class="warning">
        <b>Note:</b> A column cannot be both the X-scale column and
        excluded at the same time. If you tick a column that's also
        selected as X-scale Column, the detection summary line turns red
        with a warning, and the import itself will fail with a clear error
        if you proceed — pick a different X-scale column, or untick it
        from Exclude Columns.
    </div>
    <div class="warning">
        <b>Note:</b> Like Layout, Label Column, and X-scale Column,
        Exclude Columns is a per-file setting — it resets to nothing
        excluded after every import.
    </div>

    <h3 id="zero-padding">Zero Padding</h3>
    <p>
        Digit width used when spectra are numbered automatically.
        Default of 4 gives <code>0001</code>, <code>0002</code>, &hellip;
        Increase only if you import files with more than 9&nbsp;999 spectra.
        The Preview table's column headers update immediately when you
        change this, so you can confirm the numbering before importing.
    </p>
    <p>
        Unlike the rest of the settings on this page, Zero Padding also
        applies to <b>SPE</b> and <b>SPC</b> files — it stays visible even
        though every other text/Excel setting is hidden for those formats,
        and controls the digit width of a multi-frame SPE file's
        <code>0001</code>, <code>0002</code>, … frame numbering, or a
        multi-subfile SPC file's equivalent subfile numbering, the exact
        same way it does for text/Excel imports. Changing it live-updates
        the SPE/SPC preview and summary line just like it does elsewhere.
        It's the only general setting SPE/SPC share with text/Excel
        imports — see the SPE and SPC sections above.
    </p>
    <div class="info">
        <strong>The main spectra list sorts labels in "natural" (numeric-aware)
        order, not plain alphabetical order</strong> — embedded numbers compare
        as numbers, not character-by-character, so <code>spectrum 4</code>
        already sorts before <code>spectrum 39</code> and
        <code>spectrum 40</code> without any padding. You no longer need to
        pad numbers just to get a sensible sort order. Zero Padding here is
        now purely a readability/consistency choice — a fixed digit width
        keeps a long list of auto-numbered spectra visually tidy and
        equal-width — not something the sort order depends on. See
        <a href="help://user_guide#selection">User Guide &rarr; 2. Spectrum
        Selection</a> for how natural sort works, including the one edge case
        (a minus sign glued onto a preceding letter, e.g.
        <code>sample-1</code>, is read as a plain separator rather than a
        negative sign — see that section for the reasoning).
    </div>

    <h3>Analyze Rows</h3>
    <p>
        Number of rows examined during auto-detection of delimiter, decimal
        separator, and header. The default of 20 is sufficient for virtually
        all files. Increase only if your file has a long preamble before the
        data starts. The Preview table and the Detection Summary line below
        it re-read the file and re-detect immediately when you change this,
        so you can see exactly what a larger (or smaller) sample changes
        before importing — this also changes how many rows the Preview
        table shows, since it previews exactly the rows being analyzed.
    </p>

    <h2>The Preview Table</h2>
    <p>
        Shows rows from the currently previewed file — the same rows
        Analyze Rows examines (8 by default) — and updates instantly when
        any setting changes, including Zero Padding and Analyze Rows
        themselves.
    </p>
    <ul>
        <li><b style="color:#006699;">Cyan cells</b> — X-scale (a column in
            Standard/Interlaced layout, a row in Row-oriented layout)</li>
        <li><b>White cells</b> — Y-scale (intensity) values,
            one spectrum per column (or per row, in Row-oriented layout)</li>
        <li>Header labels show detected labels from the header row/column
            when present; when a header row exists but a particular
            column's cell is blank, that column's label instead shows the
            same zero-padded fallback number (<code>0002</code>,
            <code>0003</code>, &hellip;) the importer will actually assign,
            not just a raw column position — see Zero Padding above. With no
            header row at all, columns show generic <code>x</code>,
            <code>y1</code>, <code>y2</code>, &hellip; names (<code>x</code>
            / <code>y</code> pairs for interlaced).</li>
    </ul>

    <h2>Detection Summary Line</h2>
    <p>
        The line directly below the settings controls shows exactly what the
        importer will use — including the auto-detected values where
        <em>Auto</em> is selected. Check this line before clicking Import
        to confirm the settings are correct.
    </p>

    <h2>X-Axis Options</h2>

    <h3>Use row number (1, 2, 3, &hellip;) as the X axis</h3>
    <p>
        For tables that have <b>no meaningful numeric X axis at all</b> — a table
        of concentration profiles, say, whose only non-numeric column is a sample
        name (<code>temp_01</code>, <code>temp_02</code>, &hellip;).
    </p>
    <p>
        Excluding that name column does <i>not</i> solve the problem: the first
        remaining column would then be eaten as the X-scale, silently costing you
        a real data column. Tick this instead and a synthetic X axis
        (1, 2, 3, &hellip;) is used, so <b>every remaining column stays a
        spectrum</b>.
    </p>
    <div class="note">
        <b>Row-oriented layout:</b> the X-scale normally comes from the first data
        <i>row</i>. With this ticked there is no such row — <b>every row is a
        spectrum</b> and the X axis becomes the point number. Same idea, applied
        to the layout you chose.
    </div>
    <div class="note">
        Cannot be combined with an explicit <b>X-scale column</b> — there is no X
        column to pick — so that picker is greyed out while this is ticked.
    </div>

    <h3>Ascending X-axis — automatic, not a setting</h3>
    <p>
        Some files list their X values out of order. The data is perfectly valid —
        every <code>(x, y)</code> pair is intact — but a line plot drawn in file
        order zig-zags back and forth across the axis and looks like nonsense.
    </p>
    <p>
        This application always reorders a spectrum's points so X ascends,
        automatically, for every file and every layout — there is no checkbox for
        it because there's no case where you'd want it off. It is <b>purely
        cosmetic</b>: the same points, drawn left to right. No value is changed,
        added or removed, and each <code>y</code> stays with its own <code>x</code>.
        A spectrum that gets reordered this way is flagged internally
        (<code>x_axis_reordered</code> in its metadata) so the change is always
        traceable, even though nothing about the data itself changed.
    </p>

    <h2>Duplicate Spectrum Names</h2>
    <p>
        Spectra are identified by their label, so two spectra can never share
        one. If an import would produce a label that already exists — two files
        with the same name, two sheets with the same column headings, or the
        same file imported twice with <b>Add</b> — the new spectrum is stored
        under a numbered variant instead (<code>My spectrum (2)</code>), and the
        original is left untouched. Nothing is ever silently overwritten or
        lost; the substitution is also recorded in the application log.
    </p>

    <h2>Session Memory  <small>(carries over to your NEXT time opening Import)</small></h2>
    <p>
        This is separate from the "starting point for the next file" carry-
        forward described above, which only applies <em>within</em> one
        multi-file batch. Session Memory is about what the dialog opens
        with the <em>next time</em> you use Import — for a completely new
        batch of files, possibly much later.
    </p>
    <p>
        The delimiter, decimal separator, and <b>Header threshold</b> are
        remembered as defaults for the rest of the session, based on
        whatever the <em>last file</em> in your most recent import batch
        was left showing when you clicked Import. However, if you leave
        delimiter/decimal on <b>Auto</b>, each file is always auto-detected
        independently — session memory only applies when you have manually
        overridden a setting.
        The <b>Layout</b>, <b>Label column</b>, <b>X-scale column</b>, and
        <b>Exclude columns</b> choices are intentionally <em>not</em>
        remembered — all four reset to their defaults (Standard; Auto
        first column; Auto first column; nothing excluded) for every new
        file and every new import, to prevent accidentally applying
        Interlaced, Row-oriented, or a specific column choice to a file
        it was never intended for.
    </p>

    <div class="tip">
        <b>Tip — round-tripping with Save:</b> Files saved by this application
        using the <em>common x-scale</em> option (Text or Excel format) can
        always be re-imported without changing any settings. Files saved with
        <em>individual x-scales</em> use an interlaced layout and require
        <b>Layout: Interlaced</b> to be selected on re-import. Files saved
        with the <b>Rows</b> layout option require <b>Layout: Row-oriented</b>
        on re-import. The Save dialog shows a reminder when either applies —
        see <a href="help://save">Save Spectra help</a> for the full list of
        export options.
    </div>

    </body>
    </html>
    """
