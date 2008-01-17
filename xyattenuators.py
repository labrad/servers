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
from labrad.server import setting
from labrad import types as T
from twisted.internet.defer import inlineCallbacks, returnValue

class XYAttenuatorServer(GPIBDeviceServer):
    name = 'XY Attenuator Server'
    deviceName = '<unknown> <unknown>'

    @inlineCallbacks
    def setAtten(self, c, data, commands):
        """Helper method to set either the X or Y attenuation.

        This method looks up the desired attenuation and gpib
        command in the provided dictionary.
        """
        dev = self.selectedDevice(c)
        val = int(data.value)
        if val not in dictionary:
            raise Exception('Invalid attenuation value.')

        yield dev.write(commands[val])
        returnValue(T.Value(val, 'dB'))

    # settings

    @setting(10000, data=['v[dB]'], returns=['v[dB]'])
    def x_atten(self, c, data):
        """Set the X attenuation.

        Allowed values of are 0, 1, 2, ... 11 dB.
        """
        return self.setAtten(c, data, XattnDict)

    @setting(10001, data=['v[dB]'], returns=['v[dB]'])
    def y_atten(self, c, data):
        """Set the Y attenuation.

        Allowed values are 0, 10, 20, ... 70 dB.
        """
        return self.setAtten(c, data, YattnDict)

# commands for X attenuation
XattnDict = {
     0: 'B1234',
     1: 'A1B234',
     2: 'A2B134',
     3: 'A12B34',
     4: 'A3B124',
     5: 'A13B24',
     6: 'A23B14',
     7: 'A123B4',
     8: 'A34B12',
     9: 'A134B2',
    10: 'A234B1',
    11: 'A1234'
}

# commands for Y attenuation
YattnDict = {
     0: 'B5678',
    10: 'A5B678',
    20: 'A6B578',
    30: 'A56B78',
    40: 'A7B568',
    50: 'A57B68',
    60: 'A67B58',
    70: 'A567B8'
}

__server__ = XYAttenuatorServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
