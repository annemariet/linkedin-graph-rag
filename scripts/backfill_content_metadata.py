#!/usr/bin/env python3
"""Deprecated: use ``scripts/backfill_content_store.py`` (same CLI, expanded)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent / "backfill_content_store.py"
runpy.run_path(str(_HERE), run_name="__main__")
