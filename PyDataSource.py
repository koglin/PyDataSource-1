#--------------------------------------------------------------------------
# File and Version Information:
#  $Id: PyDataSource.py  koglin@SLAC.STANFORD.EDU $
#
# Description:
#  module PyDataSource
#--------------------------------------------------------------------------
"""Python implementation of psana DataSource object.

Example:

    # Import the PyDataSource module
    In [1]: import PyDataSource

    # Load example run
    In [2]: ds = PyDataSource.DataSource('exp=xpptut15:run=54')

    # Access the first event
    In [3]: evt = ds.events.next()

    # Tab to see Data objects in current event
    In [4]: evt.
    evt.EBeam            evt.FEEGasDetEnergy  evt.XppEnds_Ipm0     evt.cspad            evt.next
    evt.EventId          evt.L3T              evt.XppSb2_Ipm       evt.get              evt.yag2
    evt.Evr              evt.PhaseCavity      evt.XppSb3_Ipm       evt.keys             evt.yag_lom

    # Tab to see EBeam attributes
    In [4]: evt.EBeam.
    evt.EBeam.EventId            evt.EBeam.ebeamEnergyBC1     evt.EBeam.ebeamPhotonEnergy  evt.EBeam.epicsData
    ...
    evt.EBeam.ebeamDumpCharge    evt.EBeam.ebeamLTUPosY       evt.EBeam.ebeamXTCAVPhase    

    # Print a table of the EBeam data for the current event
    In [4]: evt.EBeam.show_info()
    --------------------------------------------------------------------------------
    EBeam xpptut15, Run 54, Step -1, Event 0, 11:37:12.4517, [140, 141, 41, 40]
    --------------------------------------------------------------------------------
    damageMask                 1.0486e+06         Damage mask.
    ebeamCharge                0.00080421 nC      Beam charge in nC.
    ...
    ebeamPhotonEnergy                   0 eV      computed photon energy, in eV
    ...

    # Print summary of the cspad detector (uses PyDetector methods for creatining calib and image data)
    In [5]: evt.cspad.show_info()
    --------------------------------------------------------------------------------
    cspad xpptut15, Run 54, Step -1, Event 0, 11:37:12.4517, [140, 141, 41, 40]
    --------------------------------------------------------------------------------
    calib                <0.010653> ADU     Calibrated data
    image               <0.0081394> ADU     Reconstruced 2D image from calibStore geometry
    raw                    <1570.2> ADU     Raw data
    shape              (32, 185, 388)         Shape of raw data array
    size                  2.297e+06         Total size of raw data

    # Print summary of cspad detector calibration data (using PyDetector access methods) 
    In [6]: evt.cspad.calibData.show_info()
    areas                  <1.0077>         Pixel area correction factor
    bkgd                      <0.0>         
    ...
    shape              (32, 185, 388)         Shape of raw data array
    size                  2.297e+06         Total size of raw data
    status             <0.00069396>         

    # Print summary of cspad detector calibration data (using PyDetector access methods) 
    In [7]: evt.cspad.configData.show_info()
    activeRunMode                       3         
    asicMask                           15         
    ...
    roiMasks                   0xffffffff         
    runDelay                        58100         
    tdi                                 4         

This software was developed for the LCLS project.
If you use all or part of it, please give an appropriate acknowledgment.

@version $Id: PyDataSource.py  koglin@SLAC.STANFORD.EDU $

@author Koglin, Jason
"""
#------------------------------
__version__ = "$Revision:  $"
##-----------------------------

import sys
import operator
import re
import time
import traceback
import psana
import numpy as np
from DataSourceInfo import *
from psana_doc_info import * 

_eventCodes_rate = {
        40: '120 Hz',
        41: '60 Hz',
        42: '30 Hz',
        43: '10 Hz',
        44: '5 Hz',
        45: '1 Hz',
        46: '0.5 Hz',
        140: 'Beam & 120 Hz',
        141: 'Beam & 60 Hz',
        142: 'Beam & 30 Hz',
        143: 'Beam & 10 Hz',
        144: 'Beam & 5 Hz',
        145: 'Beam & 1 Hz',
        146: 'Beam & 0.5 Hz',
        150: 'Burst',
        162: 'BYKIK',
        163: 'BAKIK',
        }


def get_key_info(psana_obj):
    """Get a dictionary of the (type, src, key) for the data types of each src.
    """
    key_info = {}
    for key in psana_obj.keys():
        typ = key.type()
        src = key.src()
        if typ:
            srcstr = str(src)
            if srcstr not in key_info:
                key_info[srcstr] = [] 
            key_info[srcstr].append((typ, src, key.key()))

    return key_info

def get_keys(psana_obj):
    """Get a dictionary of the (type, src, key) for the data types of each src.
    """
    key_info = {}
    _modules = {}
    for key in psana_obj.keys():
        typ = key.type()
        src = key.src()
        if typ:
            srcstr = str(src)
            if srcstr not in key_info:
                key_info[srcstr] = [] 
            
            key_info[srcstr].append((typ, src, key.key()))
            
            type_name = typ.__name__
            module = typ.__module__.lstrip('psana.')
            if module:
                if module not in _modules:
                    _modules[module] = {}
                
                if type_name not in _modules[module]:
                    _modules[module][type_name] = []

                _modules[module][type_name].append((typ, src, key.key()))

    return key_info, _modules


def _repr_value(value):
    """Represent a value for use in show_info method.
    """
    if isinstance(value,str):
        return value
    else:
        if isinstance(value, list):
            if len(value) > 4:
                return 'list'
            else:
                return str(value)
        elif hasattr(value, 'mean'):
            try:
                return '<{:.4}>'.format(value.mean())
            except:
                return str(value)
        else:
            try:
                return '{:10.5g}'.format(value)
            except:
                try:
                    return str(value)
                except:
                    return value

def _is_psana_type(value):
    """True if the input is a psana data type
    """
    return hasattr(value, '__module__') and value.__module__.startswith('psana')

def _get_typ_func_attr(typ_func, attr, nolist=False):
    """Return psana functions as properties.
    """
    value = getattr(typ_func, attr)
    module = typ_func.__module__.lstrip('psana.')
    type_name = typ_func.__class__.__name__
    try: 
        info = psana_doc_info[module][type_name].get(attr, {'unit': '', 'doc': ''}).copy()
    except:
        info = {'unit': '', 'doc': ''}

    info['typ_func'] = typ_func
    info['attr'] = attr

    if info.get('func_shape'):
        nvals = info.get('func_shape')
        if isinstance(nvals, str):
            nvals = getattr(typ_func, nvals)()[0]
        
        try:
            value = [value(i) for i in range(nvals)]
        except:
            pass

    elif info.get('func_len_hex'):
        nvals = getattr(typ_func, info.get('func_len_hex'))()
        try:
            value = [hex(value(i)) for i in range(nvals)]
        except:
            pass

    elif info.get('func_len'):
        nvals = info.get('func_len')
        if isinstance(nvals, str):
            nvals = getattr(typ_func, nvals)()
        
        try:
            value = [value(i) for i in range(nvals)]
        except:
            pass

    elif info.get('func_index'):
        vals = getattr(typ_func, info.get('func_index'))()
        try:
            value = [value(int(i)).name for i in vals]
        except:
            pass

    elif 'func_method' in info:
        info['value'] = info.get('func_method')(value())
        return info


    if hasattr(value, '_typ_func') and str(value._typ_func)[0].islower():
        # evaluate as name to avoid recursive psana functions 
        if 'name' in value._attrs and 'conjugate' in value._attrs:   
            info['value'] = value.name
  
    try:
        value = value()
        if hasattr(value, 'name'):
            info['value'] = value.name
            return info
    except:
        pass

    if isinstance(value, list):
        values = []
        is_type_list = False
        nvals = info.get('list_len', len(value))
        if isinstance(nvals, str):
            nvals = getattr(typ_func, nvals)()
       
        for i in range(nvals):
            val = value[i]
            if _is_psana_type(val):
                values.append(PsanaTypeData(val))
                is_type_list = True
            else:
                values.append(val)

        if is_type_list: # and not nolist:
            values = PsanaTypeList(values)

        info['value'] = values
        return info

    if _is_psana_type(value):
        info['value'] = PsanaTypeData(value)
    else:
        info['value'] = value

    return info

class ScanData(object):
    """
    """
    _array_attrs = ['pvControls_value', 'pvMonitors_loValue', 'pvMonitors_hiValue']
    _uses_attrs = ['uses_duration', 'uses_events', 'uses_l3t_events']
    _npv_attrs = ['npvControls', 'npvMonitors']

    def __init__(self, ds):
        self._ds = ds
        self._attrs = sorted(ds.configData.ControlData._all_values.keys())
        self._scanData = {attr: [] for attr in self._attrs}
        ds.reload()
        self.nsteps = ds._idx_nsteps
        start_times = []
        ievent_end = []
        ievent_start = []
        for istep, events in enumerate(ds.steps):
            evt = events.next()
            ttup = (evt.EventId.sec, evt.EventId.nsec, evt.EventId.fiducials)
            ievent = ds._idx_times_tuple.index(ttup)
            ievent_start.append(ievent)
            if istep > 0:
                ievent_end.append(ievent-1)
            start_times.append(evt.EventId.timef64) 
 
            for attr in self._attrs:
                self._scanData[attr].append(ds.configData.ControlData._all_values[attr])
        
        ievent_end.append(len(ds._idx_times_tuple)-1)       
        end_times = []
        for istep, ievent in enumerate(ievent_end):
            end_times.append(ds.events.next(ievent).EventId.timef64)
 
        self._scanData['ievent_start'] = np.array(ievent_start)
        self._scanData['ievent_end'] = np.array(ievent_end)
        self.nevents = np.array(ievent_end)-np.array(ievent_start)       
        self.start_times = np.array(start_times)
        self.end_times = np.array(end_times)
        self.step_times = np.array(end_times) - np.array(start_times)
 
        for attr in self._uses_attrs:
            setattr(self, attr, all(self._scanData.get(attr)))

        if (self.uses_duration or self.uses_events or self.uses_l3t_events) \
                and len(set(self._scanData['npvControls'])) == 1 \
                and len(set(self._scanData['npvMonitors'])) == 1 :
            self._is_simple = True
            for attr in self._npv_attrs:
                setattr(self, attr, self._scanData.get(attr)[0]) 

            if 'pvControls_name' in self._attrs:
                self.pvControls = self._scanData['pvControls_name'][0]
            else:
                self.pvControls = None
            
            if 'pvMonitors_name' in self._attrs:
                self.pvMonitors = self._scanData['pvMonitors_name'][0]
            else:
                self.pvMonitors = None

            self.pvLabels = self._scanData['pvLabels'][0]
            if not self.pvLabels:
                self.pvLabels = []
                for pv in self.pvControls:
                    alias = ds.epicsData.alias(pv)
                    if not alias:
                        alias = pv

                    self.pvLabels.append(alias) 
            
            self.control_values = {} 
            self.monitor_hivalues = {}
            self.monitor_lovalues = {}
            if self.pvControls is not None:
                for i, pv in enumerate(self.pvControls):
                    self.control_values[pv] = \
                            np.array([val[i] for val in self._scanData['pvControls_value']])
                
            if self.pvMonitors is not None:
                for i, pv in enumerate(self.pvMonitors):
                    self.monitor_hivalues[pv] = \
                            np.array([val[i] for val in self._scanData['pvMonitors_hiValue']])
                    self.monitor_lovalues[pv] = \
                            np.array([val[i] for val in self._scanData['pvMonitors_loValue']])

            self.pvAliases = {}
            for i, pv in enumerate(self.pvControls):
                alias = self.pvLabels[i]
                self.pvAliases[pv] = re.sub('-|:|\.| ','_', alias)
                setattr(self, alias, self.control_values[pv])

        ds.reload()

    def show_info(self):
        attrs = { 
            'nsteps':      {'unit': '',     'desc': 'Number of steps'}, 
            'npvControls': {'unit': '',     'desc': 'Number of control PVs'},
            'npvMonitors': {'unit': '',     'desc': 'Number of monitor PVs'},
            }

        print '{:10}: Run {:}'.format(self._ds.data_source.exp, self._ds.data_source.run)
        print '-'*70
        for attr, item in attrs.items():
            print '{:24} {:10} {:16}'.format(item.get('desc'), getattr(self, attr), attr)
       
        print ''
        print '{:24} {:40}'.format('Alias', 'PV')
        print '-'*70
        for name, alias in self.pvAliases.items():
            print '{:24} {:40}'.format(alias, name)
        print ''

        self._control_format = {}
        self._name_len = {}
        header1 = '{:4} {:6} {:>10}'.format('Step', 'Events', 'Time [s]')
        for i, name in enumerate(self.control_values):
            alias = self.pvAliases.get(name, name)
            name_len = len(alias)
            self._name_len[name] = name_len 
            name_format = ' {:>'+str(name_len)+'}'
            header1 += name_format.format(alias)
            vals = self.control_values[name]
            if self.nsteps > 1:
                sigdigit = int(np.floor(np.log10(abs(np.mean(vals[1:]-vals[:-1])))))
            else:
                sigdigit = int(np.floor(np.log10(abs(vals))))
            
            if sigdigit < -5 or sigdigit > 5:
                self._control_format[name] = ' {:'+str(name_len)+'.3e}'
            elif sigdigit < 0:
                self._control_format[name] = ' {:'+str(name_len)+'.'+str(-sigdigit+1)+'f}'
            else:
                self._control_format[name] = ' {:'+str(name_len)+'}'

        print header1
        print '-'*(21+sum(self._name_len.values()))
        for i, nevents in enumerate(self.nevents):
            a = '{:4} {:6} {:8.3f}'.format(i, nevents, self.step_times[i])
            for name, vals in self.control_values.items():
                a += self._control_format[name].format(vals[i])
            
            print a

    def __str__(self):
        return  'ScanData: '+str(self._ds.data_source)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        print '< '+repr_str+' >'
        self.show_info()
        return '< '+repr_str+' >'




class DataSource(object):
    """Python version of psana.DataSource with support for event and config
       data as well as PyDetector functions to access calibrated data.
    """

    _ds_funcs = ['end', 'env']
    _ds_attrs = ['empty']
    _env_attrs = ['calibDir', 'instrument', 'experiment','expNum']

    def __init__(self, data_source=None, **kwargs):
        self.load_run(data_source=data_source, **kwargs)
        if self.data_source.smd:
            self._load_smd_config()

    def _load_smd_config(self):
        """Load configData of first calib cycle by going to first step.
           Reload so that steps can be used as an iterator.
        """
        if self.data_source.smd:
            step = self.steps.next()
            self.reload()
    
    def load_run(self, data_source=None, reload=False, **kwargs):
        """Load a run with psana.
        """
        self._evtData = None
        self._current_evt = None
        self._current_step = None
        self._current_run = None
        self._evt_keys = {}
        self._evt_modules = {}
        if not reload:
            self.data_source = DataSourceInfo(data_source=data_source, **kwargs)

        # do not reload shared memory
        if not (self.data_source.monshmserver and self._ds):
            if True:
                self._ds = psana.DataSource(str(self.data_source))
                _key_info, _modules = get_keys(self._ds.env().configStore())
                if 'Partition' in _modules:
                    try_idx = False

                else:
                    #if not self.data_source.smd:
                    if False:
                        print 'Exp {:}, run {:} is has no Partition data.'.format( \
                            self.data_source.exp, self.data_source.run)
                        print 'PyDataSource requires Partition data.'
                        print 'Returning psana.DataSource({:})'.format(str(self.data_source))
                        return self._ds
                    else:
                        try_idx = True
                        print 'Exp {:}, run {:} smd data has no Partition data -- loading idx data instead.'.format( \
                            self.data_source.exp, self.data_source.run)
            else:
                try_idx = True
                print 'Exp {:}, run {:} smd data file not available -- loading idx data instead.'.format( \
                            self.data_source.exp, self.data_source.run)

        if try_idx:
            if self.data_source.smd:
                try:
                    print 'Use smldata executable to convert idx data to smd data.'
                    data_source_smd = self.data_source
                    data_source_idx = str(data_source_smd).replace('smd','idx')
                    self.data_source = DataSourceInfo(data_source=data_source_idx)
                    self._ds = psana.DataSource(str(self.data_source))
                except:
                    print 'Failed to load either smd or idx data for exp {:}, run {:}'.format( \
                            self.data_source.exp, self.data_source.run)
                    print 'Data can be restored from experiment data portal:  https://pswww.slac.stanford.edu'
                    return False

        self.epicsData = EpicsData(self._ds) 

        self._evt_time_last = (0,0)
        self._ievent = -1
        self._istep = -1
        self._irun = -1
        if self.data_source.idx:
            self.runs = Runs(self, **kwargs)
            self.events = self.runs.next().events
        
        elif self.data_source.smd:
            self.steps = Steps(self, **kwargs)
            # SmdEvents automatically goes to next step if no events in current step.
            self.events = SmdEvents(self)
            if not reload:
                self._scanData = None
                data_source_idx = str(self.data_source).replace('smd','idx')
                self._idx_ds = psana.DataSource(data_source_idx)
                self._idx_run = self._idx_ds.runs().next()
                self._idx_nsteps = self._idx_run.nsteps()
                self._idx_times = self._idx_run.times()
                self.nevents = len(self._idx_times)
                self._idx_times_tuple = [(a.seconds(), a.nanoseconds(), a.fiducial()) \
                                        for a in self._idx_times]
        
        else:
            # For live data or data_source without idx or smd
            self.events = Events(self)
            self.nevents = None

        return str(self.data_source)

    def reload(self):
        """Reload the current run.
        """
        self.load_run(reload=True)

    def _load_ConfigData(self):
        self._ConfigData = ConfigData(self)

    @property
    def configData(self):
        """Configuration Data from ds.env().configStore().
           For effieciency only loaded at beginning of run or step unless
           working with shared memory.
        """
        if self.data_source.monshmserver:
            self._load_ConfigData()
        
        return self._ConfigData

    def _init_detectors(self):
        """Initialize psana.Detector classes based on psana env information.
        """
        self._detectors = {}
        self._load_ConfigData()
        self._aliases = self.configData._aliases
        for srcstr, item in self.configData._sources.items():
            alias = item.get('alias')
            self._add_dets(**{alias: srcstr})

    def _add_dets(self, **kwargs):
        for alias, srcstr in kwargs.items():
            try:
                det = Detector(self, alias)
                self._detectors.update({alias: det})
            except Exception as err:
                print 'Cannot add {:}:  {:}'.format(alias, srcstr) 
                traceback.print_exc()
    
    def show_info(self):
        self.configData.show_info()
    
    def __str__(self):
        return  str(self.data_source)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        if self.nevents:
            repr_str += ' {:} events'.format(self.nevents)
        print '< '+repr_str+' >'
        self.show_info()
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        if attr in self._ds_attrs:
            return getattr(self._ds, attr)()
        if attr in self._ds_funcs:
            return getattr(self._ds, attr)
        if attr in self._env_attrs:
            return getattr(self._ds.env(), attr)()
        
    def __dir__(self):
        all_attrs =  set(self._ds_attrs + 
                         self._ds_funcs + 
                         self._env_attrs +
                         self.__dict__.keys() + dir(DataSource))
        
        return list(sorted(all_attrs))


class Runs(object):
    """psana DataSource Run iterator from ds.runs().
    """
    def __init__(self, ds, **kwargs):
        self._ds_runs = []
        self._kwargs = kwargs
        self._ds = ds

    def __iter__(self):
        return self

    @property
    def current(self):
        return self._ds._current_run

    def next(self):
        self._ds._ds_run = self._ds._ds.runs().next()
        self._ds_runs.append(self._ds._ds_run)
        self._ds._irun +=1
        self._ds._istep = -1
        self._ds._ievent = -1
        self._ds._init_detectors()
        self._ds._current_run = Run(self._ds)

        return self._ds._current_run


class Run(object):
    """Python psana.Run class from psana.DataSource.runs().next().
    """
    _run_attrs = ['nsteps', 'times']
    _run_funcs = ['end', 'env']

    def __init__(self, ds, **kwargs):
        self._ds = ds

    @property
    def events(self):
        return RunEvents(self._ds)

#    @property
#    def steps(self):
#        return RunSteps(self._ds)

    def __getattr__(self, attr):
        if attr in self._run_attrs:
            return getattr(self._ds._ds_run, attr)()
        if attr in self._run_funcs:
            return getattr(self._ds._ds_run, attr)
        
    def __dir__(self):
        all_attrs =  set(self._run_attrs +
                         self._run_funcs + 
                         self.__dict__.keys() + dir(Run))
        
        return list(sorted(all_attrs))


#class RunSteps(object):
#    """Step iterator from psana.DataSource.runs().steps().
#    """
#    def __init__(self, ds, **kwargs):
#        self._ds = ds
#        self._kwargs = kwargs
#        self._ds_steps = []
#        self._configSteps = []
#
#    def __iter__(self):
#        return self
#
#    def next(self):
#        try:
#            self._ds._ievent = -1
#            self._ds._istep +=1
#            self._ds._ds_step = self._ds._current_run.steps().next()
#            self._ds_steps.append(self._ds._ds_step)
#            self._ds._init_detectors()
#            return StepEvents(self._ds)
#        
#        except: 
#            raise StopIteration()


class RunEvents(object):
    """Event iterator from ds.runs() for indexed idx data 

       No support yet for multiple runs in a data_source
    """
    def __init__(self, ds, **kwargs):
        self._kwargs = kwargs
        self._ds = ds
        self.times = self._ds.runs.current.times 
        self._ds.nevents = len(self.times)

    def __iter__(self):
        return self

    @property
    def current(self):
        return EvtDetectors(self._ds)

    def next(self, evt_time=None):
        """Optionally pass either an integer for the event number in the data_source
           or a psana.EventTime time stamp to jump to an event.
        """
        try:
            if evt_time is not None:
                if isinstance(evt_time, int):
                    self._ds._ievent = evt_time
                else:
                    self._ds._ievent = self.times.index(evt_time)
            else:
                self._ds._ievent += 1
            
            if self._ds._ievent >= len(self.times):
                raise StopIteration()
            else:
                evt = self._ds._ds_run.event(self.times[self._ds._ievent]) 
                self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
                self._ds._current_evt = evt

            return EvtDetectors(self._ds)

        except: 
            raise StopIteration()


class SmdEvents(object):
    """Event iterator for smd xtc data that iterates first over steps and then
       events in steps (to make sure configData is updated for each step since
       it is possible that it changes).
    """
    def __init__(self, ds, **kwargs):
        self._ds = ds

    @property
    def current(self):
        return EvtDetectors(self._ds)

    def __iter__(self):
        return self

    def next(self, evt_time=None):
        try:
            return self._ds._current_step.next(evt_time=evt_time)
        except:
            try:
                self._ds.steps.next()
                return self._ds._current_step.next()
            except:
                raise StopIteration()


class Steps(object):
    """Step iterator from ds.steps().
    """
    def __init__(self, ds, **kwargs):
        self._ds = ds
        self._kwargs = kwargs
        self._ds_steps = []

    @property
    def current(self):
        return self._ds._current_step

    def __iter__(self):
        return self

    def next(self):
        try:
            if self._ds._istep == self._ds._idx_run.nsteps()-1:
                raise StopIteration()
            else:
                self._ds._ievent = -1
                self._ds._istep +=1
                self._ds._ds_step = self._ds._ds.steps().next()
                self._ds_steps.append(self._ds._ds_step)
                self._ds._init_detectors()
                self._ds._current_step = StepEvents(self._ds)
                return self._ds._current_step

        except: 
            raise StopIteration()


class StepEvents(object):
    """Event iterator from ds.steps().events() 
    """
    def __init__(self, ds, **kwargs):
        self._kwargs = kwargs
        self._ds = ds

    @property
    def current(self):
        return EvtDetectors(self._ds)

    def __iter__(self):
        return self

    def next(self, evt_time=None):
        """Next event in step.  Optionally pass either an integer for the 
           event number in the data_source, a psana.EventTime time stamp
           or a time stamp tupple (second, nanosecond, fiducial)
           to jump to an event.  If no event time or number is passed, the
           event loop will procede from the last event in the step regardless
           of which event was previously jumped to.
        """
        if evt_time is not None:
            # Jump to the specified event
            try:
                if self._ds._istep >= 0:
                    # keep trak of event index to go back to step event loop
                    self._ds._ievent_last = self._ds._ievent
                    self._ds._istep_last = self._ds._istep
                    self._ds._istep = -1
                
                if evt_time.__class__.__name__ == 'EventTime':
                    # lookup event index from time tuple
                    ttup = (evt_time.seconds(), evt_time.nanoseconds(), evt_time.fiducial())
                    self._ds._ievent = self._ds._idx_times_tuple.index(ttup)
                elif isinstance(evt_time, tuple):
                    # optionally accept a time tuple (seconds, nanoseconds, fiducial)
                    self._ds._ievent = self._ds._idx_times_tuple.index(evt_time)
                    evt_time = self._ds._idx_times[self._ds._ievent]
                else:
                    # if an integer was passed jump to the appropriate time from 
                    # the list of run times -- i.e., psana.DataSource.runs().next().times()
                    self._ds._ievent = evt_time
                    evt_time = self._ds._idx_times[evt_time]

                #print self._ds._ievent, evt_time.seconds(), evt_time.nanoseconds()
                evt = self._ds._idx_run.event(evt_time) 
                    
                self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
                self._ds._current_evt = evt
            
            except:
                print evt_time, 'is not a valid event time'
        
        else:
            try:
                if self._ds._istep == -1:
                    # recover event and step index after previoiusly jumping to an event 
                    self._ds._ievent = self._ds._ievent_last
                    self._ds._istep = self._ds._istep_last
                
                self._ds._ievent += 1
                evt = self._ds._ds_step.events().next()
                self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
                self._ds._current_evt = evt 
            except:
                raise StopIteration()

        return EvtDetectors(self._ds)


class Events(object):
    """Event iterator
    """

    def __init__(self, ds, **kwargs):
        self._kwargs = kwargs
        self._ds = ds
        self._ds._init_detectors()

    @property
    def current(self):
        return EvtDetectors(self._ds)

    def __iter__(self):
        return self

    def next(self):
        try:
            self._ds._ievent += 1
            evt = self._ds._ds.events().next()
            self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
            self._ds._current_evt = evt 
        except:
            raise StopIteration()

        return EvtDetectors(self._ds)


class PsanaTypeList(object):

    def __init__(self, type_list):

        self._type_list = type_list
        typ_func = type_list[0]._typ_func
        module = typ_func.__module__.lstrip('psana.')
        type_name = typ_func.__class__.__name__
        info = psana_doc_info[module][type_name].copy()
        
        self._typ_func = typ_func
        self._values = {}
        self._attr_info = {}
        for attr, item in info.items():
            item['value'] = None

        attrs = [key for key in info.keys() if not key[0].isupper()]
        for attr in attrs:
            values = [getattr(item, attr) for item in self._type_list]

            try:
                if isinstance(values[0], np.ndarray):
                    values = np.array(values)
            except:
                pass
#                print module, type_name, info
#                print values

            if hasattr(values[0], '_typ_func'):
                vals = PsanaTypeList(values)
                for name, item in vals._attr_info.copy().items():
                    alias = attr+'_'+name
                    self._values[alias] = item['value']
                    self._attr_info[alias] = item.copy()
                    self._attr_info[alias]['attr'] = alias

            else:
                self._values[attr] = values
                self._attr_info[attr] = info[attr].copy()
                self._attr_info[attr]['value'] = values
                self._attr_info[attr]['attr'] = attr

        self._attrs = self._values.keys()

    @property
    def _all_values(self):
        """All values in a flattened dictionary.
        """
        avalues = {}
        items = sorted(self._values.items(), key = operator.itemgetter(0))
        for attr, val in items:
            if hasattr(val, '_all_values'):
                for a, v in val._all_values.items():
                    avalues[attr+'_'+a] = v
            else:
                avalues[attr] = val
        return avalues

    def show_info(self, prefix=''):
        """Show a table of the attribute, value, unit and doc information
        """
        items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
        for attr, item in items:
            if attr in self._attrs:
                alias = item.get('attr')
                str_repr = _repr_value(item.get('value'))
                unit = item.get('unit')
                doc = item.get('doc')
                if prefix:
                    alias = prefix+'_'+alias
                print '{:24s} {:>12} {:7} {:}'.format(alias, str_repr, unit, doc)

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self._values.get(attr)

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(PsanaTypeList))
        return list(sorted(all_attrs))


class PsanaTypeData(object):
    """Python representation of a psana data object (event or configStore data).
    """

    def __init__(self, typ_func, nolist=False):
        if typ_func:
            self._typ_func = typ_func
            module = typ_func.__module__.lstrip('psana.')
            type_name = typ_func.__class__.__name__
        else:
            type_name = None
        self._nolist = nolist

        if type_name in psana_doc_info[module]:
            self._info = psana_doc_info[module][type_name].copy()
            self._attrs = [key for key in self._info.keys() if not key[0].isupper()]
        else:
            self._attrs = [attr for attr in dir(typ_func) if not attr.startswith('_')]
            self._info = {}

        self._attr_info = {}
        for attr in self._attrs:
            self._attr_info[attr] = _get_typ_func_attr(typ_func, attr, nolist=nolist)

    @property
    def _values(self):
        """Dictionary of attributes: values. 
        """
        return {attr: self._attr_info[attr]['value'] for attr in self._attrs}

    @property
    def _all_values(self):
        """All values in a flattened dictionary.
        """
        avalues = {}
        items = sorted(self._values.items(), key = operator.itemgetter(0))
        for attr, val in items:
            if hasattr(val, '_all_values'):
                for a, v in val._all_values.items():
                    avalues[attr+'_'+a] = v
            else:
                avalues[attr] = val
        return avalues

    def show_info(self, prefix=None):
        """Show a table of the attribute, value, unit and doc information
        """
        items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
        for attr, item in items:
            value = item.get('value')
            alias = item.get('attr')
            if prefix:
                alias = prefix+'_'+alias
            if hasattr(value, 'show_info'):
                value.show_info(prefix=alias)
            else:
                str_repr = _repr_value(item.get('value'))
                unit = item.get('unit')
                doc = item.get('doc')
                print '{:24s} {:>12} {:7} {:}'.format(alias, str_repr, unit, doc)

    def __str__(self):
        return '{:}.{:}.{:}'.format(self._typ_func.__class__.__module__,
                                    self._typ_func.__class__.__name__, 
                                    str(self._typ_func))

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self._attr_info[attr]['value']

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(PsanaTypeData))
        return list(sorted(all_attrs))


class PsanaSrcData(object):
    """Dictify psana data for a given detector source.
       key_info: get_key_info(objclass) for faster evt data access.
    """
    def __init__(self, objclass, srcstr, key_info=None, nolist=False):
        self._srcstr = srcstr
        if not key_info:
            key_info = get_key_info(objclass)

        self._types = {}
        self._type_attrs = {}
        self._keys = key_info.get(srcstr)
        if self._keys:
            for (typ, src, key) in self._keys:
                if key:
                    typ_func = objclass.get(*item)
                else:
                    typ_func = objclass.get(typ, src)

                module = typ_func.__module__.lstrip('psana.')
                type_name = typ_func.__class__.__name__
                type_alias = module+type_name+key 
                type_data = PsanaTypeData(typ_func, nolist=nolist)
                self._types[type_alias] = type_data 
                self._type_attrs.update({attr: type_alias for attr in type_data._attrs})
                #self._types[(typ,key)] = type_data 
                #self._type_attrs.update({attr: (typ,key) for attr in type_data._attrs})

    @property
    def _attrs(self):
        attrs = []
        for type_data in self._types.values():
            attrs.extend(type_data._attrs)

        return attrs

    @property
    def _attr_info(self):
        """Attribute information including the unit and doc information 
           and a str representation of the value for all data types.
        """
        attr_info = {}
        for type_data in self._types.values():
            attr_info.update(**type_data._attr_info)

        return attr_info

    @property
    def _values(self):
        """Dictionary of attributes: values for all data types.
        """
        values = {}
        for type_data in self._types.values():
            values.update(**type_data._values)

        return values

    @property
    def _all_values(self):
        """All values in a flattened dictionary.
        """
        values = {}
        for type_data in self._types.values():
            values.update(**type_data._all_values)

        return values

    def show_info(self):
        """Show a table of the attribute, value, unit and doc information
           for all data types of the given source.
        """
        for type_data in self._types.values():
            type_data.show_info()

    def _get_type(self, typ):
        return self._types.get(typ)

    def __str__(self):
        return '{:}'.format(self._srcstr)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        item = self._type_attrs.get(attr)
        if item:
            return getattr(self._types.get(item), attr)
        
        if attr in self._types:
            return self._types.get(attr)

                   #
    def __dir__(self):
        all_attrs = set(self._type_attrs.keys() +
                        self._types.keys() + 
                        self.__dict__.keys() + dir(PsanaSrcData))
        return list(sorted(all_attrs))


class ConfigData(object):
    """ConfigData
    """
    _configStore_attrs = ['get','put','keys']
    # Alias default provides way to keep aliases consistent for controls devices like the FEE_Spec
    _alias_defaults = {
            'BldInfo(FEE-SPEC0)': 'FEE_Spec',
            'BldInfo(NH2-SB1-IPM-01':  'Nh2Sb1_Ipm1',
            'BldInfo(NH2-SB1-IPM-02':  'Nh2Sb1_Ipm2',
            }

    def __init__(self, ds):
        configStore = ds.env().configStore()
        if (hasattr(ds, 'data_source') and ds.data_source.monshmserver):
            self._monshmserver = ds.data_source.monshmserver
        else:
            self._monshmserver = None 
       
        self._ds = ds
        self._configStore = configStore
        self._key_info, self._modules = get_keys(configStore)

        # Build _config dictionary for each source
        self._config = {}
        for attr, keys in self._key_info.items():
            config = PsanaSrcData(self._configStore, attr, 
                                  key_info=self._key_info, nolist=True)
            self._config[attr] = config

        self._sources = {}
        #Setup Partition
        if not self._modules.get('Partition'):
            #print 'ERROR:  No Partition module in configStore data.'
            self._partition = {}
            self._srcAlias = {}
            for srcstr, item in self._config.items():
                if srcstr[0:7] in ['BldInfo', 'DetInfo']:
                    alias = srcstr[8:-1]
                    alias = re.sub('-|:|\.| ','_', alias)
                    src = item._keys[0][1] 
                    self._partition[srcstr] = {
                                               #'alias': alias, 
                                               'group': 0, 
                                               'src': src}

                    self._srcAlias[alias] = (src, 0)

                self._bldMask = 0
                self._ipAddrpartition = 0 
                self._readoutGroup = {0: {'eventCodes': [], 'srcs': []}}

        elif len(self._modules['Partition']) != 1:
            print 'ERROR:  More than one Partition config type in configStore data.'
            return
        else:
            #Build _partition _srcAlias _readoutGroup dictionaries based on Partition configStore data. 
            type_name = self._modules.get('Partition').keys()[0]
            if len(self._modules['Partition'][type_name]) == 1:
                typ, src, key = self._modules['Partition'][type_name][0]
                srcstr = str(src)
                config = self._config[srcstr]
                self.Partition = config
            else:
                print 'ERROR:  More that one Partition module in configStore data.'
                print '       ', self._modules['Partition'][type_name]
                return

    # to convert ipAddr int to address 
    # import socket, struct
    # s = key.src()
    # socket.inet_ntoa(struct.pack('!L',s.ipAddr()))

            self._ipAddrPartition = src.ipAddr()
            self._bldMask = config.bldMask
            self._readoutGroup = {group: {'srcs': [], 'eventCodes': []} \
                                  for group in set(config.sources.group)}
            self._partition = {str(src): {'group': config.sources.group[i], 'src': src} \
                               for i, src in enumerate(config.sources.src)}

            self._srcAlias = {}
            if self._modules.get('Alias'):
                for type_name, keys in self._modules['Alias'].items():
                    for typ, src, key in keys:
                        srcstr = str(src)
                        config = self._config[srcstr]
                        ipAddr = src.ipAddr()
                        for i, source in enumerate(config.srcAlias.src):
                            alias = config.srcAlias.aliasName[i]
                            self._srcAlias[alias] = (source, ipAddr)

        self._aliases = {}
        for alias, item in self._srcAlias.items():
            src = item[0]
            ipAddr = item[1]
            srcstr = str(src)
            alias = re.sub('-|:|\.| ','_', alias)
            group = None
            if srcstr in self._partition:
                self._partition[srcstr]['alias'] = alias
                if srcstr.find('NoDetector') == -1:
                    self._aliases[alias] = srcstr
                
                group = self._partition[srcstr].get('group', -1)
            
            elif ipAddr != self._ipAddrPartition or self._monshmserver:
                if self._monshmserver:
                    # add data sources not in partition for live data
                    group = -2
                else:
                    # add data sources not in partition that come from recording nodes
                    group = -1

                self._partition[srcstr] = {'src': src, 'group': group, 'alias': alias}
                self._aliases[alias] = srcstr
                if group not in self._readoutGroup:
                    self._readoutGroup[group] = {'srcs': [], 'eventCodes': []}

                self._sources[srcstr] = {'group': group, 'alias': alias}
            
            if group:
                self._readoutGroup[group]['srcs'].append(srcstr)
            #else:
            #    print 'No group for', srcstr

        # Determine data sources and update aliases
        for srcstr, item in self._partition.items():
            if not item.get('alias'):
                if srcstr in self._alias_defaults:
                    alias = self._alias_defaults.get(srcstr)
                else:
                    try:
                        alias = srcstr.split('Info(')[1].rstrip(')')
                    except:
                        alias = srcstr
                
                alias = re.sub('-|:|\.| ','_',alias)
                item['alias'] = alias
                self._aliases[alias] = srcstr

            if 'NoDetector' not in srcstr and 'NoDevice' not in srcstr:
                # sources not recorded have group None
                # only include these devices for shared memory
                if srcstr not in self._sources:
                    self._sources[srcstr] = {}
                self._sources[srcstr].update(**item)

        # Make dictionary of src: alias for sources with config objects 
        self._config_srcs = {}
        for attr, item in self._sources.items():
            config = self._config.get(attr)
            if config:
                self._config_srcs[item['alias']] = attr
    
        self._output_maps = {}
        self._evr_pulses = {}
        self._eventcodes = {}

        IOCconfig_type = None
        config_type = None
        for type_name in self._modules['EvrData'].keys():
            if type_name.startswith('IOConfig'):
                IOCconfig_type = type_name
                self._IOCconfig_type = type_name
            elif type_name.startswith('Config'):
                config_type = type_name

        if IOCconfig_type:
            # get eventcodes and combine output_map info from all EvrData config keys
            map_attrs = ['map', 'conn_id', 'module', 'value', 'source_id']
            for typ, src, key in self._modules['EvrData'][config_type]:
                srcstr = str(src)
                config = self._config[srcstr]
                for eventcode in config.eventcodes._type_list:
                    self._eventcodes.update({eventcode.code: eventcode._values})
                    if eventcode.isReadout:
                        group = eventcode.readoutGroup
                        if group not in self._readoutGroup:
                            self._readoutGroup[group] = {'srcs': [], 'eventCodes': []}
                        self._readoutGroup[group]['eventCodes'].append(eventcode.code)

                for output_map in config.output_maps._type_list:
                    map_key = (output_map.module,output_map.conn_id)
                    if output_map.source == 'Pulse':
                        pulse_id = output_map.source_id
                        pulse = config.pulses._type_list[pulse_id]
                        evr_info = { 'evr_width': pulse.width*pulse.prescale/119.e6, 
                                     'evr_delay': pulse.delay*pulse.prescale/119.e6, 
                                     'evr_polarity': pulse.polarity}
                    else:
                        pulse_id = None
                        pulse = None
                        evr_info = {'evr_width': None, 'evr_delay': None, 'evr_polarity': None}

                    self._output_maps[map_key] = {attr: getattr(output_map,attr) for attr in map_attrs} 
                    self._output_maps[map_key].update(**evr_info) 

            # Assign evr info to the appropriate sources
            if len(self._modules['EvrData'][IOCconfig_type]) > 1:
                print 'WARNING: More than one EvrData.{:} objects'.format(IOCconfig_type)

            IOCconfig_type = self._IOCconfig_type
            typ, src, key = self._modules['EvrData'][IOCconfig_type][0]
            srcstr = str(src)
            config = self._config[srcstr]
            for ch in config._values['channels']._type_list:
                map_key = (ch.output.module, ch.output.conn_id)
                for i in range(ch.ninfo):
                    src = ch.infos[i]
                    srcstr = str(src)
                    self._sources[srcstr]['map_key'] = map_key
                    for attr in ['evr_width', 'evr_delay', 'evr_polarity']:
                        self._sources[srcstr][attr] = self._output_maps[map_key][attr]

            for group, item in self._readoutGroup.items():
                if item['eventCodes']:
                    for srcstr in item['srcs']: 
                        if srcstr in self._sources:
                            self._sources[srcstr]['eventCode'] = item['eventCodes'][0]

        # Get control data
        if self._modules.get('ControlData'):
            type_name, keys = self._modules['ControlData'].items()[0]
            typ, src, key = keys[0]
            config = self._config[str(src)]
            self._controlData = config._values
            self.ControlData = config

        if self._modules.get('SmlData'):
            type_name, keys = self._modules['SmlData'].items()[0]
            typ, src, key = keys[0]
            config = self._config[str(src)]
            self._smlData = config._values

    @property
    def ScanData(self):
        """Scan configuration from steps ControlData.  
           May take several seconds to load the first time.
           Only relevant for smd data.
        """
        #if self._ds.data_source.monshmserver is not None:
        if not self._ds.data_source.smd:
            return None

        if self._ds._scanData is None:
            self._ds._scanData = ScanData(self._ds)

        return self._ds._scanData

    def show_info(self):
        print '*Detectors in group 0 are "BLD" data recorded at 120 Hz on event code 40'
        if self._monshmserver:
            print '*Detectors listed as Monitored are not being recorded (group -2).'
        else:
            print '*Detectors listed as Controls are controls devices with unknown event code (but likely 40).'
        print ''
        header =  '{:22} {:>8} {:>13} {:>5} {:>5} {:12} {:12} {:26}'.format('Alias', 'Group', 
                 'Rate', 'Code', 'Pol.', 'Delay [s]', 'Width [s]', 'Source') 
        print header
        print '-'*(len(header)+10)
        cfg_srcs = self._config_srcs.values()
        data_srcs = {item['alias']: s for s,item in self._sources.items() \
                       if s in cfg_srcs or s.startswith('Bld')}
        
        for alias, srcstr in sorted(data_srcs.items(), key = operator.itemgetter(0)):
            item = self._sources.get(srcstr,{})

            polarity = item.get('evr_polarity', '')
            if polarity == 1:
                polarity = 'Pos'
            elif polarity == 0:
                polarity = 'Neg'

            delay = item.get('evr_delay', '')
            if delay:
                delay = '{:11.9f}'.format(delay)

            width = item.get('evr_width', '')
            if width:
                width = '{:11.9f}'.format(width)

            group = item.get('group')
            if group == -1:
                group = 'Controls'
            elif group == -2:
                group = 'Monitor'

            if group == 0:
                eventCode = 40
            else:
                eventCode = item.get('eventCode', '')

            rate = _eventCodes_rate.get(eventCode, '')

            print '{:22} {:>8} {:>13} {:>5} {:>5} {:12} {:12} {:40}'.format(alias, 
                   group, rate, eventCode, polarity, delay, width, srcstr)

    def __str__(self):
        return  'ConfigData: '+str(self._ds.data_source)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self._ds.data_source))
        print '< '+repr_str+' >'
        self.show_info()
        return '< '+repr_str+' >'
    
    def __getattr__(self, attr):
        if attr in self._config_srcs:
            return self._config[self._config_srcs[attr]]

        if attr in self._configStore_attrs:
            return getattr(self._configStore, attr)
        
    def __dir__(self):
        all_attrs = set(self._configStore_attrs +
                        self._config_srcs.keys() + 
                        self.__dict__.keys() + dir(ConfigData))
        return list(sorted(all_attrs))


class EvtDetectors(object):
    """Psana tab accessible event detectors.
       All detectors in Partition or defined in any configStore Alias object 
       (i.e., recording nodes as well as daq) return the relevant attributes of 
       a PyDetector object for that src, but only the sources in the evt.keys()
       show up in the ipython tab accessible dir.
       Preserves get, keys and run method of items in psana events iterators.
    """

    _init_attrs = ['get', 'keys'] #  'run' depreciated
    _event_attrs = ['EventId', 'Evr', 'L3T']

    def __init__(self, ds): 
        self._ds = ds
        
    @property
    def EventId(self):
        return EventId(self._ds._current_evt)

    @property
    def _attrs(self):
        """List of detector names in current evt data.
        """
        return [alias for alias, srcstr in self._ds._aliases.items() \
                                        if srcstr in self._ds._evt_keys]

    @property
    def _dets(self):
        """Dictionary of detectors.
        """
        return self._ds._detectors

    @property
    def Evr(self):
        """Master evr from psana evt data.
        """
        if 'EvrData' in self._ds._evt_modules:
            return EvrData(self._ds)
        else:
            return EvrNullData(self._ds)

    @property
    def L3T(self):
        """L3T Level 3 trigger.
        """
        if 'L3T' in self._ds._evt_modules:
            return L3Tdata(self._ds)
        else:
            return L3Ttrue(self._ds)

    def next(self, *args, **kwargs):
        return self._ds.events.next(*args, **kwargs)
 
    def __iter__(self):
        return self

    def __str__(self):
        return  '{:}, Run {:}, Step {:}, Event {:}, {:}, {:}'.format(self._ds.data_source.exp, 
                self._ds.data_source.run, self._ds._istep, self._ds._ievent, 
                str(self.EventId), str(self.Evr))

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__, str(self))
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        if attr in self._ds._detectors:
            return self._ds._detectors[attr]
        
        if attr in self._init_attrs:
            return getattr(self._ds._current_evt, attr)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self._init_attrs +
                         self.__dict__.keys() + dir(EvtDetectors))
        
        return list(sorted(all_attrs))


class L3Ttrue(object):

    def __init__(self, ds):

        self._ds = ds
        self._attr_info = {'result': {'attr': 'result',
                                      'doc':  'No L3T set',
                                      'unit': '',
                                      'value': True}}

        self._attrs = self._attr_info.keys()

    @property
    def _values(self):
        """Dictionary of attributes: values. 
        """
        return {attr: self._attr_info[attr]['value'] for attr in self._attrs}

    def show_info(self):
        """Show a table of the attribute, value, unit and doc information
        """
        items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
        for attr, item in items:
            value = item.get('value')
            if hasattr(value, 'show_info'):
                value.show_info(prefix=attr)
            else:
                item['str'] = _repr_value(value)
                print '{attr:24s} {str:>12} {unit:7} {doc:}'.format(**item)

    def __str__(self):
        return str(self.result)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self._attr_info[attr]['value']

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(L3Ttrue))
        return list(sorted(all_attrs))



class L3Tdata(PsanaTypeData):

    def __init__(self, ds):

        self._typ, self._src, key = ds._evt_modules['L3T'].values()[0][0]
        typ_func = ds._current_evt.get(self._typ,self._src)
        PsanaTypeData.__init__(self, typ_func)

    def __str__(self):
        return str(self.result)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))


class EvrData(PsanaTypeData):

    def __init__(self, ds):

        self._typ, self._src, key = ds._evt_modules['EvrData'].values()[0][0]
        typ_func = ds._current_evt.get(self._typ,self._src)
        PsanaTypeData.__init__(self, typ_func)
        self.eventCodes = self.fifoEvents.eventCode
        #self._xray_dims = {'eventCode': ([],())}

    def present(self, eventCode):
        """Return True if the eventCode is present.
        """
        try:
            pres = self._typ_func.present(eventCode)
            if pres:
                return True
            else:
                return False
        except:
            return False

    def __str__(self):
        try:
            eventCodeStr = '{:}'.format(self.eventCodes)
        except:
            eventCodeStr = ''
        
        return eventCodeStr

class EvrNullData(object):
    """Evr data class when no EvrData type is in event keys.
       Occurs for controls cameras with no other daq data present.
    """

    def __init__(self, ds):
        self.eventCodes = []
        #self._xray_dims = {'eventCode': ([],())}

    def __str__(self):
        return ''


class EventId(object):
    """Time stamp information from psana EventId. 
    """

    _attrs = ['fiducials', 'idxtime', 'run', 'ticks', 'time', 'vector']
    _properties = ['datetime64', 'EventTime', 'timef64', 'nsec', 'sec']

    def __init__(self, evt):

        self._EventId = evt.get(psana.EventId)

    @property
    def datetime64(self):
        """NumPy datetime64 representation of EventTime.
           see:  http://docs.scipy.org/doc/numpy/reference/arrays.datetime.html
        """
        return np.datetime64(int(self.sec*1e9+self.nsec), 'ns')

    @property
    def EventTime(self):
        """psana.EventTime for use in indexed idx xtc files.
        """
        return psana.EventTime(int((self.sec<<32)|self.nsec), self.fiducials)

    @property
    def timef64(self):
        return np.float64(self.sec)+np.float64(self.nsec)/1.e9 

    @property
    def nsec(self):
        """nanosecond part of event time.
        """
        return self.time[1]

    @property
    def sec(self):
        """second part of event time.
        """
        return self.time[0]

    def show_info(self):
        print self.__repr__()
        for attr in self._attrs:
            if attr != 'idxtime': 
                print '{:18s} {:>12}'.format(attr, getattr(self, attr))

    def __str__(self):
        try:
            EventTimeStr = time.strftime('%H:%M:%S',
                    time.localtime(self.time[0]))
            EventTimeStr += '.{:04}'.format(int(self.time[1]/1e5))
        except:
            EventTimeStr = 'NA'

        return '{:}'.format(EventTimeStr)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(self._EventId, attr)()

    def __dir__(self):
        all_attrs =  set(self._attrs+
                         self.__dict__.keys() + dir(EventId))
        
        return list(sorted(all_attrs))


class Detector(object):
    """Includes epicsData, configData, evrConfig info 
       Uses full ds in order to be able to access epicsData info on
       an event basis.
    """
   
    _tabclass = 'evtData'
    _calib_class = None
    _det_class = None

    def __init__(self, ds, alias, verbose=False, **kwargs):
        """Initialize a psana Detector class for a given detector alias.
           Provides the attributes of the PyDetector functions for the current 
           event if applicable.  Otherwise provides the attributes from the
           raw data in the psana event keys for the given detector.
        """

        self._alias = alias
        self._ds = ds
        self.src = ds._aliases.get(alias)

        if self.src:
            if verbose:
                print 'Adding Detector: {:20} {:40}'.format(alias, psana.Source(self.src))
        
        else:
            print 'ERROR No Detector with alias {:20}'.format(alias)
            return

        self._srcstr = str(self.src)
        self._srcname = self._srcstr.split('(')[1].split(')')[0]
       
        self.configData = getattr(ds.configData, self._alias)

        try:
            self._pydet = psana.Detector(self._srcname, ds._ds.env())
        except:
            self._pydet = None

        if not hasattr(self._pydet, 'dettype'):
            # PyDetector for Ipimb does not provide dettype
            if hasattr(self._pydet, 'sum'):
                self._det_class = IpimbData
                self._calib_class = None
                self._tabclass = 'detector'
            else:
                self._det_class = None
                self._tabclass = 'evtData'
        # Quartz camera not yet implemented as AreaDetector
        elif self._pydet.dettype in [18]:
            self._det_class = None
            self._tabclass = 'evtData'
        # WFDetector
        elif self._pydet.dettype in [16, 17]:
            self._det_class = WaveformData
            self._calib_class = WaveformCalibData
            self._tabclass = 'detector'
        # AreaDetector
        elif self._pydet.dettype:
            self._det_class = ImageData
            self._calib_class = ImageCalibData
            self._tabclass = 'detector'
        else:
            self._det_class = None
            self._tabclass = 'evtData'

    @property
    def _xray_attrs(self):
        """Attributes
        """
        return {attr: item for attr, item in self.configData._all_values.items() \
                if np.product(np.shape(item)) <= 17}

    @property
    def _coords(self):
        if self._det_class == WaveformData:
            coords_dict = {
                    't': np.arange(self.configData.horiz.nbrSamples) \
                            *self.configData.horiz.sampInterval \
                            +self.configData.horiz.delayTime
                    }
            return coords_dict 

        elif self._det_class == ImageData:
            if self.calibData.ndim == 3:
                raw_dims = (['sensor', 'row', 'column'], self.calibData.shape)
                attrs = ['areas', 'coords_x', 'coords_y', 'coords_z', 
                         'gain', 'indexes_x', 'indexes_y', 'pedestals', 'rms']
                coords_dict = {}
                    
            elif self.calibData.ndim == 2:
                raw_dims = (['X', 'Y'], self.calibData.shape)
                attrs = []
                coords_dict = {
                        'X': self.calibData.ximage,
                        'Y': self.calibData.yimage}
            else:
                return {}

            for attr in attrs:
                val = getattr(self.calibData, attr)
                if val is not None:
                    coords_dict[attr] = (raw_dims[0], val)
        
            return coords_dict

        else:
            return {}


    @property
    def _xray_dims(self):
        """Dimensions of data attributes.
        """
        if self.src == 'BldInfo(FEE-SPEC0)':
            dims_dict = {attr: ([], ()) for attr in ['integral', 'npeaks']}
            dims_dict['hproj'] = (['X'], self.hproj.shape)

        elif self.src == 'DetInfo(XrayTransportDiagnostic.0:Opal1000.0)':
            dims_dict = {'data16': (['X', 'Y'], self.data16.shape)}

        elif self._det_class == WaveformData:
            dims_dict = {
                    'waveform':  (['ch', 't'], 
                        (self.configData.nbrChannels, self.configData.horiz.nbrSamples)),
                    }

        elif self._det_class == IpimbData:
            dims_dict = {
                    'sum':      ([], ()),
                    'xpos':     ([], ()),
                    'ypos':     ([], ()),
                    'channel':  (['ch'], (4,)),
                    }

        elif self._det_class == ImageData:
            if self.calibData.ndim == 3:
                raw_dims = (['sensor', 'row', 'column'], self.calibData.shape)
                dims_dict = {
#                    'image':     image_dims,
                    'calib':     raw_dims,
#                    'raw':       raw_dims,
                    }
            else:
                raw_dims = (['X', 'Y'], self.calibData.shape)
                if self.calibData.ximage is not None and self.calibData.yimage is not None:
                    image_shape = (len(self.calibData.ximage),len(self.calibData.yimage))
                    image_dims = (['X', 'Y'], image_shape)
                    dims_dict = {'calib':     image_dims}
                else:
                    image_dims = None
                    dims_dict = {}
   
        # temporary fix for Quartz camera not in PyDetector class
        elif self._pydet is not None and hasattr(self._pydet, 'dettype') \
                and self._pydet.dettype == 18:
            try:
                dims_dict = {'data8': (['X', 'Y'], self.data8.shape)}
            except:
                print str(self), 'Not valid data8'
        
        else:
            dims_dict = {attr: ([], ()) for attr in self.evtData._all_values}
                    
        return dims_dict

    @property
    def _attrs(self):
        """Attributes of psana.Detector functions if relevant, and otherwise
           attributes of raw psana event keys for the given detector.
        """
        if self._tabclass:
            tabclass = getattr(self, self._tabclass)
            if hasattr(tabclass, '_attrs'):
                return tabclass._attrs

        return []

    def next(self, *args, **kwargs):
        return getattr(self._ds.events.next(*args, **kwargs), self._alias)
 
    def __iter__(self):
        return self

    def monitor(self, nevents=-1, sleep=0.2):
        """Monitor detector attributes continuously with show_info function.
        """ 
        ievent = nevents
        try:
            while ievent != 0:
                self.next()
                try:
                    self.show_info()
                except:
                    pass
                
                if ievent < nevents and sleep:
                    time.sleep(sleep)

                ievent -= 1

        except KeyboardInterrupt:
            ievent = 0

    def show_all(self):
        print '-'*80
        print str(self)
        print '-'*80
        print 'Event Data:'
        print '-'*18
        self.evtData.show_info()
        if self._tabclass == 'detector':
            print '-'*80
            print 'Processed Data:'
            print '-'*18
            self.detector.show_info()
            if self._calib_class:
                print '-'*80
                print 'Calibration Data:'
                print '-'*18
                self.calibData.show_info()

        if self.configData:
            print '-'*80
            print 'Configuration Data:'
            print '-'*80
            self.configData.show_info()
        
        if self.epicsData:
            print '-'*80
            print 'Epics Data:'
            print '-'*18
            self.epicsData.show_info()

    def show_info(self):
        print '-'*80
        print str(self)
        print '-'*80
        getattr(self, self._tabclass).show_info()

    @property
    def evtData(self):
        """Tab accessible raw data from psana event keys.
        """
        return PsanaSrcData(self._ds._current_evt, self._srcstr, key_info=self._ds._evt_keys)

    @property
    def epicsData(self):
        return getattr(self._ds.epicsData, self._alias)

    @property
    def detector(self):
        """Raw, calib and image data using psana.Detector class
        """
        if self._pydet:
            return self._det_class(self._pydet, self._ds._current_evt)
        else:
            return None

    @property
    def calibData(self):
        """Calibration data using psana.Detector class
        """
        if self._pydet:
            return self._calib_class(self._pydet, self._ds._current_evt)
        else:
            return None

    def __str__(self):
        return '{:} {:}'.format(self._alias, str(self._ds.events.current))

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(getattr(self, self._tabclass), attr)

        if attr in self._ds.events.current._event_attrs:
            return getattr(self._ds.events.current, attr)

    def __dir__(self):
        all_attrs =  set(self._attrs+
                         self._ds.events.current._event_attrs +
                         self.__dict__.keys() + dir(Detector))
        
        return list(sorted(all_attrs))


class IpimbData(object):
    """Tab accessibile dictified psana.Detector object.
       
       Attributes come from psana.Detector 
       with low level implementation done in C++ or python.  
       Boost is used for the C++.
    """

    _attrs = ['channel', 'sum', 'xpos', 'ypos'] 

    _attr_info = {
            'channel':     {'doc': 'Array of 4 channel values',
                            'unit': 'V'},
            'sum':         {'doc': 'Sum of all 4 channels',
                            'unit': 'V'},
            'xpos':        {'doc': 'Calulated X beam position',
                            'unit': 'mm'},
            'ypos':        {'doc': 'Calulated Y beam position',
                            'unit': 'mm'},
            } 

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det

    @property
    def instrument(self):
        """Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def show_info(self):
        """Show information for relevant detector attributes.
        """
        try:
            items = sorted(self._attr_info.items(), key=operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                print '{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict)
        except:
            print 'No Event'

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(self._det, attr)(self._evt)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(IpimbData))
        
        return list(sorted(all_attrs))


class WaveformData(object):
    """Tab accessibile dictified psana.Detector object.
       
       Attributes come from psana.Detector 
       with low level implementation done in C++ or python.  
       Boost is used for the C++.
    """

    _attrs = ['raw', 'waveform', 'wftime'] 

    _attr_info = {
            'waveform':    {'doc': 'Waveform array',
                            'unit': 'V'},
            'wftime':      {'doc': 'Waveform sample time',
                            'unit': 's'},
            } 

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det

    @property
    def instrument(self):
        """Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def show_info(self):
        """Show information for relevant detector attributes.
        """
        try:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                print '{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict)
        except:
            print 'No Event'

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(self._det, attr)(self._evt)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(WaveformData))
        
        return list(sorted(all_attrs))


class WaveformCalibData(object):
    """Calibration data using psana.Detector access.
    """

    _attrs = ['runnum'] 

    _attr_info = {
            'runnum':      {'doc': 'Run number',
                            'unit': ''}
            }

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det

    @property
    def instrument(self):
        """Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def print_attributes(self):
        """Print detector attributes.
        """
        self._det.print_attributes()

    def set_calibration(self):
        """On/off correction of time.'
        """
        if self._det.dettype == 16:
            self._det.set_correct_acqiris_time()
        elif self._det.dettype == 17:
            self._det.set_calib_imp()

    def show_info(self):
        """Show information for relevant detector attributes.
        """
        try:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                print '{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict)
        except:
            print 'No Event'

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(self._det, attr)(self._evt)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(WaveformCalibData))
        
        return list(sorted(all_attrs))


class ImageData(object):
    """Tab accessibile dictified psana Detector object.
       
       Attributes come from psana.Detector  
       with low level implementation done in C++ or python.  
       Boost is used for the C++.
    """
    _attrs = ['image', 'raw', 'calib', 'shape', 'size'] 
    _attr_info = {
            'shape':       {'doc': 'Shape of raw data array', 
                            'unit': ''},
            'size':        {'doc': 'Total size of raw data', 
                            'unit': ''},
            'raw':         {'doc': 'Raw data', 
                            'unit': 'ADU'},
            'calib':       {'doc': 'Calibrated data',
                            'unit': 'ADU'},
            'image':       {'doc': 'Reconstruced 2D image from calibStore geometry',
                            'unit': 'ADU'},
            } 

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det

    @property
    def instrument(self):
        """Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def make_image(self, nda):
        """Make an image from the input numpy array based on the 
           geometry in the calib directory for this event.
        """
        return self._det.image(self._evt, nda)

    def common_mode_correction(self, nda):
        """Return the common mode correction for the input numpy 
           array (pedestal-subtracted). 
        """
        return self._det.common_mode_correction(self._evt, nda)
        
    def common_mode_apply(self, nda):
        """Apply in place the common mode correction for the input 
           numpy array (pedestal-subtracted). 
        """
        self._det.common_mode_apply(self._evt, nda)

    def show_info(self):
        """Show information for relevant detector attributes.
        """
        if self.size > 0:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                print '{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict)
        else:
            print 'No Event'

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(self._det, attr)(self._evt)
        
    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(ImageData))
        
        return list(sorted(all_attrs))


class ImageCalibData(object):
    """Calibration Data from psana Detector object.
    """

    _attrs = ['shape', 'size', 'ndim', 'pedestals', 'rms', 'gain', 'bkgd', 'status',
              'common_mode', 'runnum',
              'areas', 'indexes_x', 'indexes_y', 'pixel_size',
              'coords_x', 'coords_y', 'coords_z', 
             ] 
    _attr_info = {
            'runnum':      {'doc': 'Run number',
                            'unit': ''},
            'shape':       {'doc': 'Shape of raw data array', 
                            'unit': ''},
            'size':        {'doc': 'Total size of raw data', 
                            'unit': ''},
            'ndim':        {'doc': 'Number of dimensions of raw data', 
                            'unit': ''},
            'pedestals':   {'doc': 'Pedestals from calibStore', 
                            'unit': 'ADU'},
            'rms':         {'doc': '', 
                            'unit': 'ADU'},
            'gain':        {'doc': 'Pixel Gain factor from calibStore', 
                            'unit': ''},
            'bkgd':        {'doc': '', 
                            'unit': ''},
            'status':      {'doc': '',
                            'unit': ''},
            'common_mode': {'doc': 'Common mode parameters', 
                            'unit': ''},
            'areas':       {'doc': 'Pixel area correction factor', 
                            'unit': ''},
            'indexes_x':   {'doc': 'Pixel X index', 
                            'unit': ''},
            'indexes_y':   {'doc': 'Pixel Y index', 
                            'unit': ''},
            'pixel_size':  {'doc': 'Pixel Size',
                            'unit': 'um'},
            'coords_x':    {'doc': 'Pixel X coordinate', 
                            'unit': 'um'},
            'coords_y':    {'doc': 'Pixel Y coordinate', 
                            'unit': 'um'},
            'coords_z':    {'doc': 'Pixel Z coordinate', 
                            'unit': 'um'},
            } 

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det

    @property
    def instrument(self):
        """Instrument to which this detector belongs.
        """
        return self._det.instrument()

    @property
    def ximage(self):
        """X axis of image [um].
        """
        if self.indexes_x is not None:
            n = self.indexes_x.max()+1
            return (np.arange(n)-n/2.)*self.pixel_size
        else:
            if len(self.shape) == 2:
                return np.arange(self.shape[0])

    @property
    def yimage(self):
        """Y axis of image [um].
        """
        if self.indexes_y is not None:
            n = self.indexes_y.max()+1
            return (np.arange(n)-n/2.)*self.pixel_size
        else:
            if len(self.shape) == 2:
                return np.arange(self.shape[1])

    def set_do_offset(do_offset=True):
        """Not sure what do offset does?
        """
        self._det.set_do_offset(do_offset=do_offset)

    def mask(self, calib=False, status=False, 
                   edges=False, central=False, 
                   unbond=False, unbondnbrs=False):
        """Returns combined mask.
                calib:      mask from file in calib directory.
                status:     pixel status from file in calib director.
                edges:      mask detector module edge pixels (mbit +1 in mask_geo).
                central:    mask wide central columns (mbit +2 in mask_geo).
                unbond:     mask unbonded pixels (mbit +4 in mask_geo).
                unbondnbrs: mask unbonded neighbour pixels (mbit +8 in mask_geo).
        """
        return self._det.mask(self._evt, calib=False, status=False, edges=False, 
                              central=False, unbond=False, unbondnbrs=False)

    def mask_geo(self, mbits=15): 
        """Return geometry mask for given mbits keyword.
           Default is mbits=15 to mask edges, wide central columns,
             non-bo pixels and their neighbors

           mbits =  +1-edges; 
                    +2-wide central cols; 
                    +4 unbonded pixel; 
                    +8-unbonded neighbour pixels;
        """
        return self._det.mask_geo(self._evt, mbits=mbits)

    def print_attributes(self):
        """Print detector attributes.
        """
        self._det.print_attributes()

    def show_info(self):
        """Show information for relevant detector attributes.
        """
        if self.size > 0:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                print '{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict)
        else:
            print 'No Event'

    def __getattr__(self, attr):
        if attr in self._attrs:
            return (getattr(self._det, attr)(self._evt))
        
    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(ImageCalibData))
        
        return list(sorted(all_attrs))


class EpicsConfig(object):
    """Tab Accessible configStore Epics information.
       Currently relatively simple, but expect this to be expanded
       at some point with more PV config info with daq update.
    """

    _pv_attrs = ['description', 'interval', 'pvId']

    def __init__(self, configStore):

        # move to PsanaSrcData objects
        self._pvs = {}
        for key in configStore.keys():
            if key.type() and key.type().__module__ == 'psana.Epics':
                a = configStore.get(key.type(),key.src())
                for pv in a.getPvConfig():
                    pvdict = {attr: getattr(pv, attr)() for attr in self._pv_attrs} 
                    self._pvs[pv.description()] = pvdict

    def show_info(self):
        for alias, items in self._pvs.items():
            print '{:18s} {:}'.format(alias, item.pvId)

    def __getattr__(self, attr):
        if attr in self._pvs:
            return self._pvs.get(attr)

    def __dir__(self):
        all_attrs =  set(self._pvs.keys() +
                         self.__dict__.keys() + dir(EpicsConfig))
        
        return list(sorted(all_attrs))


class EpicsData(object):
    """Epics data from psana epicsStore.
       e.g., 
         epicsStore = EpicsData(ds)
         returns dictified representation of ds.env().epicsStore()
    """

    def __init__(self, ds):

        self._ds = ds

        pv_dict = {}
        epicsStore = self._ds.env().epicsStore()
        self.epicsConfig = EpicsConfig(self._ds.env().configStore())

        for pv in  epicsStore.names():
            name = re.sub(':|\.','_',pv)
            #check if valid -- some old data had aliases generated from comments in epicsArch files.
            if re.match("[_A-Za-z][_a-zA-Z0-9]*$", name) and not ' ' in name and not '-' in name:
                pvname = epicsStore.pvName(pv)
                if pvname:
                    pvalias = pv
                else:
                    pvalias = epicsStore.alias(pv)
                    pvname = pv

                pvalias = re.sub(':|\.|-| ','_',pvalias)
                components = re.split(':|\.|-| ',pv)
                if len(components) == 1:
                    components = re.split('_',pv,1)
                
                # check if alias has 2 components -- if not fix
                if len(components) == 1:
                    pv = '_'.join([components[0], components[0]])
                    components = re.split('_',pv,1)

                for i,item in enumerate(components):
                    if item[0].isdigit():
                         components[i] = 'n'+components[i]

                pv_dict[name] =  { 'pv': pvname,
                                   'alias': pvalias,
                                   'components': components,
                                 }
        self._pv_dict = pv_dict
        self._attrs = list(set([val['components'][0] for val in self._pv_dict.values()]))

    def __getattr__(self, attr):
        if attr in self._attrs:
            attr_dict = {key: pdict for key,pdict in self._pv_dict.items()
                         if pdict['components'][0] == attr}
            return PvData(attr_dict, self._ds, level=1)
        
        if attr in dir(self._ds.env().epicsStore()):
            return getattr(self._ds.env().epicsStore(),attr)

    def __dir__(self):
        all_attrs = set(self._attrs +
                        dir(self._ds.env().epicsStore()) +
                        self.__dict__.keys() + dir(EpicsData))
        return list(sorted(all_attrs))


class PvData(object):
    """Epics PV Data.
    """

    def __init__(self, attr_dict, ds, level=0):
        self._attr_dict = attr_dict
        self._ds = ds
        self._level = int(level)
        self._attrs = list(set([pdict['components'][level]
                                for key,pdict in attr_dict.items()]))

    def _get_pv(self, pv):
        return EpicsStorePV(self._ds.env().epicsStore(), pv)

    def show_info(self):
        """Show information from PVdictionary for all PV's starting with 
           the specified dictified base.
           (i.e. ':' replaced by '.' to make them tab accessible in python)
        """
        print self.get_info()

    def get_info(self):
        """Return string representation of all PV's starting with 
           the specified dictified base.
           (i.e. ':' replaced by '.' to make them tab accessible in python)
        """
        info = ''
        items = sorted(self._attr_dict.items(), key=operator.itemgetter(0))
        for key,pdict in items:
            alias = pdict['alias']
            if alias:
                name = alias
                pv = pdict['pv']
            else:
                name = pdict['pv']
                pv = ''

            pvfunc = self._get_pv(pdict['pv'])
            value = pvfunc.value
            if pvfunc.isCtrl:
                comment = 'isCtrl'
            else:
                comment = ''

            try:
                info += '{:30s} {:12.4g} -- {:30s} {:10}\n'.format( \
                        name, value, pv, comment)
            except:
                info += '{:30s} {:>12} -- {:30s} {:10}\n'.format( \
                        name, value, pv, comment)
        return info

    def __getattr__(self, attr):
        if attr in self._attrs:
            attr_dict = {key: pdict for key,pdict in self._attr_dict.items()
                         if pdict['components'][self._level] == attr}
            if len(attr_dict) == 1:
                key = attr_dict.keys()[0]
                if len(self._attr_dict[key]['components']) == (self._level+1):
                    pv = self._attr_dict[key]['pv']
                    return self._get_pv(pv)
            if len(attr_dict) > 0:
                return PvData(attr_dict, self._ds, level=self._level+1)

    def __repr__(self):
        return self.get_info()

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(PvData))
        return list(sorted(all_attrs))


class EpicsStorePV(object):
    """Epics PV access from epicsStore. 
    """

    def __init__(self, epicsStore, pv):
        self._epicsStore = epicsStore
        self._pvname = pv
        self._store = epicsStore.getPV(pv)
        self._attrs = [attr for attr in dir(self._store) \
                if not attr.startswith('_')]
        self._show_attrs = [attr for attr in self._attrs \
                if attr not in ['dbr','stamp']]

    def get_info(self):
        info = '-'*80+'\n'
        info += '{:} = {:} -- {:}\n'.format(self._pvname, \
                                self.value, self.stamp)
        info += '-'*80+'\n'
        for attr in self._show_attrs:
            val = self.get(attr)
            info += '{:20} {:12}\n'.format(attr, val)
        
        return info

    def show_info(self):
        print self.get_info()

    def get(self, attr):
        if attr in self._attrs:
            if attr is 'value':
                return self._epicsStore.value(self._pvname)
            else:
                val = getattr(self._store,attr)
                try:
                    if attr is 'stamp':
                        return TimeStamp(val())
                    else:
                        return val() 
                except:
                    return val
        else:
            return None

    def __str__(self):
        return '{:}'.format(self.value)

    def __repr__(self):
        return '< {:} = {:}, {:} -- {:} >'.format(self._pvname, \
                self.value, self.stamp, \
                self.__class__.__name__)

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self.get(attr)

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(EpicsStorePV))
        return list(sorted(all_attrs))


class TimeStamp(object):

    def __init__(self, stamp):
        self.sec = stamp.sec()
        self.nsec = stamp.nsec()

    @property
    def date(self):
        return time.strftime('%Y-%m-%d', 
                time.localtime(self.sec))

    @property
    def time(self): 
        EventTimeStr = time.strftime('%H:%M:%S',
                time.localtime(self.sec))
        EventTimeStr += '.{:04}'.format(int(self.nsec/1e5))
        return EventTimeStr

    def __str__(self):
        return '{:}.{:} sec'.format(self.sec, self.nsec)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name_, _self.__str__)


