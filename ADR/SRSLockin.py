# Copyright (C) 2013 Ted White
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
name = SRS lockin
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
from labrad import util
from labrad.units import V

__QUERY__ = """\
:FORM INT,32
:FORM:BORD NORM
:TRAC? TRACE%s"""

class SRSLockin(GPIBManagedServer):
    name = 'SRS lockin'
    deviceName = ['Stanford_Research_Systems SIM900']


        
    @setting(21, 'r', returns=['v[V] {Peak Amplitude}'])
    def r(self, c):
        """Gets the current amplitude from the peak detector"""
        dev = self.selectedDevice(c)
        yield dev.write('CONN 7, "xyz"')
        data =  yield dev.query('RVAL?')
        value = float(data)*V
        yield dev.write('xyz')
        returnValue(value)

    @setting(25, 'auto sensitivity')
    def auto_sensitivity(self, c):
       pass   
    

__server__ = SRSLockin()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
