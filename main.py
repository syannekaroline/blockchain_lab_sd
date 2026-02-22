#!/usr/bin/env python3
"""Ponto de entrada do projeto LSD Blockchain."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from lsdchain.cli.app import run


if __name__ == "__main__":
    run()
