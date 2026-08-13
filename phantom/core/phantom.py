#!/usr/bin/env python3
"""
phantom.py — La puerta.

Corre desde Node/phantom/core/:
    python phantom.py

Este es el UNICO archivo que toca sys.path.
Todo lo demas importa directamente.
"""
import sys
import os

# Agregar esta carpeta al path para que phantom_core, session, etc. sean importables
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from cli.main import main

if __name__ == "__main__":
    main()
