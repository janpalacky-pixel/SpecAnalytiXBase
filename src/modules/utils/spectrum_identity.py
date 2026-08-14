# src/modules/utils/spectrum_identity.py
#
# One shared definition of "what identifies a spectrum", for anything
# that needs to track a specific spectrum across more than one moment in
# time — a dialog reopening, a rename, a list-widget rebuild, a save/load
# cycle.
#
# Why this exists (see developer_guide_help.py's "Golden Rule: Spectrum
# Identity" section for the full history): a spectrum's 'label' is a
# display string the user can change at any time — it is NEVER a stable
# identity. metadata['unique_id'] is assigned once at import and never
# changes; it's the only safe key. Many Managers across this codebase
# already define their own local, identical copy of this exact function
# (typically named _key_for) — this module exists so that logic doesn't
# need to be reimplemented, correctly or otherwise, in a new file every
# time. Existing correct local copies were intentionally left as-is when
# this was introduced (touching dozens of already-working files for a
# pure style change carries real regression risk for zero behaviour
# change) — this is for new code, and any file being edited anyway that
# already needs this exact logic.

from typing import Optional


def spectrum_key(spectrum: dict) -> str:
    """
    Return the stable identity key for *spectrum* — its
    metadata['unique_id'] if present, else its label as a last-resort
    fallback (only relevant for spectra that somehow reached this point
    without going through the normal import path, which always assigns
    a unique_id — see SpectrumManager._store_spectrum_dict and
    Spectrum.__post_init__).
    """
    metadata = spectrum.get('metadata') or {}
    return metadata.get('unique_id') or spectrum['label']


def spectrum_id(spectrum: dict) -> Optional[str]:
    """
    Return spectrum's metadata['unique_id'], or None if it genuinely
    doesn't have one. Unlike spectrum_key(), this never falls back to
    the label — use this when a caller specifically needs to know
    whether a real permanent id exists (e.g. deciding whether a
    QListWidgetItem's stored id can be trusted), and use spectrum_key()
    when a fallback-to-label default is actually fine.
    """
    metadata = spectrum.get('metadata') or {}
    return metadata.get('unique_id')
