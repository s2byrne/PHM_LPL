"""
This runs ROMS for one or more days, allowing for either a forecast or backfill.

This code:
- runs forecast as three separate days
- saves blowup log and last history files

testing on mac:
python3 driver_roms3.py -g cas6 -t v00 -x uu0mb -s continuation -0 2021.01.01 -np 196 -N 28 --get_forcing False --run_roms False --move_his False

testing on mox:
python3 driver_roms3.py -g cas6 -t v00 -x uu0mb -s continuation -0 2021.01.01 -np 196 -N 28 --short_roms True < /dev/null > uu0mb_test.log &

production run on mox:
python3 driver_roms3.py -g cas6 -t v00 -x uu0mb -s continuation -0 2021.01.01 -1 2021.01.02 -np 196 -N 28 < /dev/null > uu0mb_a.log &
python3 driver_roms3.py -g cas6 -t v00 -x uu0mb -0 2021.01.03 -1 2021.12.31 -np 196 -N 28 < /dev/null > uu0mb_b.log &
"""

import sys, os
import shutil
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
from time import time, sleep
import random
import string

# these are functions specifically for this model

testing = 1
if testing ==1:
    from importlib import reload

# add the path by hand so that it will run on klone or mox (outside of loenv)
#pth = Path(__file__).absolute().parent.parent / 'sdpm_py_util'

# Lfun has a bunch of functions that help in running the model
import Lfun
if testing ==1:
    reload(Lfun)

# now lets parse the input arguments
parser = argparse.ArgumentParser()
args = Lfun.parserfun(parser)

# check for required arguments this is specific to the particular driver, here roms
argsd = args.__dict__

for a in ['gridname', 'tag', 'ex_name', 'run_type', 'start_type', 'np_num', 'cores_per_node']:
    if argsd[a] == None:
        print('*** Missing required argument for driver_roms.py: ' + a)
        sys.exit()

# get Ldir, this contains all of the model information, like paths and location of executable that are fixed
# it will also add in things from the invoking argument list, like t1 t2
Ldir = Lfun.Lstart(gridname=args.gridname, tag=args.tag, ex_name=args.ex_name)

# reformat the model times for easy manipulation, t fmt YYYY:MM:DD, s fmt YYYY:MM:DD HH:MM:SS
dt0, ds0, dt1, ds1 = Lfun.time_fun(args,Ldir)

# dict of dates for this simulation
dlist=Lfun.date_list_utility(dt0, dt1,Ldir['daystep'])

# dict of input files needed to run this simulation, includes raw and nc files
infiles = Lfun.get_input_nc_file_names(args,Ldir,dlist)

# dict of whether or not there are input netcdf files, needed for running ROMS
gotinncfiles = Lfun.got_input_nc_files(infiles)

# dict of whether or not there are input raw files, needed to make input .nc files 
gotinrawfiles = Lfun.got_input_raw_files(infiles)

# make (interpolate from 1 grid to another) and grab files using ncks if needed 
file_msg = Lfun.make_get_needed_input_files(dlist,args,Ldir,infiles,gotinncfiles,gotinrawfiles)

# are the files there now? these both need to be all True for ROMS to run
gotinncfiles2  = Lfun.got_input_nc_files(infiles)
gotinrawfiles2 = Lfun.got_input_raw_files(infiles)

if testing==1:
    print('runs up to here in driver_roms.py')
    sys.exit()


# Loop over days
dt = dt0
start_type = args.start_type

print('Running ROMS %s %s-%s' % (args.run_type, ds0, ds1))

while dt <= dt1:        
    # update start_type after the first day
    if (dt != dt0) and (start_type in ['new', 'continuation']):
        start_type = 'perfect'
        
    f_string = 'f' + dt.strftime(Lfun.ds_fmt)
    f_string0 = 'f' + dt0.strftime(Lfun.ds_fmt) # used for forcing a forecast
    print('')
    print((' ' + f_string + ' ').center(30,'='))
    print(' > started at %s' % (datetime.now().strftime('%Y.%m.%d %H:%M:%S')))
    sys.stdout.flush()
    
    # Set various paths.
    force_dir = Ldir['LOo'] / 'forcing' / Ldir['gridname'] / f_string
    roms_out_dir = Ldir['roms_out'] / Ldir['gtagex'] / f_string
    log_file = roms_out_dir / 'log.txt'
    
    # Look to see if there is a user instance of this dot_in, and if so, use it.
    user_dot_in_dir = Ldir['LOu'] / 'dot_in' / Ldir['gtagex']
    dot_in_dir = Ldir['LO'] / 'dot_in' / Ldir['gtagex']
    if user_dot_in_dir.is_dir():
        dot_in_dir = user_dot_in_dir
    
    # Decide where to look for executable.
    # use updated ROMS
    roms_ex_dir = Ldir['parent'] / 'LO_roms_user' / Ldir['ex_name']
    roms_ex_name = 'romsM'
    
    print(str(roms_out_dir)) # always print this
    if args.verbose:
        print(' - force_dir:    ' + str(force_dir))
        print(' - dot_in_dir:   ' + str(dot_in_dir))
        print(' - log_file:     ' + str(log_file))
        print(' - roms_ex_dir:  ' + str(roms_ex_dir))
        sys.stdout.flush()
    
    # Get the list of which forcing folders to copy
    force_dict = dict()
    with open(dot_in_dir / 'forcing_list.csv', 'r') as f:
        for line in f:
            which_force, force_choice = line.strip().split(',')
            force_dict[which_force] = force_choice
    
    if args.get_forcing:
        for fff in range(10):
            # We put this in a loop to allow it to try several times. This is prompted
            # by intermittent ssh_exchange_identification errors, particularly on mox.
            got_forcing = True
            tt0 = time()
            # Name the place where the forcing files will be copied from
            remote_dir = remote_user + '@' + remote_machine + ':' + remote_dir0
            Lfun.make_dir(force_dir, clean=True)
            # Copy the forcing files, one folder at a time.
            for force in force_dict.keys():
                if force == 'open':
                    pass
                else:
                    force_choice = force_dict[force]
                    if args.run_type == 'backfill':
                        F_string = f_string
                    elif args.run_type == 'forecast':
                        F_string = f_string0
                    cmd_list = ['scp','-r',
                        remote_dir + '/LO_output/forcing/' + Ldir['gridname'] + '/' + F_string + '/' + force_choice,
                        str(force_dir)]
                    proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = proc.communicate()
                    if len(stderr) > 0:
                        got_forcing = False
                    Lfun.messages(stdout, stderr, 'Copy forcing ' + force_choice, args.verbose)
            print(' - time to get forcing = %d sec' % (time()-tt0))
            sys.stdout.flush()
            if got_forcing == True:
                break
            else:
                sleep(60)
        if got_forcing == False:
            print('Error getting forcing, fff = %d' % (fff))
            sys.exit()
    else:
        print(' ** skipped getting forcing')
        
    # Loop over blow ups.
    blow_ups = 0
    if args.short_roms:
        blow_ups_max = 0
    else:
        blow_ups_max = 5
    roms_worked = False
    while blow_ups <= blow_ups_max:
        # print((' - Blow-ups = ' + str(blow_ups)))
        sys.stdout.flush()

        if args.run_dot_in:
            # Make the dot_in file.  NOTE: roms_out_dir is made clean by make_dot_in.py
            cmd_list = ['python3', str(dot_in_dir / 'make_dot_in.py'),
                        '-g', args.gridname, '-t', args.tag, '-x', args.ex_name,
                        '-r', 'backfill', '-s', start_type,
                        '-d', dt.strftime(Lfun.ds_fmt),
                        '-bu', str(blow_ups), '-np', str(args.np_num),
                        '-short_roms', str(args.short_roms)]
            proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            Lfun.messages(stdout, stderr, 'Make dot in', args.verbose)
            
            # Create batch script
            if 'klone' in Ldir['lo_env']:
                batch_name = 'klone3_make_batch.py'
            elif 'mox' in Ldir['lo_env']:
                batch_name = 'mox3_make_batch.py'
            else: # for testing
                batch_name = 'mox3_make_batch.py'
            # generate a random jobname
            jobname = ''.join(random.choices(string.ascii_lowercase, k=5))
            cmd_list = ['python3', str(Ldir['LO'] / 'driver' / 'batch' / batch_name),
                '-xd', str(roms_ex_dir),
                '-rxn', roms_ex_name,
                '-rod', str(roms_out_dir),
                '-np', str(args.np_num),
                '-N', str(args.cores_per_node),
                '-x', Ldir['ex_name'],
                '-j', jobname]
            proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            Lfun.messages(stdout, stderr, 'Create batch script', args.verbose)
        else:
            print(' ** skipped making dot_in and batch script')
            args.run_roms = False # never run ROMS if we skipped making the dot_in
        
        if args.run_roms:
            tt0 = time()
            # Run ROMS using the batch script.
            if 'klone' in Ldir['lo_env']:
                cmd_list = ['sbatch', '-p', 'compute', '-A', 'macc',
                    str(roms_out_dir / 'klone_batch.sh')]
            elif 'mox' in Ldir['lo_env']:
                cmd_list = ['sbatch', '-p', 'macc', '-A', 'macc',
                    str(roms_out_dir / 'mox_batch.sh')]
            proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # now we need code to wait until the run has completed
            
            # these are for checking on the run using squeue
            if 'mox' in Ldir['lo_env']:
                cmd_list = ['squeue', '-p', 'macc']
            elif 'klone' in Ldir['lo_env']:
                cmd_list = ['squeue', '-A', 'macc']

            # first figure out if it has started
            for rrr in range(10):
                if rrr == 9:
                    print('Took too long for job to start: quitting')
                    sys.exit()
                proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                if jobname not in stdout.decode():
                    if args.verbose:
                        print('still waiting for run to start ' + str(rrr))
                        sys.stdout.flush()
                elif jobname in stdout.decode():
                    if args.verbose:
                        print('run started ' + str(rrr))
                        sys.stdout.flush()
                    break
                sleep(10)

            # and then figure out if it has finished
            for rrr in range(60):
                proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                Lfun.messages(stdout, stderr, 'Finished?', args.verbose)
                if jobname in stdout.decode():
                    if args.verbose:
                        print('still waiting ' + str(rrr))
                        sys.stdout.flush()
                    else:
                        pass
                elif (jobname not in stdout.decode()) and (len(stderr) == 0):
                    print(' - time to run ROMS = %d sec' % (time()-tt0))
                    sys.stdout.flush()
                    break
                else:
                    pass
                sleep(120)
    
            # The code here is a lot of claptrap to make sure there is a log file
            
            # A bit of checking to make sure that the log file exists...
            lcount = 0
            while not log_file.is_file():
                sleep(10)
                if args.verbose:
                    print(' - lcount = %d' % (lcount))
                    sys.stdout.flush()
                lcount += 1
                
                # trap for possible sbatch errors
                if lcount >= 10:
                    print(' - too long to write log.txt, assume there was some sbatch error')
                    print(' - generating a fake log.txt file')
                    with open(log_file,'w') as ff:
                        ff.write('LO_RERUN')
                    break # escape from the lcount while-loop
                    
            # ...and that it is done being written to.
            llcount = 0
            log_done = False
            while log_done == False:
                sleep(3)
                if 'mox' in Ldir['lo_env']:
                    cmd_list = ['/usr/sbin/lsof', '-u', local_user,'|','grep',str(log_file)]
                else:
                    cmd_list = ['lsof', '-u', local_user,'|','grep',str(log_file)]
                proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                if args.verbose:
                    print(' - llcount = %d' % (llcount))
                    sys.stdout.flush()
                llcount += 1
                if str(log_file) not in stdout.decode():
                    if args.verbose:
                        print(' - log done and closed')
                        sys.stdout.flush()
                    log_done = True
                    
            # Look in the log file to see what happened, and decide what to do.
            roms_worked = False
            with open(log_file, 'r') as ff:
                found_line = False
                for line in ff:
                    if ('Blowing-up' in line) or ('BLOWUP' in line) or ('Blows up' in line):
                        print(' - Run blew up, blow ups = ' + str(blow_ups))
                        found_line = True
                        roms_worked = False
                        
                        # save some info if the run blew up
                        print(' - blew up at %s' % (datetime.now().strftime('%Y.%m.%d %H:%M:%S')))
                        roms_bu_out_dir = Ldir['roms_out'] / Ldir['gtagex'] / (f_string + '_blowup')
                        Lfun.make_dir(roms_bu_out_dir, clean=True)
                        try:
                            shutil.copy(roms_out_dir / 'log.txt', roms_bu_out_dir)
                            if args.verbose:
                                print(' - log.txt file saved to %s' % (str(roms_bu_out_dir)))
                        except FileNotFoundError:
                            print(' - log.txt file not found')
                        #
                        try:
                            his_list = roms_out_dir.glob('ocean_his_*.nc')
                            his_list = list(his_list)
                            his_list.sort()
                            if len(his_list) > 0:
                                shutil.copy(his_list[-1], roms_bu_out_dir)
                                if args.verbose:
                                    print(' - %s saved to %s' % (his_list[-1].name, str(roms_bu_out_dir)))
                            else:
                                print(' - no history files found')
                        except Exception as e:
                            print(' - problem saving blow-up history file:')
                            print(e)
                        break
                    elif 'LO_RERUN' in line:
                        print(' - LO_RERUN: Trying run again.')
                        # This is not a perfect solution because it increments blow_ups,
                        # which will slow things down, but at least it provides an end to the
                        # attempted reruns.
                        found_line = True
                        roms_worked = False
                        break
                    elif 'ERROR' in line:
                        print(' - Run had an error. Check the log file.')
                        found_line = True
                        roms_worked = False
                        sys.exit()
                    elif 'ROMS/TOMS: DONE' in line:
                        found_line = True
                        print(' - ROMS SUCCESS')
                        roms_worked = True
                        break
            if not found_line:
                print(' - Problem finding line in log file.')
                sys.exit()
            sys.stdout.flush()
            if roms_worked:
                break # escape from blow_ups loop
            else:
                blow_ups += 1
        else:
            print(' ** skipped running ROMS')
            roms_worked = True
            break # escape from blow_ups loop

    if roms_worked:
        if args.move_his:
            tt0 = time()
            # Copy history files to the remote machine and clean up
            # (i) make sure the output directory exists
            cmd_list = ['ssh', remote_user + '@' + remote_machine,
                'mkdir -p ' + remote_dir0 + '/LO_roms/' + Ldir['gtagex']]
            for rrr in range(10):
                proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                if len(stderr) == 0: # it worked
                    break
                else:
                    sleep(20) # try again
            Lfun.messages(stdout, stderr, 'Make output directory on ' + remote_machine, args.verbose)
            # (ii) move the contents of roms_out_dir
            cmd_list = ['scp','-r',str(roms_out_dir),
                remote_user + '@' + remote_machine + ':' + remote_dir0 + '/LO_roms/' + Ldir['gtagex']]
            for rrr in range(10):
                proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = proc.communicate()
                if len(stderr) == 0: # it worked
                    break
                else:
                    sleep(20) # try again
            Lfun.messages(stdout, stderr, 'Copy ROMS output to ' + remote_machine, args.verbose)
            # (iii) delete roms_out_dir and forcing files from several days in the past
            dt_prev = dt - timedelta(days=4)
            f_string_prev = 'f' + dt_prev.strftime(Lfun.ds_fmt)
            roms_out_dir_prev = Ldir['roms_out'] / Ldir['gtagex'] / f_string_prev
            roms_bu_out_dir_prev = Ldir['roms_out'] / Ldir['gtagex'] / (f_string_prev + '_blowup')
            force_dir_prev = Ldir['LOo'] / 'forcing' / Ldir['gridname'] / f_string_prev
            shutil.rmtree(str(roms_out_dir_prev), ignore_errors=True)
            shutil.rmtree(str(roms_bu_out_dir_prev), ignore_errors=True)
            shutil.rmtree(str(force_dir_prev), ignore_errors=True)
            print(' - copy & clean up = %d sec' % (time()-tt0))
            sys.stdout.flush()
        else:
            print(' ** skipped moving history files')
            
        # Write a "done" file so that we know not to run the forecast again.
        if (dt == dt1) and (args.run_type == 'forecast'):
            with open(done_fn, 'w') as ffout:
                ffout.write(datetime.now().strftime('%Y.%m.%d %H:%M:%S'))
            
        dt += timedelta(days=1)
    else:
        print(' - ROMS FAIL for ' + dt.strftime(Lfun.ds_fmt))
        sys.exit()
        
    print(' > finished at %s' % (datetime.now().strftime('%Y.%m.%d %H:%M:%S')))
    sys.stdout.flush()
    



