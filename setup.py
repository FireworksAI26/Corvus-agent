"""Compatibility shim.

Configuration lives in pyproject.toml; modern pip/setuptools build from there.
This shim exists so legacy toolchains (very old pip, or `pip install -e .
--no-build-isolation`, or a direct `python setup.py develop`) can still install
the flat-layout modules and the `corvus` console script.
"""
from setuptools import setup

setup()
