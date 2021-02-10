import numpy as np
import xarray as xr
import warnings
from dask.array.core import map_blocks

from .fortran import grid2triple as grid2triple_fort
from .fortran import (triple2grid1)

from .errors import (ChunkError, CoordinateError, DimensionError)
from .missing_values import (fort2py_msg, py2fort_msg)

# Dask Wrappers or Internal Wrappers _<funcname>()
# These Wrapper are executed within dask processes, and should do anything that
# can benefit from parallel excution.


def _grid_to_triple(x, y, z, msg_py):
    # Transpose z before Fortran function call
    z = np.transpose(z, axes=(1, 0))

    # Handle Python2Fortran missing value conversion
    z, msg_py, msg_fort = py2fort_msg(z, msg_py=msg_py)

    # Fortran call
    # num_elem is the total number of elements from beginning of each column in the array,
    # which are non missing-value
    out, num_elem = grid2triple_fort(x, y, z, msg_fort)

    # Transpose output to correct dimension order before returning it to outer wrapper
    # As well as get rid of indices corresponding to missing values
    out = np.asarray(out)
    out = np.transpose(out, axes=(1, 0))
    out = out[:, :num_elem]

    # Handle Fortran2Python missing value conversion back
    fort2py_msg(z, msg_fort=msg_fort, msg_py=msg_py)
    fort2py_msg(out, msg_fort=msg_fort, msg_py=msg_py)

    return out


def _triple_to_grid(data,
                    x_in,
                    y_in,
                    x_out,
                    y_out,
                    shape,
                    method=None,
                    distmx=None,
                    domain=None,
                    msg_py=None):

    # Handle Python2Fortran missing value conversion
    data, msg_py, msg_fort = py2fort_msg(data, msg_py=msg_py)

    # Fortran function call
    grid = triple2grid1(x_in,
                        y_in,
                        data,
                        x_out,
                        y_out,
                        zmsg=msg_fort,
                        domain=domain,
                        method=method,
                        distmx=distmx)

    # Reshape output to correct the dimensionality  before returning it to the outer wrapper
    grid = np.asarray(grid)
    grid = grid.reshape(shape)

    # Handle Fortran2Python missing value conversion back
    fort2py_msg(data, msg_fort=msg_fort, msg_py=msg_py)
    fort2py_msg(grid, msg_fort=msg_fort, msg_py=msg_py)

    print(grid)

    return grid


# TODO: Revisit for implementing this function after deprecating geocat.ncomp
def _triple_to_grid_2d(x_in, y_in, data, x_out, y_out, msg_py):
    # ''' signature:  grid = _triple2grid(x_in, y_in,data,x_out,y_out,msg_py)
    pass


# Outer Wrappers <funcname>()
# These Wrappers are excecuted in the __main__ python process, and should be
# used for any tasks which would not benefit from parallel execution.


def grid_to_triple(data, x_in=None, y_in=None, msg_py=None):
    """Converts a two-dimensional grid with one-dimensional coordinate variables
           to an array where each grid value is associated with its coordinates.

            Args:

                data (:class:`xarray.DataArray` or :class:`numpy.ndarray`):
                        Two-dimensional array of size ny x mx containing the data values.
                        Missing values may be present in `data`, but they are ignored.

                x_in (:class:`xarray.DataArray` or :class:`numpy.ndarray`):
                        Coordinates associated with the right dimension of the variable `data`.
                        If `data` is of type :class:`xarray.DataArray` and `x_in` is unspecified,
                        then it comes as the associated coordinate of `data` (if `x_in` is explicitly
                        given, then it will be used for calculations). If `data` is of type
                        :class:`numpy.ndarray`, then it must be explicitly given as input and it
                        must have the same dimension (call it `mx`) as the right dimension of `data`.

                y_in (:class:`xarray.DataArray` or :class:`numpy.ndarray`):
                        Coordinates associated with the left dimension of the variable `data`.
                        If `data` is of type :class:`xarray.DataArray` and `y_in` is unspecified,
                        then it comes as the associated coordinate of `data` (if `y_in` is explicitly
                        given, then it will be used for calculations). If `data` is of type
                        :class:`numpy.ndarray`, then it must be explicitly given as input and it
                        must have the same dimension (call it `ny`) as the left dimension of `data`.

                msg_py (:obj:`numpy.number`):
                    A numpy scalar value that represent a missing value in `data`.
                    This argument allows a user to use a missing value scheme
                    other than NaN or masked arrays, similar to what NCL allows.

            Returns:
                :class:`xarray.DataArray`: The maximum size of the returned array will be 3 x ld,
                where ld <= ny x mx.
                If no missing values are encountered in `data`, then ld = ny x mx. If missing
                values are encountered in `data`, they are not returned and hence ld will be
                equal to ny x mx minus the number of missing values found in `data`.
                The return array will be double if any of the input arrays are double, and float
                otherwise.

            Examples:

                Example 1: Using grid_to_triple with :class:`xarray.DataArray` input

                .. code-block:: python

                    import numpy as np
                    import xarray as xr
                    import geocat.comp

                    # Open a netCDF data file using xarray default engine and load the data stream
                    ds = xr.open_dataset("./NETCDF_FILE.nc")

                    # [INPUT] Grid & data info on the source curvilinear
                    data = ds.DIST_236_CBL[:]
                    x_in = ds.gridlat_236[:]
                    y_in = ds.gridlon_236[:]

                    output = geocat.comp.grid_to_triple(data, x_in, y_in)
        """

    # TODO: Will need to be revisited after sanity_check work is finished

    # ''' Start of boilerplate
    if not isinstance(data, xr.DataArray):
        if (x_in is None) | (y_in is None):
            raise CoordinateError(
                "ERROR grid_to_triple: Argument `x_in` and `y_in` must be provided explicitly "
                "unless `data` is an xarray.DataArray.")

        data = xr.DataArray(data)

        data = xr.DataArray(
            data.data,
            coords={
                data.dims[-1]: x_in,
                data.dims[-2]: y_in,
            },
            dims=data.dims,
        )

    if (x_in is None):
        x_in = data.coords[data.dims[-1]]
    if (y_in is None):
        y_in = data.coords[data.dims[-2]]

    # Basic sanity checks
    if data.ndim != 2:
        raise DimensionError(
            "ERROR grid_to_triple: `z` must have two dimensions !\n")

    if x_in.ndim != 1:
        raise DimensionError(
            "ERROR grid_to_triple: `x_in` must have one dimension !\n")
    elif x_in.shape[0] != data.shape[1]:
        raise DimensionError(
            "ERROR grid_to_triple: `x_in` must have the same size (call it `mx`) as the "
            "right dimension of z. !\n")

    if y_in.ndim != 1:
        raise DimensionError(
            "ERROR grid_to_triple: `y_in` must have one dimension !\n")
    elif y_in.shape[0] != data.shape[0]:
        raise DimensionError(
            "ERROR grid_to_triple: `y_in` must have the same size (call it `ny`) as the left dimension of z. !\n"
        )
    # ''' end of boilerplate

    out = _grid_to_triple(x_in.data, y_in.data, data.data, msg_py)

    out = xr.DataArray(out, attrs=data.attrs)

    return out


def triple_to_grid(data, x_in, y_in, x_out, y_out, method=1, domain=float(1.0), distmx=None, missing_value=np.nan, meta=False):
    """
    Places unstructured (randomly-spaced) data onto the nearest locations of a rectilinear grid.

    Parameters
    ----------

    data : :class:`xarray.DataArray`: or :class:`numpy.ndarray`:
        A multi-dimensional array, whose rightmost dimension is the same
        length as `x_in` and `y_in`, containing the values associated with
        the "x" and "y" coordinates. Missing values may be present but
        will be ignored.

    x_in : :class:`xarray.DataArray`: or :class:`numpy.ndarray`:
        One-dimensional arrays of the same length containing the coordinates
        associated with the data values. For geophysical variables, "x"
        correspond to longitude.

    y_in : :class:`xarray.DataArray`: or :class:`numpy.ndarray`:
        One-dimensional arrays of the same length containing the coordinates
        associated with the data values. For geophysical variables, "y"
        correspond to latitude.

    x_out : :class:`xarray.DataArray`: or :class:`numpy.ndarray`:
        A one-dimensional array of length M containing the "x" coordinates
        associated with the returned two-grid. For geophysical variables,
        these are longitudes. The coordinates' values must be
        monotonically increasing.

    y_out : :class:`xarray.DataArray`: or :class:`numpy.ndarray`:
        A one-dimensional array of length N containing the "y" coordinates
        associated with the returned grid. For geophysical ~variables,
        these are latitudes. The coordinates' values must be
        monotonically increasing.

    Optional Parameters
    -------------------

    method :
        An integer value that can be 0 or 1. The default value is 1.
        A value of 1 means to use the great circle distance formula
        for distance calculations.
        Warning: `method` = 0, together with `domain` = 1.0, could
        result in many of the target grid points to be set to the
        missing value if the number of grid points is large (ie: a
        high resolution grid) and the number of observations
        relatively small.

    domain :
        A float value that should be set to a value >= 0. The
        default value is 1.0. If present, the larger this factor,
        the wider the spatial domain allowed to influence grid boundary
        points. Typically, `domain` is 1.0 or 2.0. If `domain` <= 0.0,
        then values located outside the grid domain specified by
        `x_out` and `y_out` arguments will not be used.

    distmx :
        Setting `distmx` allows the user to specify a search
        radius (km) beyond which observations are not considered
        for nearest neighbor. Only applicable when `method` = 1.
        The default `distmx`=1e20 (km) means that every grid point
        will have a nearest neighbor. It is suggested that users
        specify a reasonable value for `distmx`.

    missing_value : :obj:`numpy.number`:
        A numpy scalar value that represent
        a missing value in `data`. The default value is `np.nan`.
        If specified explicitly, this argument allows the user to
        use a missing value scheme other than NaN or masked arrays.

    meta : :obj:`bool`:
        If set to True and the input array is an Xarray,
        the metadata from the input array will be copied to the
        output array; default is False.
        Warning: This option is not yet supported for this function.

    Returns
    -------

    grid : :class:`xarray.DataArray`:
        The returned array will be K x N x M, where K
        represents the leftmost dimensions of `data`, N represent the size of `y_out`,
        and M represent the size of `x_out` coordinate vectors. It will be of type
        double if any of the input is double, and float otherwise.

    Description
    -----------

        This function puts unstructured data (randomly-spaced) onto the nearest
        locations of a rectilinear grid. A default value of `domain` option is
        now set to 1.0 instead of 0.0.

        This function does not perform interpolation; rather, each individual
        data point is assigned to the nearest grid point. It is possible that
        upon return, grid will contain grid points set to missing value if
        no `x_in(n)`, `y_in(n)` are nearby.

    Examples
    --------

    Example 1: Using triple_to_grid with :class:`xarray.DataArray` input

    .. code-block:: python

        import numpy as np
        import xarray as xr
        import geocat.comp

        # Open a netCDF data file using xarray default engine and load the data stream
        ds = xr.open_dataset("./ruc.nc")

        # [INPUT] Grid & data info on the source curvilinear
        data = ds.DIST_236_CBL[:]
        x_in = ds.gridlat_236[:]
        y_in = ds.gridlon_236[:]
        x_out = ds.gridlat_236[:]
        y_out = ds.gridlon_236[:]


        # [OUTPUT] Grid on destination points grid (or read the 1D lat and lon from
        #	       an other .nc file.
        newlat1D_points=np.linspace(lat2D_curv.min(), lat2D_curv.max(), 100)
        newlon1D_points=np.linspace(lon2D_curv.min(), lon2D_curv.max(), 100)

        output = geocat.comp.triple_to_grid(data, x_out, y_out, x_in, y_in)
        """

    # TODO: May need to be revisited after sanity_check work is finished

    if (x_in is None) | (y_in is None):
        raise CoordinateError(
            "ERROR triple_to_grid: Arguments x_in and y_in must always be explicitly provided"
        )

    # ''' Start of boilerplate
    # If a Numpy input is given, convert it to Xarray and chunk it just with its dims
    if not isinstance(data, xr.DataArray):
        data = xr.DataArray(data)
        data_chunk = dict([
            (k, v) for (k, v) in zip(list(data.dims), list(data.shape))
        ])

        data = xr.DataArray(
            data.data,
            # coords={
            #     data.dims[-1]: x_in,
            #     data.dims[-2]: y_in,
            # },
            dims=data.dims,
        ).chunk(data_chunk)
    else:
        # If an unchunked Xarray input is given, chunk it just with its dims
        if (data.chunks is None):
            data_chunk = dict([
                (k, v) for (k, v) in zip(list(data.dims), list(data.shape))
            ])
            data = data.chunk(data_chunk)

        # Ensure the rightmost dimension of input is not chunked
        elif list(data.chunks)[-1:] != [x_in.shape]:
            raise ChunkError(
                "ERROR triple_to_grid: Data must be unchunked along the rightmost two dimensions"
            )

    # x_in = data.coords[data.dims[-1]]
    # y_in = data.coords[data.dims[-2]]

    # Basic sanity checks
    if x_in.shape[0] != y_in.shape[0] or x_in.shape[0] != data.shape[data.ndim -
                                                                     1]:
        raise DimensionError(
            "ERROR triple_to_grid: The length of `x_in` and `y_in` must be the same "
            "as the rightmost dimension of `data` !")
    if x_in.ndim > 1 or y_in.ndim > 1:
        raise DimensionError(
            "ERROR triple_to_grid: `x_in` and `y_in` arguments must be one-dimensional arrays !\n"
        )
    if x_out.ndim > 1 or y_out.ndim > 1:
        raise DimensionError(
            "ERROR triple_to_grid: `x_out` and `y_out` arguments must be one-dimensional array !\n"
        )

    if not isinstance(method, int):
        raise TypeError(
            'ERROR triple_to_grid: `method` arg must be an integer. Set it to either 1 or 0.'
        )

    if (method != 0) and (method != 1):
        raise TypeError(
            'ERROR triple_to_grid: `method` arg accepts either 0 or 1.')

    # `distmx` is only applicable when `method`==1
    if method:
        if np.asarray(distmx).size != 1:
            raise ValueError(
                "ERROR triple_to_grid: Provide a scalar value for `distmx` !"
            )
    else:
        if distmx is not None:
            raise ValueError(
                "ERROR triple_to_grid: `distmx` is only applicable when `method`==1 !"
            )

    if np.asarray(domain).size != 1:
        raise ValueError(
            "ERROR triple_to_grid: Provide a scalar value for `domain` !")

    # `data` data structure elements and autochunking
    data_chunks = list(data.dims)
    data_chunks[:-1] = [
        (k, 1) for (k, v) in zip(list(data.dims)[:-1],
                                 list(data.chunks)[:-1])
    ]
    data_chunks[-1:] = [
        (k, v[0])
        for (k, v) in zip(list(data.dims)[-1:],
                          list(data.chunks)[-1:])
    ]
    data_chunks = dict(data_chunks)
    data = data.chunk(data_chunks)

    # grid datastructure elements
    grid_chunks = list(data.chunks)
    grid_chunks[-1] = (y_out.shape[0] * x_out.shape[0],)
    grid_chunks = tuple(grid_chunks)
    dask_grid_shape = tuple(a[0] for a in list(grid_chunks))
    grid_coords = {k: v for (k, v) in data.coords.items()}
    grid_coords[data.dims[-1]] = x_out
    grid_coords[data.dims[-2]] = y_out
    # ''' end of boilerplate

    grid = map_blocks(
        _triple_to_grid,
        data.data,
        x_in,
        y_in,
        x_out,
        y_out,
        dask_grid_shape,
        method=method,
        distmx=distmx,
        domain=domain,
        msg_py=missing_value,
        chunks=grid_chunks,
        dtype=data.dtype,
        drop_axis=[data.ndim - 1],
        new_axis=[data.ndim - 1],
    )

    # Reshape grid to its final shape
    grid_shape = (data.shape[:-1] + (y_out.shape[0],) + (x_out.shape[0],))
    grid = grid.reshape(grid_shape)

    if meta:
        # grid = xr.DataArray(grid.compute(), attrs=data.attrs, dims=data.dims, coords=grid_coords)
        import warnings
        warnings.warn(
            "WARNING triple_to_grid: Retention of metadata is not yet supported; "
            "it will thus be ignored in the output!")
    # else:
    #     grid = xr.DataArray(grid.compute(), coords=grid_coords)

    grid = xr.DataArray(grid.compute())

    return grid


# TODO: Revisit for implementing this function after deprecating geocat.ncomp
def triple_to_grid_2d(x_in, y_in, data, x_out, y_out, msg_py):
    # ''' signature:  grid = triple2grid2d(x,y,data,x_out,y_out,msg_py)
    pass


# Transparent wrappers for geocat.ncomp backwards compatibility


def grid2triple(x_in, y_in, data, msg_py):
    warnings.warn("WARNING grid_to_triple: `grid2triple` function name and signature deprecated but still " \
                  "supported for backward compatibility purposes. Please use `grid_to_triple` in the future!")

    return grid_to_triple(data, x_in, y_in, msg_py)


def triple2grid(x_in, y_in, data, x_out, y_out, **kwargs):
    warnings.warn("WARNING triple_to_grid: `triple2grid` function name and signature deprecated but still " \
                  "supported for backward compatibility purposes. Please use `triple_to_grid` in the future!")

    return triple_to_grid(data, x_in, y_in, x_out, y_out, **kwargs)
