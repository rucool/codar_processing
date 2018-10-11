#!/usr/bin/env python
"""
Convert CODAR Totals MATLAB .mat files generated using the HFRProgs toolbox into Climate Forecasting compliant netcdf files
@author Mike Smith
@email michaesm@marine.rutgers.edu
@purpose Convert MAT files created using the hfrProgs MATLAB toolbox into CF-1.6/NCEI Grid 2.0 compliant netCDF4 files
"""
import datetime as dt
import logging
import numpy as np
import os
import pandas as pd
import sys
import xarray as xr
from scipy.io import loadmat
from codar_processing.common import create_dir, timestamp_from_lluv_filename
from codar_processing.calc import gridded_index
from codar_processing.common import make_encoding
from configs import configs_default as configs

# Set up the parse_wave_files logger
logger = logging.getLogger(__name__)
log_level = 'INFO'
log_format = '%(module)s:%(levelname)s:%(message)s [line %(lineno)d]'
logging.basicConfig(stream=sys.stdout, format=log_format, level=log_level)


def matlab2datetime(matlab_time):
    """
    Convert Matlab time to Python datetime
    :param matlab_time: MATLAB datenum integer
    :return: Python Datetime
    """
    day = dt.datetime.fromordinal(int(matlab_time))
    day_frac = dt.timedelta(days=matlab_time % 1) - dt.timedelta(days=366)
    return day + day_frac


def main(grid, mat_file, save_dir, user_attributes, flags=None, domain=[], method='oi'):
    """
    Convert MAT files created using the hfrProgs MATLAB toolbox into CF-1.6/NCEI Grid 2.0 compliant netCDF4 files
    :param grid: CSV file containing lon,lat grid information
    :param mat_file: Filepath to MAT file containing HFRProgs
    :param save_dir: Directory to save netCDF files to
    :param user_attributes: User defined dataset attributes for netCDF global attribute. Required for CF/NCEI compliance
    :param flags: Dictionary of thresholds at which we should filter data above
    :param method: 'oi' or 'lsq'. OI is optimal interpolation. LSQ is unweighted least squares
    """
    fname = os.path.basename(mat_file)
    try:
        # load .mat file
        data = loadmat(mat_file, squeeze_me=True, struct_as_record=False)
        logging.debug('{} - MAT file successfully loaded '.format(fname))
    except Exception as err:
        logging.error('{} - {}. MAT file could not be loaded.'.format(fname, err))
        return

    if not domain:
        domain = data['TUV'].DomainName
        if not domain:
            domain = 'MARA'
    else:
        domain = 'MARA'

    time = timestamp_from_lluv_filename(mat_file)

    # convert matlab time to python datetime
    # time = dt.datetime.strptime(mat_time, '%Y_%m_%d_%H00')
    time_index = pd.date_range(time.strftime('%Y-%m-%d %H:%M:%S'), periods=1)  # create pandas datetimeindex from time
    time_string = time.strftime('%Y%m%dT%H%M%SZ')  # create timestring from time

    file_name = 'RU_{}_{}.nc'.format(domain, time_string)
    file_and_path = os.path.join(save_dir, file_name)

    try:
        logging.debug('{} - Saving file data to variables'.format(fname))
        # load longitude and latitude data associated with variables
        lonlat = data['TUV'].LonLat.astype(np.float32)

        # create variables for eastward and northward velocities
        u = data['TUV'].U.astype(np.float32)
        v = data['TUV'].V.astype(np.float32)
        u_units = data['TUV'].UUnits
        v_units = data['TUV'].VUnits

        maxspd = data['TUV'].OtherMetadata.cleanTotals.maxspd

        if method == 'oi':
            # create variables for associated error values
            u_err = data['TUV'].ErrorEstimates.Uerr.astype(np.float32)
            v_err = data['TUV'].ErrorEstimates.Verr.astype(np.float32)
            uv_covariance = data['TUV'].ErrorEstimates.UVCovariance

            # Data Processing Information
            num_rads = data['TUV'].OtherMatrixVars.makeTotalsOI_TotalsNumRads.astype(int)
            min_rads = data['TUV'].OtherMetadata.makeTotalsOI.parameters.MinNumRads
            min_sites = data['TUV'].OtherMetadata.makeTotalsOI.parameters.MinNumSites
            mdlvar = data['TUV'].OtherMetadata.makeTotalsOI.parameters.mdlvar
            errvar = data['TUV'].OtherMetadata.makeTotalsOI.parameters.errvar
            sx = data['TUV'].OtherMetadata.makeTotalsOI.parameters.sx
            sy = data['TUV'].OtherMetadata.makeTotalsOI.parameters.sy
            temporal_threshold = data['TUV'].OtherMetadata.makeTotalsOI.parameters.tempthresh
            processing_parameters = [maxspd, min_sites, min_rads, temporal_threshold, sx, sy, mdlvar, errvar]
            processing_parameters_info = '1) Maximum Total Speed Threshold (cm s-1)\n'
            processing_parameters_info += '2) Minimum number of radial sites\n'
            processing_parameters_info += '3) Minimum number of radial vectors\n'
            processing_parameters_info += '4) Temporal search window for radial solutions (Fraction of a day)\n'
            processing_parameters_info += '5) Decorrelation scales in the north direction\n'
            processing_parameters_info += '6) Decorrelation scales in the east direction\n'
            processing_parameters_info += '7) Signal variance of the surface current fields (cm2 s-2)\n'
            processing_parameters_info += '8) Data error variance of the input radial velocities (cm2 s-2)\n'

        elif method == 'lsq':
            # create variables for associated error values
            u_err = data['TUV'].ErrorEstimates[1].Uerr.astype(np.float32)
            v_err = data['TUV'].ErrorEstimates[1].Verr.astype(np.float32)
            uv_covariance = data['TUV'].ErrorEstimates[1].UVCovariance.astype(np.float32)

            # Data Processing Information
            num_rads = data['TUV'].OtherMatrixVars.makeTotals_TotalsNumRads.astype(int)
            min_rads = data['TUV'].OtherMetadata.makeTotals.parameters.MinNumRads
            min_sites = data['TUV'].OtherMetadata.makeTotals.parameters.MinNumSites
            spatial_threshold = data['TUV'].OtherMetadata.makeTotals.parameters.spatthresh
            temporal_threshold = data['TUV'].OtherMetadata.makeTotals.parameters.tempthresh
            processing_parameters = [maxspd, min_sites, min_rads, temporal_threshold, spatial_threshold]
            processing_parameters_info = '1) Maximum Total Speed Threshold (cm s-1)\n'
            processing_parameters_info += '2) Minimum number of radial sites.\n'
            processing_parameters_info += '3) Minimum number of radial vectors.\n'
            processing_parameters_info += '4) Temporal search window for radial solutions (Fractions of a day)\n'
            processing_parameters_info += '5) Spatial search radius for radial solutions (km)\n'
    except AttributeError as err:
        logging.error('{} - {}. MAT file missing variable needed to create netCDF4 file'.format(fname, err))
        return

    # Create a grid to shape 1d data
    lon = np.unique(grid['lon'].values.astype(np.float32))
    lat = np.unique(grid['lat'].values.astype(np.float32))
    [x, y] = np.meshgrid(lon, lat)

    # Create a dictionary of variables that we want to grid
    data_dict = dict(u=u,
                     v=v,
                     u_err=u_err,
                     v_err=v_err,
                     uv_covariance=uv_covariance,
                     num_radials=num_rads,)

    logging.debug('{} - Gridding data to 2d grid'.format(fname))
    # convert 1d data into 2d gridded form. data_dict must be a dictionary.
    x_ind, y_ind = gridded_index(x, y, lonlat[:, 0], lonlat[:, 1])

    for key in data_dict.keys():
        temp_data = np.matlib.tile(np.nan, x.shape)
        temp_data[(y_ind, x_ind)] = data_dict[key]

        # expand dimensions for time and depth
        count = 0
        while count < 2:  # add two dimensions to from of array for time and z (depth)
            temp_data = np.expand_dims(temp_data, axis=0)
            count = count + 1
            data_dict[key] = temp_data

    logging.debug('{} - Loading data into xarray dataset'.format(fname))

    # initialize xarray dataset. Add variables. Add coordinates
    ds = xr.Dataset()
    coords = ('time', 'z', 'lat', 'lon')
    ds['u'] = (coords, np.float32(data_dict['u']))
    ds['v'] = (coords, np.float32(data_dict['v']))
    ds['u_err'] = (coords, np.float32(data_dict['u_err']))
    ds['v_err'] = (coords, np.float32(data_dict['v_err']))
    ds['uv_covariance'] = (coords, np.float32(data_dict['uv_covariance']))
    ds['num_radials'] = (coords, data_dict['num_radials'])

    ds.coords['lon'] = lon
    ds.coords['lat'] = lat
    ds.coords['z'] = np.array([np.float32(0)])
    ds.coords['time'] = time_index

    if flags:
        for k, v in flags.items():
            ds = ds.where(ds[k] <= v)

    ds['processing_parameters'] = (('parameters'), processing_parameters)

    # Grab min and max time in dataset for entry into global attributes for cf compliance
    time_start = ds['time'].min().data
    time_end = ds['time'].max().data

    global_attributes = configs.netcdf_global_attributes(user_attributes, time_start, time_end)

    global_attributes['geospatial_lat_min'] = lat.min()
    global_attributes['geospatial_lat_max'] = lat.max()
    global_attributes['geospatial_lon_min'] = lon.min()
    global_attributes['geospatial_lon_max'] = lon.max()
    if method == 'oi':
        global_attributes['method'] = 'Optimal Interpolation'
    elif method == 'lsq':
        global_attributes['method'] = 'Unweighted Least Squares'

    logging.debug('{} - Assigning global attributes to dataset'.format(fname))
    ds = ds.assign_attrs(global_attributes)

    logging.debug('{} - Assigning local attributes to each variable in dataset'.format(fname))
    # set time attribute
    ds['time'].attrs['standard_name'] = 'time'

    # Set lon attributes
    ds['lon'].attrs['long_name'] = 'Longitude'
    ds['lon'].attrs['standard_name'] = 'longitude'
    ds['lon'].attrs['short_name'] = 'lon'
    ds['lon'].attrs['units'] = 'degrees_east'
    ds['lon'].attrs['axis'] = 'X'
    ds['lon'].attrs['valid_min'] = np.float32(-180.0)
    ds['lon'].attrs['valid_max'] = np.float32(180.0)

    # Set lat attributes
    ds['lat'].attrs['long_name'] = 'Latitude'
    ds['lat'].attrs['standard_name'] = 'latitude'
    ds['lat'].attrs['short_name'] = 'lat'
    ds['lat'].attrs['units'] = 'degrees_north'
    ds['lat'].attrs['axis'] = 'Y'
    ds['lat'].attrs['valid_min'] = np.float32(-90.0)
    ds['lat'].attrs['valid_max'] = np.float32(90.0)

    # Set depth attributes
    ds['z'].attrs['long_name'] = 'Average Depth of Sensor'
    ds['z'].attrs['standard_name'] = 'depth'
    ds['z'].attrs['comment'] = 'Derived from mean value of depth variable'
    ds['z'].attrs['units'] = 'm'
    ds['z'].attrs['axis'] = 'Z'
    ds['z'].attrs['positive'] = 'down'

    # Set u attributes
    ds['u'].attrs['long_name'] = 'Eastward Surface Current (cm/s)'
    ds['u'].attrs['standard_name'] = 'surface_eastward_sea_water_velocity'
    ds['u'].attrs['short_name'] = 'u'
    ds['u'].attrs['units'] = u_units
    ds['u'].attrs['valid_min'] = np.float32(-300)
    ds['u'].attrs['valid_max'] = np.float32(300)
    ds['u'].attrs['coordinates'] = 'lon lat'
    ds['u'].attrs['grid_mapping'] = 'crs'

    # Set v attributes
    ds['v'].attrs['long_name'] = 'Northward Surface Current (cm/s)'
    ds['v'].attrs['standard_name'] = 'surface_northward_sea_water_velocity'
    ds['v'].attrs['short_name'] = 'v'
    ds['v'].attrs['units'] = v_units
    ds['v'].attrs['valid_min'] = np.float32(-300)
    ds['v'].attrs['valid_max'] = np.float32(300)
    ds['v'].attrs['coordinates'] = 'lon lat'
    ds['v'].attrs['grid_mapping'] = 'crs'

    # Set u_err attributes
    ds['u_err'].attrs['units'] = '1'
    ds['u_err'].attrs['valid_min'] = np.float32(0)
    ds['u_err'].attrs['valid_max'] = np.float32(1)
    ds['u_err'].attrs['coordinates'] = 'lon lat'
    ds['u_err'].attrs['grid_mapping'] = 'crs'

    # Set v_err attributes
    ds['v_err'].attrs['units'] = '1'
    ds['v_err'].attrs['valid_min'] = np.float32(0)
    ds['v_err'].attrs['valid_max'] = np.float32(1)
    ds['v_err'].attrs['coordinates'] = 'lon lat'
    ds['v_err'].attrs['grid_mapping'] = 'crs'

    if method == 'lsq':
        ds['u_err'].attrs['long_name'] = 'Associated GDOP mapping error value associated with eastward velocity component'
        ds['v_err'].attrs['long_name'] = 'Associated GDOP mapping error value associated with northward velocity component'
        ds['u_err'].attrs['comment'] = 'velocity measurements with error values over 1.5 are of questionable quality'
        ds['v_err'].attrs['comment'] = 'velocity measurements with error values over 1.5 are of questionable quality'
    elif method == 'oi':
        ds['u_err'].attrs['long_name'] = 'Normalized uncertainty error associated with eastward velocity component'
        ds['v_err'].attrs['long_name'] = 'Normalized uncertainty error associated with northward velocity component'
        ds['u_err'].attrs['comment'] = 'velocity measurements with error values over 0.6 are of questionable quality'
        ds['v_err'].attrs['comment'] = 'velocity measurements with error values over 0.6 are of questionable quality'

    # Set uv_covariance attributes
    ds['uv_covariance'].attrs['long_name'] = 'Eastward and Northward covariance directional information of u and v'
    ds['uv_covariance'].attrs['units'] = '1'
    ds['uv_covariance'].attrs['comment'] = 'directional information of u and v'
    ds['uv_covariance'].attrs['coordinates'] = 'lon lat'
    ds['uv_covariance'].attrs['grid_mapping'] = 'crs'

    # Set num_radials attributes
    ds['num_radials'].attrs['long_name'] = 'Number of radial measurements used to calculate each totals velocity'
    ds['num_radials'].attrs['comment'] = 'totals are not calculated with fewer than 3 contributing radial measurements from 2 sites'
    ds['num_radials'].attrs['coordinates'] = 'lon lat'
    ds['num_radials'].attrs['grid_mapping'] = 'crs'

    # Set num_radials attributes
    ds['processing_parameters'].attrs['long_name'] = 'General and method specific processing parameter information'
    ds['processing_parameters'].attrs['comment'] = processing_parameters_info
    # ds['processing_parameters'].attrs['coordinates'] = 'parameters'

    # encoded_sites = data['TUV'].OtherMatrixVars.makeTotalsOI_TotalsSiteCode

    # # load site ids that are set in our mysqldb
    # query_obj = Session.query(tables.Sites)
    # site_encoding = pd.read_sql(query_obj.statement, query_obj.session.bind)
    #
    # # convert site codes into binary numbers
    # binary_positions_mat = data['conf'].Radials.Sites.shape[0]
    #
    # decoded_sites_mat = np.tile(0, (encoded_sites.shape[0], binary_positions_mat))
    #
    # for i, v in enumerate(encoded_sites):
    #     decoded_sites_mat[i] = np.array(map(int, np.binary_repr(v, width=binary_positions_mat)))
    #
    # decoded_sites_mat = np.fliplr(decoded_sites_mat)
    #
    # decoded_sites_new = np.tile(0, (encoded_sites.shape[0], np.max(site_encoding['id'])))
    #
    # for site in data['RTUV']:
    #     print site.SiteName + ' ' + str(np.log2(site.SiteCode))
    #     ind_mat = np.log2(site.SiteCode)
    #     ind_real = site_encoding['id'].loc[site_encoding['site'] == site.SiteName].values[0]
    #     decoded_sites_new[:, ind_real] = decoded_sites_mat[:, int(ind_mat)]
    #
    # decoded_sites_new = np.fliplr(decoded_sites_new)
    # new_encoded_sites = [bool2int(x[::-1]) for x in decoded_sites_new]
    # flag_masks = [2 ** int(x) for x in site_encoding['id'].tolist()]
    # flag_meanings = ' '.join(site_encoding['site'].tolist())

    # ds['site_code_flags'].attrs['long_name'] = 'Bitwise AND representation of site contributions to a radial point'
    # # ds['site_code_flags'].attrs['_FillValue'] = int(0)
    # ds['site_code_flags'].attrs['flag_masks'] = 'b '.join(map(str, flag_masks))
    # ds['site_code_flags'].attrs['flag_meanings'] = flag_meanings
    # ds['site_code_flags'].attrs['comment'] = 'Values are binary sums. Must be converted to binary representation to interpret flag_masks and flag_meanings'

    logging.debug('{} - Setting variable encoding and fill values for netCDF4 output'.format(fname))

    # encode variables for export to netcdf
    encoding = make_encoding(ds)
    encoding['lon'] = dict(zlib=False, _FillValue=False)
    encoding['lat'] = dict(zlib=False, _FillValue=False)
    encoding['z'] = dict(zlib=False, _FillValue=False)

    # add container variables that contain no data
    kwargs = dict(crs=None, instrument=None)
    ds = ds.assign(**kwargs)

    # Set crs attributes
    ds['crs'].attrs['grid_mapping_name'] = 'latitude_longitude'
    ds['crs'].attrs['inverse_flattening'] = 298.257223563
    ds['crs'].attrs['long_name'] = 'Coordinate Reference System'
    ds['crs'].attrs['semi_major_axis'] = '6378137.0'
    ds['crs'].attrs['epsg_code'] = 'EPSG:4326'
    ds['crs'].attrs['comment'] = 'http://www.opengis.net/def/crs/EPSG/0/4326'

    ds['instrument'].attrs['long_name'] = 'CODAR SeaSonde High Frequency Radar'
    ds['instrument'].attrs['sensor_type'] = 'Direction-finding high frequency radar antenna'
    ds['instrument'].attrs['make_model'] = 'CODAR SeaSonde'
    ds['instrument'].attrs['serial_number'] = 1

    # Create save directory if it doesn't exist.
    create_dir(save_dir)

    logging.debug('{} - Saving dataset to netCDF4 file: {}'.format(fname, file_and_path))
    ds.to_netcdf(file_and_path, encoding=encoding, format='netCDF4', engine='netcdf4', unlimited_dims=['time'])
    logging.info('{} - netCDF4 file successfully created: {}'.format(fname, file_and_path))


if __name__ == '__main__':
    import glob

    # Define test inputs
    files = sorted(glob.glob('../../data/totals/mat/*.mat'))
    grid_file = '../../data/grid_files/maracoos_grid_6km_extended.txt'
    save_dir = '../../data/totals/nc/hourly'
    threshold = dict(u_err=0.6, v_err=0.6, uv_covariance=0.6)

    # load csv file containing the grid
    grid = pd.read_csv(grid_file, sep=',', header=None, names=['lon', 'lat'], delim_whitespace=True)

    user_attributes = dict(title='MARACOOS 6km Sea Surface Currents',
                           naming_authority='edu.rutgers.marine.rucool',
                           comment='Network maintained by MARACOOS. For oi_* global attribute explanations, see references attribute',
                           acknowledgment='This data is provided by the Mid-Atlantic Regional Association Coastal Ocean Observing System (MARACOOS). Funding is provided by the U.S. Integration Ocean Observing System (IOOS).',
                           standard_name_vocabulary='CF Standard Name Table v41',
                           creator_name='Michael Smith',
                           creator_email='michaesm@marine.rutgers.edu',
                           creator_url='rucool.marine.rutgers.edu',
                           institution='Center for Ocean Observing and Leadership, Department of Marine & Coastal Sciences, Rutgers University',
                           project='Mid-Atlantic Regional Association Coastal Ocean Observing System - High Frequency Radar Sea Surface Current Mapping',
                           sea_name='Mid-Atlantic Bight',
                           creator_type='person',
                           creator_institution='Rutgers University',
                           contributor_name='Scott Glenn, Josh Kohut, Hugh Roarty, Ethan Handel, Michael Smith, Laura Nazzaro, Teresa Updyke, Larry Atkinson, Rich Arena, Wendell Brown, Mike Muglia, Harvey Seim',
                           contributor_role='Principal Investigator, Principal Investigator, Principal Investigator, Hardware Maintenance, Data Manager, Data Manager, Hardware Maintenance, Principal Investigator, Hardware Maintenance, Principal Investigator, Hardware Maintenance, Principal Investigator',
                           platform='MARACOOS HF Radar 5MHz Network',
                           instrument='Network includes CODAR sites AMAG, ASSA, BLCK, BRIG, CEDR, CORE, DUCK, FARO, HATY, HEMP, HOOK, LISL, LOVE, MABO, MRCH, MVCO, NANT, NAUS, PYFC, and WILD',
                           references='http://maracoos.org/node/146 https://rucool.marine.rutgers.edu/facilities https://rucool.marine.rutgers.edu/data',
                           summary='Optimally Interpolated Total Vectors calculated by HFRProgs toolbox using MATLAB. Mercator lat/lon projection',
                           ncei_template_version='NCEI_NetCDF_Grid_Template_v2.0',
                           history='Hourly codar radial data combined into one hourly file containing vectors.',
                           cdm_data_type='Grid',
                           source='CODAR SeaSonde Surface Current Mapping Device',
                           processing_level='Level 3',
                           keywords='Environmental Advisories > Marine Advisories > Marine Weather/Forecast, Oceans > Coastal Processes, Oceans > Ocean Circulation, Oceans > Ocean Waves, Oceans > Ocean Winds, Oceans > Ocean Tides, Spectral/Engineering > Radar',
                           publisher_name='NOAA National Centers for Environmental Information',
                           publisher_email='ncei.info@noaa.gov',
                           publisher_url='www.ncei.noaa.gov')

    for file in files:
        main(grid, file, save_dir, user_attributes, threshold)
