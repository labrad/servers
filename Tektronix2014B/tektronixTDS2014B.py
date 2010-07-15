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

COUPLINGS = ['AC', 'DC']
SCALES = []

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
        # TODO wait for reset to complete

    @setting(12, returns=[])
    def clear_buffers(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('*CLS')

    #Channel settings
    @setting(21, channel = 'i', returns = '(vss)')
    def channel(self, c, channel):
        """Get information on one of the scope channels.

        INPUTS
        channel - integer indicating a scope channel
        
        OUTPUTS 
        A tuple of (position, coupling, unit)

        TODO
        Parse the rest of the parameters that come back from the CH<x> call.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('CH%d?' %channel)
        first, second, third, position, coupling, sixth, seventh, unit = resp.split(';')

        #Convert strings to numerical data when appropriate
        first = None
        second = None
        third = None
        position = T.Value(eng2float(position),'')
        coupling = coupling
        sixth = None
        seventh = None
        unit = unit[1:-1]

        returnValue((position, coupling, unit))

    @setting(22, channel = 'i', coupling = 's', returns=['s'])
    def coupling(self, c, channel, coupling = None):
        """Get or set the coupling of a specified channel"""
        dev = self.selectedDevice(c)
        if coupling is None:
            resp = yield dev.query('CH%d:COUP?' %channel)
        else:
            coupling = coupling.upper()
            if coupling not in COUPLINGS:
                raise Exception('Coupling must be "AC" or "DC"')
            yield dev.write(('CH%d:COUP '+coupling) %channel)
            resp = yield dev.query('CH%d:COUP?' %channel)
        returnValue(resp)

    @setting(23, channel = 'i', scale = 'v', returns = ['v'])
    def scale(self, c, channel, scale = None):
        """scale(int(channel), Value(scale))

        Get or set the vertical scale of a channel
        """
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('CH%d:SC?' %channel)
        else:
            yield dev.write(('CH%d:SCA '+scale) %channel)

    @setting(41, channel = 'i', start = 'i', stop = 'i', returns='s')
    def get_trace(self, c, channel, start=1, stop=2):
        """get_trace(int channel, )

        DATA ENCODINGS
        RIB - signed, MSB first
        RPB - unsigned, MSB first
        SRI - signed, LSB first
        SRP - unsigned, LSB first
        """
        dev = self.selectedDevice(c)
        #DAT:SOU - set waveform source
        yield dev.write('DAT:SOU CH%d' %channel)
        #DAT:ENC - data format (binary/ascii)
        yield dev.write('DAT:ENC RIB')
        #DAT:WID - set number of bytes per point
        yield dev.write('DAT:WID 2')
        #DAT:STAR- starting and stopping point
        yield dev.write('DAT:STAR %d' %start)
        yield dev.write('DAT:STOP %d' %stop)
        #WFMPR - transfer waveform preamble
        preamble = yield dev.query('WFMP?')
        #CURV - transfer waveform data
        resp = yield dev.query('CURV?')
        returnValue(resp)


def eng2float(s):
    """Convert engineering notation string to a float"""
    s = s.split('E')
    value = float(s[0])*10**float(s[1])
    return value

def float2eng(x):
    """Convert a floating point number to a string in engineering notation"""
    

__server__ = Tektronix2014BServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
