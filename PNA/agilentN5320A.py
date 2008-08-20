#!c:\Python25\python.exe

# Copyright (C) 2007  Matthew Neeley
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

# the names of the measured parameters
MEAS_PARAM = ['S11', 'S12', 'S21', 'S22']

class PNAWrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        yield self.write('FORM:DATA REAL,64')
        yield self.setupMeasurements(['S21'])

    @inlineCallbacks
    def setupMeasurements(self, desired_meas):
        resp = yield self.query('CALC:PAR:CAT?')
        resp = resp[1:-2].split(',')
        
        defined_par = resp[::2]
        defined_meas = resp[1::2]
        defined_both = zip(defined_par, defined_meas)

        desired_par = [_parName(meas) for meas in desired_meas]
        desired_both = zip(desired_par, desired_meas)
        
        print 'desired:', desired_both
        print 'defined:', defined_both

        deletions = ["CALC:PAR:DEL '%s'" % par \
                     for (par, meas) in defined_both \
                     if meas not in desired_meas]
        additions = ["CALC:PAR:DEF '%s',%s" % (par, meas) \
                     for (par, meas) in desired_both \
                     if par not in defined_par]

        for cmd in deletions + additions:
            print cmd
            yield self.write(cmd)

def _parName(meas):
    return 'labrad_%s' % meas

class AgilentPNAServer(GPIBManagedServer):
    name = 'Agilent N5230A PNA'
    deviceName = 'Agilent Technologies N5230A'
    deviceWrapper = PNAWrapper

    def initContext(self, c):
        c['meas'] = ['S21']
        
    @setting(10, bw=['v[Hz]'], returns=['v[Hz]'])
    def bandwidth(self, c, bw=None):
        """Get or set the current bandwidth."""
        dev = self.selectedDevice(c)
        if bw is None:
            resp = yield dev.query('SENS:BAND?')
            bw = T.Value(float(resp), 'Hz')
        elif isinstance(bw, T.Value):
            yield dev.write('SENS:BAND %f' % bw.value)
        returnValue(bw)

    @setting(11, f=['v[Hz]'], returns=['v[Hz]'])
    def frequency(self, c, f=None):
        """Get or set the CW frequency."""
        dev = self.selectedDevice(c)
        if f is None:
            resp = yield dev.query('SENS:FREQ:CW?')
            f = T.Value(float(resp), 'Hz')
        elif isinstance(f, T.Value):
            yield dev.write('SENS:FREQ:CW %f' % f.value)
        returnValue(f)

    @setting(12, fs=['(v[Hz], v[Hz])'], returns=['(v[Hz], v[Hz])'])
    def frequency_range(self, c, fs=None):
        """Get or set the frequency range."""
        dev = self.selectedDevice(c)
        if fs is None:
            resp = yield dev.query('SENS:FREQ:STAR?; STOP?')
            fs = tuple(T.Value(float(f), 'Hz') for f in resp.split(';'))
        else:
            yield dev.write('SENS:FREQ:STAR %f; STOP %f' % (fs[0], fs[1]))
        returnValue(fs)

    @setting(13, p=['v[dBm]'], returns=['v[dBm]'])
    def power(self, c, p=None):
        """Get or set the power."""
        dev = self.selectedDevice(c)
        if p is None:
            resp = yield dev.query('SOUR:POW?')
            p = T.Value(float(resp), 'dBm')
        elif isinstance(p, T.Value):
            yield dev.write('SOUR:POW %f' % p.value)
        returnValue(p)

    @setting(14, ps=['(v[dBm], v[dBm])'], returns=['(v[dBm], v[dBm])'])
    def power_range(self, c, ps=None):
        """Get or set the power range."""
        dev = self.selectedDevice(c)
        if ps is None:
            resp = yield dev.query('SOUR:POW:STAR?; STOP?')
            ps = tuple(T.Value(float(p), 'dBm') for p in resp.split(';'))
        else:
            good_atten = None
            for attn in [0, 10, 20, 30, 40, 50, 60]:
                if -attn-30 <= ps[0] and -attn+20 >= ps[1]:
                    good_atten = attn
                    break
            if good_atten is None:
                raise Exception('Power out of range.')
            yield dev.write('SOUR:POW:ATT %f; STAR %f; STOP %f' % \
                            (good_atten, ps[0], ps[1]))
        returnValue(ps)

    @setting(15, n=['w'], returns=['w'])
    def num_points(self, c, n=None):
        """Get or set the number of points."""
        dev = self.selectedDevice(c)
        if n is None:
            resp = yield dev.query('SENS:SWE:POIN?')
            n = long(resp)
        elif isinstance(n, long):
            yield dev.write('SENS:SWE:POIN %u' % n)
        returnValue(n)

    @setting(16, av=['w'], returns=['w'])
    def averages(self, c, av=None):
        """Get or set the number of averages."""
        dev = self.selectedDevice(c)
        if av is None:
            resp = yield dev.query('SENS:AVER:COUN?')
            av = long(resp)
        elif isinstance(av, long):
            yield dev.write('SENS:AVER:COUN %u' % av)
        returnValue(av)

    @setting(40, att=['(v[dB], v[dB])'], returns=[''])
    def atten(self, c, att=None):
        """Get or set the x/y attenuation (ignored...)."""
        dev = self.selectedDevice(c)

    @setting(100, returns=['*v[Hz]*2c'])
    def freq_sweep(self, c):
        """Initiate a frequency sweep."""
        dev = self.selectedDevice(c)

        resp = yield dev.query('SENS:FREQ:STAR?; STOP?')
        fstar, fstop = [float(f) for f in resp.split(';')]

        sweeptime, npoints = yield self.startSweep(dev, 'LIN')
        if sweeptime > 1:
            sweeptime *= self.sweepFactor(c)
            yield util.wakeupCall(sweeptime)

        sparams = yield self.getSweepData(dev, c['meas'])

        freq = util.linspace(fstar, fstop, npoints)
        freq = [T.Value(f, 'Hz') for f in freq]
        for s in sparams:
            for i, c in enumerate(s):
                s[i] = T.Complex(c)
        returnValue((freq, sparams))

    @setting(101, returns=['*v[Hz]*2c'])
    def power_sweep(self, c):
        """Initiate a power sweep."""
        dev = self.selectedDevice(c)

        resp = yield dev.query('SOUR:POW:STAR?; STOP?')
        pstar, pstop = [float(p) for p in resp.split(';')]

        sweeptime, npoints = yield self.startSweep(dev, 'POW')
        if sweeptime > 1:
            sweeptime *= self.sweepFactor(c)
            yield util.wakeupCall(sweeptime)

        sparams = yield self.getSweepData(dev, c['meas'])

        power = util.linspace(pstar, pstop, npoints)
        power = [T.Value(p, 'dBm') for p in power]
        for s in sparams:
            for i, c in enumerate(s):
                s[i] = T.Complex(c)
        returnValue((power, sparams))
        
    @setting(111, name=['s'], returns=['*2v'])
    def power_sweep_save(self, c, name='untitled'):
        """Initiate a power sweep.

        The data will be saved to the data vault in the current
        directory for this context.  Note that the default directory
        in the data vault is the root directory, so you should cd
        before trying to save."""
        dev = self.selectedDevice(c)

        resp = yield dev.query('SOUR:POW:STAR?; STOP?')
        pstar, pstop = [float(p) for p in resp.split(';')]

        sweeptime, npoints = yield self.startSweep(dev, 'POW')
        if sweeptime > 1:
            sweeptime *= self.sweepFactor(c)
            yield util.wakeupCall(sweeptime)

        sparams = yield self.getSweepData(dev, c['meas'])

        power = util.linspace(pstar, pstop, npoints)
        power = [T.Value(p, 'dBm') for p in power]
        for s in sparams:
            for i, cplx in enumerate(s):
                s[i] = T.Complex(cplx)

        p = numpy.array(power)
        s = 20*numpy.log10(abs(numpy.array(sparams)))
        data = numpy.vstack((p, s)).T
        data = data.astype('float64')

        dv = self.client.data_vault
        freq = yield self.frequency(c)
        bw = yield self.bandwidth(c)
        
        independents = ['power [dBm]']
        dependents = [('log mag', Sij, 'dB') for Sij in c['meas']]
        p = dv.packet()
        p.new(name, independents, dependents)
        p.add(data)
        p.add_comment('Autosaved by PNA server.')
        p.add_parameter('frequency', freq)
        p.add_parameter('bandwidth', bw)
        yield p.send(context=c.ID)
        
        returnValue(data)
        
    @setting(110, name=['s'], returns=['*2v'])
    def freq_sweep_save(self, c, name='untitled'):
        """Initiate a frequency sweep.

        The data will be saved to the data vault in the current
        directory for this context.  Note that the default directory
        in the data vault is the root directory, so you should cd
        before trying to save.
        """
        dev = self.selectedDevice(c)

        resp = yield dev.query('SENS:FREQ:STAR?; STOP?')
        fstar, fstop = [float(f) for f in resp.split(';')]

        sweeptime, npoints = yield self.startSweep(dev, 'LIN')
        if sweeptime > 1:
            sweeptime *= self.sweepFactor(c)
            yield util.wakeupCall(sweeptime)

        sparams = yield self.getSweepData(dev, c['meas'])

        freq = util.linspace(fstar, fstop, npoints)
        freq = [T.Value(f, 'Hz') for f in freq]
        for s in sparams:
            for i, cplx in enumerate(s):
                s[i] = T.Complex(cplx)

        f = numpy.array(freq)
        s = 20*numpy.log10(abs(numpy.array(sparams)))
        data = numpy.vstack((f, s)).T
        data = data.astype('float64')

        dv = self.client.data_vault
        power = yield self.power(c)
        bw = yield self.bandwidth(c)
        
        independents = ['frequency [Hz]']
        dependents = [('log mag', Sij, 'dB') for Sij in c['meas']]
        p = dv.packet()
        p.new(name, independents, dependents)
        p.add(data)
        p.add_comment('Autosaved by PNA server.')
        p.add_parameter('power', power)
        p.add_parameter('bandwidth', bw)
        yield p.send(context=c.ID)
        
        returnValue(data)

    @setting(200, params=['*s'], returns=['*s'])
    def s_parameters(self, c, params=None):
        """Specify the scattering parameters to be measured.

        The available scattering parameters are:
        'S11', 'S12', 'S21', 'S22'
        """
        dev = self.selectedDevice(c)

        if isinstance(params, list):
            desired = [m.upper() for m in params]
            desired = [m for m in desired if m in MEAS_PARAM]
            
            yield dev.setupMeasurements(desired)
            
            c['meas'] = desired
            
        returnValue(c['meas'])

    # helper methods

    @inlineCallbacks
    def startSweep(self, dev, sweeptype):
        yield dev.write('SENS:SWE:TIME:AUTO ON; :INIT:CONT OFF; :OUTP ON')

        resp = yield dev.query('SENS:SWE:TIME?; POIN?')
        sweeptime, npoints = resp.split(';')
        sweeptime = float(sweeptime)
        npoints = int(npoints)

        yield dev.write('SENS:SWE:TYPE %s' % sweeptype)
        yield dev.write('ABORT;INIT:IMM')

        returnValue((sweeptime, npoints))

    @inlineCallbacks
    def getSweepData(self, dev, meas):
        yield dev.query('*OPC?') # wait for sweep to finish
        sdata = yield self.getSParams(dev, meas)
        yield dev.write('OUTP OFF')
        returnValue(sdata)

    @inlineCallbacks
    def getSParams(self, dev, measurements):
        sdata = [(yield self.getData(dev, m)) for m in measurements]
        returnValue(sdata)

    def sweepFactor(self, c):
        """Multiply the sweeptime by this factor, which
        counts the number of ports that send power.
        """
        ports = set(int(p[-1]) for p in c['meas'])
        return len(ports)

    @inlineCallbacks
    def getData(self, dev, meas):
        """Get binary sweep data from the PNA and parse it.

        The data has the following format:

            1 byte:  '#' (ignored)
            1 byte:  h = header length
            h bytes: d = data length
            d bytes: binary sweep data, as pairs of 64-bit numbers
            1 byte:  <newline> (ignored)

        The 64-bit numbers are unpacked using the struct.unpack
        function from the standard library.
        """
        yield dev.write("CALC:PAR:SEL '%s'" % _parName(meas))
        yield dev.write("CALC:DATA? SDATA")
        yield dev.read(bytes=1L) # throw away first byte
        
        headerLen = long((yield dev.read(bytes=1L)))
        dataLen = long((yield dev.read(bytes=headerLen)))

        # read data in chunks
        dataStr = ''
        while len(dataStr) < dataLen:
            chunk = min(10000, dataLen - len(dataStr))
            dataStr += yield dev.read(bytes=long(chunk))
            
        yield dev.read(bytes=1L) # read last byte and discard

        nPoints = dataLen / 16
        
        _parse = lambda s: complex(*unpack('>dd', s))
        data = [_parse(dataStr[16*n:16*(n+1)]) for n in range(nPoints)]
        
        returnValue(data)


__server__ = AgilentPNAServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
