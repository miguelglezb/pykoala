"""
Module for estimating and applying wavelength offset corrections related to
inaccuracies in the original wavelength calibration.
"""
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.gridspec import GridSpec

from astropy.io import fits
from scipy.ndimage import median_filter, gaussian_filter, percentile_filter

from pykoala import vprint
from pykoala.corrections.correction import CorrectionBase
from pykoala.data_container import RSS
from pykoala.ancillary import flux_conserving_interpolation, vac_to_air
# from pykoala.corrections.sky import ContinuumEstimator


class WavelengthOffset(object):
    """Wavelength offset class.

    This class stores a 2D wavelength offset.

    Attributes
    ----------
    offset_data : np.ndarray
        Wavelength offset, in pixels.
    offset_error : np.ndarray
        Standard deviation of ``offset_data``.
    path: str
        Filename path.

    """
    offset_data = None
    offset_error = None

    def __init__(self, path=None, offset_data=None, offset_error=None):
        self.path = path
        self.offset_data = offset_data
        self.offset_error = offset_error

    def tofits(self, output_path=None):
        """Save the offset in a FITS file.
        
        Parameters
        ----------
        output_path: str, optional, default=None
            FITS file name path. If None, and ``self.path`` exists,
            the original file is overwritten.

        Notes
        -----
        The output fits file contains an empty PrimaryHDU, and two ImageHDU
        ("OFFSET", "OFFSET_ERR") containing the offset data and associated error.
        """
        if output_path is None:
            if self.path is None:
                raise NameError("Provide output path")
            else:
                output_path = self.path
        primary = fits.PrimaryHDU()
        data = fits.ImageHDU(data=self.offset_data, name='OFFSET')
        error = fits.ImageHDU(data=self.offset_error, name='OFFSET_ERR')
        hdul = fits.HDUList([primary, data, error])
        hdul.writeto(output_path, overwrite=True)
        hdul.close(verbose=True)
        vprint(f"Wavelength offset saved at {output_path}")

    @classmethod
    def from_fits(cls, path):
        """Load the offset data from a fits file.

        Loads offset values (extension 1) and
        associated errors (extension 2) from a fits file.

        Parameters
        ----------
        path : str
            Path to the FITS file containing the offset data.

        Returns
        -------
        wavelength_offset : :class:`WavelengthOffset`
            A :class:`WavelengthOffset` initialised with the input data.
        """
        if not os.path.isfile(path):
            raise NameError(f"offset file {path} does not exist.")
        vprint(f"Loading wavelength offset from {path}")
        with fits.open(path) as hdul:
            offset_data = hdul[1].data
            offset_error = hdul[2].data
        return cls(offset_data=offset_data, offset_error=offset_error,
                   path=path)


class WavelengthCorrection(CorrectionBase):
    """Wavelength correction class.

    This class accounts for the relative wavelength offset between fibres.

    Attributes
    ----------
    name : str
        Correction name, to be recorded in the log.
    offset : WavelengthOffset
        2D wavelength offset (n_fibres x n_wavelengths)
    verbose: bool
        False by default.
    """
    name = "WavelengthCorrection"
    offset = None
    verbose = False

    def __init__(self, offset_path=None, offset=None, **correction_kwargs):
        super().__init__(**correction_kwargs)

        self.path = offset_path
        self.offset = offset

    @classmethod
    def from_fits(cls, path):
        """Initialise a WavelegnthOffset correction from an input FITS file.
        
        Parameters
        ----------
        path : str
            Path to the FITS file containing the offset data.

        Returns
        -------
        wave_correction : :class:`WavelengthCorrection`
            A :class:`WavelengthCorrection` initialised with the input data.
        """
        return cls(offset=WavelengthOffset.from_fits(path=path),
                   offset_path=path)

    def apply(self, rss):
        """Apply a 2D wavelength offset model to a RSS.

        Parameters
        ----------
        rss : :class:`pykoala.rss.RSS`
            Original Row-Stacked-Spectra object to be corrected.

        Returns
        -------
        rss_corrected : :class:`pykoala.rss.RSS`
            Corrected copy of the input RSS.
        """

        assert isinstance(rss, RSS)

        rss_out = rss.copy()
        x = np.arange(rss.wavelength.size)
        for i in range(rss.intensity.shape[0]):
            rss_out.intensity[i] = flux_conserving_interpolation(
                x, x - self.offset.offset_data[i], rss.intensity[i])

        self.record_correction(rss_out, status='applied')
        return rss_out


class SolarCrossCorrOffset(WavelengthCorrection):
    """WavelengthCorrection based on solar spectra cross-correlation.
    
    This class constructs a WavelengthOffset and applies the resulting correction
    from a cross-correlation between a reference spectrum of the Sun and a twilight
    exposure, dominated by solar spectra features.

    Attributes
    ----------
    sun_intensity : np.ndarray
        Reference solar spectrum.
    sun_wavelength : np.ndarray
        Wavelength vector associated to ``sun_intensity``
    """
    name = "SolarCrossCorrelationOffset"

    def __init__(self, sun_wavelength, sun_intensity, **kwargs):
        super().__init__(offset=WavelengthOffset(), **kwargs)
        self.sun_wavelength = sun_wavelength
        self.sun_intensity = sun_intensity

    @classmethod
    def from_fits(cls, path=None, extension=1):
        """Initialise a WavelegnthOffset correction from an input FITS file.
        
        Parameters
        ----------
        path : str, optional
            Path to the FITS file containing the reference Sun's spectra. The
            file must contain an extension with a table including a ``WAVELENGTH``
            and ``FLUX`` columns.The wavelength array must be angstrom in the
            vacuum frame.
        extension : int or str, optional
            HDU extension containing the table. Default is 1.

        Returns
        -------
        solar_offset_correction : :class:`SolarCrossCorrOffset`
            An instance of SolarCrossCorrOffset.
        """
        if path is None:
            path = os.path.join(os.path.dirname(__file__), '..',
                     'input_data', 'spectrophotometric_stars',
                     'sun_mod_001.fits')
        with fits.open(path) as hdul:
            sun_wavelength = hdul[extension].data['WAVELENGTH']
            sun_wavelength = vac_to_air(sun_wavelength)
            sun_intensity = hdul[extension].data['FLUX']
        return cls(sun_wavelength=sun_wavelength,
                   sun_intensity=sun_intensity)

    @classmethod
    def from_text_file(cls, path, loadtxt_args={}):
        """Initialise a :class:`SolarCrossCorrOffset` correction from an input text file.
        
        Parameters
        ----------
        path: str
            Path to the text file containing the reference Sun's spectra. The
            text file must contain two columns consisting of the
            vacuum wavelength array in angstrom and the solar flux or luminosity.
        loadtxt_args: dict, optional
            Additional arguments to be passed to ``numpy.loadtxt``.

        Returns
        -------
        solar_offset_correction: :class:`SolarCrossCorrOffset`
            An instance of SolarCrossCorrOffset.
        """
        sun_wavelength, sun_intensity = np.loadtxt(path, unpack=True,
                                                   usecols=(0, 1),
                                                   **loadtxt_args)
        sun_wavelength = vac_to_air(sun_wavelength)
        return cls(sun_wavelength=sun_wavelength,
                   sun_intensity=sun_intensity)


    def get_solar_features(self, solar_wavelength, solar_spectra,
                            window_size_aa=20):
        """
        Estimate the regions of the solar spectrum dominated by absorption features.

        Notes
        -----
        First, a median filter is applied to estimate the upper envelope of the
        continuum. Then, the median ratio between the solar spectra and the median-filtered
        estimate is used to compute the relative weights:

        .. math::
            \\begin{equation}
                w = \\left\\|\\frac{F_\\odot}{F_{cont}} - Median(\\frac{F_\\odot}{F_{cont}})\\right\\|
            \\end{equation}

        Parameters
        ----------
        solar_wavelength: numpy.ndarray
            Solar spectra wavelengths array.
        solar_spectra: numpy.ndarray
            Array containing the flux of the solar spectra associated to a given
            wavelength.
        window_size_aa: int, optional
            Size of a spectral window in angstrom to perform a median filtering
            and estimate the underlying continuum. Default is 20 AA.

        Returns
        -------
        weights: numpy.ndarray
            Array of weights representing the prominance of an absorption feature.

        """
        self.vprint("Estimating regions of solar spectra dominated by absorption lines.")
        delta_pixel = int(window_size_aa
                          / (solar_wavelength[-1] - solar_wavelength[0])
                          * solar_wavelength.size)
        if delta_pixel % 2 == 0:
            delta_pixel += 1
        solar_continuum = median_filter(solar_spectra, delta_pixel)
        # Detect absorption features
        median_continuum_ratio = np.nanmedian(solar_spectra / solar_continuum)
        weights = np.abs(solar_spectra / solar_continuum -  median_continuum_ratio)
        return weights

    def compute_grid_of_models(self, pix_shift_array, pix_std_array, pix_array,
                              sun_intensity, weights):
        """Compute a grid of Solar spectra models convolved with a gaussian LSF.
        
        Parameters
        ----------
        pix_shift_array: 1D-np.array
            Array containing the wavelength offsets expressed in pixels.
        pix_std_array: 1D-np.array
            Array containing the values of the gaussian LSF standard deviation
            in pixels.
        pix_array: 1D-np.array
            Array of pixels to sample the grid of models.
        sun_intensity: 1D-np.array
            Array of solar fluxes associated to ``pix_array``.
        weights: 1D-np.array
            Array of absorption-features weights associated to ``sun_intensity``.
        
        Returns
        -------
        models_grid: numpy.ndarray
            Grid of models with dimensions `(n, m, s)`, where `n`, `m` and `s`
            correspond to the size of `pix_shift_array`, `pix_std_array`, and
            `pix_array`, respectively.
        weights_grid: numpy.ndarray
            Grid of absorption-feature weights associated to `models_grid`.

        See also
        --------
        :For more details on the computation of the weights array see :func:`get_solar_features`.

        """
        self.vprint("Computing grid of solar spectra models")
        models_grid = np.zeros((pix_shift_array.size, pix_std_array.size,
                           sun_intensity.size))
        weights_grid = np.zeros((pix_shift_array.size, pix_std_array.size,
                           sun_intensity.size))
        for i, velshift in enumerate(pix_shift_array):
                for j, gauss_std in enumerate(pix_std_array):
                    new_pixel_array = pix_array + velshift
                    
                    interp_sun_intensity = flux_conserving_interpolation(
                        new_pixel_array, pix_array, sun_intensity)
                    interp_sun_intensity = gaussian_filter(
                        interp_sun_intensity, gauss_std)
                    models_grid[i, j] = interp_sun_intensity

                    interp_sun_weight = flux_conserving_interpolation(
                        new_pixel_array, pix_array, weights)
                    interp_sun_weight = gaussian_filter(
                        interp_sun_weight, gauss_std, truncate=2.0)
                    interp_sun_weight /= np.nansum(interp_sun_weight)
                    weights_grid[i, j] = interp_sun_weight
        return models_grid, weights_grid

    def compute_shift_from_twilight(self, spectra_container,
                                    sun_window_size_aa=20, keep_features_frac=0.1,
                                    response_window_size_aa=200,
                                    wave_range=None,
                                    pix_shift_array=None,
                                    pix_std_array=None,
                                    logspace=True, use_mean=True,
                                    inspect_fibres=None):
        """Compute the wavelenght offset of between a given SpectraContainer and a reference Solar spectra.
        
        Parameters
        ----------
        spectra_container: `pykoala.data_container.SpectraContainer`
            Spectra container (RSS or Cube) to cross-correlate with the reference
            spectra.
        sun_window_size_aa: int, optional
            Size of a spectral window in angstrom to perform a median filtering
            and estimate the underlying continuum. Default is 20 AA.
            See `get_solar_features` for details.
        keep_features_frac: float, optional
            Fraction of absorption-features weights to keep. All values below
            that threshold will be set to 0. Default is 0.1.
        wave_range: list or tuple, optional
            If provided, the cross-correlation will only be done in the provided
            wavelength range. Default is None.
        pix_shift_array: 1D-np.array, optional, default=np.arange(-5, 5, 0.1)
            Array containing the wavelength offsets expressed in pixels.
        pix_std_array: 1D-np.array, optional, default=np.arange(0.1, 3, 0.1)
            Array containing the values of the gaussian LSF standard deviation
            in pixels. See `compute_grid_of_models` for details.
        logspace: bool, optional
            If True, the cross-correlation will be perform using a logarithmic
            sampling in terms of wavelength. Default is True.
        use_mean: bool, optional
            If True, the mean likelihood-weighted value of the wavelength offset
            is used to create the `WavelengthOffsetCorrection`. Otherwise, the
            best fit parameters of the input grid are used. Default is True.
        inspect_fibres: list or tuple, optional
            Iterable containing RSS-wise spectra indices. If provided, a
            quality-control plot of each fibre is produced.
        
        Returns
        -------
        results: dict
            The dictionary contains the ``best-fit`` and ``mean`` likelihood-weighted
            values of ``pix_shift_array`` and ``pix_std_array`` in a tuple, respectively.
            If ``inspect_fibres`` is not ``None``, it containes a list of figures
            for each fibre included in ``inspect_fibres``.

        """
        if pix_shift_array is None:
            pix_shift_array = np.arange(-5, 5, 0.1)
        if pix_std_array is None:
            pix_std_array = np.arange(0.1, 3, 0.1)

        if logspace:
            new_wavelength = np.geomspace(spectra_container.wavelength[0],
                                          spectra_container.wavelength[-1],
                                          spectra_container.wavelength.size)
            rss_intensity = np.array([flux_conserving_interpolation(
                new_wavelength, spectra_container.wavelength, fibre
                ) for fibre in spectra_container.rss_intensity])
        else:
            new_wavelength = spectra_container.wavelength
            rss_intensity = spectra_container.rss_intensity
        
        # Interpolate the solar spectrum to the new grid of wavelengths
        sun_intensity = flux_conserving_interpolation(
        new_wavelength, self.sun_wavelength, self.sun_intensity)

        # Make an array of weights to focus on the absorption lines
        if wave_range is None:
            weights = self.get_solar_features(new_wavelength, sun_intensity,
                                            window_size_aa=sun_window_size_aa)
            weights[weights < np.nanpercentile(weights, 1 - keep_features_frac)] = 0
            weights[:100] = 0
            weights[-100:] = 0
        else:
            weights = np.array(
                (new_wavelength >= wave_range[0]) & (new_wavelength <= wave_range[-1]),
                dtype=float)
        
        valid_pixels = weights > 0
        self.vprint("Number of pixels with non-zero weights: "
                    + f"{np.count_nonzero(valid_pixels)} out of {valid_pixels.size}")

        # Estimate the response curve for each individual fibre
        delta_pixel = int(response_window_size_aa
                        / (new_wavelength[-1] - new_wavelength[0])
                        * new_wavelength.size)
        if delta_pixel % 2 == 0:
            delta_pixel += 1

        response_spectrograph = rss_intensity / sun_intensity[np.newaxis]
        smoothed_r_spectrograph = median_filter(
            response_spectrograph, delta_pixel, axes=1)
        spectrograph_upper_env = percentile_filter(
            smoothed_r_spectrograph, 95, delta_pixel, axes=1)
        # Avoid regions dominated by telluric absorption
        self.vprint("Including the masking of pixels dominated by telluric absorption")
        fibre_weights =  1 / (1  + (
                spectrograph_upper_env / smoothed_r_spectrograph
                - np.nanmedian(spectrograph_upper_env / smoothed_r_spectrograph)
                )**2)

        normalized_rss_intensity = rss_intensity / smoothed_r_spectrograph
        # Generate and fit the model
        pix_array = np.arange(new_wavelength.size)

        models_grid, weights_grid = self.compute_grid_of_models(
            pix_shift_array, pix_std_array, pix_array, sun_intensity, weights)

        # loop over one variable to avoir memory errors
        all_chi2 = np.zeros((pix_shift_array.size,
                             pix_std_array.size,
                             rss_intensity.shape[0]))
        
        self.vprint("Performing the cross-correlation with the grid of models")
        for i in range(pix_shift_array.size):
            all_chi2[i] = np.nansum(
                (models_grid[i, :, np.newaxis]
                 - normalized_rss_intensity[np.newaxis, :, :])**2
                * weights_grid[i, :, np.newaxis]
                * fibre_weights[np.newaxis, :, :],
                axis=-1) / np.nansum(
                    weights_grid[i, :, np.newaxis]
                    * fibre_weights[np.newaxis, :, :],
                    axis=-1)
            
        likelihood = np.exp(- (all_chi2 - all_chi2.min())/ 2)
        likelihood /= np.nansum(likelihood, axis=(0, 1))[np.newaxis, np.newaxis, :]
        mean_pix_shift = np.sum(likelihood.sum(axis=1)
                                * pix_shift_array[:, np.newaxis], axis=0)
        mean_std = np.sum(likelihood.sum(axis=0)
                          * pix_std_array[:, np.newaxis], axis=0)

        best_fit_idx = np.argmax(likelihood.reshape((-1, likelihood.shape[-1])),
                                 axis=0)
        best_vel_idx, best_std_idx = np.unravel_index(
                best_fit_idx, all_chi2.shape[:-1])
        best_sigma, best_shift = (pix_std_array[best_std_idx],
                                    pix_shift_array[best_vel_idx])

        if inspect_fibres is not None:
            self.vprint("Inspecting input fibres")
            fibre_figures = self.inspect_fibres(
                inspect_fibres, pix_shift_array, pix_std_array,
                best_vel_idx, best_std_idx, mean_pix_shift, mean_std,
                likelihood, models_grid, weights_grid, normalized_rss_intensity,
                new_wavelength)
        else:
            fibre_figures= None
        if use_mean:
            self.vprint("Using mean likelihood-weighted values to compute the wavelength offset correction")
            self.offset.offset_data = - mean_pix_shift
        else:
            self.vprint("Using best fit values to compute the wavelength offset correction")
            self.offset.offset_data = - best_shift
        
        self.offset.offset_error = np.full_like(best_shift, fill_value=np.nan)

        return {"best-fit": (best_shift, best_sigma),
                "mean": (mean_pix_shift, mean_std),
                "fibre_figures": fibre_figures}
    
    def inspect_fibres(self, fibres, pix_shift_array, pix_std_array,
                       best_vel_idx, best_std_idx, mean_vel, mean_std,
                       likelihood,
                       models_grid, weights_grid,
                       normalized_rss_intensity, wavelength):
        """
        Create a quality control plot of the solar cross-correlation process of each input fibre.

        Parameters
        ----------
        fibres: iterable
            List of input fibres to check.
        pix_shift_array: 1D-np.array
            Array containing the wavelength offsets expressed in pixels.
        pix_std_array: 1D-np.array
            Array containing the values of the gaussian LSF standard deviation
            in pixels. See :func:`compute_grid_of_models` for details.
        best_vel_idx: int
            Index of ``pix_shift_array`` that correspond to the best fit.
        best_std_idx: int
            Index of ``pix_std_array`` that correspond to the best fit.
        mean_vel: float
            Mean likelihood-weighted values of ``pix_shift_array``.
        mean_std: float
            Mean likelihood-weighted values of ``pix_std_array``.
        likelihood: numpy.ndarray:
            Likelihood of the cross-correlation.
        models_grid: numpy.ndarray
            Grid of solar spectra models. See :func:`compute_grid_of_models` for details.
        weights_grid: numpy.ndarray
            Grid of solar spectra weights. See :func:`compute_grid_of_models` for details.
        normalized_rss_intensity: numpy.ndarray
            Array containing the RSS intensity values of a SpectraContainer including
            the correction of the spectrograph response curve.
        wavelength: np.array
            Wavelength array associated to ``normalized_rss_intensity`` and ``models_grid``.

        Returns
        -------
        fibres_figures: list
            List of figures containing a QC plot of each fibre.
        """
        fibre_figures = []
        best_sigma, best_shift = (pix_std_array[best_std_idx],
                                  pix_shift_array[best_vel_idx])
        for fibre in fibres:
            fig = plt.figure(constrained_layout=True, figsize=(10, 8))
            gs = GridSpec(2, 4, figure=fig, wspace=0.25, hspace=0.25)

            ax = fig.add_subplot(gs[0, 0])
            mappable = ax.pcolormesh(
                pix_std_array, pix_shift_array, likelihood[:, :, fibre],
                cmap='gnuplot',
                norm=LogNorm(vmin=likelihood.max() / 1e2, vmax=likelihood.max()))
            plt.colorbar(mappable, ax=ax,
                         label=r"$e^(-\sum_\lambda w(I - \hat{I}(s, \sigma))^2 / 2)$")
            ax.plot(best_sigma[fibre], best_shift[fibre], '+', color='cyan',
                    label=r'Best fit: $\Delta\lambda$='
                    + f'{best_shift[fibre]:.2}, ' + r'$\sigma$=' + f'{best_sigma[fibre]:.2f}')
            ax.plot(mean_std[fibre], mean_vel[fibre], 'o', mec='lime', mfc='none',
                    label=r'Mean value: $\Delta\lambda$='
                    + f'{mean_vel[fibre]:.2}, ' + r'$\sigma$=' + f'{mean_std[fibre]:.2f}')
            ax.set_xlabel(r"$\sigma$ (pix)")
            ax.set_ylabel(r"$\Delta \lambda$ (pix)")
            ax.legend(bbox_to_anchor=(0., 1.05), loc='lower left', fontsize=7)

            sun_intensity = models_grid[best_vel_idx[fibre],
                                        best_std_idx[fibre]]
            weight = weights_grid[best_vel_idx[fibre],
                                        best_std_idx[fibre]]

            ax = fig.add_subplot(gs[0, 1:])
            ax.set_title(f"Fibre: {fibre}")
            ax.plot(wavelength, sun_intensity, label='Sun Model')
            ax.plot(wavelength, normalized_rss_intensity[fibre],
                    label='Fibre', lw=2)
            twax = ax.twinx()
            twax.plot(wavelength, weight, c='fuchsia',
                    zorder=-1, alpha=0.5, label='Weight')
            ax.legend(fontsize=7)
            ax.set_ylabel("Intensity")
            ax.set_xlabel("Wavelength")
            twax.set_ylabel("Relative weight")

            ax = fig.add_subplot(gs[1, :])
            max_idx = np.argmax(weight)
            max_weight_range = range(np.max((max_idx - 80, 0)),
                  np.min((max_idx + 80, wavelength.size - 1)))
            ax.plot(wavelength[max_weight_range],
                    sun_intensity[max_weight_range], label='Model')
            ax.plot(wavelength[max_weight_range],
                    normalized_rss_intensity[fibre][max_weight_range],
                    label='Fibre', lw=2)
            
            ax.set_xlim(wavelength[max_weight_range][0],
                        wavelength[max_weight_range][-1])
            twax = ax.twinx()
            twax.plot(wavelength[max_weight_range], weight[max_weight_range],
                      c='fuchsia',
                    zorder=-1, alpha=0.5, label='Absorption-feature Weight')
            twax.axhline(0)
            twax.legend(fontsize=7)
            ax.set_ylabel("Intensity")
            ax.set_xlabel("Wavelength")
            twax.set_ylabel("Relative weight")
            plt.show()
            fibre_figures.append(fig)
        plt.close()
        return fibre_figures


# =============================================================================
# Mr Krtxo \(ﾟ▽ﾟ)/
#                                                       ... Paranoy@ Rulz! ;^D
