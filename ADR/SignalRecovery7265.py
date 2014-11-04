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
name = Signal Recovery 7265
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

from labrad import types as T, gpib
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from labrad.units import Unit
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
import numpy as np, time

V, A = Unit('V'), Unit('A')

class SR7265Wrapper(GPIBDeviceWrapper):
    pass

        
class SR7265Server(GPIBManagedServer):
    name = 'Signal Recovery 7265'
    deviceName = 'Signal Recovery 7265'
    deviceWrapper = SR7265Wrapper
    deviceIdentFunc = 'identify_device'
    
    @setting(1000, server='s', address='s', idn='s')
    def identify_device(self, c, server, address, idn=None):
        try:
            yield self.client.refresh()
            p = self.client[server].packet()
            p.address(address)
            p.timeout(1)
            p.write("ID")
            p.read()
            resp = yield p.send()
            if resp.read == '7265':
                returnValue(self.deviceName)
        except Exception:
            pass

    @setting(10, 'Voltage', returns=['v[V]'])
    def voltage(self, c):
        ''' Returns measured voltage. '''
        returnValue(float( (yield self.selectedDevice(c).query("MAG.")) ))
        
    @setting(11, 'r', returns=['v[V]'])
    def r(self, c):
        ''' Returns measured voltage. '''
        return self.voltage(c)
        
    @setting(20, 'auto_sensitivity')
    def auto_sensitivity(self, c):
        ''' Auto-adjusts the sensitivity '''
        pass

        
__server__ = SR7265Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
