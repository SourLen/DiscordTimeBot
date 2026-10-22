#!/usr/bin/env python3
"""Convenience launcher: ``python main.py`` is the same as ``python -m timebot``."""

from timebot.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
