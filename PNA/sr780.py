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

from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

from struct import unpack
import numpy

class SR780Wrapper(GPIBDeviceWrapper):
    pass

class SR780Server(GPIBManagedServer):
    """Serves the Stanford Research Systems SR780 Network Signal Analyzer.
    A low frequency (0-100kHz) FFT. Can save data to datavault."""
    name = 'Signal Analyzer SR780'
    deviceName = 'Stanford Research Systems SR780'
    deviceWrapper = SR780Wrapper
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
            if resp == 'Stanford_Research_Systems,SR780,s/n31624,ver116':
                returnValue(self.deviceName)
        except Exception, e:
            print 'failed:', e
            raise
        
    @setting(10, sp=['v[Hz]'], returns=['v[Hz]'])
    def span(self, c, sp=None):
        """Get or set the current frequency span for display A."""
        dev = self.selectedDevice(c)
        if sp is None:
            resp = yield dev.query('FSPN?0\n')
            sp = T.Value(float(resp), 'Hz')
        elif isinstance(sp, T.Value):
            yield dev.write('FSPN2, %f\n' % sp.value)
        returnValue(sp)

    @setting(11, cf=['v[Hz]'], returns=['v[Hz]'])
    def center_frequency(self, c, cf=None):
        """Get or set the center frequency."""
        dev = self.selectedDevice(c)
        if cf is None:
            resp = yield dev.query('FCTR?0\n')
            cf = T.Value(float(resp), 'Hz')
        elif isinstance(cf, T.Value):
            yield dev.write('FCTR0, %f\n' % cf.value)
        returnValue(cf)

    @setting(12, fs=['v[Hz]'], returns=['v[Hz]'])
    def start_frequency(self, c, fs=None):
        """Get or set the start frequency. Must be between 0 and 100kHz"""
        dev = self.selectedDevice(c)
        if fs is None:
            resp = yield dev.query('FSTR?0\n')
            fs = T.Value(float(resp), 'Hz')
        else:
            yield dev.write('FSTR0,%f\n' % fs.value)
        returnValue(fs)

    @setting(13, fe=['v[Hz]'], returns=['v[Hz]'])
    def end_frequency(self, c, fe=None):
        """Get or set the end frequency. Must be between 0 and 100kHz"""
        dev = self.selectedDevice(c)
        if fe is None:
            resp = yield dev.query('FEND?0\n')
            fe = T.Value(float(resp), 'Hz')
        else:
            yield dev.write('FEND0,%f\n' % fe.value)
        returnValue(fe)

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
            resp = yield dev.query('FLIN?0\n')
            nl = long(resp)
        else:
            if isinstance(nl, str):
                if nl not in units:
                    raise Exception('Choose number of lines 100, 200, 400, or 800.')
                nl = units[nl]
            yield dev.write('FLIN0,%u \n' % nl)
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
            resp = yield dev.query('FAVG?0\n')
            avg = long(resp)
        else:
            if isinstance(avg, str):
                if avg.upper() not in units:
                    raise Exception('Can only turn ON or OFF.')
                avg = units[avg.upper()]
            yield dev.write('FAVG0, %u ' % avg)
        returnValue(avg)

    @setting(18, av=['w'], returns=['w'])
    def num_averages(self, c, av=None):
        """Get or set the number of averages."""
        dev = self.selectedDevice(c)
        if av is None:
            resp = yield dev.query('FAVN?0\n')
            av = long(resp)
        elif isinstance(av, long):
            yield dev.write('FAVN0, %u' % av)
        returnValue(av)
    
    @setting(30, ms=['w'], returns=['w'])
    def measure(self, c, ms=None):
        """Get or set the measurement.
        0 FFT 1; 1 FFT 2;
        2 Time 1; 3 Time 2;
        4 Windowed Time 1; 5 Windowed Time 2;
        6 Orbit; 7 Coherence; 8 Cross Spectrum;
        9 <F2/F1> Transfer Function Averaged;
        10 <F2>/<F1> Transfer Function of Averaged FFT's;
        11 Auto Correlation 1; 12 Auto Correlation 2;
        13 Cross Correlation;
        """
        dev = self.selectedDevice(c)
        if ms is None:
            resp = yield dev.query('MEAS?0\n')
            ms = long(resp)
        elif isinstance(ms, long):
            yield dev.write('MEAS0, %u ' % ms)
        returnValue(ms)

    @setting(31, mv=['w', 's'], returns=['w'])
    def measure_view(self, c, mv=None):
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
            'LOG MAG': 0,
            'LINEAR MAG': 1,
            'MAG SQUARED': 2,
            'REAL PART': 3,
            'IMAGINARY PART': 4,
            'PHASE': 5,
            'UNWRAPPED PHASE': 6,
            'NYQUIST': 7,
            'NICHOLS': 8,
            }
        if mv is None:
            resp = yield dev.query('VIEW?0\n')
            mv = long(resp)
        else:
            if isinstance(mv, str):
                if mv.upper() not in views:
                    raise Exception('Invalid View Name.')
                mv = views[mv.upper()]
            yield dev.write('VIEW0, %u ' % mv)
        returnValue(mv)

    @setting(32, un=['w', 's'], returns=['w'])
    def units(self, c, un=None):
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
            'VPK': 0,
            'VRMS': 1,
            'VPK^2': 2,
            'VRMS^2': 3,
            'DBVPK': 4,
            'DBVRMS': 5,
            'DBM': 6,
            'DBSPL': 7,
            }
        if un is None:
            resp = yield dev.query('UNIT?0\n')
            un = long(resp)
        else:
            if isinstance(un, str):
                if un.upper() not in units:
                    raise Exception('Invalid Unit.')
                un = units[un.upper()]
            yield dev.write('UNIT0, %u ' % un)
        returnValue(un)
        
    @setting(33, psd=['w', 's'], returns=['w'])
    def psd_units(self, c, psd=None):
        """Turn on or off PSD units."""
        dev = self.selectedDevice(c)
        units = {
            'OFF': 0,
            'ON': 1,
            }
        if psd is None:
            resp = yield dev.query('PSDU?0\n')
            psd = long(resp)
        else:
            if isinstance(psd, str):
                if psd.upper() not in units:
                    raise Exception('Can only turn ON or OFF.')
                psd = units[psd.upper()]
            yield dev.write('PSDU0, %u ' % psd)
        returnValue(psd)
        

    @setting(100, returns=['*(v[Hz] v[Vrms/Hz^1/2])'])
    def freq_sweep(self, c):
        """Initiate a frequency sweep."""
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
        #Calculate frequencies from current span
        resp = yield dev.query('FSTR?0\n')
        fs = T.Value(float(resp), 'Hz')
        resp = yield dev.query('FEND?0\n')
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

        length = yield dev.query("DSPN? 0\n")
        length = int(length)
        print length
        data = yield dev.query("DSPB? 0\n")
        print len(data)

        if len(data) != length*4:
            raise Exception("Lengths don't match, dude! %d isn't equal to %d" % (len(data), length*4))

        print "unpacking..."

        data = [unpack('<f', data[i*4:i*4+4])[0] for i in range(length)]
        data = numpy.array(data)
        #Calculate frequencies from current span
        resp = yield dev.query('FSTR?0\n')
        fs = T.Value(float(resp), 'Hz')
        resp = yield dev.query('FEND?0\n')
        fe = T.Value(float(resp), 'Hz')
        freq = numpy.linspace(fs, fe, length)
        
        

        dv = self.client.data_vault
        
        independents = ['frequency [Hz]']
        dependents = [('Sv', 'PSD', 'Vrms/Hz^1/2')]
        p = dv.packet()
        p.new(name, independents, dependents)
        p.add(numpy.vstack((freq, data)).T)
        p.add_comment('Autosaved by SR780 server.')
        yield p.send(context=c.ID)
        
        returnValue(zip(freq, data))

    # helper methods

    @setting(150)
    def startsweep(self, c, sweeptype):
        dev = self.selectedDevice(c)
        yield dev.write('STRT\n')
    

__server__ = SR780Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
