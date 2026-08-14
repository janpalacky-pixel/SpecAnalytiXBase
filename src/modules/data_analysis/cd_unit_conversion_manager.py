# src/modules/data_analysis/cd_unit_conversion_manager.py
"""
Business logic for converting raw circular dichroism (CD) ellipticity —
millidegrees (mdeg), the typical raw output of a CD spectropolarimeter such
as the JASCO instruments this application's JWS importer reads — into the
standard concentration-independent quantities used to compare CD spectra
recorded at different concentrations or path lengths:

  * Molar ellipticity            [theta]        (deg . cm^2 . dmol^-1)
  * Differential molar extinction coefficient   Delta-epsilon  (M^-1.cm^-1)
  * Differential absorbance                     Delta-A        (dimensionless)

Both [theta] and Delta-epsilon additionally come in two CONCENTRATION
BASES — whole-molecule ("molecular"/per-strand) or "mean-residue"/
"mean-nucleotide" (per-residue) — the standard way of putting proteins,
peptides, or nucleic acids of DIFFERENT LENGTH on an equal footing for
comparison, obtained by dividing the whole-molecule value by N, the
number of residues/nucleotides in the molecule. This choice affects
[theta] and Delta-epsilon identically (see below) and has no meaning for
Delta-A, which never involves concentration at all.

All three are derived from a single fixed instrument constant, using the
MOLAR concentration c[M] directly — the same formula commonly used to
normalize DNA/RNA CD spectra once the concentration has been determined
from A260 absorbance:

    theta_obs(mdeg) = INSTRUMENT_CONSTANT * Delta-A
    Delta-epsilon (whole)   = theta_obs(mdeg) / (INSTRUMENT_CONSTANT * c[M] * l[cm])
    [theta] (whole)         = theta_obs(mdeg) / (10 * l[cm] * c[M])
                            = (INSTRUMENT_CONSTANT / 10) * Delta-epsilon (whole)
    Delta-epsilon (mean-residue) = Delta-epsilon (whole) / N
    [theta] (mean-residue)       = [theta] (whole) / N
        where N = number of residues/nucleotides in the molecule.

The N division applies identically to Delta-epsilon and [theta] because
[theta] = 3298 * Delta-epsilon is an identity that holds regardless of
which concentration basis (whole-molecule or per-residue) was used to
compute both sides — dividing c[M] by N to get a per-residue
concentration divides Delta-epsilon by N, which divides [theta] by N via
that same fixed 3298 factor. See src/help/cd_unit_conversion_help.py's
"Where does 32980 come from?" and "Independent definitions of Delta-A,
theta, and Delta-epsilon" sections for the full from-scratch derivation
and an open, no-login source confirming both the 32980/3298 constants and
the mean-residue identity explicitly.

Notably, NONE of these need a molecular weight at all once the
concentration is already known in a molar unit (M / mM / uM) — a
molecular weight only enters the picture as a way to convert a MASS
concentration (mg/mL) to a molar one, for users who don't already have a
molar concentration in hand. This matters because it's easy to
over-parametrize the classic mg/mL-based [theta] formula
([theta] = theta_obs * M / (10 * l * c[mg/mL])) into requiring both a
full molecular weight AND a separate mean-residue weight — but only their
RATIO (the number of residues) ever actually affects the result. Asking
for two absolute weights when only their ratio matters is both
unnecessary and confusing (two numbers to look up instead of one, with no
way to tell whether the app is using them correctly). This version asks
for the minimum information each output genuinely needs.

PER-SPECTRUM parameters: real CD experiments frequently vary path length,
concentration, and molecule identity from spectrum to spectrum within the
very same batch (a titration series, or several different samples each
measured once) — so path length, concentration, molecular weight, AND the
residue/nucleotide count (N, needed only for the mean-residue
concentration basis, for either [theta] or Delta-epsilon output) are all
tracked PER SPECTRUM here (self.per_spectrum, keyed by the spectrum's
stable identity — see spectrum_identity.spectrum_key), populated by the
dialog's Excel-like table (one row per selected spectrum). Concentration
unit and ellipticity convention are kept as single SHARED settings across
the whole batch — in practice these describe which measurement/analysis
convention is being used, not something that typically varies spectrum to
spectrum within one conversion run.

See src/help/cd_unit_conversion_help.py for the full derivation, worked
example, and literature references.
"""
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.spectrum_identity import spectrum_key

logger = get_logger(__name__)

# Fixed instrument constant relating raw millidegree ellipticity to
# differential absorbance: theta_obs(mdeg) = INSTRUMENT_CONSTANT * Delta-A.
# The commonly cited literature value is ~32980 (sometimes given more
# precisely as 32982). 32980 is used here so that
# INSTRUMENT_CONSTANT / 10 == 3298 exactly, matching the standard
# [theta] = 3298 * Delta-epsilon relation and keeping all three output
# quantities below perfectly self-consistent with each other for the
# same input — using two slightly different published constants for two
# of the three outputs would otherwise make them disagree by a fraction
# of a percent for no physical reason.
INSTRUMENT_CONSTANT = 32980.0

# Conversion factors from each supported molar concentration unit to mol/L.
CONCENTRATION_UNIT_TO_MOLAR = {
    'M': 1.0,
    'mM': 1e-3,
    'µM': 1e-6,
}


class CDUnitConversionManager:
    """Business logic for converting CD spectra from raw millidegrees to
    molar/mean-residue ellipticity, differential molar extinction
    coefficient (Delta-epsilon), or differential absorbance (Delta-A).

    Path length, concentration, molecular weight, and residue/nucleotide
    count (N) are all tracked per spectrum (self.per_spectrum);
    concentration unit and ellipticity convention are shared across the
    whole batch. See the module docstring for the full reasoning.
    """

    OUTPUT_MOLAR_ELLIPTICITY = 'molar_ellipticity'
    OUTPUT_DELTA_EPSILON = 'delta_epsilon'
    OUTPUT_DELTA_A = 'delta_a'

    OUTPUT_CHOICES = (OUTPUT_MOLAR_ELLIPTICITY, OUTPUT_DELTA_EPSILON, OUTPUT_DELTA_A)

    # Human-readable (display name, unit string) for each output type.
    OUTPUT_LABELS = {
        OUTPUT_MOLAR_ELLIPTICITY: ('Molar / mean-residue ellipticity [θ]', 'deg·cm²·dmol⁻¹'),
        OUTPUT_DELTA_EPSILON: ('Differential molar extinction coefficient Δε', 'M⁻¹·cm⁻¹'),
        OUTPUT_DELTA_A: ('Differential absorbance ΔA', '(dimensionless)'),
    }

    CONVENTION_MOLECULAR = 'molecular'
    CONVENTION_MEAN_RESIDUE = 'mean_residue'

    CONCENTRATION_UNITS = ('M', 'mM', 'µM', 'mg/mL')

    def __init__(self):
        # Shared across the whole batch — see module docstring.
        self.concentration_unit = 'µM'      # one of CONCENTRATION_UNITS
        self.ellipticity_convention = self.CONVENTION_MOLECULAR
        self.output_type = self.OUTPUT_MOLAR_ELLIPTICITY

        # Per spectrum — keyed by spectrum_key(spectrum) (stable identity:
        # metadata['unique_id'], falling back to label). Each value is a
        # dict: {'path_length_cm': float, 'concentration_value': float,
        # 'molecular_weight': float, 'num_residues': float}.
        # molecular_weight (g/mol == Da) is only used, and only required,
        # when concentration_unit is 'mg/mL' — see _concentration_molar.
        # num_residues (N) — the number of residues (protein/peptide) or
        # nucleotides (nucleic acid) in that spectrum's molecule — is only
        # used, and only required, for mean-residue ellipticity.
        self.per_spectrum: dict = {}

    def update_settings(self, settings):
        """Update parameters from a settings dict. Unknown/absent keys are
        left unchanged, matching every other manager's update_settings."""
        if 'concentration_unit' in settings:
            self.concentration_unit = settings['concentration_unit']
        if 'ellipticity_convention' in settings:
            self.ellipticity_convention = settings['ellipticity_convention']
        if 'output_type' in settings:
            self.output_type = settings['output_type']
        if 'per_spectrum' in settings:
            self.per_spectrum = dict(settings['per_spectrum'])

    # ------------------------------------------------------------------
    # Concentration helper — everything downstream works from the MOLAR
    # concentration of the whole species. A molecular weight is consulted
    # only in the one case where it's unavoidable: the input concentration
    # was given as a mass concentration (mg/mL) rather than already molar.
    # ------------------------------------------------------------------
    def _concentration_molar(self, params):
        """Return concentration in mol/L for one spectrum's *params* dict
        (as stored in self.per_spectrum)."""
        conc_value = params.get('concentration_value', 0.0)
        if self.concentration_unit != 'mg/mL':
            molar_factor = CONCENTRATION_UNIT_TO_MOLAR.get(self.concentration_unit)
            if molar_factor is None:
                raise ValueError(f"Unknown concentration unit: {self.concentration_unit!r}")
            return conc_value * molar_factor
        molecular_weight = params.get('molecular_weight', 0.0)
        if molecular_weight <= 0:
            raise ValueError(
                "a molecular weight (> 0, in g/mol) is required to convert "
                "a mg/mL concentration to a molar concentration"
            )
        return conc_value / molecular_weight   # (g/L) / (g/mol) = mol/L

    def params_for(self, spectrum):
        """Return the stored per-spectrum params dict for *spectrum*, or
        None if nothing has been entered for it yet."""
        return self.per_spectrum.get(spectrum_key(spectrum))

    def validate_parameters(self, spectra):
        """Raise ValueError with a clear, actionable message if the
        current settings are insufficient for the selected output type,
        for ANY of *spectra*. Called once up front by the controller,
        before touching any spectrum, so a whole batch fails (or
        succeeds) identically and predictably instead of a confusing
        per-spectrum exception deep in a processing loop. Every problem
        found is reported together (not just the first one), so the user
        can fix everything in one pass instead of one error at a time."""
        needs_conc = self.output_type != self.OUTPUT_DELTA_A
        # The mean-residue/mean-nucleotide concentration basis applies to
        # BOTH [theta] and Delta-epsilon (not just [theta]) — see the
        # module docstring for why the N division is identical for both.
        # It's meaningless for Delta-A, which never uses concentration.
        needs_residues = needs_conc and self.ellipticity_convention == self.CONVENTION_MEAN_RESIDUE
        missing, invalid = [], []
        for spectrum in spectra:
            label = spectrum.get('label', '?')
            params = self.params_for(spectrum)
            if params is None:
                missing.append(label)
                continue
            if not needs_conc:
                continue
            if params.get('path_length_cm', 0.0) <= 0:
                invalid.append(f"'{label}': path length must be greater than zero")
                continue
            if params.get('concentration_value', 0.0) <= 0:
                invalid.append(f"'{label}': concentration must be greater than zero")
                continue
            try:
                self._concentration_molar(params)
            except ValueError as exc:
                invalid.append(f"'{label}': {exc}")
                continue
            if needs_residues and params.get('num_residues', 0.0) <= 0:
                invalid.append(
                    f"'{label}': number of residues/nucleotides must be greater than "
                    "zero for the mean-residue/mean-nucleotide concentration basis"
                )

        if missing:
            names = ', '.join(missing)
            raise ValueError(
                f"No sample parameters entered for: {names}.\n"
                "Fill in every row of the table before converting."
            )
        if invalid:
            raise ValueError("Invalid sample parameters:\n" + "\n".join(invalid))

    # ------------------------------------------------------------------
    # Core conversion
    # ------------------------------------------------------------------
    def convert_y_scale(self, y_scale, params):
        """Convert a raw mdeg y_scale array to the currently selected
        output_type, using one spectrum's own *params* dict (path length,
        concentration, molecular weight). Assumes y_scale is already in
        millidegrees (the raw instrument unit produced by the CD channel
        of this application's importers, e.g. JWS)."""
        y_scale = np.asarray(y_scale, dtype=float)
        if self.output_type == self.OUTPUT_DELTA_A:
            return y_scale / INSTRUMENT_CONSTANT

        c_molar = self._concentration_molar(params)
        path_length_cm = params.get('path_length_cm', 0.0)

        # The mean-residue/mean-nucleotide concentration basis (dividing
        # by N) applies identically to Delta-epsilon and [theta] — see
        # the module docstring for the derivation of why this is exact,
        # not an approximation, for both.
        use_mean_residue = self.ellipticity_convention == self.CONVENTION_MEAN_RESIDUE

        if self.output_type == self.OUTPUT_DELTA_EPSILON:
            delta_epsilon_whole = y_scale / (INSTRUMENT_CONSTANT * c_molar * path_length_cm)
            if use_mean_residue:
                return delta_epsilon_whole / params.get('num_residues', 0.0)
            return delta_epsilon_whole
        elif self.output_type == self.OUTPUT_MOLAR_ELLIPTICITY:
            theta_whole_molecule = y_scale / (10.0 * path_length_cm * c_molar)
            if use_mean_residue:
                return theta_whole_molecule / params.get('num_residues', 0.0)
            return theta_whole_molecule
        else:
            raise ValueError(f"Unknown output type: {self.output_type!r}")

    def convert_spectra(self, spectra, settings=None, progress_callback=None):
        """Convert a list of spectrum dicts. Returns a new list — inputs
        are never mutated. Each spectrum is converted using its OWN path
        length / concentration / molecular weight from self.per_spectrum
        (see class/module docstring); concentration unit, ellipticity
        convention, and output type are shared across the whole batch.

        progress_callback: optional callable, invoked every 50 spectra —
        same hook/contract as every other manager in this codebase (see
        progress_utils.notify_progress). None (the default) — no change.

        Raises ValueError (via validate_parameters) if the current
        settings can't produce the selected output — callers should
        catch this and show it to the user rather than letting it
        propagate as a raw traceback.
        """
        if settings:
            self.update_settings(settings)
        self.validate_parameters(spectra)

        name, unit = self.OUTPUT_LABELS[self.output_type]

        converted_spectra = []
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            converted = spectrum.copy()
            y_scale = spectrum.get('y_scale', [])

            if len(y_scale) == 0:
                converted_spectra.append(converted)
                continue

            params = self.params_for(spectrum) or {}

            converted['y_scale'] = self.convert_y_scale(y_scale, params)

            info = {
                'output_type': self.output_type,
                'output_name': name,
                'output_unit': unit,
                'concentration_unit': self.concentration_unit,
            }
            if self.output_type != self.OUTPUT_DELTA_A:
                info['path_length_cm'] = params.get('path_length_cm')
                info['concentration_value'] = params.get('concentration_value')
                if self.concentration_unit == 'mg/mL' and params.get('molecular_weight', 0.0) > 0:
                    info['molecular_weight'] = params['molecular_weight']
                # The concentration basis (molecular vs. mean-residue)
                # applies to Delta-epsilon exactly as it does to [theta] —
                # see the module docstring — so it's recorded for both,
                # not just [theta].
                if self.output_type in (self.OUTPUT_MOLAR_ELLIPTICITY, self.OUTPUT_DELTA_EPSILON):
                    info['ellipticity_convention'] = self.ellipticity_convention
                    if self.ellipticity_convention == self.CONVENTION_MEAN_RESIDUE:
                        info['num_residues'] = params.get('num_residues')
            converted['cd_conversion_info'] = info

            # converted = spectrum.copy() above is a SHALLOW copy —
            # converted['metadata'] would still be the exact same dict
            # object as the source spectrum's metadata unless replaced
            # here, which would silently mutate the original too (same
            # bug pattern fixed in NormalizationManager and
            # SavitzkyGolayManager).
            converted['metadata'] = dict(converted.get('metadata') or {})
            converted['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'CD Unit Conversion', info
            )

            converted_spectra.append(converted)

        return converted_spectra
