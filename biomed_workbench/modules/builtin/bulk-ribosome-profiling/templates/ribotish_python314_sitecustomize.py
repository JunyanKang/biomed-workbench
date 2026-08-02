"""Restore the POSIX fork start method expected by Ribo-TISH 0.2.7.

Python 3.14 changed the POSIX multiprocessing default from ``fork`` to
``forkserver``. Ribo-TISH 0.2.7 initializes genome state in the parent process
and its prediction workers expect that state to be inherited. Restrict this
compatibility shim to the pinned Ribo-TISH processes in nf-core/riboseq 1.2.0.
"""

from __future__ import annotations

import multiprocessing


try:
    multiprocessing.set_start_method("fork")
except RuntimeError:
    # A caller may have selected the method explicitly before sitecustomize
    # finished importing. In that case, retaining the explicit choice is safer.
    pass
