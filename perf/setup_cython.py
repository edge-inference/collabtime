"""
Setup script for Cython compilation of hot paths.

Usage:
    python perf/setup_cython.py build_ext --inplace
"""

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

extensions = [
    Extension(
        "perf.astar_fast",
        ["perf/astar_fast.pyx"],
        include_dirs=[np.get_include()],
    ),
    Extension(
        "perf.cache_merge_fast",
        ["perf/cache_merge_fast.pyx"],
        include_dirs=[np.get_include()],
    ),
]

setup(
    name="warehouse_perf",
    ext_modules=cythonize(extensions, compiler_directives={
        'language_level': "3",
        'boundscheck': False,
        'wraparound': False,
        'cdivision': True,
    }),
)

