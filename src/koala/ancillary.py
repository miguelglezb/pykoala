"""
This module contains a colelction of ancilliary functions which are either partially implemented or not fully implemented. 
Currently this acts as a placeholder for functions that were in the original non-modular version of PyKOALA which have
not been included in the modular version
"""

# =============================================================================
# Basics packages
# =============================================================================
import numpy as np
from matplotlib import pyplot as plt
from scipy import interpolate
from scipy import optimize
# =============================================================================
# Astropy and associated packages
# =============================================================================
from astropy.io import fits
# =============================================================================

# =============================================================================
# Ancillary Functions - RSS Related
# =============================================================================

#This has not been implemented. Is meant to return the range of RA and DEC from centre RA and DEC

def coord_range(rss_list):
    """
    Returns the full extent of the coordinate range of a given set of RSS files 
    """
    ra = [rss.RA_centre_deg + rss.offset_RA_arcsec / 3600. for rss in rss_list]
    ra_min = np.nanmin(ra)
    ra_max = np.nanmax(ra)
    dec = [rss.DEC_centre_deg + rss.offset_DEC_arcsec / 3600. for rss in rss_list]
    dec_min = np.nanmin(dec)
    dec_max = np.nanmax(dec)
    return ra_min, ra_max, dec_min, dec_max


def detect_edge(rss):
    """
    Detect the edges of a RSS. Returns the minimum and maximum wavelength that 
    determine the maximum interval with valid (i.e. no masked) data in all the 
    spaxels.

    Parameters
    ----------
    rss : RSS object.

    Returns
    -------
    min_w : float
        The lowest value (in units of the RSS wavelength) with 
        valid data in all spaxels.
    min_index : int
        Index of min_w in the RSS wavelength variable.
    max_w : float
        The higher value (in units of the RSS wavelength) with 
        valid data in all spaxels.
    max_index : int
        Index of max_w in the RSS wavelength variable.

    """
    collapsed = np.sum(rss.intensity, 0)
    nans = np.isfinite(collapsed)
    wavelength = rss.wavelength
    min_w = wavelength[nans].min()
    min_index = wavelength.tolist().index(min_w)
    max_w = wavelength[nans].max()
    max_index = wavelength.tolist().index(max_w)
    return min_w, min_index, max_w, max_index


# RSS info dictionary template
rss_info_template = dict(name=None,  # Name of the object
                         exptime=None,  # Total rss exposure time (seconds)
                         obj_ra=None, obj_dec=None,  # Celestial coordinates of the object (deg)
                         cen_ra=None, cen_dec=None,  # Celestial coordinates of the pointing (deg)
                         fib_ra_offset=None, fib_dec_offset=None,  # Fibres' celestial offset
                         pos_angle=None,  # Instrument position angle
                         airmass=None  # Airmass
                         )


def vprint(*arg):
    """
    Prints the arguments only if vprint.verbose is previously setted True.
    """
    vprint.verbose
    if vprint.verbose:
        for i in arg:
            print(i,end=' ')


def interpolate_nan(spectrum):
    """
    Replace any NaN value in a spectrum by interpolating non-NaNs sideways.
    """
    
    inds = np.arange(spectrum.shape[0])
    good = np.where(np.isfinite(spectrum))
    f = interpolate.interp1d(inds[good], spectrum[good],bounds_error=False)
    filled_spectrum = np.where(np.isfinite(spectrum),spectrum,f(inds))
    return filled_spectrum


def nearest(array, value):
    """
    Returns the index of the element in <array> nearest to <value>.
    
    """
    array = np.asarray(array)
    idx = (np.abs(array - value)).argmin()
    return idx

# Originally a method of RSS

def cut_wave(rss,
             wave,
             wave_index=-1,
             #plot=False,
             #ymax="",
             ):
    """

    Parameters
    ----------
    wave : wavelength to be cut
        DESCRIPTION.
    plot : TYPE, optional
        DESCRIPTION. The default is False.
    ymax : TYPE, optional
        DESCRIPTION. The default is "".

    Returns
    -------
    corte_wave : TYPE
        DESCRIPTION.

    """
    w = rss.wavelength
    if wave_index == -1:
        _w_ = np.abs(w - wave)
        w_min = np.nanmin(_w_)
        wave_index = _w_.tolist().index(w_min)
    else:
        wave = w[wave_index]
    corte_wave = rss.intensity_corrected[:, wave_index]

    return corte_wave


def running_mean(x, n_window):
    """
    This function calculates the running mean of an array.

    Parameters
    ----------
    x : (n,) np.ndarray
        This is the given array.
    n_window : Int
        Number of neighbours for computing the running mean.

    Returns
    -------
    running_mean_x: (n - n_window,) np.ndarray
        Running mean array.

    """
    cumsum = np.cumsum(np.insert(x, 0, 0))
    return (cumsum[n_window:] - cumsum[:-n_window]) / n_window


# ----------------------------------------------------------------------------------------------------------------------
# Arithmetic operations
# ----------------------------------------------------------------------------------------------------------------------


def flux_conserving_interpolation(new_wavelength, wavelength, spectra, **interp_args):
    """
    #TODO...
    Parameters
    ----------
    new_wavelength
    wavelength
    spectra
    interp_args

    Returns
    -------

    """
    dwave = wavelength[1:] - wavelength[:-1]
    wavelength_edges = np.hstack((wavelength[0] - dwave[0] / 2, wavelength[:-1] + dwave / 2,
                                  wavelength[-1] + dwave[-1] / 2))
    new_dwave = new_wavelength[1:] - new_wavelength[:-1]
    new_wavelength_edges = np.hstack((new_wavelength[0] - new_dwave[0] / 2, new_wavelength[:-1] + new_dwave / 2,
                                      new_wavelength[-1] + new_dwave[-1] / 2))
    cum_spectra = np.nancumsum(np.diff(wavelength_edges) * spectra)
    cum_spectra = np.hstack((0, cum_spectra))
    new_cum_spectra = np.interp(new_wavelength_edges, wavelength_edges, cum_spectra, **interp_args)
    new_spectra = np.diff(new_cum_spectra) / np.diff(new_wavelength_edges)
    return new_spectra


def centre_of_mass(w, x, y):
    """Compute the centre of mass of a given image.
    Parameters
    ----------
    w: np.ndarray(float)
        (n,) weights computing the centre of mass.
    x: np.ndarray(float)
        (n,) Coordinates corresponding to the x-axis (columns).
    y: np.ndarray(float)
        (n,) Coordinates corresponding to the y-axis (rows).
    Returns
    -------
    x_com: float
    y_com: float
    """
    norm = np.nansum(w)
    x_com, y_com = np.nansum(w * x) / norm, np.nansum(w * y) / norm
    return x_com, y_com


def growth_curve_1d(f, x, y):
    """TODO"""
    r2 = x**2 + y**2
    idx_sorted = np.argsort(r2)
    growth_c = np.cumsum(f[idx_sorted])
    return r2[idx_sorted], growth_c


def growth_curve_2d(image, x0=None, y0=None):
    """Compute the curve of growth of an array f with respect to a given point (x0, y0).

    Parameters
    ----------
    image: np.ndarray
        2D array
    x0: float
        Origin of coordinates in pixels along the x-axis (columns).
    y0: float
        Origin of coordinates in pixels along the y-axis (rows).

    Returns
    -------
    r2: np.ndarray
        Vector containing the square radius with respect to (x0, y0).
    growth_curve: np.ndarray
        Curve of growth centered at (x0, y0).
    """
    xx, yy = np.meshgrid(np.arange(0, image.shape[1]),
                         np.arange(0, image.shape[1]))
    r2 = (xx - x0) ** 2 + (yy - y0) ** 2
    idx_sorted = np.argsort(r2)
    growth_c = np.cumsum(image.flatten()[idx_sorted])
    return r2[idx_sorted], growth_c


# ----------------------------------------------------------------------------------------------------------------------
# Models and fitting
# ----------------------------------------------------------------------------------------------------------------------


def cumulative_1d_sky(r2, sky_brightness):
    """1D cumulative sky brightness.
        F_sky = 4*pi*r2 * B_sky
    Parameters
    ----------
    r2: np.array(float)
        Square radius from origin.
    sky_brightness: float
        Sky surface brightness.

    Returns
    -------
    cumulative_sky_brightness: np.array(float)
        Cumulative sky brightness.
    """
    return np.pi * r2 * sky_brightness


def cumulative_1d_moffat(r2, l_star, alpha2, beta):
    """
    Cumulative Moffat ligth profile.

    Parameters
    ----------
    r2 : np.array(float)
        Square radius with respect to the profile centre.
    l_star : float
        Total luminosity integrating from 0 to inf.
    alpha2 : float
        Characteristic square radius.
    beta : float
        Power-low slope

    Returns
    -------
    cum_moffat_prof: np.array(float)
        Cumulative Moffat profile
    """
    return l_star * (1 - np.power(1 + (r2 / alpha2), -beta))


def cumulative_1d_moffat_sky(r2, l_star, alpha2, beta, sky_brightness):
    """Combined model of cumulative_1d_moffat and cumulative_1d_sky."""
    return cumulative_1d_sky(r2, sky_brightness) + cumulative_1d_moffat(r2, l_star, alpha2, beta)


def fit_moffat(r2_growth_curve, f_growth_curve,
               f_guess, r2_half_light, r_max, plot=False):
    """
    Fits a Moffat profile to a flux growth curve
    as a function of radius squared,
    cutting at to r_max (in units of the half-light radius),
    provided an initial guess of the total flux and half-light radius squared.

    Parameters #TODO
    ----------
    r2_growth_curve : TYPE
        DESCRIPTION.
    F_growth_curve : TYPE
        DESCRIPTION.
    F_guess : TYPE
        DESCRIPTION.
    r2_half_light : TYPE
        DESCRIPTION.
    r_max : TYPE
        DESCRIPTION.
    plot : Boolean, optional
        If True generates and shows the plots. The default is False.

    Returns
    -------
    fit : TYPE
        DESCRIPTION.

    """
    index_cut = np.searchsorted(r2_growth_curve, r2_half_light * r_max ** 2)
    fit, cov = optimize.curve_fit(cumulative_1d_moffat,
                                  r2_growth_curve[:index_cut], f_growth_curve[:index_cut],
                                  p0=(f_guess, r2_half_light, 1)
                                  )
    if plot:
        print("Best-fit: L_star =", fit[0])
        print("          alpha =", np.sqrt(fit[1]))
        print("          beta =", fit[2])
        r_norm = np.sqrt(np.array(r2_growth_curve) / r2_half_light)
        plt.plot(r_norm, cumulative_1d_moffat(np.array(r2_growth_curve),
                                           fit[0], fit[1], fit[2]) / fit[0], ':')
    return fit


# Mr Krtxo \(ﾟ▽ﾟ)/