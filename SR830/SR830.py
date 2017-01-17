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
version = 2.8.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""
from labrad.units import Unit
V, mV, us, ns, GHz, MHz, Hz, dBm, dB, K, deg = [Unit(s) for s in (
    'V', 'mV', 'us', 'ns', 'GHz', 'MHz', 'Hz', 'dBm', 'dB', 'K', 'deg')]
from labrad import types as T, gpib, units
from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import inlineCallbacks, returnValue

def getTC(i):
    """converts from the integer label used by the SR830 to a time"""
    if i < 0:
        return getTC(0)
    elif i > 19:
        return getTC(19)
    elif i % 2 == 0:
        return 10**(-5 + i/2) * units.s
    else:
        return 3*10**(-5 + i/2) * units.s

def getSensitivity(i):
    """converts form the integer label used by the SR830 to a sensitivity"""
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
        """returns the input mode. 0=A, 1=A-B, 2=I(10**6), 3=I(10**8)"""
        dev = self.selectedDevice(c)
        mode = yield dev.query('ISRC?')
        returnValue(int(mode))

    @inlineCallbacks
    def outputUnit(self, c):
        """returns a labrad unit, V or A, for what the main output type is. (R, X, Y)"""
        mode = yield self.inputMode(c)
        if mode < 2:
            returnValue(units.V)
        else:
            returnValue(units.A)

    @setting(12, 'Phase',
             ph=['', 'v[deg]'],
             returns='v[deg]: phase')
    def phase(self, c, ph=None):
        """Set or get the excitation phase offset.

        Args:
            ph (Value[deg]): Phase offset to set. If not included, then we
                query the existing phase instead.

        Returns:
            (Value[deg]): The phase offset.
        """
        dev = self.selectedDevice(c)
        if ph is not None:
            yield dev.write('PHAS {}'.format(ph['deg']))
        resp = yield dev.query('PHAS?')
        returnValue(float(resp)*deg)

    @setting(13, 'Reference',
             ref=[': query reference source', 'b: set external (false) or internal (true) reference source'],
             returns='b')
    def reference(self, c, ref=None):
        """Set or get the reference source.

        Args:
            ref (bool): False sets external source, True sets internal source.
                If the argument is omitted we query the existing source.

        Returns:
            (bool):  The excitation source.
        """
        dev = self.selectedDevice(c)
        if ref is not None:
            yield dev.write('FMOD {}'.format(int(ref)))
        resp = yield dev.query('FMOD?')
        returnValue(bool(int(resp)))

    @setting(14, 'Frequency', f=[': query frequency', 'v[Hz]: set frequency'], returns='v[Hz]')
    def frequency(self, c, f=None):
        """Set or get the excitation frequency (when source is internal)

        Args:
            f (value[Hz]): Frequency to set.  If none, then we query the
                existing frequency

        Returns:
            (value[Hz]): The internal excitation frequency.
        """
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('FREQ {}'.format(f['Hz']))
        resp = yield dev.query('FREQ?')
        returnValue(float(resp)*Hz)

    @setting(15, 'External Reference Slope', ers=[': query', 'i: set'], returns='i')
    def external_reference_slope(self, c, ers=None):
        """Set or get the external reference slope.

        Args:
            ers (int): Specifies the external reference source.
                0 = Sine, 1 = TTL Rising, 2 = TTL Falling

        Returns:
            (int):  The external reference source.
                0 = Sine, 1 = TTL Rising, 2 = TTL Falling
        """
        dev = self.selectedDevice(c)
        if ers is not None:
            yield dev.write('RSLP {}'.format(ers))
        resp = yield dev.query('RSLP?')
        returnValue(int(resp))

    @setting(16, 'Harmonic', h=[': query harmonic', 'i: set harmonic'], returns='i')
    def harmonic(self, c, h=None):
        """Set or get the harmonic.  
        
        Harmonic can be set as high as 19999 but is capped at a frequency of 102kHz.

        Args:
            h (int): The harmonic to set.  Integer from 1 to 19999, but frequency
                must be less than 102kHz (that is, harmonic * f0).

        Returns:
            (int): The harmonic being measured.
        """
        dev = self.selectedDevice(c)
        if h is not None:
            yield dev.write('HARM {}'.format(h))
        resp = yield dev.query('HARM?')
        returnValue(int(resp))

    @setting(17, 'Sine Out Amplitude', amp=[': query', 'v[V]: set'], returns='v[V]')
    def sine_out_amplitude(self, c, amp=None):
        """ Set or get the amplitude of the excitation sine waveform.

        Args:
            amp (Value[V]): RMS excitation amplitude
                Accepts values between .004 and 5.0 Vrms.

        Returns:
            (Value[V]): The RMS excitation amplitude.
        """
        dev = self.selectedDevice(c)
        if amp is not None:
            yield dev.write('SLVL {}'.format(amp['V']))
        resp = yield dev.query('SLVL?')
        returnValue(float(resp)*V)

    @setting(18, 'Aux Input', n='i', returns='v[V]')
    def aux_input(self, c, n):
        """Get the value of the Aux Input channel n (1,2,3,4)

        Args:
            n (i): Aux input channel to query.

        Returns:
            (Value[V]): the value of the specified Aux input.
        """
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        resp = yield dev.query('OAUX? {}'.format(n))
        returnValue(float(resp)*V)

    @setting(19, 'Aux Output', n='i', v=['v[V]'], returns='v[V]')
    def aux_output(self, c, n, v=None):
        """Get or set the value of an Aux Output.

        Args:
            n (i): The aux input channel to set or query. n (1,2,3,4).
            v (Value[V]):  The value to set the specified Aux channel to.
                v can be from -10.5 to 10.5 V.

        Returns:
            (Value[V]): The voltage of Aux channel n.
        """
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        if v is not None:
            yield dev.write('AUXV {}, {}'.format(n, v))
        resp = yield dev.query('AUXV? {}'.format(n))
        returnValue(float(resp)*V)

    @setting(21, 'x', returns='v')
    def x(self, c):
        """Query the value of X, the in phase signal.

        Returns:
            (Value[V] or [A]): The X reading in units dependent on the input
                mode.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 1')
        unit = yield self.outputUnit(c)
        returnValue(float(resp) * unit)

    @setting(22, 'y', returns='v')
    def y(self, c):
        """Query the value of Y, the quadrature signal.

        Returns:
            (Value[V] or [A]): The Y reading in units dependent on the input
                mode.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 2')
        unit = yield self.outputUnit(c)
        returnValue(float(resp) * unit)

    @setting(23, 'r', returns='v')
    def r(self, c):
        """Query the value of R, the magnitude of the signal.

        Returns:
            (Value[V] or [A]): The R reading in units dependent on the input
                mode.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 3')
        unit = yield self.outputUnit(c)
        returnValue(float(resp) * unit)

    @setting(24, 'theta', returns='v[deg]')
    def theta(self, c):
        """Query the value of theta: arctan(quadrature-signal/in-phase-signal).

        Returns:
            (Value[deg]): The value of theta.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 4')
        returnValue(float(resp)*deg)

    @setting(30, 'Time Constant', i='i', returns='v[s]')
    def time_constant(self, c, i=None):
        """Set or get the time constant.

        Args:
            i (i): The time constant to set.
                i=0 --> 10 us; 1-->30us, 2-->100us, 3-->300us, ..., 19 --> 30ks

        Returns:
            (Value[s]): The time constant.

        """
        dev = self.selectedDevice(c)
        if i is not None:
            yield dev.write('OFLT {}'.format(i))
        resp = yield dev.query("OFLT?")
        returnValue(getTC(int(resp)))

    @setting(31, 'Sensitivity', i='i', returns='v')
    def sensitivity(self, c, i=None):
        """Set or get the sensitivity.

        Args:
            i (i):  The sensitivity to set.
                i=0 --> 2 nV/fA; 1-->5nV/fA, 2-->10nV/fA,
                3-->20nV/fA, ..., 26 --> 1V/uA.

        Returns:
            (Value[V] or [uA]):  The input range (sensitivity).
        """
        dev = self.selectedDevice(c)
        mode = yield self.inputMode(c)
        if mode < 2:
            u = units.V
        else:
            u = units.uA
        if i is not None:
            yield dev.write('SENS {}'.format(i))
        resp = yield dev.query("SENS?")
        returnValue(getSensitivity(int(resp)) * u)

    @setting(41, 'Sensitivity Up', returns='v')
    def sensitivity_up(self, c):
        """Kicks the sensitivity up a notch."""
        dev = self.selectedDevice(c)
        returnValue((yield self.sensitivity(c, int((yield dev.query('SENS?'))) + 1)))

    @setting(42, 'Sensitivity Down', returns='v')
    def sensitivity_down(self, c):
        """Turns the sensitivity down a notch."""
        dev = self.selectedDevice(c)
        returnValue((yield self.sensitivity(c, int((yield dev.query('SENS?'))) - 1)))

    @setting(43, 'Auto Sensitivity')
    def auto_sensitivity(self, c):
        """Automatically adjusts sensitivity until signal is between 35% and 95% of full range."""
        waittime = yield self.wait_time(c)
        r = yield self.r(c)
        sens = yield self.sensitivity(c)
        while r/sens > 0.95:
            # print "sensitivity up... ",
            yield self.sensitivity_up(c)
            yield util.wakeupCall(waittime)
            r = yield self.r(c)
            sens = yield self.sensitivity(c)
        while r/sens < 0.35:
            # print "sensitivity down... ",
            yield self.sensitivity_down(c)
            yield util.wakeupCall(waittime)
            r = yield self.r(c)
            sens = yield self.sensitivity(c)

    @setting(32, 'Auto Gain')
    def auto_gain(self, c):
        """Runs the auto gain function. Does nothing if time constant >= 1s."""
        dev = self.selectedDevice(c)
        yield dev.write("AGAN");
        done = False
        resp = yield dev.query("*STB? 1")
        while resp != '0':
            resp = yield dev.query("*STB? 1")
            print "Waiting for auto gain to finish..."

    @setting(33, 'Filter Slope', i='i', returns='i')
    def filter_slope(self, c, i=None):
        """Sets/gets the low pass filter slope. 0=>6, 1=>12, 2=>18, 3=>24 dB/oct"""
        dev = self.selectedDevice(c)
        if i is None:
            resp = yield dev.query("OFSL?")
            returnValue(int(resp))
        else:
            yield dev.write('OFSL {}'.format(i))
            returnValue(i)

    @setting(34, 'Wait Time', returns='v[s]')
    def wait_time(self, c):
        """Returns the recommended wait time given current time constant and low-pass filter slope."""
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

    @setting(35, 'Output Overload', returns='b')
    def output_overload(self, c):
        """Gets the output overload status bit

        The output overload status bit will return True if the input voltages
        has exceeded the 'sensitivity' setting since the last time the status
        bits were read or cleared.  Reading this status bit or sending a *CLS
        command will reset the value of this status bit to False until another
        overload event occurs.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query("LIAS? 2")
        returnValue(bool(int(resp)))

__server__ = SR830()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
