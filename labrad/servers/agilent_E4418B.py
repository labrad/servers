# Copyright (C) 2012 Jim Wenner
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
version = 1.1
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

    @setting(201, 'Units', units=['s'], returns=['s'])
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

    @setting(202, 'Frequency', f=['v[Hz]'], returns=['v[Hz]'])
    def frequency(self, c, f=None):
        """
        Get or set the calibration frequency.
        """
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('SENS:FREQ %fHz' %f)
        resp = yield dev.query('SENS:FREQ?')
        returnValue(float(resp))

    @setting(301, 'Averaging OnOff', onoff=['b'], returns=['b'])
    def averagingOnOff(self, c, onoff=None):
        """
        Turn averaging on or off.
        If onoff is not specified, determine if averaging is on or off.
        """
        dev = self.selectedDevice(c)
        if onoff is not None:
            yield dev.write('SENS:AVER %d' %int(onoff))
        resp = yield dev.query('SENS:AVER?')
        returnValue(bool(int(resp)))

    @setting(302, 'Averaging Length', num=['w'], returns=['w'])
    def averagingLength(self, c, num=None):
        """
        Get or set the averaging length.
        Allowable values between 1 and 1024.
        """
        dev = self.selectedDevice(c)
        if num is not None:
            yield dev.write('SENS:AVER:COUN %d' %num)
        resp = yield dev.query('SENS:AVER:COUN?')
        returnValue(int(resp))


__server__ = AgilentPMServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
