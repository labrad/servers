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
name = Tektronix TDS 2014B Oscilloscope
version = 0.1
description = Talks to the Tektronix 2014B oscilloscope

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

from struct import unpack

import numpy

class Tektronix2014BWrapper(GPIBDeviceWrapper):
    pass
#    @inlineCallbacks
#    def initialize(self):
#        pass

##def _parName(meas):
##    return 'labrad_%s' % meas

class Tektronix2014BServer(GPIBManagedServer):
    name = 'TEKTRONIX 2014B OSCILLOSCOPE'
    deviceName = 'TEKTRONIX TDS 2014B'
    deviceWrapper = Tektronix2014BWrapper

    def initContext(self, c):
        pass
        
    @setting(11, returns=[])
    def reset(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('*RST')
        # wait for reset to complete

    #Channel settings
    @setting(21, channel = 'i', returns=['s'])
    def channel(self, c, channel):
        """Get information on one of the scope channels.

        INPUTS
        channel - integer indicating a scope channel
        
        OUTPUTS 
        A tuple of (?,?,scale,position,coupling,?,?,units)
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('CH%d?' %channel)
        returnValue(resp)

    @setting(22, channel = 'i', coupling = 's', returns=[])
    def coupling(self, c, channel, coupling = None):
        dev = self.selectedDevice(c)
        if coupling is None:
            resp = yield dev.query('CH%d:COUP?' %channel)
        else:
            yield dev.write('CH%d:COUP '+coupling %channel)
            resp = yield dev.query('CH%d:COUP?' %channel)
        returnValue(resp)

    def other():
        pass

__server__ = Tektronix2014BServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
