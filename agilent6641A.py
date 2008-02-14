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

from labrad.gpib import GPIBDeviceServer
from labrad.server import setting, returnValue

class AgilentPSServer(GPIBDeviceServer):
    name = 'Agilent 6641A PS'
    deviceName = 'HEWLETT-PACKARD 6641A'

    @setting(10000, 'Output State', os=['b'], returns=['b'])
    def output_state(self, c, os=None):
        """Get or set the output state, on or off."""
        dev = self.selectedDevice(c)
        if os is None:
            resp = yield dev.query('OUTP?')
            os = bool(int(resp))
        else:
            yield dev.write('OUTP %d' % int(os))
        returnValue(os)

    @setting(10001, 'Current', cur=['v[A]'], returns=['v[A]'])
    def current(self, c, cur=None):
        """Get or set the current."""
        dev = self.selectedDevice(c)
        if cur is None:
            resp = yield dev.query('MEAS:CURR?')
            cur = float(resp)
        else:
            yield dev.write('CURR %f' % cur)
        returnValue(cur)

    @setting(10002, 'Voltage', v=['v[V]'], returns=['v[V]'])
    def voltage(self, c, v=None):
        """Get or set the voltage."""
        dev = self.selectedDevice(c)
        if v is None:
            resp = yield dev.query('MEAS:VOLT?')
            v = float(resp)
        else:
            yield dev.write('VOLT %f' % v)
        returnValue(v)

__server__ = AgilentPSServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
