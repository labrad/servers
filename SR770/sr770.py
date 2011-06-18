# Copyright (C) 2009 Daniel Sank
# Adapted from sr780.py by Erik Lucero
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
version = 1.2.0
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

from labrad import util

from labrad.units import Value, Unit

Hz,MHz,V,nV = [Unit(s) for s in ['Hz', 'MHz', 'V', 'nV']]

from struct import unpack
import numpy as np

NUM_POINTS=400

COUPLINGS = {0: 'AC',
             1: 'DC'}

GROUNDINGS = {
              0: 'FLOAT',
              1: 'GROUND'
              }

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

WINDOWS = {
            'UNIFORM': 0,
            'FLATTOP': 1,
            'HANNING': 2,
            'BLACKMANHARRIS': 3
            }
class SR770Wrapper(GPIBDeviceWrapper):
    #TODO
    #Set up device parameters and move logic code from settings to here so the device knows if a command will
    #fail because of conflicting setings, ie trying to set a phase unit when amplitude is being displayed.
    def initialize(self):
        self.SETTLING_TIME = Value(30,'s')
        self.AVERAGING_TIME = Value(10,'s')
        
    #DEVICE SETUP AND OPERATION
    @inlineCallbacks
    def input_range(self,range):
        #If the user gave an input range
        if range is not None:
            if isinstance(range,int):
                if range<-60 or range>34 or not(range%2==0):
                    raise Exception('Input range must be an even number in [-60,34]')
            else:
                raise Exception('Input range must be an integer')
            yield self.write('IRNG%d\n' %range)
        #Readback input range
        resp = yield self.query('IRNG?\n')
        resp = int(resp)
        returnValue(resp)
        
    @inlineCallbacks
    def coupling(self, coupling):
        if coupling is not None:
            if isinstance(coupling,int):
                if coupling not in [0,1]:
                    raise Exception('Coupling specified as integer must be 0 or 1')
            elif isinstance(coupling,str):
                if coupling.upper() not in ['AC','DC']:
                    raise Exception('Coupling specified as string must be AC or DC')
                coupling = inverseDict(COUPLINGS)[coupling.upper()]
            else:
                raise Exception('Coupling not recognized')
            yield self.write('ICPL%d\n' %coupling)
        resp = yield self.query('ICPL?\n')
        returnValue(COUPLINGS[int(resp)])

    @inlineCallbacks
    def grounding(self, grounding):
        if grounding is not None:
            if isinstance(grounding,int) and grounding not in GROUNDINGS.keys():
                raise Exception('Groundings specified as integer must be 0 or 1')
            elif isinstance(grounding,str):
                if grounding.upper() not in GROUNDINGS.values():
                    raise Exception('Grounding specified as string must be %s or %s' %tuple([u for u in GROUNDINGS.values()]))
                grounding = inverseDict(GROUNDINGS)[grounding.upper()]
            yield self.write('IGND%d\n' %grounding)
        resp = yield self.query('IGND?\n')
        returnValue(GROUNDINGS[int(resp)])
        
    @inlineCallbacks
    def start(self):
        yield self.write('STRT\n')

    #Averaging
    @inlineCallbacks
    def overlapPercentage(self,ov):
        yield self.write('OVLP%f\n' %ov)
        resp = yield self.query('OVLP?\n')
        returnValue(resp)
        
    #Status checks and wait functions
    @inlineCallbacks
    def clearStatusBytes(self):
        yield self.write('*CLS\n')
    
    @inlineCallbacks
    def waitForAveraging(self):
        waited = 0
        while 1:
            done = yield self.doneAveraging()
            if done:
                returnValue(None) #Return None because returnValue needs an argument
            else:
                waited+=1
                print 'Device waiting for averaging to complete.'
                print 'Will check again in %d seconds' %self.AVERAGING_TIME['s']
                print 'This is wait number: %d' %waited
                yield util.wakeupCall(self.AVERAGING_TIME['s'])
    
    @inlineCallbacks
    def doneAveraging(self):
        resp = yield self.query('FFTS?4\n')
        if int(resp)==1:
            returnValue(True)
        else:
            returnValue(False)
            
    @inlineCallbacks
    def waitForSettling(self):
        while 1:
            done = yield self.doneSettling()
            if done:
                returnValue(None) #Return None because returnValue needs an argument
            else:
                print 'Device waiting for settling. Will check again in %d seconds' %self.SETTLING_TIME['s']
                yield util.wakeupCall(self.SETTLING_TIME['s'])
    
    @inlineCallbacks
    def doneSettling(self):
        resp = yield self.query('FFTS?7\n')
        if int(resp)==1:
            returnValue(True)
        else:
            returnValue(False)

    @inlineCallbacks
    def clearReadBuffer(self):
        raise Exception('Does not work')
        i=0
        while 1:
            i+=1
            print i
            try:
                resp = yield self.read()
                'Cleared: ', resp
                yield self.wakeupCall(1)
            except:
                break
            
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
            if isinstance(fs,Value) and fs.isCompatible('Hz'):
                fs = fs['Hz']
            else:
                raise Exception('Start frequency must be a frequency Value')
            #Write to the device
            yield dev.write('STRF%f\n' % float(fs))
        #Readback the start frequency
        resp = yield dev.query('STRF?\n')
        fs = Value(float(resp), 'Hz')
        returnValue(fs)
    
    @setting(13, sp=['i','v[Hz]'], fs='v[Hz]', returns='(v[Hz]v[Hz])')
    def freq_and_settle(self, c, sp, fs):
        dev = self.selectedDevice(c)
        yield dev.write('*CLS\n')
        sp = yield self.span(c, sp)
        fs = yield self.start_frequency(c, fs)
        yield dev.waitForSettling()
        returnValue((sp,fs))

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
    
    @setting(19, ov='v{overlap percentage}', returns='v{readback overlap percentage}')
    def overlap(self, c, ov):
        dev = self.selectedDevice(c)
        ov = yield dev.overlapPercentage(ov)
        returnValue(ov)
    #SCALE SETTINGS
    @setting(20, trace='i')
    def autoscale(self, c, trace):
        """Autoscale the display"""
        dev = self.selectedDevice(c)
        dev.write('AUTS%d\n' %trace)
    
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

    @setting(33, trace='i', window=['i','s'], returns=['s{Window type}'])
    def window(self, c, trace, window=None):
        dev = self.selectedDevice(c)
        if window is not None:
            if isinstance(window,str):
                window = WINDOWS[window.upper()]
            elif isinstance(window,int) and window not in [0,1,2,3]:
                raise Exception('Window specified as integer must be in range 0 to 3')
            yield dev.write('WNDO%d,%d\n' %(trace,window))
        resp = yield dev.query('WNDO?%d\n' %trace)
        answer = inverseDict(WINDOWS)[int(resp)]
        returnValue(answer)
        
    #DEVICE SETUP AND OPERATION
    @setting(50, coupling=['i','s'], returns='s')
    def coupling(self, c, coupling=None):
        dev = self.selectedDevice(c)
        resp = yield dev.coupling(coupling)
        returnValue(resp)
    
    @setting(51, returns='')
    def start(self, c):
        dev = self.selectedDevice(c)
        yield dev.start()

    @setting(52, range='i{input range in dbV}', returns='i{input range in dbV}')
    def input_range(self, c, range=None):
        """Get or set the input range
        Note that the units of the input range are the weird decibel unit defined as
        
        20*log10(N)
        """
        dev = self.selectedDevice(c)
        result = yield dev.input_range(range)
        returnValue(result)

    @setting(53, grnd=['i','s'], returns = 's')
    def grounding(self, c, grnd=None):
        dev = self.selectedDevice(c)
        result = yield dev.grounding(grnd)
        returnValue(result)
        

    @setting(54, returns='')
    def clear_status_bytes(self, c):
        dev = self.selectedDevice(c)
        yield dev.clearStatusBytes()
        
    @setting(55, returns='')
    def clear_read_buffer(self, c):
        raise Exception('Does not work')
        dev = self.selectedDevice(c)
        yield dev.clearReadBuffer()
        
    #DATA RETREIVAL
    @setting(100, trace='i{trace}', returns='*v{raw numeric trace data}')
    def get_trace(self, c, trace):
        """Get the trace."""
        dev = self.selectedDevice(c)
        #Read from device
        bytes = yield dev.query('SPEB?%d\n' %trace)
        #Unpack binary data
        numeric = unpackBinary(bytes)
        returnValue(numeric)

    @setting(101, trace='i{trace}', returns='*2v{[freq,sqrt(psd)]}')
    def power_spectral_amplitude(self, c, trace):
        """Get the trace in spectral amplitude (RMS) units
        
        Window correction factors have not yet been implemented, so for now we
        raise an exception if the window isn't uniform!!!
        """
        dev = self.selectedDevice(c)
        #Clear all status bytes
        yield dev.clearStatusBytes()
        #Check that display is log magnitude
        disp = yield self.display(c, trace)
        if disp[1]!='LOG MAG':
            raise Exception('Display must be LOG MAG for power spectral amplitude retrieval')
        #Get input range, span, linewidth, and start frequency
        inputRange = yield self.input_range(c)
        span = yield self.span(c)
        linewidth = span/NUM_POINTS
        freqStart = yield self.start_frequency(c)
        #Check the window type
        window = self.window(c)
        if not window=='UNIFORM':
            raise Exception('Window must be set to uniform for power spectral amplitude')
        #Start the averagine cycle
        yield dev.start()
        yield dev.waitForAveraging()
        #Read from device
        bytes = yield dev.query('SPEB?%d\n' %trace)
        #Convert to power spectral density
        numeric = unpackBinary(bytes)                               #Data at this point matches screen with...
        dbVoltsPkPerBin = scaleLogData(numeric, inputRange)         #SPECTRUM with UNITS= dbV Pk
        voltsPkPerBin = 10**(dbVoltsPkPerBin/20.0)                  #SPECTRUM with UNITS= V Pk
        voltsPkPerRtHz = voltsPkPerBin/np.sqrt(linewidth['Hz'])     #PSD with UNITS = V Pk
        voltsRmsPerRtHz = voltsPkPerRtHz/np.sqrt(2)                 #PSD with UNITS = Vrms
        #Window correction factor not yet implemented!!!
        #Make frequency axis
        freqs = np.linspace(freqStart['Hz'],(span+freqStart)['Hz'],len(voltsRmsPerRtHz))
        data = np.vstack((freqs,voltsRmsPerRtHz)).T
        returnValue(data)


# helper methods
def bin(x,width):
    s = ''
    for i in range(width):
        s = str((x>>i)&1)+s
    return s

def scaleLogData(data, inputLevel):
    scaled = (data*3.0103/512.0)-114.3914
    corrected = scaled+inputLevel
    return corrected

def unpackBinary(data):
    print 'unpackBinary in server, data length',len(data)
    if len(data)==800:
        return np.array(unpack('h'*400,data))
    elif len(data)==799:
        return np.array(unpack('h'*399,data[0:798]))

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
