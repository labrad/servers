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
name = Agilent 34401A DMM
version = 1.3
description = 

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
from labrad.units import V, mV, Ohm, A, mA

class AgilentDMMServer(GPIBManagedServer):
    name = 'Agilent 34401A DMM'
    deviceName = ['HEWLETT-PACKARD 34401A', 'Agilent Technologies 34461A']

    @setting(10, AC='b{AC}', returns='v[V]')
    def voltage(self, c, AC=False):
        """ Measures voltage. Defaults to DC voltage, unless AC = True. """
        dev = self.selectedDevice(c)
        s = 'AC' if AC else 'DC'
        ans = yield dev.query('MEAS:VOLT:%s?' % s)
        returnValue(float(ans) * V)
    
    @setting(11, AC = 'b', returns='v[A]')
    def current(self, c, AC=False):
        """ Measures current. Defaults to DC current, unless AC = True.
        """
        dev = self.selectedDevice(c)
        s = 'AC' if AC else 'DC'
        ans = yield dev.query('MEAS:CURR:%s?' % s)
        returnValue(float(ans) * A)
        
    @setting(12, fourWire = 'b', returns='v[Ohm]')
    def resistance(self, c, fourWire = False):
        """ Measures resistance. Defaults to 2-wire measurement, unless fourWire = True. """
        dev = self.selectedDevice(c)
        ans = yield dev.query('MEAS:%s?' % ('FRES' if fourWire else 'RES'))
        returnValue(float(ans) * Ohm)

    @setting(13, vRange='v[V]', resolution ='v[V]')
    def configure_voltage(self, c, vRange = 10, resolution = 0.0001):
        """ Sets the DMM to voltage mode, with given range and resolution. """
        dev = self.selectedDevice(c)
        dev.write("CONF:VOLT:DC %s, %s" % (vRange, resolution))

    @setting(14, returns='v[V]')
    def read_voltage(self, c):
        """ Does a 'READ' instead of 'MEAS'. Device must previously have been
        set to voltage mode with configure_voltage. """
        dev = self.selectedDevice(c)
        ans = yield dev.query("READ?")
        returnValue(float(ans) * V)
    
__server__ = AgilentDMMServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
