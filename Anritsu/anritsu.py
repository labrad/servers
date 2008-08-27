#!c:\python25\python.exe

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

from labrad import types as T
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

class AnritsuWrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        self.frequency = yield self.getFrequency()
        self.amplitude = yield self.getAmplitude()
        self.outputStateKnown = False # there is not way to query for the output state
        self.output = True

    @inlineCallbacks
    def getFrequency(self):
        self.frequency = yield self.query('OF 1').addCallback(float)
        returnValue(self.frequency)

    @inlineCallbacks
    def getAmplitude(self):
        self.amplitude = yield self.query('OL 1').addCallback(float)
        returnValue(self.amplitude)

    @inlineCallbacks
    def setFrequency(self, f):
        if self.frequency != f:
            yield self.write('F1 %fMH' % f)
            self.frequency = f
    
    @inlineCallbacks
    def setAmplitude(self, a):
        if self.amplitude != a:
            yield self.write('L1 %fDM' % a)
            self.amplitude = a

    @inlineCallbacks
    def setOutput(self, out):
        if self.output != out or not self.outputStateKnown:
            yield self.write('RF %d' % int(out))
            self.output = out
            self.outputStateKnown = True

class AnritsuServer(GPIBManagedServer):
    name = 'Anritsu Server'
    deviceName = 'ANRITSU 68367C'
    deviceWrapper = AnritsuWrapper

    @setting(10, 'Frequency', f=['v[MHz]'], returns=['v[MHz]'])
    def frequency(self, c, f=None):
        """Get or set the CW frequency."""
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.setFrequency(f)
        returnValue(dev.frequency)

    @setting(11, 'Amplitude', a=['v[dBm]'], returns=['v[dBm]'])
    def amplitude(self, c, a=None):
        """Get or set the CW amplitude."""
        dev = self.selectedDevice(c)
        if a is not None:
            yield dev.setAmplitude(a)
        returnValue(dev.amplitude)

    @setting(12, 'Output', os=['b'], returns=['b'])
    def output_state(self, c, os=None):
        """Get or set the output status."""
        dev = self.selectedDevice(c)
        if os is not None:
            yield dev.setOutput(os)
        returnValue(dev.output)

__server__ = AnritsuServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
