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

from labrad import types as T, gpib
from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import inlineCallbacks, returnValue

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
        vals = [float(val) for val in resp.split(',')]
        returnValue(vals)

    @setting(11, 'Voltages', returns=['*v[V]'])
    def voltages(self, c):
        """Read channel voltages.

        Returns a ValueList of the channel voltages in Volts.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('SRDG? 0')
        vals = [float(val) for val in resp.split(',')]
        returnValue(vals)

__server__ = LakeshoreDiodeServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
