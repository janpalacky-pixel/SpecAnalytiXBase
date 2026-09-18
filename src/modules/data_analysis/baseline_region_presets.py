# src/modules/data_analysis/baseline_region_presets.py
#
# Named region shortcuts for the Automated Baseline dialog's "Region
# Shortcuts" panel (see AutomatedBaselineDialog.create_control_panel).
#
# Each preset is purely a convenience autofill into the normal
# fitting-regions table (AutomatedBaselineDialog.fitting_ranges):
# checking its checkbox adds a row exactly as if you'd dragged that
# range on the plot yourself, and unchecking it (or deleting the row
# directly from the table) removes that same row. A preset carries no
# special exclusion behavior of its own — once added, its region
# follows Invert Regions exactly like a manually drawn one (with
# Invert checked, a preset range marks a region to fit WITHIN, not
# exclude). Multiple presets can be checked at once; their ranges are
# just added as separate rows (additive), same as adding several
# manual ranges.
#
# AutomatedBaselineManager.apply_correction() never sees this module —
# by the time settings reach it, a preset-added range is
# indistinguishable from a manually drawn one, both are just entries
# in params['fitting_ranges'].
#
# To add a new shortcut: add one entry to the right category below, or
# start a new category key. 'key' must be unique across every category
# combined — it is what synchronizes a checkbox with its table row.

REGION_PRESET_CATEGORIES = {
    "Raman": [
        {
            "key": "raman_water_oh_stretch",
            "short_label": "Water band",
            "label": "Water / O–H stretch (2800–3700 cm⁻¹)",
            "range": (2800.0, 3700.0),
            "tooltip": (
                "O-H/C-H stretch region that swamps aqueous or biological "
                "Raman spectra. Adds this range to the table below — "
                "it then follows Invert Regions like any other row."
            ),
        },
    ],
    # Ranges below are common candidates from general Raman literature,
    # not measured against any specific instrument here — check them
    # against your own excitation wavelength, substrate and sample prep
    # before relying on them, and adjust the 'range' tuple if needed.
    "Biological / Cell Imaging": [
        {
            "key": "bio_silent_region",
            "short_label": "Silent region",
            "label": "Silent region (1800–2600 cm⁻¹)",
            "range": (1800.0, 2600.0),
            "tooltip": (
                "Gap with essentially no native biomolecule Raman signal — "
                "commonly used as a clean zone for bioorthogonal/Raman-tag "
                "imaging or as a flat baseline reference in cells. Verify "
                "against your own setup."
            ),
        },
        {
            "key": "bio_glass_substrate_hump",
            "short_label": "Glass substrate",
            "label": "Glass/fused-silica substrate hump (400–550 cm⁻¹)",
            "range": (400.0, 550.0),
            "tooltip": (
                "Broad background band from a glass microscope slide or "
                "coverslip, common in cell-imaging setups. Verify against "
                "your own substrate."
            ),
        },
        {
            "key": "bio_caf2_substrate_peak",
            "short_label": "CaF₂ substrate",
            "label": "CaF₂ substrate peak (320–325 cm⁻¹)",
            "range": (320.0, 325.0),
            "tooltip": (
                "Narrow feature from calcium fluoride slides, a common "
                "low-fluorescence substrate choice for biological Raman. "
                "Verify against your own substrate."
            ),
        },
    ],
}


def find_preset(key):
    """Look up a preset dict by its key across every category. Returns
    None if no preset has that key (e.g. a stale key from a settings
    dict saved before a preset was renamed/removed)."""
    for presets in REGION_PRESET_CATEGORIES.values():
        for preset in presets:
            if preset["key"] == key:
                return preset
    return None
