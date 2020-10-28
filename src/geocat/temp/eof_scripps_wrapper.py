import numpy as np
import xarray as xr
from dask.array.core import map_blocks
import time

from geocat.temp.fortran import (deof11)
from .missing_values import (fort2py_msg, py2fort_msg)

# Dask Wrappers _<funcname>()
# These Wrapper are executed within dask processes, and should do anything that
# can benefit from parallel excution.

def _eof11(d, nmodes, icovcor, msg_py):
    #''' eigenvalues,eigenvectors,variance,princomp = deof11(d,nmodes,[icovcor,dmsg])
    # missing value handling
    d, msg_py, msg_fort = py2fort_msg(d, msg_py=msg_py)
    # fortran call
    eigenvalues, eigenvectors, variance, princomp = deof11(d,nmodes,[icovcor,msg_fort])
    return eigenvalues, eigenvectors, variance, princomp

def eof11(d, nmodes, icovcor=0, msg_py=np.nan):
    # this is effectivly a stub, since this is not a parallelizable task.
    return _eof11(d, nmodes, icovcor, msg_py)

def eof_test():
    d = np.random.random((1000,10000))
    nmodes = 10
    print(eof11(d, nmodes))

start = time.time()
eof_test()
end = time.time()
print(end-start)