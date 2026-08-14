# src/modules/data_analysis/xaxis_unit_conversion_manager.py
"""
Business logic for converting a spectrum's X-AXIS between the standard
units used across UV-Vis, CD/ECD, and general optical spectroscopy:

  * Wavelength    nm      (nanometres)
  * Wavenumber    cm^-1   (reciprocal centimetres)
  * Energy        eV      (electron-volts)
  * Frequency     Hz      (hertz)

All four are related to wavelength by a simple reciprocal relationship,
using nanometres as the hub unit so only 2*N (not N^2) conversion
functions are needed for N units:

    wavenumber (cm^-1) = 1e7 / wavelength(nm)          [cm = 1e7 nm]
    energy (eV)         = (h*c/e) / wavelength(nm)      [h*c/e in eV*nm]
    frequency (Hz)       = c / wavelength(nm)             [c in nm/s]

and each relation is its own inverse (wavelength(nm) = 1e7 / wavenumber,
etc.) — the SAME reciprocal constant appears on both sides, so one
generic "value <-> nm" pair of helper functions (see _to_nm / _from_nm)
handles the full N-unit conversion table, going through nm as an
intermediate step even when neither the source nor destination is nm
itself (e.g. cm^-1 -> eV goes cm^-1 -> nm -> eV).

The physical constants used are built from the SI's exactly-defined
values (2019 redefinition: h, c, and e are all exact by definition, not
measured) — see PLANCK_TIMES_LIGHTSPEED_OVER_CHARGE and LIGHTSPEED_NM_PER_S
below for the derivation. This means the eV and Hz conversions here are
exact to floating-point precision, not approximations.

WHAT THIS DOES NOT DO: convert Raman shift (cm^-1 relative to an
excitation laser) to/from absolute wavelength. That conversion needs the
excitation laser's wavelength as an extra input, AND is only as good as
the accuracy of the spectrometer's own wavelength axis — this operation
has no way to verify or calibrate that (true wavelength calibration
against a reference source, e.g. a neon lamp or silicon standard, is a
metrology procedure this software does not perform). Deliberately left
out of this operation's scope for that reason; see
src/help/xaxis_unit_conversion_help.py for the full explanation.

ASCENDING-X INVARIANT: wavelength, wavenumber, energy, and frequency are
all inversely related to each other (except identical units), so an
ascending wavelength axis becomes a DESCENDING axis in every other unit.
This application requires an ascending x-axis everywhere (see
spectrum_manager._sort_spectrum_by_x) — every downstream operation
(Savitzky-Golay, derivatives, FFT/denoising, baselines, peak indices,
np.interp, ...) assumes it. So this manager re-sorts each converted
spectrum's x/y pairs back to ascending order after the unit conversion,
exactly mirroring the same fix already applied once, centrally, at
import time.
"""
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress

logger = get_logger(__name__)

# ----------------------------------------------------------------------
# Physical constants — all derived from the SI's exactly-defined values
# (2019 redefinition of the SI base units: h, c, and e have no
# measurement uncertainty, they are exact by definition).
#
#   h (Planck constant)      = 6.62607015e-34   J*s   (exact)
#   c (speed of light)       = 299792458          m/s   (exact)
#   e (elementary charge)    = 1.602176634e-19   C     (exact)
#
# Energy of a photon: E(J) = h*c / wavelength(m).
# Converting to eV (divide by e) and nm (multiply wavelength by 1e9):
#   E(eV) = (h*c/e) [J*m/C -> eV*m] * 1e9 [m->nm] / wavelength(nm)
#         = 1239.8419843320025 / wavelength(nm)
# This is the standard, widely tabulated "1239.84 eV*nm" constant.
PLANCK_TIMES_LIGHTSPEED_OVER_CHARGE_EV_NM = 1239.8419843320025

# Frequency: f(Hz) = c(m/s) / wavelength(m) = c(nm/s) / wavelength(nm).
LIGHTSPEED_NM_PER_S = 299792458e9   # 2.99792458e17 nm/s

UNIT_WAVELENGTH = 'nm'
UNIT_WAVENUMBER = 'cm-1'
UNIT_ENERGY = 'eV'
UNIT_FREQUENCY = 'Hz'

UNIT_CHOICES = (UNIT_WAVELENGTH, UNIT_WAVENUMBER, UNIT_ENERGY, UNIT_FREQUENCY)

UNIT_LABELS = {
    UNIT_WAVELENGTH: 'Wavelength (nm)',
    UNIT_WAVENUMBER: 'Wavenumber (cm⁻¹)',
    UNIT_ENERGY: 'Energy (eV)',
    UNIT_FREQUENCY: 'Frequency (Hz)',
}

# Short unit symbol only (no name) — used where UNIT_LABELS' full
# "Name (symbol)" form would be too long, e.g. table column headers that
# need to show the symbol next to a numeric range.
UNIT_SHORT = {
    UNIT_WAVELENGTH: 'nm',
    UNIT_WAVENUMBER: 'cm⁻¹',
    UNIT_ENERGY: 'eV',
    UNIT_FREQUENCY: 'Hz',
}

# Reciprocal constant k such that:  nm = k / unit_value   and   unit_value = k / nm
# (wavelength itself has no entry — it's the hub, handled as an identity
# case in _to_nm/_from_nm below, not a reciprocal relationship to itself).
_RECIPROCAL_CONSTANT = {
    UNIT_WAVENUMBER: 1.0e7,                                  # cm = 1e7 nm
    UNIT_ENERGY: PLANCK_TIMES_LIGHTSPEED_OVER_CHARGE_EV_NM,
    UNIT_FREQUENCY: LIGHTSPEED_NM_PER_S,
}


class XAxisUnitConversionManager:
    """Business logic for converting spectra's x-axis between wavelength
    (nm), wavenumber (cm^-1), energy (eV), and frequency (Hz).

    Unlike CD Unit Conversion, from_unit/to_unit are single settings
    shared across the whole batch — there is no per-spectrum parameter
    this conversion needs (it's pure physics, no concentration/path
    length/instrument constant involved), so there is no per-spectrum
    table in the dialog.
    """

    def __init__(self):
        self.from_unit = UNIT_WAVELENGTH
        self.to_unit = UNIT_WAVENUMBER

    def update_settings(self, settings):
        """Update parameters from a settings dict. Unknown/absent keys are
        left unchanged, matching every other manager's update_settings."""
        if 'from_unit' in settings:
            self.from_unit = settings['from_unit']
        if 'to_unit' in settings:
            self.to_unit = settings['to_unit']

    # ------------------------------------------------------------------
    # Unit conversion helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_nm(value, unit):
        """Convert an array of values FROM *unit* TO wavelength in nm."""
        if unit == UNIT_WAVELENGTH:
            return np.asarray(value, dtype=float)
        k = _RECIPROCAL_CONSTANT[unit]
        return k / np.asarray(value, dtype=float)

    @staticmethod
    def _from_nm(nm_value, unit):
        """Convert an array of wavelength (nm) values TO *unit*."""
        if unit == UNIT_WAVELENGTH:
            return np.asarray(nm_value, dtype=float)
        k = _RECIPROCAL_CONSTANT[unit]
        return k / np.asarray(nm_value, dtype=float)

    def convert_x_values(self, x_values, from_unit=None, to_unit=None):
        """Convert an array of x-axis values from *from_unit* to *to_unit*
        (defaults to self.from_unit/self.to_unit). Pure array transform —
        does NOT re-sort; see convert_x_scale for the sorted version used
        on actual spectra."""
        from_unit = from_unit or self.from_unit
        to_unit = to_unit or self.to_unit
        nm = self._to_nm(x_values, from_unit)
        return self._from_nm(nm, to_unit)

    def convert_x_scale(self, x_scale, y_scale, from_unit=None, to_unit=None):
        """Convert *x_scale* from from_unit to to_unit, and re-sort both
        x_scale and y_scale back to ascending x order (see module
        docstring — required since every reciprocal conversion here
        reverses the direction of an ascending axis, except when
        from_unit == to_unit).

        Returns (new_x, new_y, was_reordered: bool).
        """
        x_scale = np.asarray(x_scale, dtype=float)
        y_scale = np.asarray(y_scale, dtype=float)
        new_x = self.convert_x_values(x_scale, from_unit, to_unit)

        if len(new_x) < 2 or np.all(np.diff(new_x) >= 0):
            return new_x, y_scale, False

        order = np.argsort(new_x, kind='stable')
        return new_x[order], y_scale[order], True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate_parameters(self, spectra):
        """Raise ValueError with a clear, actionable message if any
        spectrum's x-axis contains a value <= 0 — every one of the four
        supported units (wavelength, wavenumber, energy, frequency) is a
        strictly positive physical quantity, and every conversion here
        involves a reciprocal (1/x) at some point, which is undefined at
        zero and meaningless (a sign flip) for negative values."""
        if self.from_unit == self.to_unit:
            return   # identity conversion — nothing to validate

        invalid = []
        for spectrum in spectra:
            label = spectrum.get('label', '?')
            x = np.asarray(spectrum.get('x_scale', []), dtype=float)
            if len(x) == 0:
                continue
            if np.any(x <= 0):
                n_bad = int(np.sum(x <= 0))
                invalid.append(
                    f"'{label}': {n_bad} x-axis value(s) are zero or negative — "
                    f"{UNIT_LABELS[self.from_unit]} must be a positive quantity "
                    "for this conversion."
                )
        if invalid:
            raise ValueError("Invalid x-axis values:\n" + "\n".join(invalid))

    # ------------------------------------------------------------------
    # Core conversion
    # ------------------------------------------------------------------
    def convert_spectra(self, spectra, settings=None, progress_callback=None):
        """Convert a list of spectrum dicts' x-axis. Returns a new list —
        inputs are never mutated.

        progress_callback: optional callable, invoked every 50 spectra —
        same hook/contract as every other manager in this codebase (see
        progress_utils.notify_progress). None (the default) — no change.

        Raises ValueError (via validate_parameters) if any spectrum's
        x-axis has a non-positive value — callers should catch this and
        show it to the user rather than letting it propagate as a raw
        traceback.
        """
        if settings:
            self.update_settings(settings)
        self.validate_parameters(spectra)

        converted_spectra = []
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            converted = spectrum.copy()
            x_scale = spectrum.get('x_scale', [])
            y_scale = spectrum.get('y_scale', [])

            if len(x_scale) == 0:
                converted_spectra.append(converted)
                continue

            new_x, new_y, was_reordered = self.convert_x_scale(x_scale, y_scale)
            converted['x_scale'] = new_x
            converted['y_scale'] = new_y

            info = {
                'from_unit': self.from_unit,
                'from_unit_label': UNIT_LABELS[self.from_unit],
                'to_unit': self.to_unit,
                'to_unit_label': UNIT_LABELS[self.to_unit],
                'x_axis_reordered': was_reordered,
            }
            converted['xaxis_unit_conversion_info'] = info

            # converted = spectrum.copy() above is a SHALLOW copy —
            # converted['metadata'] would still be the exact same dict
            # object as the source spectrum's metadata unless replaced
            # here, which would silently mutate the original too (same
            # fix already applied in every other manager in this app).
            converted['metadata'] = dict(converted.get('metadata') or {})
            converted['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'X-axis Unit Conversion', info
            )

            converted_spectra.append(converted)

        return converted_spectra
