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
name = Agilent E4418B Power Meter
version = 1.0
description = Power meter.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad.gpib import GPIBManagedServer
from labrad.server import setting, returnValue

class AgilentPMServer(GPIBManagedServer):
    name = 'Agilent E4418B'
    deviceName = 'HEWLETT-PACKARD E4418B'

    @setting(100, 'Power', returns=['v[dBm]'])
    def power(self, c):
        """
        Get the current power.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('FETC:POW:AC?')
        returnValue(float(resp))

    @setting(101, 'Units', units=['s'], returns=['s'])
    def units(self, c, units=None):
        """
        Get or set the power units.
        Must be either 'DBM' or 'W'.
        """
        dev = self.selectedDevice(c)
        if units is not None:
            yield dev.write('UNIT:POW '+units)
        resp = yield dev.query('UNIT:POW?')
        returnValue(resp)

    @setting(102, 'Frequency', f=['v[Hz]'], returns=['v[Hz]'])
    def frequency(self, c, f=None):
        """
        Get or set the calibration frequency.
        """
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('SENS:FREQ %fHz' %f)
        resp = yield dev.query('SENS:FREQ?')
        returnValue(float(resp))

__server__ = AgilentPMServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
