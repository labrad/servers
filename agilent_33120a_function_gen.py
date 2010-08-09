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
name = Agilent 33120a function generator
version = 1.0
description = 

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

class FunctionGenerator(GPIBManagedServer):
    name = 'Agilent Function Generator Server'
    deviceName = 'Agilent 33120a'
    @setting(11,'Set DC', f='v[Volts]', returns='')
    def set_dc_waveform(self, c,f=0):
        """Puts generator into DC mode with given voltage.
        accepts value from -5V to 5V"""
        dev = self.selectedDevice(c)
        dev.write(':APPL:DC DEF, DEF, %f' % float(f))
