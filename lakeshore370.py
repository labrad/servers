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

from datetime import datetime
import math

from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper

READ_ORDER = [1, 2, 1, 3, 1, 4, 1, 5]
N_CHANNELS = 5
SETTLE_TIME = 8

def res2temp(r):
    try:
        return ((math.log(r) - 6.02) / 1.76) ** (-1/.345)
    except:
        return 0.0

class RuOxWrapper(GPIBDeviceWrapper):
    def initialize(self):
        self.readings = [(0, datetime.now())] * N_CHANNELS
        self.alive = True
        self.onlyChannel = 0
        self.readLoop().addErrback(log.err)


    def shutdown(self):
        self.alive = False

    @inlineCallbacks
    def selectChannel(self, channel):
        yield self.write('SCAN %d,0' % channel)


    @inlineCallbacks
    def readLoop(self, idx=0):
        while self.alive:
            print self.onlyChannel
            # read only one specific channel
            if self.onlyChannel > 0:
                chan = self.onlyChannel
                yield util.wakeupCall(SETTLE_TIME)
                r = yield self.query('RDGR? %d' % chan)
                self.readings[chan-1] = float(r), datetime.now()
            # scan over channels
            else:   
                chan = READ_ORDER[idx]
                yield self.selectChannel(chan)
                yield util.wakeupCall(SETTLE_TIME)
                r = yield self.query('RDGR? %d' % chan)
                self.readings[chan-1] = float(r), datetime.now()
                idx = (idx + 1) % len(READ_ORDER)

        
class LakeshoreRuOxServer(GPIBManagedServer):
    name = 'Lakeshore RuOx'
    deviceName = 'LSCI MODEL370'
    deviceWrapper = RuOxWrapper

    @setting(10, 'Temperatures', returns=['*(v[K], t)'])
    def temperatures(self, c):
        """Read channel temperatures.

        Returns a ValueList of the channel temperatures in Kelvin.
        """
        dev = self.selectedDevice(c)
        return [(res2temp(r), t) for r, t in dev.readings]

    @setting(11, 'Resistances', returns=['*(v[Ohm], t)'])
    def resistances(self, c):
        """Read channel voltages.

        Returns a ValueList of the channel voltages in Volts.
        """
        dev = self.selectedDevice(c)
        return dev.readings

    @setting(12, 'Select channel', channel=['w'], returns=['w'])
    def selectchannel(self, c, channel):
        """Select channel to be read. If argument is 0,
        scan over channels.

        Returns selected channel.
        """
        dev = self.selectedDevice(c)
        dev.onlyChannel=channel
        if channel > 0:
            dev.selectChannel(channel)
        return channel



__server__ = LakeshoreRuOxServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
