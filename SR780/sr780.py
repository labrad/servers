# Copyright (C) 2008 Erik Lucero
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

# Updated Sep 2013 by Peter O'Malley, again Dec 2013

"""
### BEGIN NODE INFO
[info]
name = Signal Analyzer SR780
version = 2.0
description = Talks to the Stanford Research Systems Signal Analyzer

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

from struct import unpack
import numpy as np

COUPLINGS = {0: 'DC',
             1: 'AC'}

GROUNDINGS = {
              0: 'FLOAT',
              1: 'GROUND'
              }

WINDOWS = {
            'UNIFORM': 0,
            'FLATTOP': 1,
            'HANNING': 2,
            'BLACKMANHARRIS': 3,
            'T2T2':8,
            '0T2':9,
            'T4T4':10
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

             
def inverseDict(d):
    outDict = dict([(value,key) for key,value in d.items()])
    return outDict

class SR780Wrapper(GPIBDeviceWrapper):
    SETTLING_TIME = T.Value(5, 's')
    AVERAGING_TIME = T.Value(5, 's')
    
    @inlineCallbacks
    def initialize(self):
        p = self._packet()
        p.clear()
        p.term_chars('\n')
        yield p.send()

    @inlineCallbacks
    def clearStatusBytes(self):
        yield self.write("*CLS")
    
    @inlineCallbacks
    def doneSettling(self):
        #yield self.write("*CLS")
        respa = yield self.query("DSPS? 2")
        #respb = yield self.query("DSPS? 10")
        returnValue(bool(int(respa)))# and int(respb))
        
    @inlineCallbacks
    def waitForSettling(self, minSettle=T.Value(0,'s')):
        yield self.write("*CLS")
        yield self.write("UNST 0")
        # wait for 1 / (5 * bandwidth)
        span = yield self.query("FSPN? 0")
        time = 0.2 / float(span)
        yield util.wakeupCall(max(time, minSettle['s']))
        done = yield self.doneSettling()
        while not done:
            yield util.wakeupCall(self.SETTLING_TIME['s'])
            done = yield self.doneSettling()
        returnValue(None)
        
    @inlineCallbacks
    def doneAveraging(self):
        n = yield self.query("FAVN? 0")
        n = int(n)
        ndone = yield self.query("NAVG? 0")
        ndone = int(ndone)
        avgOn = yield self.query("FAVG? 0")
        avgOn = int(avgOn)
        returnValue( avgOn and ndone >= n )
        
    @inlineCallbacks
    def waitForAveraging(self):
        done = yield self.doneAveraging()
        while not done:
            yield util.wakeupCall(self.AVERAGING_TIME['s'])
            done = yield self.doneAveraging()
        returnValue(None)
        
    @inlineCallbacks
    def overlapPercentage(self, ov):
        if ov is not None:
            yield self.write("FOVL 0 %s" % ov)
        resp = yield self.query("FOVL? 0")
        returnValue(resp)
        
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
            yield self.write('I1RG%d' %range)
            yield self.write('I2RG%d' %range)
        #Readback input range
        resp = yield self.query('I1RG?')
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
            yield self.write('I1CP%d' %coupling)
            yield self.write('I2CP%d' %coupling)
        resp = yield self.query('I1CP?')
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
            yield self.write('I1GD%d' %grounding)
            yield self.write('I2GD%d' %grounding)
        resp = yield self.query('I1GD?')
        returnValue(GROUNDINGS[int(resp)])
        


class SR780Server(GPIBManagedServer):
    """Serves the Stanford Research Systems SR780 Network Signal Analyzer.
    A low frequency (0-100kHz) FFT. Can save data to datavault."""
    name = 'Signal Analyzer SR780'
    deviceName = 'Stanford_Research_Systems SR780'
    deviceWrapper = SR780Wrapper
    deviceIdentFunc = 'identify_device'

    @setting(1000, server='s', address='s')
    def identify_device(self, c, server, address):
        print 'identifying:', server, address
        try:
            s = self.client[server]
            p = s.packet()
            p.address(address)
            p.write('*IDN?')
            p.read()
            ans = yield p.send()
            resp = ans.read
            if resp == 'Stanford_Research_Systems,SR780,s/n31624,ver116':
                returnValue(self.deviceName)
        except Exception, e:
            print 'failed:', e
            raise
        
    @setting(10, sp=['v[Hz]'], returns=['v[Hz]'])
    def span(self, c, sp=None):
        """Get or set the current frequency span for display A."""
        dev = self.selectedDevice(c)
        if sp is not None:
            yield dev.write('FSPN2, %f' % sp['Hz'])
        resp = yield dev.query('FSPN?0')
        sp = T.Value(float(resp), 'Hz')
        returnValue(sp)

    @setting(11, cf=['v[Hz]'], returns=['v[Hz]'])
    def center_frequency(self, c, cf=None):
        """Get or set the center frequency."""
        dev = self.selectedDevice(c)
        if cf is None:
            resp = yield dev.query('FCTR?0')
            cf = T.Value(float(resp), 'Hz')
        elif isinstance(cf, T.Value):
            yield dev.write('FCTR0, %f' % cf.value)
        returnValue(cf)

    @setting(12, fs=['v[Hz]'], returns=['v[Hz]'])
    def start_frequency(self, c, fs=None):
        """Get or set the start frequency. Must be between 0 and 100kHz"""
        dev = self.selectedDevice(c)
        if fs is not None:
            yield dev.write('FSTR 2,%f' % fs['Hz'])
        resp = yield dev.query('FSTR?0')
        fs = T.Value(float(resp), 'Hz')
        returnValue(fs)

    @setting(13, fe=['v[Hz]'], returns=['v[Hz]'])
    def end_frequency(self, c, fe=None):
        """Get or set the end frequency. Must be between 0 and 100kHz"""
        dev = self.selectedDevice(c)
        if fe is None:
            resp = yield dev.query('FEND?0')
            fe = T.Value(float(resp), 'Hz')
        else:
            yield dev.write('FEND0,%f' % fe.value)
        returnValue(fe)
        
    @setting(14, sp='v[Hz]', fs='v[Hz]', minSettle='v[s]', returns='(v[Hz]v[Hz])')
    def freq_and_settle(self, c, sp, fs, minSettle=T.Value(0, 's')):
        dev = self.selectedDevice(c)
        sp = yield self.span(c, sp)
        fs = yield self.start_frequency(c, fs)
        yield dev.waitForSettling(minSettle)
        returnValue((sp, fs))

    @setting(15, nl=['w', 's'], returns=['w'])
    def num_lines(self, c, nl=None):
        """Get or set the number of FFT Lines:
        100
        200
        400
        800. 
        800 is the highest resolution /slowest measurement time (t=Lines/Span).
        """
        dev = self.selectedDevice(c)
        units = {
            '100': 0,
            '200': 1,
            '400': 2,
            '800': 3,
            }
        if nl is None:
            resp = yield dev.query('FLIN?0')
            nl = long(resp)
        else:
            if isinstance(nl, str):
                if nl not in units:
                    raise Exception('Choose number of lines 100, 200, 400, or 800.')
                nl = units[nl]
            yield dev.write('FLIN0,%u ' % nl)
        returnValue(nl)    

    @setting(17, avg=['w', 's'], returns=['w'])
    def average(self, c, avg=None):
        """Query or turn ON/OFF Averaging."""
        dev = self.selectedDevice(c)
        units = {
            'OFF': 0,
            'ON': 1,
            }
        if avg is None:
            resp = yield dev.query('FAVG?0')
            avg = long(resp)
        else:
            if isinstance(avg, str):
                if avg.upper() not in units:
                    raise Exception('Can only turn ON or OFF.')
                avg = units[avg.upper()]
            yield dev.write('FAVG0, %u' % avg)
        returnValue(avg)

    @setting(18, av=['w'], returns=['w'])
    def num_averages(self, c, av=None):
        """Get or set the number of averages."""
        dev = self.selectedDevice(c)
        if av is None:
            resp = yield dev.query('FAVN?0')
            av = long(resp)
        elif isinstance(av, long):
            yield dev.write('FAVN0, %u' % av)
        returnValue(av)
        
    @setting(19, ov='v{overlap percentage}', returns='v{overlap percentage}')
    def overlap(self, c, ov):
        ''' Get/set the overlap. Note that on the SR780 the terminology is
        "time record increment" rather than "overlap". Overlap = 100% - TRI.
        For TRI > 100%, there is an effective wait between scans.
        TRI of 0% to 300% allowed, so overlap from 100% to -200%. '''
        ov = yield self.selectedDevice(c).overlapPercentage(ov)
        returnValue(ov)
    
    @setting(30, disp='w{display}', ms=['w', 's'], returns=['ws'])
    def measure(self, c, disp=0, ms=None):
        """Get or set the measurement.
        0 FFT 1; 1 FFT 2;
        2 Time 1; 3 Time 2;
        4 Windowed Time 1; 5 Windowed Time 2;
        6 Orbit; 7 Coherence; 8 Cross Spectrum;
        9 <F2/F1> Transfer Function Averaged;
        10 <F2>/<F1> Transfer Function of Averaged FFTs;
        11 Auto Correlation 1; 12 Auto Correlation 2;
        13 Cross Correlation;
        """
        measureNames = {
            'FFT 1': 0L, 'FFT 2': 1L, 'TIME 1': 2L, 'TIME 2': 3L,
            'WINDOWED TIME 1': 4L, 'WINDOWED TIME 2': 5L, 'ORBIT': 6L,
            'COHERENCE': 7L, 'CROSS SPECTRUM': 8L, '<F2/F1> TRANSFER FUNCTION AVERAGED': 9L,
            '<F2>/<F1> TRANSFER FUNCTION OF AVERAGED FFTS': 10L, 'AUTO CORRELATION 1': 11L,
            'AUTO CORRELATION 2': 12L, 'CROSS CORRELATION': 13L,
        }
        if isinstance(ms, str):
            if ms.upper() not in measureNames:
                raise ValueError("Invalid Measure Name")
            ms = measureNames[ms.upper()]
        dev = self.selectedDevice(c)
        if ms is None:
            resp = yield dev.query('MEAS?%d' % disp)
            ms = long(resp)
        elif isinstance(ms, long):
            yield dev.write('MEAS%d, %u' % (disp,ms))
        returnValue((ms,inverseDict(measureNames)[ms]))

    @setting(31, disp='w{display}', mv=['w', 's'], returns=['ws'])
    def display(self, c, disp=0, mv=None):
        """Get or set the view.
        0 Log Mag;
        1 Linear Mag;
        2 Mag Squared;
        3 Real Part;
        4 Imaginary Part;
        5 Phase;
        6 Unwrapped Phase;
        7 Nyquist;
        8 Nichols;
        """
        dev = self.selectedDevice(c)
        views = {
            'LOG MAG': 0L,
            'LINEAR MAG': 1L,
            'MAG SQUARED': 2L,
            'REAL PART': 3L,
            'IMAGINARY PART': 4L,
            'PHASE': 5L,
            'UNWRAPPED PHASE': 6L,
            'NYQUIST': 7L,
            'NICHOLS': 8L,
            }
        if mv is None:
            resp = yield dev.query('VIEW?%d' % disp)
            mv = long(resp)
        else:
            if isinstance(mv, str):
                if mv.upper() not in views:
                    raise ValueError('Invalid View Name.')
                mv = views[mv.upper()]
            yield dev.write('VIEW%d, %u' % (disp, mv))
        returnValue((mv, inverseDict(views)[mv]))

    @setting(32, disp='w{display}', un=['w', 's'], returns=['ws'])
    def units(self, c, disp=0, un=None):
        """Get or set the units.
        0 Vpk;
        1 Vrms;
        2 Vpk^2;
        3 Vrms^2;
        4 dBVpk;
        5 dBVrms;
        6 dBm;
        7 dBspl;
        """
        dev = self.selectedDevice(c)
        units = {
            'VPK': 0L,
            'VRMS': 1L,
            'VPK^2': 2L,
            'VRMS^2': 3L,
            'DBVPK': 4L,
            'DBVRMS': 5L,
            'DBM': 6L,
            'DBSPL': 7L,
            }
        if un is None:
            resp = yield dev.query('UNIT?%d' % disp)
            un = long(resp)
        else:
            if isinstance(un, str):
                if un.upper() not in units:
                    raise Exception('Invalid Unit.')
                un = units[un.upper()]
            yield dev.write('UNIT%d, %u' % (un,disp))
        returnValue((un,inverseDict(units)[un]))
        
    @setting(33, psd=['w', 's'], returns=['w'])
    def psd_units(self, c, psd=None):
        """Turn on or off PSD units."""
        dev = self.selectedDevice(c)
        units = {
            'OFF': 0,
            'ON': 1,
            }
        if psd is None:
            resp = yield dev.query('PSDU?0')
            psd = long(resp)
        else:
            if isinstance(psd, str):
                if psd.upper() not in units:
                    raise Exception('Can only turn ON or OFF.')
                psd = units[psd.upper()]
            yield dev.write('PSDU0, %u' % psd)
        returnValue(psd)
        
    @setting(49, trace='i', window=['i','s'], returns=['s{Window type}'])
    def window(self, c, trace, window=None):
        dev = self.selectedDevice(c)
        if window is not None:
            if isinstance(window,str):
                window = WINDOWS[window.upper()]
            elif isinstance(window,int) and window not in [0,1,2,3,8]:
                raise Exception('Window specified as integer must be in range 0 to 3 and 8')
            yield dev.write('FWIN%d,%d' %(trace,window))
        resp = yield dev.query('FWIN?%d' %trace)
        answer = inverseDict(WINDOWS)[int(resp)]
        returnValue(answer)

    @setting(50, coupling=['i','s'], returns='s')
    def coupling(self, c, coupling=None):
        dev = self.selectedDevice(c)
        resp = yield dev.coupling(coupling)
        returnValue(resp)

    @setting(52, range='i{input range in dbV}', returns='i{input range in dbV}')
    def input_range(self, c, range=None):
        """Get or set the input range of BOTH channels.
        Note that the units of the input range are the weird decibel unit defined as
        
        20*log10(N)
        """
        dev = self.selectedDevice(c)
        result = yield dev.input_range(range)
        returnValue(result)

    @setting(53, grnd=['i','s'], returns = 's')
    def grounding(self, c, grnd=None):
        ''' Gets/sets grounding of BOTH channels. '''
        dev = self.selectedDevice(c)
        result = yield dev.grounding(grnd)
        returnValue(result)

    @setting(90, trace='i{trace}', returns='*2v{[freq,srqt(psd)]}')
    def power_spectral_amplitude_ASCII(self, c, trace):
        ''' Get the trace in spectral amplitude (RMS units). '''
        dev = self.selectedDevice(c)
        yield dev.clearStatusBytes()
        disp = yield self.display(c)
        if disp[0] != 0:
            raise Exception("Display must be LOG MAG for power spectral amplitude retrieval")
        span = yield self.span(c)
        freqStart = yield self.start_frequency(c)
        yield self.startsweep(c)
        yield dev.waitForAveraging()
        n_points = yield dev.query("DSPN? 0")
        n_points = int(n_points)
        data = yield dev.query("DSPY? 0")
        data = data.split(',')
        vrms = np.array([float(d) for d in data])
        freqs = np.linspace(freqStart['Hz'], (span+freqStart)['Hz'], n_points)
        data = np.vstack((freqs,vrms)).T
        returnValue(data)

    @setting(100, returns=['*(v[Hz] v[Vrms/Hz^1/2])'])
    def freq_sweep(self, c):
        """Initiate a frequency sweep."""
        dev = self.selectedDevice(c)

        length = yield dev.query("DSPN? 0")
        length = int(length)
        print length
        data = yield dev.query("DSPB? 0")
        print len(data)

        if len(data) != length*4:
            raise Exception("Lengths don't match, dude! %d isn't equal to %d" % (len(data), length*4))

        print "unpacking..."

        data = [unpack('<f', data[i*4:i*4+4])[0] for i in range(length)]
        #Calculate frequencies from current span
        resp = yield dev.query('FSTR?0')
        fs = T.Value(float(resp), 'Hz')
        resp = yield dev.query('FEND?0')
        fe = T.Value(float(resp), 'Hz')
        freq = util.linspace(fs, fe, length)
        
        returnValue(zip(freq, data))
        
    @setting(110, name=['s'], returns=['*(v[Hz] v[Vrms/Hz^1/2])'])
    def freq_sweep_save(self, c, name='untitled'):
        """Initiate a frequency sweep.

        The data will be saved to the data vault in the current
        directory for this context.  Note that the default directory
        in the data vault is the root directory, so you should cd
        before trying to save.
        """
        dev = self.selectedDevice(c)

        length = yield dev.query("DSPN? 0")
        length = int(length)
        print length
        data = yield dev.query("DSPB? 0")
        print len(data)

        if len(data) != length*4:
            raise Exception("Lengths don't match, dude! %d isn't equal to %d" % (len(data), length*4))

        print "unpacking..."

        data = [unpack('<f', data[i*4:i*4+4])[0] for i in range(length)]
        data = np.array(data)
        #Calculate frequencies from current span
        resp = yield dev.query('FSTR?0')
        fs = T.Value(float(resp), 'Hz')
        resp = yield dev.query('FEND?0')
        fe = T.Value(float(resp), 'Hz')
        freq = np.linspace(fs, fe, length)
        
        

        dv = self.client.data_vault
        
        independents = ['frequency [Hz]']
        dependents = [('Sv', 'PSD', 'Vrms/Hz^1/2')]
        p = dv.packet()
        p.new(name, independents, dependents)
        p.add(np.vstack((freq, data)).T)
        p.add_comment('Autosaved by SR780 server.')
        yield p.send(context=c.ID)
        
        returnValue(zip(freq, data))

    # helper methods

    @setting(150)
    def startsweep(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('STRT')
    

__server__ = SR780Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
