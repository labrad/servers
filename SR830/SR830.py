# Copyright (C) 2011 Peter O'Malley/Charles Neill
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
name = SR830
version = 2.7
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, gpib, units
from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import inlineCallbacks, returnValue

def getTC(i):
    ''' converts from the integer label used by the SR830 to a time '''
    if i < 0:
        return getTC(0)
    elif i > 19:
        return getTC(19)
    elif i % 2 == 0:
        return 10**(-5 + i/2) * units.s
    else:
        return 3*10**(-5 + i/2) * units.s

def getSensitivity(i):
    ''' converts form the integer label used by the SR830 to a sensitivity '''
    if i < 0:
        return getSensitivity(0)
    elif i > 26:
        return getSensitvity(26)
    elif i % 3 == 0:
        return 2 * 10**(-9 + i/3)
    elif i % 3 == 1:
        return 5 * 10**(-9 + i/3)
    else:
        return 10 * 10**(-9 + i/3)

class SR830(GPIBManagedServer):
    name = 'SR830'
    deviceName = 'Stanford_Research_Systems SR830'

    @inlineCallbacks
    def inputMode(self, c):
        ''' returns the input mode. 0=A, 1=A-B, 2=I(10**6), 3=I(10**8) '''
        dev = self.selectedDevice(c)
        mode = yield dev.query('ISRC?')
        returnValue(int(mode))
    
    @inlineCallbacks
    def outputUnit(self, c):
        ''' returns a labrad unit, V or A, for what the main output type is. (R, X, Y) '''
        mode = yield self.inputMode(c)
        if mode < 2:
            returnValue(units.V)
        else:
            returnValue(units.A)

    @setting(12, 'Phase', ph=[': query phase offset',  'v[deg]: set phase offset'], returns='v[deg]: phase')
    def phase(self, c, ph = None):
        ''' sets/gets the phase offset '''
        dev = self.selectedDevice(c)
        if ph is None:
            resp = yield dev.query('PHAS?')
            returnValue(float(resp))    	
        else:
            yield dev.write('PHAS ' + str(ph))
            resp = yield dev.query('PHAS?')
            returnValue(float(resp))
            
    @setting(13, 'Reference', ref=[': query reference source', 'b: set external (false) or internal (true) reference source'], returns='b')
    def reference(self, c, ref = None):
        """ sets/gets the reference source. false => external source. true => internal source. """
        dev = self.selectedDevice(c)
        if ref == '':
            resp = yield dev.query('FMOD?')
            returnValue(bool(int(resp)))
        else:
            s = '0'
            if ref:
                s = '1'
            yield dev.write('FMOD ' + s)
            returnValue(ref)   

    @setting(14, 'Frequency', f=[': query frequency', 'v[Hz]: set frequency'], returns='v[Hz]')
    def frequency(self, c, f = None):
        """ Sets/gets the frequency of the internal reference. """
        dev = self.selectedDevice(c)
        if f is None:
            resp = yield dev.query('FREQ?')
            returnValue(float(resp))
        else:
            yield dev.write('FREQ ' + str(f))
            resp = yield dev.query('FREQ?')
            returnValue(float(resp))

    @setting(15, 'External Reference Slope', ers=[': query', 'i: set'], returns='i')
    def external_reference_slope(self, c, ers = None):
        """
        Get/set the external reference slope.
        0 = Sine, 1 = TTL Rising, 2 = TTL Falling
        """
        dev = self.selectedDevice(c)
        if ers is None:
            resp = yield dev.query('RSLP?')
            returnValue(int(resp))
        else:
            yield dev.write('RSLP ' + str(ers))
            returnValue(ers)			

    @setting(16, 'Harmonic', h=[': query harmonic', 'i: set harmonic'], returns='i')
    def harmonic(self, c, h = None):
        """
        Get/set the harmonic.
        Harmonic can be set as high as 19999 but is capped at a frequency of 102kHz.
        """
        dev = self.selectedDevice(c)
        if h is None:
            resp = yield dev.query('HARM?')
            returnValue(int(resp))
        else:
            yield dev.write('HARM ' + str(h))
            returnValue(h)

    @setting(17, 'Sine Out Amplitude', amp=[': query', 'v[V]: set'], returns='v[V]')
    def sine_out_amplitude(self, c, amp = None):
        """ 
        Set/get the amplitude of the sine out.
        Accepts values between .004 and 5.0 V.
        """
        dev = self.selectedDevice(c)
        if amp is None:
            resp = yield dev.query('SLVL?')
            returnValue(float(resp))
        else:
            yield dev.write('SLVL ' + str(amp))
            resp = yield dev.query('SLVL?')
            returnValue(float(resp))

    @setting(18, 'Aux Input', n='i', returns='v[V]')
    def aux_input(self, c, n):
        """Query the value of Aux Input n (1,2,3,4)"""
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        resp = yield dev.query('OAUX? ' + str(n))
        returnValue(float(resp))

    @setting(19, 'Aux Output', n='i', v=['v[V]'], returns='v[V]')
    def aux_output(self, c, n, v = None):
        """Get/set the value of Aux Output n (1,2,3,4). v can be from -10.5 to 10.5 V."""
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        if v is None:
            resp = yield dev.query('AUXV? ' + str(n))
            returnValue(float(resp))
        else:
            yield dev.write('AUXV ' + str(n) + ', ' + str(v));
            returnValue(v)	

    @setting(21, 'x', returns='v')
    def x(self, c):
        """Query the value of X"""
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 1')
        returnValue(float(resp) * (yield self.outputUnit(c)))

    @setting(22, 'y', returns='v')
    def y(self, c):
        """Query the value of Y"""
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 2')
        returnValue(float(resp) * (yield self.outputUnit(c)))

    @setting(23, 'r', returns='v')
    def r(self, c):
        """Query the value of R"""
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 3')
        returnValue(float(resp) * (yield self.outputUnit(c)))

    @setting(24, 'theta', returns='v[deg]')
    def theta(self, c):
        """Query the value of theta """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 4')
        returnValue(float(resp))

    @setting(30, 'Time Constant', i='i', returns='v[s]')
    def time_constant(self, c, i=None):
        """ Set/get the time constant. i=0 --> 10 us; 1-->30us, 2-->100us, 3-->300us, ..., 19 --> 30ks """
        dev = self.selectedDevice(c)
        if i is None:
            resp = yield dev.query("OFLT?")
            returnValue(getTC(int(resp)))
        else:
            yield dev.write('OFLT ' + str(i))
            returnValue(getTC(i))

    @setting(31, 'Sensitivity', i='i', returns='v')
    def sensitivity(self, c, i=None):
        """ Set/get the sensitivity. i=0 --> 2 nV/fA; 1-->5nV/fA, 2-->10nV/fA, 3-->20nV/fA, ..., 26 --> 1V/uA """
        dev = self.selectedDevice(c)
        mode = yield self.inputMode(c)
        if mode < 2:
            u = units.V
        else:
            u = units.uA
        if i is None:
            resp = yield dev.query("SENS?")
            returnValue(getSensitivity(int(resp)) * u)
        else:
            yield dev.write('SENS ' + str(i))
            s = getSensitivity(i)
            returnValue(getSensitivity(i)*u)
            
    @setting(41, 'Sensitivity Up', returns='v')
    def sensitivity_up(self, c):
        ''' Kicks the sensitivity up a notch. '''
        dev = self.selectedDevice(c)
        returnValue((yield self.sensitivity(c, int((yield dev.query('SENS?'))) + 1)))
        
    @setting(42, 'Sensitivity Down', returns='v')
    def sensitivity_down(self, c):
        ''' Turns the sensitivity down a notch. '''
        dev = self.selectedDevice(c)
        returnValue((yield self.sensitivity(c, int((yield dev.query('SENS?'))) - 1)))

    @setting(43, 'Auto Sensitivity')
    def auto_sensitivity(self, c):
        ''' Automatically adjusts sensitivity until signal is between 35% and 95% of full range. '''
        waittime = yield self.wait_time(c)
        r = yield self.r(c)
        sens = yield self.sensitivity(c)
        while r/sens > 0.95:
            #print "sensitivity up... ",
            yield self.sensitivity_up(c)
            yield util.wakeupCall(waittime)
            r = yield self.r(c)
            sens = yield self.sensitivity(c)
        while r/sens < 0.35:
            #print "sensitivity down... ",
            yield self.sensitivity_down(c)
            yield util.wakeupCall(waittime)
            r = yield self.r(c)
            sens = yield self.sensitivity(c)
        
        
    @setting(32, 'Auto Gain')
    def auto_gain(self, c):
        """ Runs the auto gain function. Does nothing if time constant >= 1s. """
        dev = self.selectedDevice(c)
        yield dev.write("AGAN");
        done = False
        resp = yield dev.query("*STB? 1")
        while resp != '0':
            resp = yield dev.query("*STB? 1")
            print "Waiting for auto gain to finish..."
            
    @setting(33, 'Filter Slope', i='i', returns='i')
    def filter_slope(self, c, i=None):
        ''' Sets/gets the low pass filter slope. 0=>6, 1=>12, 2=>18, 3=>24 dB/oct '''
        dev = self.selectedDevice(c)
        if i is None:
            resp = yield dev.query("OFSL?")
            returnValue(int(resp))
        else:
            yield dev.write('OFSL ' + str(i))
            returnValue(i)
            
    @setting(34, 'Wait Time', returns='v[s]')
    def wait_time(self, c):
        ''' Returns the recommended wait time given current time constant and low-pass filter slope. '''
        dev = self.selectedDevice(c)
        tc = yield dev.query("OFLT?")
        tc = getTC(int(tc))
        slope = yield dev.query("OFSL?")
        slope = int(slope)
        if slope == 0:
            returnValue(5*tc)
        elif slope == 1:
            returnValue(7*tc)
        elif slope == 2:
            returnValue(9*tc)
        else:# slope == 3:
            returnValue(10*tc)
    

__server__ = SR830()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
