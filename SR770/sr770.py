# Copyright (C) 2008 Erik Lucero
# Edits: Daniel Sank - 2010 December
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
### BEGIN NODE INFO
[info]
name = Signal Analyzer SR770
version = 1.1.1
description = Talks to the Stanford Research Systems Signal Analyzer

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""


from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T, util

from labrad.units import Value, Unit

Hz,MHz = [Unit(s) for s in ['Hz', 'MHz']]

from struct import unpack
import numpy as np

NUM_POINTS=400

SPANS = {0:0.191,
              1:0.382,
              2:0.763,
              3:1.5,
              4:3.1,
              5:6.1,
              6:12.2,
              7:24.4,
              8:48.75,
              9:97.5,
              10:195.0,
              11:390.0,
              12:780.0,
              13:1560.0,
              14:3120.0,
              15:6250.0,
              16:12500.0,
              17:25000.0,
              18:50000.0,
              19:100000.0}

MEAS_TYPES = {
              'SPECTRUM':0,
              'PSD':1,
              'TIME RECORD':2,
              'OCTAVE':3
              }

AMPLITUDE_UNITS = {
            'VPK': 0,
            'VRMS': 1,
            'DBV': 2,
            }
PHASE_UNITS = {
            'DEGREES': 0,
            'RADIANS': 1
            }

DISPLAY_TYPES = {
            'LOG MAG': 0,
            'LINEAR MAG': 1,
            'REAL': 2,
            'IMAG': 3,
            'PHASE': 4
            }

class SR770Wrapper(GPIBDeviceWrapper):
    pass
    #TODO
    #Put device initialization code here
    #Set up device parameters and move logic code from settings to here so the device knows if a command will
    #fail because of conflicting setings, ie trying to set a phase unit when amplitude is being displayed.
    # def __init__(self):
        # self.measure='PSD'
        # self.display='LOG MAG'
        # self.units='VRMS'
        # yield self.reset()

class SR770Server(GPIBManagedServer):
    """Serves the Stanford Research Systems SR770 Network Signal Analyzer.
    A low frequency (0-100kHz) FFT. Can save data to datavault."""
    name = 'Signal Analyzer SR770'
    deviceName = 'Stanford_Research_Systems SR770'
    deviceWrapper = SR770Wrapper
    deviceIdentFunc = 'identify_device'

    @setting(1000, server='s', address='s')
    def identify_device(self, c, server, address):
        print 'identifying:', server, address
        try:
            s = self.client[server]
            p = s.packet()
            p.address(address)
            p.write('*IDN?\n')
            p.read()
            ans = yield p.send()
            resp = ans.read
            print 'got ident response:', resp
            if resp == 'Stanford_Research_Systems,SR770,s/n24489,ver091':
                returnValue(self.deviceName)
        except Exception, e:
            print 'failed:', e
            raise
            
            

    #FREQUENCY SETTINGS
    @setting(10, sp=['i{integer span code}','v[Hz]'], returns=['v[Hz]'])
    def span(self, c, sp=None):
        """Get or set the current frequency span.
        The span is specified by an integer from 0 to 19 or by a labrad
        Value with frequency units. The allowed integers are:
        
        (i,   span)
        (0,   191mHz)
        (1,   382mHz)
        (2,   763mHz)
        (3,   1.5Hz)
        (4,   3.1Hz)
        (5,   6.1Hz)
        (6,   12.2Hz)
        (7,   24.4Hz)
        (8,   48.75Hz)
        (9,   97.5Hz)
        (10,  195Hz)
        (11,  390Hz)
        (12,  780Hz)
        (13,  1.56KHz)
        (14,  3.125KHz)
        (15,  6.25KHz)
        (16,  12.5KHz)
        (17,  25KHz)
        (18,  50KHz)
        (19,  100KHz)
        
        Note that while the input spans can be integers or frequency values,
        you will always get a frequency value passed back. This is done because
        I don't expect users to know the conversion between integers and
        frequency values.
        """
        dev = self.selectedDevice(c)
        #If the user gave a span, write it to the device
        if sp is not None:
            #If span is an integer, check that it's in the allowed range, and get the appropriate value in Hz
            if isinstance(sp,int):
                if not (sp>-1 and sp<20):
                    raise Exception('span must be in [0,19]')
            #Else if span is a value, check that it's a frequency, and in the allowed range.
            elif isinstance(sp,Value):
                if not sp.isCompatible('Hz'):
                    raise Exception('Spans specified as Values must be in frequency units')
                if not sp['Hz']<100000 and sp['Hz']>0.191:
                    raise Exception('Frequency span out of range')
                sp = indexOfClosest(SPANS.values(),sp['Hz'])
            else:
                raise Exception('Unrecognized span. Span must be an integer or a Value with frequency units')
                
            yield dev.write('SPAN%d\n' % sp)
        #Readback span. This comes as an integer code, which we convert to a Value
        resp = yield dev.query('SPAN?\n')
        sp = Value(float(SPANS[int(resp)]), 'Hz')

        returnValue(sp)

    @setting(11, cf=['v[Hz]'], returns=['v[Hz]'])
    def center_frequency(self, c, cf=None):
        """Get or set the center frequency."""
        dev = self.selectedDevice(c)
        #If the user specified a center frequency
        if cf is not None:
            #Make sure it's a frequency unit
            if isinstance(cf,Value) and cf.isCompatible('Hz'):
                cf = cf['Hz']
            #Otherwise, error
            else:
                raise Exception('Center frequency must be a frequency value')
            #Send that frequency to the device
            yield dev.write('CTRF, %f\n' % cf)
        #Readback current center frequency
        resp = yield dev.query('CTRF?\n')
        cf = Value(float(resp), 'Hz')
        returnValue(cf)

    @setting(12, fs=['v[Hz]'], returns=['v[Hz]'])
    def start_frequency(self, c, fs=None):
        """Get or set the start frequency. Must be between 0 and 100kHz"""
        dev = self.selectedDevice(c)
        if fs is not None:
            if isinstance(sf,Value) and sf.isCompatible('Hz'):
                sf = sf['Hz']
            else:
                raise Exception('Start frequency must be a frequency Value')
            #Write to the device
            yield dev.write('STRF,%f\n' % fs)
        #Readback the start frequency
        resp = yield dev.query('STRF?\n')
        fs = T.Value(float(resp), 'Hz')
        returnValue(fs)
        


    #AVERAGING
    @setting(17, avg=['w', 's', 'b'], returns=['b'])
    def average(self, c, avg=None):
        """Query or turn ON/OFF Averaging."""
        dev = self.selectedDevice(c)
        units = {
            'OFF': 0,
            'ON': 1,
            }
        #If the user specified avg
        if avg is not None:
            if isinstance(avg,bool):
                avg=int(avg)
            elif isinstance(avg,int):
                pass
            elif isinstance(avg,str):
                avg = units[avg.upper()]
            else:
                raise Exception('avg type not recognized')
            yield dev.write('AVGO%d\n' %avg)
        #Readback averaging
        resp = yield dev.query('AVGO?\n')
        avg = bool(int(resp))
        returnValue(avg)

    @setting(18, av=['i'], returns=['i'])
    def num_averages(self, c, av=None):
        """Get or set the number of averages."""
        print 'type of av is: ',type(av)
        dev = self.selectedDevice(c)
        if av is not None:
            if isinstance(av,int):
                if av<2 or av>32767:
                    raise Exception('Average number out of range. Must be >2 and <32767')
            else:
                raise Exception('Number of averages must be an integer')
            yield dev.write('NAVG %d \n' %av)
        resp = yield dev.query('NAVG?\n')
        av = int(resp)
        returnValue(av)
    

    #MEASUREMENT SETTINGS
    @setting(30, trace=['i{which trace to set/get}'], measType=['i{integer code for measure type}','s{measure type}'], returns=['i{integerCode}s{measureType}'])
    def measure(self, c, trace, measType=None):
        """Get or set the measurement type.
        0: SPECTRUM,
        1: PSD,
        2: TIME RECORD,
        3: OCTAVE
        """
        dev = self.selectedDevice(c)
        #If the user specified a measure type
        if measType is not None:
            #If it's a string, get the appropriate integer code
            if isinstance(measType,str):
                measType = MEAS_TYPES[measType.upper()]
            #Otherwise if it's an integer make sure it's allowed
            elif isinstance(measType,int):
                if measType<0 or measType>3:
                    raise Exception('Measure type code out of range')
            #Write the measure type to the device
            yield dev.write('MEAS%d,%d\n' %(trace,measType))
        #Read back the current measure type for the specified trace, comes back as integer code
        resp = yield dev.query('MEAS?%d\n' %trace)
        #Turn the integer code into a string for the user
        answer = dict([(intCode,meas) for meas,intCode in MEAS_TYPES.items()])[int(resp)]
        returnValue((int(resp),answer))

    @setting(31, trace = 'i', disp=['s', 'i'], returns=['i{integer code of display type}s{display type}'])
    def display(self, c, trace, disp=None):
        """Get or set the view.
        0 Log Mag;
        1 Linear Mag;
        3 Real Part;
        4 Imaginary Part;
        5 Phase;
        """
        dev = self.selectedDevice(c)
        if disp is not None:
            if isinstance(disp,str):
                disp = DISPLAY_TYPES[disp.upper()]
            elif isinstance(disp,int):
                if disp>4 or disp<0:
                    raise Exception('integer code out of range [0,4]')
            #Find out what the current measure type is
            meas = yield self.measure(c,trace)
            meas = meas[1]
            if meas=='SPECTRUM':
                pass #All display types allowed
            elif meas=='PSD' and not (disp==0 or disp==1):
                raise Exception('PSD measurement requires lin mag or log mag display')
            elif meas=='TIME RECORD':
                pass #All display types allowed
            elif meas=='OCTAVE' and not (disp==0):
                raise Exception('OCTAVE measurement requires LOG MAG display type')
            yield dev.write('DISP%d,%d\n' %(trace,disp))
        resp = yield dev.query('DISP?%d\n' %trace)
        answer = dict([(intCode,displayType) for displayType,intCode in DISPLAY_TYPES.items()])[int(resp)]
        returnValue((int(resp),answer))

    @setting(32, trace='i', unit='s', returns=['is'])
    def units(self, c, trace, unit=None):
        """Get or set the units.
        Amplitude units
        0: Vpk;
        1: Vrms;
        2: dBV;
        3: dBVrms;
        
        Phase units
        0: degrees
        1: radians
        """
        dev = self.selectedDevice(c)
        #Find out what's currently being displayed
        display = yield self.display(c,trace)
        display = display[1]
        #If the user wants to set a new unit
        if unit is not None:
            #Find out whether we're trying to set units to a phase unit or amplitude unit
            if unit.upper() in PHASE_UNITS.keys():
                unitSetType='PHASE'
                intCode = PHASE_UNITS[unit.upper()]
            elif unit.upper() in AMPLITUDE_UNITS.keys():
                unitSetType='AMPLITUDE'
                intCode = AMPLITUDE_UNITS[unit.upper()]
            else:
                raise Exception('Units not recognized')
            if (display=='PHASE' and unitSetType=='AMPLITUDE') or (display!='PHASE' and unitSetType =='PHASE'):
                raise Exception('Unit type must match display type. Cannot set phase units without phase display, and vice versa')
            dev.write('UNIT%d,%d\n' %(trace,intCode))
        #Readback units
        resp = yield dev.query('UNIT?%d\n' %trace)
        resp = int(resp)
        if display is 'PHASE':
            returnValue((resp,inverseDict(PHASE_UNITS)[resp]))
        else:
            returnValue((resp,inverseDict(AMPLITUDE_UNITS)[resp]))
        
    @setting(100, trace='i', returns='*v')
    def get_trace(self, c, trace):
        """Get the trace."""
        dev = self.selectedDevice(c)
        #Read the binary data and unpack
        bytes = yield dev.query('SPEB?%d' %trace)
        numeric = np.array(unpack('h'*400,bytes))
        #Find out what the display is and scale the data appropriately
        display = yield self.display(c,trace)
        #Data can be on log scale,
        display=display[1]
        if display=='LOG MAG':
            tRef = yield dev.query('TREF?%d\n' %trace)
            tRef = float(tRef)
            bRef = yield dev.query('BREF?%d\n' %trace)
            bRef = float(bRef)
            fullScale = tRef-bRef
            print 'fullScale: ',type(fullScale)
            print 'numeric: ',type(numeric)
            data = ((3.013*numeric)/512.0)-(114.3914*fullScale)
        #Or linear scale amplitude,
        elif display in ['LINEAR MAG','REAL','IMAG']:
            raise Exception('crap')            
        #Or phase
        elif display=='PHASE':
            raise Exception('Phase traces not supported yet. You get to write some code!')            
        #Get frequency axis
        startFreq = yield dev.query('STRF?\n')
        startFreq = float(startFreq)
        span = yield self.span(c)
        span = span['Hz']
        stopFreq = startFreq+span
        frequencies = np.linspace(startFreq,stopFreq,400)
        returnData = np.hstack((frequencies,data)).T
        returnValue(data)
        
        
    @setting(110, name=['s'], returns=['*(v[Hz] v[Vrms/Hz^1/2])'])
    def freq_sweep_save(self, c, name='untitled'):
        """Initiate a frequency sweep.

        The data will be saved to the data vault in the current
        directory for this context.  Note that the default directory
        in the data vault is the root directory, so you should cd
        before trying to save.
        """
        dev = self.selectedDevice(c)

        length = yield dev.query("DSPN? 0\n")
        length = int(length)
        print length
        data = yield dev.query("DSPB? 0\n")
        print len(data)

        if len(data) != length*4:
            raise Exception("Lengths don't match, dude! %d isn't equal to %d" % (len(data), length*4))

        print "unpacking..."

        data = [unpack('<f', data[i*4:i*4+4])[0] for i in range(length)]
        data = np.array(data)
        #Calculate frequencies from current span
        resp = yield dev.query('FSTR?0\n')
        fs = T.Value(float(resp), 'Hz')
        resp = yield dev.query('FEND?0\n')
        fe = T.Value(float(resp), 'Hz')
        freq = np.linspace(fs, fe, length)
        
        

        dv = self.client.data_vault
        
        independents = ['frequency [Hz]']
        dependents = [('Sv', 'PSD', 'Vrms/Hz^1/2')]
        p = dv.packet()
        p.new(name, independents, dependents)
        p.add(np.vstack((freq, data)).T)
        p.add_comment('Autosaved by SR770 server.')
        yield p.send(context=c.ID)
        
        returnValue(zip(freq, data))

    # helper methods

    @setting(150)
    def startsweep(self, c, sweeptype):
        dev = self.selectedDevice(c)
        yield dev.write('STRT\n')
    

def inverseDict(d):
    outDict = dict([(value,key) for key,value in d.items()])
    return outDict

def findIndexOfMinimum(arr):
    return arr.index(min(arr))

def indexOfClosest(collection,target):
    diffs = [abs(elem-target) for elem in collection]
    index = findIndexOfMinimum(diffs)
    return index
    
__server__ = SR770Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
