#!/bin/bash
# Removes all __pycache__ and .pytest_cache folders under this directory.
# Safe to run any time - Python regenerates __pycache__ automatically as needed.

find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +

echo "Done."
