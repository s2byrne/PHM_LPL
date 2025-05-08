# -- driver_run_forecast_LV1.py  --
# master python script to do a full LV1 forecast simulation


import sys
import pickle
import matplotlib.pyplot as plt
import numpy as np
import os
import subprocess
import time
from datetime import datetime, timezone
#import cartopy.crs as ccrs
#import cartopy.feature as cfeature
#import matplotlib.pyplot as plt
#import numpy as np
#import scipy.ndimage as ndimage
#import xarray as xr
#import netCDF4 as nc
#from scipy.interpolate import RegularGridInterpolator

##############

sys.path.append('../sdpm_py_util')

import atm_functions as atmfuns
import ocn_functions as ocnfuns
import grid_functions as grdfuns
import util_functions as utlfuns 
import plotting_functions as pltfuns
from util_functions import s_coordinate_4
from get_PFM_info import get_PFM_info
from make_LV1_dotin_and_SLURM import make_LV1_dotin_and_SLURM
from run_slurm_LV1 import run_slurm_LV1

# figure out what the time is local and UTC
start_time = datetime.now()
utc_time = datetime.now(timezone.utc)
year_utc = utc_time.year
month_utc = utc_time.month
day_utc = utc_time.day
hour_utc = utc_time.hour



print("Starting: driver_run_forecast_LV1: Current local Time =", start_time, "UTC = ",utc_time)

if hour_utc < 12:
    hour_utc=12
    day_utc=day_utc-1  # this only works if day_utc \neq 1

yyyymmdd = "%d%02d%02d" % (year_utc, month_utc, day_utc)
    
#yyyymmdd = '20240717'
# the hour in Z of the forecast, hycom has forecasts once per day starting at 1200Z
hhmm='1200'
forecastZdatestr = yyyymmdd+hhmm+'Z'   # this could be used for model output to indicate when model was initialized.

yyyymmdd = '20240716'
print("Preparing forecast starting on ",yyyymmdd)


PFM=get_PFM_info()

# %%
run_type = 'forecast'

# we will use hycom for IC and BC
ocn_mod = 'hycom'
# we will use nam_nest for the atm forcing
atm_mod = 'nam_nest'
# we will use opendap, and netcdf to grab ocn, and atm data
get_method = 'open_dap_nc'

# get the ROMS grid as a dict
#fngr = '/Users/mspydell/research/FF2024/models/SDPM_mss/PFM_user/grids/GRID_SDTJRE_LV1.nc'
RMG = grdfuns.roms_grid_to_dict(PFM['lv1_grid_file'])



lv1_forc_dir = PFM['lv1_forc_dir']   #'/Users/mspydell/research/FF2024/models/SDPM_mss/atm_stuff/ocn_test_IC_file.nc'


west =  -124.5 + 360.0
east = -115 + 360.0
south = 28.0
north = 37.0

yyyymmdd='20240806'
yyyy = yyyymmdd[0:4]
mm = yyyymmdd[4:6]
dd = yyyymmdd[6:8]

# time limits
dstr0 = yyyy + '-' + mm + '-' + dd + 'T12:00'
dstr1 = yyyy + '-' + mm + '-' + str( int(dd) + 3 ) + 'T00:00'

vstr = 'surf_el,water_temp,salinity,water_u,water_v,depth'
full_fn_out = 'test.nc'

url='https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0/FMRC/runs/' 
url2 = 'GLBy0.08_930_FMRC_RUN_' + yyyy + '-' + mm + '-' + dd + 'T12:00:00Z' 
url3 = url + url2
cmd_list = ['ncks',
    '-d', 'time,'+dstr0+','+dstr1,
    '-d', 'lon,'+str(west)+','+str(east),
    '-d', 'lat,'+str(south)+','+str(north),
    '-v', vstr,
    url3 ,
    '-4', '-O', full_fn_out]
# old working command list
#cmd_list = ['ncks',
#    '-d', 'time,'+dstr0+','+dstr1,
#    '-d', 'lon,'+str(west)+','+str(east),
#    '-d', 'lat,'+str(south)+','+str(north),
#    '-v', vstr,
#    'https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0',
#    '-4', '-O', full_fn_out]

print(cmd_list)



# run ncks
tt0 = time.time()
print('entering suprocess.call(): at time ',tt0)
ret1 = subprocess.call(cmd_list)



#import ipdb; ipdb.set_trace()

# %%
# make a switch to see if this file exists. If it exists, we don't need to run the code in this block
# first the atm data
# get the data as a dict
# need to specify hhmm because nam forecast are produced at 6 hr increments
ATM = atmfuns.get_atm_data_as_dict(yyyymmdd,hhmm,run_type,atm_mod,get_method)
# put in a function to check to make sure that all the data is good
# put in a function to plot the raw atm data if we want to
pltfuns.plot_atm_fields(ATM, RMG, PFM)
print('done with plotting ATM fields')

# put the atm data on the roms grid, and rotate the velocities
# everything in this dict turn into the atm.nc file
ATM_R  = atmfuns.get_atm_data_on_roms_grid(ATM,RMG)
print('done with: atmfuns.get_atm_data_on_roms_grid(ATM,RMG)')
# all the fields plotted with the data on roms grid

pltfuns.plot_all_fields_in_one(ATM, ATM_R, RMG, PFM)
print('done with: pltfuns.plot_all_fields_in_one(ATM, ATM_R, RMG, PFM)')

# output a netcdf file of ATM_R
# make the atm .nc file here.
# fn_out is the name of the atm.nc file used by roms
fn_out = PFM['lv1_forc_dir'] + '/' + PFM['lv1_atm_file'] # LV1 atm forcing filename
print('driver_run_forcast_LV1: saving ATM file to ' + fn_out)
atmfuns.atm_roms_dict_to_netcdf(ATM_R,fn_out)
print('driver_run_forecast_LV1:  done with writing ATM file, Current time ', datetime.now())
# put in a function to plot the atm.nc file if we want to
pltfuns.load_and_plot_atm(RMG, PFM)
print('done with pltfuns.load_and_plot_atm(PFM)')

del ATM_R  # removing this from memory

# %%
# make the ocn IC and BC .nc files here
# fn*_out are the names of the the IC.nc and BC.nc roms files



# note, this function is hard wired to return 2.5 days of data
# also note that the first time of this data is yyyymmdd 12:00Z
# so we grab nam atm forecast data starting at this hour too.
OCN = ocnfuns.get_ocn_data_as_dict(yyyymmdd,run_type,ocn_mod,get_method)
print('driver_run_forecast_LV1: done with get_ocn_data_as_dict: Current time ',datetime.now() )
# add OCN plotting function here !!!!

# note this takes 24.5 minutes to run on my laptop
# 3 times this timed out
# will likely need to use a wget method and directly download .nc files (arh)
# maybe downloading the netcdf file would be quicker? 


# %%
# put the ocn data on the roms grid
print('starting: ocnfuns.hycom_to_roms_latlon(OCN,RMG)')
OCN_R  = ocnfuns.hycom_to_roms_latlon(OCN,RMG)
print('driver_run_forecast_LV1: done with hycom_to_roms_latlon')
# add OCN + OCN_R plotting function here !!!

# %%
# get the OCN_IC dictionary
OCN_IC = ocnfuns.ocn_r_2_ICdict(OCN_R,RMG)
print('driver_run_forecast_LV1: done with ocn_r_2_ICdict')
# add OCN_IC.nc plotting function here !!!!
ic_file_out = PFM['lv1_forc_dir'] + '/' + PFM['lv1_ini_file']
ocnfuns.ocn_roms_IC_dict_to_netcdf(OCN_IC, icfileout)


# %%
# get the OCN_BC dictionary
bc_file_out = PFM['lv1_forc_dir'] + '/' + PFM['lv1_bc_file']
OCN_BC = ocnfuns.ocn_r_2_BCdict(OCN_R,RMG)
print('driver_run_forecast_LV1: done with ocn_r_2_BCdict')
# %%
ocnfuns.ocn_roms_BC_dict_to_netcdf(OCN_BC, bc_file_out)


print('driver_run_forecast_LV1:  now make .in and .sb files')

pfm_driver_src_dir = os.getcwd()
os.chdir('../sdpm_py_util')
make_LV1_dotin_and_SLURM( PFM )

# run command will be
run_slurm_LV1(PFM)


os.chdir(pfm_driver_src_dir)




# postprocess figure generation
# plot fields from his.nc


