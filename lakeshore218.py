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
name = Lakeshore Diodes
version = 2.1
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, gpib
from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import inlineCallbacks, returnValue

def parse(val):
    ''' Parse function to account for the occasional GPIB glitches where we get extra characters in front of the numbers. '''
    if len(val):
        try:
            return float(val)
        except ValueError:
            return parse(val[1:])
    else:
        return 0.0

class LakeshoreDiodeServer(GPIBManagedServer):
    name = 'Lakeshore Diodes'
    deviceName = 'LSCI MODEL218S'

    @setting(10, 'Temperatures', returns=['*v[K]'])
    def temperatures(self, c):
        """Read channel temperatures.

        Returns a ValueList of the channel temperatures in Kelvin.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('KRDG? 0')
        vals = [parse(val) for val in resp.split(',')]
        returnValue(vals)

    @setting(11, 'Voltages', returns=['*v[V]'])
    def voltages(self, c):
        """Read channel voltages.

        Returns a ValueList of the channel voltages in Volts.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('SRDG? 0')
        vals = [parse(val) for val in resp.split(',')]
        returnValue(vals)

__server__ = LakeshoreDiodeServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
