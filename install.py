"""Citeline installer, run from the shipped product directory.

Run this file with the system Python, from this directory:

    python install.py [install location]
    python install.py uninstall [install location]

With no argument, the install location is the directory
named citeline beside this directory. Uninstall is the
word uninstall as the first argument, with the install
location as its optional second argument and the same
default. The output stands in the simple form only and
states the home path.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citeline.install import main

if __name__ == "__main__":
    raise SystemExit(main())
