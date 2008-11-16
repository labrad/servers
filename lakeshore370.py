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

def temp2res(t):
    try:
        return math.exp(1.76*(t**(-0.345)) + 6.02)
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
    def getHeaterOutput(self):
        ans = yield self.query('HTR?')
        returnValue(float(ans))

    @inlineCallbacks
    def setHeaterRange(self, value):
        if value is None:
            yield self.write('HTRRNG 0')
            returnValue(None)
        else:
            value = float(value)
            val = 8
            for limit in [31.6, 10, 3.16, 1, 0.316, 0.1, 0.0316]:
                if value<=limit:
                    val -= 1
            yield self.write('HTRRNG %d' % val)
            returnValue([0.0316, 0.1, 0.316, 1.0, 3.16, 10.0, 31.6, 100.0][val-1])

    @inlineCallbacks
    def controlTemperature(self, channel, resistance, loadresistor):
        yield self.write('HTRRNG 0')
        yield self.write('CSET %d,0,2,1,1,8,%f' % (channel, loadresistor))
        yield self.write('SETP %f' % resistance)

    @inlineCallbacks
    def setPID(self, P, I, D):
        yield self.write('PID %f, %f, %f' % (P, I, D))

    @inlineCallbacks
    def readLoop(self, idx=0):
        while self.alive:
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

    @setting(50, 'Regulate Temperature', channel='w', temperature='v[K]', loadresistor='v[Ohm]', returns='v[Ohm]: Target resistance')
    def regulate(self, c, channel, temperature, loadresistor=30000):
        """Initializes temperature regulation

        NOTE:
        Use "Heater Range" to turn on heater and start regulation."""
        if channel not in range(1,17):
            raise Exception('Channel needs to be between 1 and 16')
        res = temp2res(float(temperature))
        if res==0.0:
            raise Exception('Invalid temperature')
        loadresistor = float(loadresistor)
        if (loadresistor<1) or (loadresistor>100000):
            raise Exception('Load resistor value must be between 1 Ohm and 100kOhm')
        dev=self.selectedDevice(c)
        dev.onlyChannel=channel
        dev.selectChannel(channel)
        yield dev.controlTemperature(channel, res, loadresistor)
        returnValue(res)

    @setting(52, 'PID', P='v', I='v[s]', D='v[s]')
    def setPID(self, c, P, I, D=0):
        P=float(P)
        if (P<0.001) or (P>1000):
            raise Exception('P value must be between 0.001 and 1000')
        I=float(I)
        if (I<0) or (I>10000):
            raise Exception('I value must be between 0s and 10000s')
        D=float(D)
        if (D<0) or (D>2500):
            raise Exception('D value must be between 0s and 2500s')
        dev = self.selectedDevice(c)
        yield dev.setPID(P, I, D)

    @setting(55, 'Heater Range', limit=['v[mA]: Set to this current', ' : Turn heater off'], returns=['v[mA]', ''])
    def heaterrange(self, c, limit=None):
        """Sets the Heater Range"""
        dev = self.selectedDevice(c)
        ans = yield dev.setHeaterRange(limit)
        returnValue(ans)

    @setting(56, 'Heater Output', returns=['v[%]'])
    def heateroutput(self, c):
        """Queries the current Heater Output"""
        dev = self.selectedDevice(c)
        ans = yield dev.getHeaterOutput()
        returnValue(ans)



__server__ = LakeshoreRuOxServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
