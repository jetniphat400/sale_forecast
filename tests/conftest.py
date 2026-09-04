"""Pytest configuration shared by every test module.

Adds src/ to sys.path so tests can import project modules the same way the
scripts in src/ import each other (sys.path.insert(0, os.path.dirname(__file__))),
without needing the project installed as a package.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
