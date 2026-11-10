# src/modules/utils/spectra_order.py
"""How the spectra list is sorted (Qt-free): by name, in the order added,
by a property (temperature, pH, ...), by a number in the name - `sort` - or
in your own order - `apply` (below). "reverse" turns any of them upside down.

Your own order of the spectra in the list:

Without it the list is sorted by name (MainController.order_spectra). Once a
spectrum is dragged (or moved with Alt+Up / Alt+Down, or right-click › Order)
the list keeps the order you made: `custom` is the list of the spectra's
permanent ids (metadata['unique_id'], see spectrum_identity.py) in that
order. It is kept as if "reverse sorting" were off; the box only shows it
upside down. New spectra (an import that adds spectra, Combine, copies, ...)
go to the end of the list as you see it; processed spectra keep their place
(they keep their id). Ids of deleted spectra stay in `custom`, so an Undo puts
them back where they were. Saved in snapshots ('custom_order')."""


def apply(spectra, custom, reverse, key, name_key):
    """The spectra in your order -> (ordered list, custom order with the new
    spectra added). `key(spectrum)` its id, `name_key(spectrum)` the sort
    key by name (for several new spectra at once)."""
    place = {k: i for i, k in enumerate(custom)}
    known = [s for s in spectra if key(s) in place]
    new = sorted((s for s in spectra if key(s) not in place), key=name_key)
    known.sort(key=lambda s: place[key(s)])
    new_ids = [key(s) for s in new]
    if new_ids:
        # the end of the list as you see it: with reverse sorting its start
        custom = (list(reversed(new_ids)) + list(custom)) if reverse else (list(custom) + new_ids)
    ordered = known + new
    if reverse:
        ordered = list(reversed(known)) + new
    return ordered, custom


def from_visible(visible, reverse, old=None):
    """The custom order from the list as you see it (top to bottom). Ids in
    `old` that are not in the list (deleted spectra) keep their place: each
    goes right after the spectrum that was before it."""
    order = list(reversed(visible)) if reverse else list(visible)
    if not old:
        return order
    shown = set(order)
    after, last, seen = {}, None, set()
    for k in old:
        if k in shown:
            last = k
        elif k not in seen:
            after.setdefault(last, []).append(k)
            seen.add(k)
    out = list(after.get(None, []))
    for k in order:
        out.append(k)
        out.extend(after.get(k, []))
    return out


def move_to(visible, moving, row):
    """`visible` ids top to bottom; the ids in `moving` (in their order in
    the list) put before the row `row` of the list (row = len: at the end)."""
    moving = set(moving)
    row = max(0, min(int(row), len(visible)))
    picked = [k for k in visible if k in moving]
    rest = [k for k in visible if k not in moving]
    before = sum(1 for k in visible[:row] if k not in moving)
    return rest[:before] + picked + rest[before:]


def step(visible, moving, up=True):
    """Each spectrum in `moving` one place up (or down), past the next one
    that is not moved; a block of neighbours moves together; nothing moves
    past the top or the bottom."""
    moving = set(moving)
    out = list(visible)
    rng = range(1, len(out)) if up else range(len(out) - 2, -1, -1)
    for i in rng:
        j = i - 1 if up else i + 1
        if out[i] in moving and out[j] not in moving:
            out[i], out[j] = out[j], out[i]
    return out


# ---------------------------------------------------------------- the ways of sorting
# mode: {'by': 'name'} | {'by': 'added'} | {'by': 'property', 'key': 'temperature_C'} |
#       {'by': 'number', 'number': -1 (the last), 0 (the first), 1, ...} | {'by': 'own'}
BY = ('name', 'added', 'property', 'number', 'own')


def normalized(mode):
    m = dict(mode or {})
    by = m.get('by') if m.get('by') in BY else 'name'
    out = {'by': by}
    if by == 'property':
        out['key'] = str(m.get('key') or '')
    if by == 'number':
        try:
            out['number'] = int(m.get('number', -1))
        except (TypeError, ValueError):
            out['number'] = -1
    return out


def describe(mode, short=False):
    """The way of sorting in words: 'by name', 'by temperature_C', ..."""
    m = normalized(mode)
    by = m['by']
    if by == 'name':
        return "name" if short else "by name"
    if by == 'added':
        return "order added" if short else "in the order added"
    if by == 'property':
        return m['key'] if short else f"by {m['key']}"
    if by == 'number':
        from src.modules.visualization.color_by_value import _ordinal
        n = m['number']
        word = "last" if n < 0 else _ordinal(n)
        return f"{word} number" if short else f"by the {word} number in the name"
    return "own order" if short else "your own order"


def value(spectrum, mode, added=None, key=None):
    """The value a spectrum is sorted by (None: it has none)."""
    m = normalized(mode)
    if m['by'] == 'added':
        return (added or {}).get(key(spectrum)) if key else None
    from src.modules.visualization import color_by_value as cbv
    if m['by'] == 'property':
        return cbv.value_of(spectrum, 0, {'mode': 'metadata', 'metadata_key': m['key']})
    if m['by'] == 'number':
        return cbv.value_of(spectrum, 0, {'mode': 'name', 'number': m['number']})
    return None


def sort(spectra, mode, reverse, name_key, key=None, added=None):
    """The spectra sorted by `mode` (not 'own': see apply). Spectra without
    a value (e.g. no temperature) always go to the end, by name; equal
    values: by name."""
    m = normalized(mode)
    if m['by'] in ('name', 'own'):
        return sorted(spectra, key=name_key, reverse=reverse)
    have, missing = [], []
    for s in spectra:
        v = value(s, m, added, key)
        (missing if v is None else have).append((v, s))
    have.sort(key=lambda t: (t[0], name_key(t[1])), reverse=reverse)
    missing.sort(key=lambda t: name_key(t[1]))
    return [s for _, s in have] + [s for _, s in missing]
