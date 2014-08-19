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

"""
### BEGIN NODE INFO
[info]
name = Agilent 3640A DC Source
version = 1.4
description = Controls the Agilent 3640A DC Power Supply.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

# these variables for operating in the persistent switch supply mode
# (for the ADR superconducting magnet)
VOLT_LIMIT = 10
CURRENT = 0.020

import time
from labrad import types as T, util
import labrad.units as U
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

class AgilentDCWrapper(GPIBDeviceWrapper):
    def initialize(self):
        self.psMode = False
        self.psChangeTime = 0
            
class AgilentDCSource(GPIBManagedServer):
    """Controls the Agilent 3640A DC Power Supply."""
    name = 'Agilent 3640A DC Source'
    deviceName = 'Agilent Technologies E3640A'
    deviceWrapper = AgilentDCWrapper
        
    @setting(10, state='b', returns='b')
    def output(self, c, state=None):
        """Get or set the output state."""
        dev = self.selectedDevice(c)
        if state is None:
            ans = yield dev.query('OUTP?')
            state = bool(int(ans))
        else:
            if state != bool(int( (yield dev.query('OUTP?')) )):
                dev.psChangeTime = time.time()
            yield dev.write('OUTP %d' % state)
        returnValue(state)

    @setting(20, curr='v[A]', returns='v[A]')
    def current(self, c, curr=None):
        """Get or set the output current.

        Returns the measured output current, which
        may not be equal to the set level if the output
        is off or the device is voltage-limited, etc.
        """
        dev = self.selectedDevice(c)
        if not dev.psMode and curr is not None:
            yield dev.write('CURR %g' % float(curr))
        ans = yield dev.query('MEAS:CURR?')
        returnValue(float(ans)*U.A)
        
    @setting(21, curr='v[A]', returns='v[A]')
    def set_current(self, c, curr=None):
        """ Identical to current(curr), but returns the set value of current, not the measured value. """
        dev = self.selectedDevice(c)
        if not dev.psMode and curr is not None:
            yield self.current(c, curr)
        returnValue(float( (yield self.selectedDevice(c).query('CURR?')) )*U.A)

    @setting(30, volt='v[V]', returns='v[V]')
    def voltage(self, c, volt=None):
        """Get or set the output voltage.

        Returns the measured output voltage, which
        may not be equal to the set level if the output
        is off or the device is current-limited, etc.
        """
        dev = self.selectedDevice(c)
        if not dev.psMode and volt is not None:
            yield dev.write('VOLT %g' % float(volt))
        ans = yield dev.query('MEAS:VOLT?')
        returnValue(float(ans)*U.V)
        
    @setting(31, volt='v[V]', returns='v[V]')
    def set_voltage(self, c, volt=None):
        """ Identical to voltage(volt), but returns the set value of current, not the measured value. """
        dev = self.selectedDevice(c)
        if not dev.psMode and volt is not None:
            yield self.voltage(c, volt)
        returnValue(float( (yield dev.query('VOLT?')) )*U.V)
        
    @setting(40, mode='b', returns='b')
    def persistent_switch_mode(self, c, mode=None):
        '''
        Gets/sets whether this device is in "persistent switch mode".
        If so, it is fixed to 47 mA, and the only operation allowed is output on/off.
        '''
        dev = self.selectedDevice(c)
        if mode is not None:
            if mode:
                yield dev.write('CURR %g' % CURRENT)
                yield dev.write('VOLT %g' % VOLT_LIMIT)
                if not dev.psMode:
                    dev.psChangeTime = time.time()
            dev.psMode = mode
        returnValue(dev.psMode)
        
    @setting(41, returns='v[s]')
    def persistent_switch_time_elapsed(self, c):
        ''' 
        returns the amount of time since the mode changed (on/off).
        only valid in persistent switch mode (returns 0 if not).
        '''
        dev = self.selectedDevice(c)
        if dev.psMode:
            return time.time() - dev.psChangeTime
        else:
            return 0

__server__ = AgilentDCSource()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
