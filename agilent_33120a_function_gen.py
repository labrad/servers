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
#
# Written August 9, 2010 by Nate Earnest

"""
### BEGIN NODE INFO
[info]
name = Agilent 33120a generator
version = 1.0
description = Controls Agilent 33120a function generator

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, errors
from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from struct import unpack
from twisted.internet.defer import inlineCallbacks, returnValue

class AgilentFunctionGenerator(GPIBManagedServer):
    name = 'Agilent 33120a generator'
    deviceName = 'HEWLETT-PACKARD 33120A'
    @setting(11,'Set DC', f='v[Volts]', returns='')
    def set_dc_waveform(self, c,f=0):
        if f< -5 or f > 5:
            raise Exception('Signal Gnerator only puts out -5 to 5 volts in DC Voltage')
        """Puts generator into DC mode with given voltage."""
        dev = self.selectedDevice(c)
        dev.write(':APPL:DC DEF, DEF, %f' % float(f))



__server__ = AgilentFunctionGenerator()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)



