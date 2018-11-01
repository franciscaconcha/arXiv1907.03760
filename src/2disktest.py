from amuse.lab import *
from amuse.couple.bridge import Bridge
from amuse.community.fractalcluster.interface import new_fractal_cluster_model
import numpy
from matplotlib import pyplot
import gzip
import copy
from scipy import interpolate
from decorators import timer


def luminosity_fit(mass):
    """
    Return stellar luminosity (in LSun) for corresponding mass, as calculated with Martijn's fit

    :param mass: stellar mass in MSun
    :return: stellar luminosity in LSun
    """
    if 0.12 < mass < 0.24:
        return (1.70294E16 * numpy.power(mass, 42.557)) | units.LSun
    elif 0.24 < mass < 0.56:
        return (9.11137E-9 * numpy.power(mass, 3.8845)) | units.LSun
    elif 0.56 < mass < 0.70:
        return (1.10021E-6 * numpy.power(mass, 12.237)) | units.LSun
    elif 0.70 < mass < 0.91:
        return (2.38690E-4 * numpy.power(mass, 27.199)) | units.LSun
    elif 0.91 < mass < 1.37:
        return (1.02477E-4 * numpy.power(mass, 18.465)) | units.LSun
    elif 1.37 < mass < 2.07:
        return (9.66362E-4 * numpy.power(mass, 11.410)) | units.LSun
    elif 2.07 < mass < 3.72:
        return (6.49335E-2 * numpy.power(mass, 5.6147)) | units.LSun
    elif 3.72 < mass < 10.0:
        return (6.99075E-1 * numpy.power(mass, 3.8058)) | units.LSun
    elif 10.0 < mass < 20.2:
        return (9.73664E0 * numpy.power(mass, 2.6620)) | units.LSun
    elif 20.2 < mass:
        return (1.31175E2 * numpy.power(mass, 1.7974)) | units.LSun
    else:
        return 0 | units.LSun


def find_nearest(array, value):
    """
    Return closest number to "value" in array
    :param array: Array of floats
    :param value: Value to find
    :return: Index of most similar number to value, and the number
    """
    array = numpy.asarray(array)
    idx = numpy.abs(array - value).argmin()
    return idx, array[idx]


def read_UVBLUE(filename, limits=None):
    """
    Read UVBLUE spectrum

    :param filename: Name of file to read, including path
    :param limits: [low, high] Lower and higher wavelength limits to read. If not specified, the whole spectrum is returned
    :return: Array with radiation in the range given by limits, or full wavelength range
    """

    column1 = []  # data
    column2 = []  # "fit"?

    with gzip.open(filename, 'r') as fuv:
        for line in fuv.readlines()[3:]:
            l1, l2 = line.split()
            column1.append(float(l1))
            column2.append(float(l2))

    if limits is not None:
        with gzip.open(filename, 'r') as fuv:
            wl = fuv.readlines()[1].split()
        steps, first, last = int(wl[0]), float(wl[1]), float(wl[2])

        # Find the correct range in the wavelengths, return corresponding radiation range
        wavelengths = numpy.linspace(first, last, steps)

        id_lower, lower = find_nearest(wavelengths, limits[0])
        id_higher, higher = find_nearest(wavelengths, limits[1])

        FUV_radiation = column1[id_lower:id_higher + 1]  # + 1 to include higher
        return numpy.array(FUV_radiation) | units.erg
    else:
        return numpy.array(column1)

    #pyplot.plot(column1)
    #pyplot.plot(column2)
    #pyplot.show()
    #return numpy.array(column1)


def integrate_FUV(filename, lower, higher):
    """
    Return total FUV radiation in SED between wavelenghts lower and higher.
    :param filename: Name for UVBLUE file to read
    :param lower: Lower limit for wavelength
    :param higher: Higher limit for wavelength
    :return: Total radiation between lower and higher wavelengths
    """
    radiation = read_UVBLUE(filename, [lower, higher])
    return radiation.sum()


def distance(star1, star2):
    """
    Return distance between star1 and star2
    :param star1:
    :param star2:
    :return:
    """
    return numpy.sqrt((star2.x - star1.x)**2 + (star2.y - star1.y)**2 + (star2.z - star1.z)**2)


def radiation_at_distance(rad, R):
    """
    Return radiation rad at distance R
    :param rad: total radiation of star in erg/s
    :param R: distance in cm
    :return: radiation of star at distance R, in erg * s^-1 * cm^-2
    """
    return rad / (4 * numpy.pi * R**2) | (units.erg / (units.s * units.cm**2))


def find_indices(column, val):
    """
    Return indices of column values in between which val is located.
    Return i,j such that column[i] < val < column[j]

    :param column: column where val is to be located
    :param val: number to be located in column
    :return: i, j indices
    """

    # The largest element of column less than val
    try:
        value_below = column[column < val].max()
    except ValueError:
        # If there are no values less than val in column, return smallest element of column
        value_below = column.min()
    # Find index
    index_i = numpy.where(column == value_below)[0][0]

    # The smallest element of column greater than val
    try:
        value_above = column[column > val].min()
    except ValueError:
        # If there are no values larger than val in column, return largest element of column
        value_above = column.max()
    # Find index
    index_j = numpy.where(column == value_above)[0][0]

    return int(index_i), int(index_j)


def viscous_timescale(star, alpha, temperature_profile, Rref, Tref, mu, gamma):
    """Compute the viscous timescale of the circumstellar disk.

    :param star: star with the circumstellar disk.
    :param alpha: turbulence mixing strenght.
    :param temperature_profile: negative of the temperature profile exponent, q in eq. (8).
    :param Rref: reference distance from the star at which the disk temperature is given.
    :param Tref: disk temperature at the reference distance for a star with solar luminosity.
    :param mu: molar mass of the gas in g/mol.
    :param gamma: radial viscosity dependence exponent.
    :return: viscous timescale in Myr
    """
    # To calculate luminosity
    stellar_evolution = SeBa()
    stellar_evolution.particles.add_particles(Particles(mass=star.mass))
    stellar_luminosity = stellar_evolution.particles.luminosity.value_in(units.LSun)
    stellar_evolution.stop()

    R = star.initial_characteristic_disk_radius
    T = Tref * (stellar_luminosity ** 0.25)
    q = temperature_profile
    M = constants.G * star.mass

    return mu * (R ** (0.5 + q)) * (M ** 0.5) / 3 / alpha / ((2 - gamma) ** 2) \
           / constants.molar_gas_constant / T / (Rref ** q)


def radius_containing_mass(star, mass):
    """ Return the radius (AU) encompassing mass in the star's disk.

    :param star: star with disk
    :param mass: amount of mass for which to find radius, in MJup
    :return: radius which encompasses mass, in AU
    """
    disk_characteristic_radius = star.disk_radius.value_in(units.AU)
    total_disk_mass = star.disk_mass.value_in(units.MJupiter)

    #print disk_characteristic_radius * numpy.log(1 / (1 - (mass.value_in(units.MJupiter)/total_disk_mass))) | units.AU
    return disk_characteristic_radius * numpy.log(1 / (1 - mass.value_in(units.MJupiter)/total_disk_mass)) | units.AU


@timer
def main(N, Rvir, Qvir, alpha, R, gas_presence, gas_expulsion, gas_expulsion_onset, gas_expulsion_timescale,
         t_ini, t_end, save_interval, run_number, save_path,
         gamma=1,
         mass_factor_exponent=0.2,
         truncation_parameter=1. / 3,
         gas_to_stars_mass_ratio=2.0,
         gas_to_stars_plummer_radius_ratio=1.0,
         plummer_radius=0.5 | units.parsec,
         dt=2000 | units.yr,
         temp_profile=0.5,
         Rref=1.0 | units.AU,
         Tref=280 | units.K,
         mu=2.3 | units.g / units.mol,
         filename=''):

    try:
        float(t_end)
        t_end = t_end | units.Myr
    except TypeError:
        pass

    max_stellar_mass = 100 | units.MSun
    stellar_masses = new_kroupa_mass_distribution(N, max_stellar_mass)  # , random=False)
    converter = nbody_system.nbody_to_si(stellar_masses.sum(), Rvir)
    stars = new_plummer_model(N, converter)
    stars.scale_to_standard(converter, virial_ratio=Qvir)

    stars.stellar_mass = stellar_masses

    # Bright stars: no disks; emit FUV radiation
    #bright_stars = [s for s in stars if s.stellar_mass.value_in(units.MSun) > 1.9]
    bright_stars = stars[stars.stellar_mass.value_in(units.MSun) > 1.9]

    # Small stars: with disks; radiation not considered
    #small_stars = [s for s in stars if s.stellar_mass.value_in(units.MSun) < 1.9]
    small_stars = stars[stars.stellar_mass.value_in(units.MSun) < 1.9]

    bright_stars.disk_mass = 0 | units.MSun
    small_stars.disk_mass = 0.1 * small_stars.stellar_mass

    small_stars.disk_radius = 100 * (small_stars.stellar_mass.value_in(units.MSun) ** 0.5) | units.AU
    bright_stars.disk_radius = 0 | units.AU

    #print small_stars.disk_radius

    # Start gravity code, add all stars
    gravity = ph4(converter)
    gravity.parameters.timestep_parameter = 0.01
    gravity.parameters.epsilon_squared = (100 | units.AU) ** 2
    gravity.particles.add_particles(stars)

    # Start stellar evolution code, add only massive stars
    stellar = SeBa()
    stellar.parameters.metallicity = 0.02
    stellar.particles.add_particles(bright_stars)

    #temp, temp2 = [], []
    lower_limit, upper_limit = 1000, 3000  # Limits for FUV, in Angstrom
    fuv_filename_base = "p00/t{0}g{1}p00k2.flx.gz"
    g = "00"

    gravity = ph4(converter)
    gravity.parameters.timestep_parameter = 0.01
    gravity.parameters.epsilon_squared = (100 | units.AU) ** 2
    gravity.particles.add_particles(stars)

    channel_from_stellar_to_framework \
        = stellar.particles.new_channel_to(stars)
    channel_from_stellar_to_gravity \
        = stellar.particles.new_channel_to(gravity.particles)
    channel_from_gravity_to_framework \
        = gravity.particles.new_channel_to(stars)

    Etot_init = gravity.kinetic_energy + gravity.potential_energy
    dE_gr = 0 | Etot_init.unit
    time = 0.0 | t_end.unit
    dt = stellar.particles.time_step.amin()

    # Read FRIED grid
    grid = numpy.loadtxt('friedgrid.dat', skiprows=2)

    # Getting only the useful parameters from the grid (not including Mdot)
    FRIED_grid = grid[:, [0, 1, 2, 4]]
    grid_log10Mdot = grid[:, 5]

    grid_stellar_masses = FRIED_grid[:, 0]
    grid_FUV = FRIED_grid[:, 1]
    grid_disk_mass = FRIED_grid[:, 2]
    grid_disk_radius = FRIED_grid[:, 3]

    time_total_mass_loss = numpy.zeros(len(small_stars))


    while time < t_end:
        dt = min(dt, t_end - time)
        stellar.evolve_model(time + dt/2)
        channel_from_stellar_to_gravity.copy()
        Etot_gr = gravity.kinetic_energy + gravity.potential_energy
        gravity.evolve_model(time + dt)
        dE_gr += (gravity.kinetic_energy + gravity.potential_energy - Etot_gr)

        #channel_to_framework.copy_attributes(["radius", "temperature",
        #                                      "luminosity"])
        #temp.append(stellar.particles[2].temperature.value_in(units.K))
        #temp2.append(round(stellar.particles[2].temperature.value_in(units.K) / 500) * 500)

        for s in bright_stars:  # For each massive/bright star

            # Calculate FUV luminosity of the bright star, in LSun
            lum = luminosity_fit(s.stellar_mass.value_in(units.MSun))

            z = 0
            for ss in small_stars:
                dist = distance(s, ss)
                radiation_ss = radiation_at_distance(lum.value_in(units.erg / units.s),
                                                     dist.value_in(units.cm))
                radiation_ss_G0 = radiation_ss.value_in(units.erg/(units.s * units.cm**2)) / 1.6E-3
                #print(ss.mass.value_in(units.MSun),
                #      radiation_ss_G0,
                #      ss.disk_mass.value_in(units.MJupiter),
                #      ss.disk_radius.value_in(units.AU)
                #      )

                # For the small star, I want to interpolate the photoevaporative mass loss
                # xi will be the point used for the interpolation. Adding star values...
                xi = numpy.ndarray(shape=(1, 4), dtype=float)
                xi[0][0] = ss.stellar_mass.value_in(units.MSun)
                xi[0][1] = radiation_ss_G0
                xi[0][2] = ss.disk_mass.value_in(units.MJupiter)
                xi[0][3] = ss.disk_radius.value_in(units.AU)

                # Building the subgrid (of FRIED grid) over which I will perform the interpolation
                subgrid = numpy.ndarray(shape=(8, 4), dtype=float)

                # Finding indices between which ss.mass is located in the grid
                stellar_mass_i, stellar_mass_j = find_indices(grid_stellar_masses, ss.stellar_mass.value_in(units.MSun))
                subgrid[0] = FRIED_grid[stellar_mass_i]
                subgrid[1] = FRIED_grid[stellar_mass_j]

                # Finding indices between which the radiation over the small star is located in the grid
                FUV_i, FUV_j =  find_indices(grid_FUV, radiation_ss_G0)
                subgrid[2] = FRIED_grid[FUV_i]
                subgrid[3] = FRIED_grid[FUV_j]

                # Finding indices between which ss.disk_mass is located in the grid
                disk_mass_i, disk_mass_j = find_indices(grid_disk_mass, ss.disk_mass.value_in(units.MJupiter))
                subgrid[4] = FRIED_grid[disk_mass_i]
                subgrid[5] = FRIED_grid[disk_mass_j]

                # Finding indices between which ss.disk_radius is located in the grid
                disk_radius_i, disk_radius_j = find_indices(grid_disk_radius, ss.disk_radius.value_in(units.AU))
                subgrid[6] = FRIED_grid[disk_radius_i]
                subgrid[7] = FRIED_grid[disk_radius_j]

                # Adding known values of Mdot, in the indices found above, to perform interpolation
                Mdot_values = numpy.ndarray(shape=(8, ), dtype=float)
                indices_list = [stellar_mass_i, stellar_mass_j,
                                FUV_i, FUV_j,
                                disk_mass_i, disk_mass_j,
                                disk_radius_i, disk_radius_j]
                for x in indices_list:
                    Mdot_values[indices_list.index(x)] = grid_log10Mdot[x]

                # Interpolate!
                # Photoevaporative mass loss in log10(MSun/yr)
                photoevap_Mdot = interpolate.griddata(subgrid, Mdot_values, xi, method="nearest")  # MSun/yr

                #Calculate total mass lost due to photoevaporation during dt
                total_photoevap_mass_loss = float(numpy.power(10, photoevap_Mdot) * dt.value_in(units.yr))

                time_total_mass_loss[z] += total_photoevap_mass_loss
                z += 1
                #print total_photoevap_mass_loss

                """if time.value_in(units.Myr) % 10 == 0:
                    #Remaining disk mass in MJupiter
                    #remaining_mass = (ss.disk_mass.value_in(units.MSun) - total_photoevap_mass_loss) * (1/954.79)*1E6 | units.MJupiter
                    remaining_mass = (ss.disk_mass.value_in(units.MSun) - time_total_mass_loss) * (1/954.79)*1E6 | units.MJupiter
                    new_radius = radius_containing_mass(ss, remaining_mass)
                    print gravity.model_time
                    print "accumulated mass loss:"
                    print time_total_mass_loss
                    print "old radius, new radius"
                    print ss.disk_radius, new_radius
                    ss.disk_radius = new_radius
                    time_total_mass_loss = 0"""

        stellar.evolve_model(time + dt)
        channel_from_stellar_to_gravity.copy()
        channel_from_gravity_to_framework.copy()
        time += dt
        #print(time)

    print "total mass loss:"
    print time_total_mass_loss

    for t, ss in zip(time_total_mass_loss, small_stars):
        print(ss.disk_radius.value_in(units.AU), radius_containing_mass(ss, (1 - t) * ss.disk_mass).value_in(units.AU))



        #print(round(stellar.particles[2].temperature.value_in(units.K) / 500) * 500)
        #write_set_to_file(stars, 'results/{0}.hdf5'.format(int(stellar.model_time.value_in(units.Myr))), 'amuse')

    #stellar.evolve_model(t_end)

    stellar.stop()

    #pyplot.plot(temp, label="Original temperatures")
    #pyplot.plot(temp2, label="Temperatures rounded to closest 500")
    #pyplot.legend()
    #pyplot.show()

    """times = numpy.arange(0, 10005, 5)
    T1, L1, R1 = [], [], []
    T2, L2, R2 = [], [], []
    T3, L3, R3 = [], [], []

    for t in times:
        stars = read_set_from_file('results/{0}.hdf5'.format(t), 'hdf5')
        T1.append(stars[0].temperature.value_in(units.K))
        L1.append(stars[0].luminosity.value_in(units.LSun))
        R1.append(stars[0].radius.value_in(units.RSun))

        T2.append(stars[1].temperature.value_in(units.K))
        L2.append(stars[1].luminosity.value_in(units.LSun))
        R2.append(stars[1].radius.value_in(units.RSun))

        T3.append(stars[2].temperature.value_in(units.K))
        L3.append(stars[2].luminosity.value_in(units.LSun))
        R3.append(stars[2].radius.value_in(units.RSun))

    x_label = "T [K]"
    y_label = "L [L$_\odot$]"
    fig = pyplot.figure(figsize=(10, 8), dpi=90)
    ax = pyplot.subplot(111)
    pyplot.xlabel(x_label)
    pyplot.ylabel(y_label)
    ax.set_yscale('log')
    #pyplot.gca().invert_xaxis()
    #pyplot.scatter(T1, L1, s=80*numpy.sqrt(R1), c=times, cmap='Greens')
    #pyplot.scatter(T2, L2, s=80*numpy.sqrt(R2), c=times, cmap='Blues')
    #pyplot.scatter(T3, L3, s=80*numpy.sqrt(R3), c=times, cmap='Oranges')

    pyplot.plot(times, L1)
    pyplot.plot(times, L2)
    pyplot.plot(times, L3)

    #pyplot.plot(T1[0], L1[0], 'rx')
    #pyplot.plot(T2[0], L2[0], 'rx')
    #pyplot.plot(T3[0], L3[0], 'rx')

    pyplot.show()"""

    """stars = read_set_from_file('stars.h5', 'hdf5')
    T = stars.temperature.value_in(units.K)
    L = stars.luminosity.value_in(units.LSun)
    R = stars.radius.value_in(units.RSun)

    #R = 80 * numpy.sqrt(R)
    pyplot.scatter(T, L, c='b', lw=0)
    pyplot.show()"""


def new_option_parser():
    from amuse.units.optparse import OptionParser
    result = OptionParser()

    # Simulation parameters
    result.add_option("-n", dest="run_number", type="int", default=0,
                      help="run number [%default]")
    result.add_option("-s", dest="save_path", type="string", default='.',
                      help="path to save the results [%default]")
    result.add_option("-i", dest="save_interval", type="int", default=50000 | units.yr,
                      help="time interval of saving a snapshot of the cluster [%default]")

    # Cluster parameters
    result.add_option("-N", dest="N", type="int", default=2000,
                      help="number of stars [%default]")
    result.add_option("-R", dest="Rvir", type="float",
                      unit=units.parsec, default=0.5,
                      help="cluster virial radius [%default]")
    result.add_option("-Q", dest="Qvir", type="float", default=0.5,
                      help="virial ratio [%default]")

    # Disk parameters
    result.add_option("-a", dest="alpha", type="float", default=1E-4,
                      help="turbulence parameter [%default]")
    result.add_option("-c", dest="R", type="float", default=30.0,
                      help="Initial disk radius [%default]")

    result.add_option("-e", dest="gas_expulsion_onset", type="float", default=0.6 | units.Myr,
                      help="the moment when the gas starts dispersing [%default]")
    result.add_option("-E", dest="gas_expulsion_timescale", type="float", default=0.1 | units.Myr,
                      help="the time after which half of the initial gas is expulsed assuming gas Plummer radius of 1 parsec [%default]")

    # Time parameters
    result.add_option("-I", dest="t_ini", type="int", default=0 | units.yr,
                      help="initial time [%default]")
    result.add_option("-t", dest="dt", type="int", default=2000 | units.yr,
                      help="time interval of recomputing circumstellar disk sizes and checking for energy conservation [%default]")
    result.add_option("-x", dest="t_end", type="float", default=2 | units.Myr,
                      help="end time of the simulation [%default]")

    # Gas behaviour
    result.add_option("-l", dest="gas_presence", action="store_false", default=False,
                      help="gas presence [%default]")
    result.add_option("-k", dest="gas_expulsion", action="store_false", default=False,
                      help="gas expulsion [%default]")

    return result


if __name__ == '__main__':
    o, arguments = new_option_parser().parse_args()
    main(**o.__dict__)
