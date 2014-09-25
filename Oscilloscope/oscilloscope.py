# Copyright (C) 2013  Daniel Sank
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
name = Oscilloscope
version = 0.1
description = Talks to oscilloscopes

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

class Tektronix5054BWrapper(GPIBDeviceWrapper):
    pass
    
class AgilentDSO91304AWrapper(GPIBDeviceWrapper):
    pass
    
class OscilloscopeServer(GPIBManagedServer):
    name = 'oscilloscope_server'
    #Add wrappers for various oscilloscopes here
    deviceWrappers = {
                     'Tektronix 2014B': Tektronix2014BWrapper,
                     'Tektronix 5054B': Tektronix5054BWrapper,
                     'Agilent DSO91304': AgilentDSO91304Wrapper
                     }
    
    ############
    ###SYSTEM###
    ############
    
    @setting(11, returns=[])
    def reset(self, c):
        dev = self.selectedDevice(c)
        yield dev.reset()
    
    ##############
    ###VERTICAL###
    ##############
    
    ################
    ###HORIZONTAL###
    ################    
    
__server__ = OscilloscopeServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
