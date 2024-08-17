# =============================================================================
# Basics packages
# =============================================================================
from matplotlib import pyplot as plt
import numpy as np
import os

# =============================================================================
# Astropy and associated packages
# =============================================================================

# =============================================================================
# KOALA packages
# =============================================================================
from pykoala import vprint
from pykoala.data_container import SpectraContainer
from pykoala.corrections.correction import CorrectionBase


# =============================================================================
class AtmosphericExtCorrection(CorrectionBase):
    """Atmospheric Extinction Correction.

    This module accounts for the brightness reduction caused due to the absorption of 
    photons by the atmosphere.

    For a given observed (F_obs) and intrinsic flux F_int, the extinction E takes the form:
    F_obs(lambda) = E(lambda) * F_int(lambda) = 10^(0.4 * airmass * eta(lambda))
    where eta corresponds to the extinction curve that depends on the frequency.

    Attributes
    ----------
    - extinction_correction: np.ndarray, optional, default=None
        Atmospheric extinction curve.
    - extinction_correction_wave: np.ndarray, optional, default=None
        Atmospheric extinction curve wavelength array.
    - extinction_file: str
        Path to a text file containing a wavelength, and a extinction curve.
        If None, a default extinction model will be used, corresponding to the extinction curve at Siding Spring Observatory.

    See Also
    --------
    `pykoala.corrections.correction.CorrectionBase`: for a list of all
    attributes.
    """
    name = "AtmosphericExtinction"
    verbose = True
    default_extinction = os.path.join(os.path.dirname(__file__), '..', 'input_data',
                                      'observatory_extinction', 'ssoextinct.dat')
    def __init__(self,
                 extinction_correction=None,
                 extinction_correction_wave=None,
                 extinction_correction_file='unknown',
                 **correction_args):
        super().__init__(**correction_args)
        self.vprint("Initialising correction")

        # Initialise variables
        self.extinction_correction = extinction_correction
        self.extinction_correction_wave = extinction_correction_wave
        self.extinction_correction_file = extinction_correction_file

    @classmethod
    def from_text_file(cls, path=None):
        if path is None:
            path = cls.default_extinction
        wavelength, extinct = np.loadtxt(path, unpack=True)
        return cls(extinction_correction=extinct,
                   extinction_correction_wave=wavelength,
                   extinction_correction_file=path)

    def extinction(self, wavelength, airmass):
        """Compute the atmospheric extinction for a given airmass and wavelength.
        
        Parameters
        ----------
        - wavelength: np.ndarray
            Input array of wavelengths where to estimate the extinction.
        - airmass: float
            Target airmass at which the observation is performed.
        
        Returns
        -------
        - extinction:
            Extinction function shuch that
                   .. math::
                    F_obs(lambda) = E(lambda) * F_int(lambda)
        """
        extinction_correction = np.interp(wavelength,
                                          self.extinction_correction_wave,
                                          self.extinction_correction)
        return 10**(0.4 * airmass * extinction_correction)

    def apply(self, spectra_container, airmass=None):
        """Apply the Extinction Correction to a DataContainer.
        
        Parameters
        ----------
        - airmass: float, optional
            If provided, the extinction will be computed using this value,
            otherwise the airmass stored at the `info` attribute will be used.
        
        Returns
        -------
        - corrected_spectra_container: SpectraContainer
            SpectraContainer with the corrected intensity and variance.
        """
        assert isinstance(spectra_container, SpectraContainer)
        spectra_container_out = spectra_container.copy()
        if airmass is None:
            airmass = spectra_container.info['airmass']

        if self.extinction_correction is not None:
            self.vprint("Applying model-based extinction correction to"
                        f"Data Container ({airmass:.2f} airmass)")
            extinction = self.extinction(spectra_container_out.wavelength, airmass)
            comment = ("Atm. extinction file :" + os.path.basename(
                        self.extinction_correction_file)
                        + f"|airmass={airmass:.2f}")
        else:
            raise AttributeError("Extinction correction not provided")

        # Apply the correction
        extinction = np.expand_dims(extinction, axis=0)
        spectra_container_out.rss_intensity = (spectra_container_out.rss_intensity
                                            * extinction)
        spectra_container_out.rss_variance = (spectra_container_out.rss_variance
                                           * extinction**2)
        self.record_correction(spectra_container_out, status='applied',
                            comment=comment)
        return spectra_container_out


# =============================================================================
# Atmospheric Differential Refraction
# =============================================================================

def get_adr(data_container, max_adr=0.5, pol_deg=2, plot=False):
    """Computes the ADR for a given DataContainer."""
    # Centre of mass using multiple power of the intensity
    com = []
    for i in range(1, 5):
        com.append(data_container.get_centre_of_mass(power=i))
    com = np.array(com) * 3600
    com -= np.nanmedian(com, axis=2)[:, :, np.newaxis]
    median_com = np.nanmedian(
        com, axis=0) - np.nanmedian(com, axis=(0, 2))[:, np.newaxis]
    median_com[np.abs(median_com) > max_adr] = np.nan

    finite_mask = np.isfinite(median_com[0])
    if finite_mask.any():
        p_x = np.polyfit(data_container.wavelength[finite_mask],
                         median_com[0][finite_mask], deg=pol_deg)
        polfit_x = np.poly1d(p_x)(data_container.wavelength)
    else:
        vprint("[ADR] ERROR: Could not compute ADR-x, all NaN")
        polfit_x = np.zeros_like(data_container.wavelength)

    finite_mask = np.isfinite(median_com[1])
    if finite_mask.any():
        p_y = np.polyfit(data_container.wavelength[finite_mask],
                         median_com[1][finite_mask], deg=pol_deg)
        polfit_y = np.poly1d(p_y)(data_container.wavelength)
    else:
        vprint("[ADR] ERROR: Could not compute ADR-y, all NaN")
        polfit_y = np.zeros_like(data_container.wavelength)
    

    if plot:
        fig = plt.figure(figsize=(10, 5))
        ax = fig.add_subplot(121)
        ax.plot(data_container.wavelength, com[0, 0], label='COM', lw=0.7)
        ax.plot(data_container.wavelength, com[1, 0], label='COM2', lw=0.7)
        ax.plot(data_container.wavelength, com[2, 0], label='COM3', lw=0.7)
        ax.plot(data_container.wavelength, com[3, 0], label='COM4', lw=0.7)
        ax.plot(data_container.wavelength, median_com[0], c='k', label='Median', lw=0.7)
        ax.plot(data_container.wavelength, polfit_x, c='fuchsia', label=f'pol. fit (deg={pol_deg})', lw=0.7)
        ax.set_ylim(-max_adr, max_adr)
        ax.legend(ncol=2, bbox_to_anchor=(0.5, 1), loc='lower center')
        ax.set_ylabel(r'$\Delta RA$ (arcsec)')
        ax.set_xlabel(r'$\lambda$')

        ax = fig.add_subplot(122)
        ax.plot(data_container.wavelength, com[0, 1], label='COM', lw=0.7)
        ax.plot(data_container.wavelength, com[1, 1], label='COM2', lw=0.7)
        ax.plot(data_container.wavelength, com[2, 1], label='COM3', lw=0.7)
        ax.plot(data_container.wavelength, com[3, 1], label='COM4', lw=0.7)
        ax.plot(data_container.wavelength, median_com[1], c='k', label='Median', lw=0.7)
        ax.plot(data_container.wavelength, polfit_y, c='fuchsia', label=f'pol. fit (deg={pol_deg})', lw=0.7)
        ax.set_ylim(-max_adr, max_adr)
        ax.legend(ncol=2, bbox_to_anchor=(0.5, 1), loc='lower center')
        ax.set_ylabel(r'$\Delta DEC$ (arcsec)')
        ax.set_xlabel(r'$\lambda$')

        fig.subplots_adjust(wspace=0.3)
        plt.close(fig)
        return polfit_x, polfit_y, fig
    return polfit_x, polfit_y
