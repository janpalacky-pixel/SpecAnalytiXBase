# src/views/table_sorting.py
"""Writing into a table that can be sorted by a click on a heading.

While such a table is sorted by a column (a heading was clicked), Qt sorts
it again after EVERY changed cell of that column - so a loop that writes
row by row (paste, delete, fill down, add a prefix, number them, ...) has
the rows moving under it: values land in the wrong rows and some selected
cells are never reached. Every such loop runs inside

    with sorting_paused(table):
        ...

and the table is sorted once, at the end. (A table filled right after it
was made - no heading clicked yet - is not affected; one that can be
refilled after a click must pause too.)"""

from contextlib import contextmanager


@contextmanager
def sorting_paused(table):
    """Sorting off while the block writes; on again (and sorted once) after."""
    was_on = table.isSortingEnabled()
    table.setSortingEnabled(False)
    try:
        yield table
    finally:
        table.setSortingEnabled(was_on)
