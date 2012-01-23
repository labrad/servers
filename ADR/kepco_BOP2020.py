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
name = Kepco BOP 20-20
version = 0.2
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

VOLT_LIMIT = 1.0 * V
CURRENT_LIMIT = 17.17 * A
RAMP_RATE = 0.036 * A # (per second)
RESOLUTION = 0.001 # power supply measurement resolution, in amps

# make a list:
# clear
# dwell
# add current levels
# count -> 1
# execute

# stop a list:
# set current to current level
# mode:fix

class KepcoWrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        if not int( (yield self.query("FUNC:MODE?")) ):
            yield self.write("FUNC:MODE CURR")
        if float( (yield self.query("VOLT?")) ) > VOLT_LIMIT['V']:
            yield self.write("VOLT %f" % VOLT_LIMIT['V'])
            
        # don't change target current if we just turned on server now
        self.targetCurrent = float( (yield self.query("MEAS:CURR?")) ) * A
        print "STARTUP CURENT %s" % self.targetCurrent
        
        self.lastTime = 0
        self.inLoop = False
        self.timeInterval = 0.2
        self.loop = LoopingCall(self.mainLoop)
        self.loopDone = self.loop.start(self.timeInterval, now=True)
    
    @inlineCallbacks
    def shutdown(self):
        self.loop.stop()
        yield self.loopDone
    
    @inlineCallbacks
    def mainLoop(self):
        if self.inLoop:
            return
        self.inLoop = True
        # see if our current has settled
        curr = float( (yield self.query("MEAS:CURR?")) )
        #print "in loop, curr = %s" % curr
        if abs(curr - float( (yield self.query("CURR?")) )) < RESOLUTION:
            distance = self.targetCurrent['A'] - curr
            #print "need to move %f" % distance
            if abs(distance) > RESOLUTION:
                #print "target not within resolution"
                yield self.write("OUTP ON")
                deltaT = min(time.time() - self.lastTime, 1)
                change = np.sign(distance) * min(abs(distance), RAMP_RATE['A'] * deltaT)
                #print "attempting to set to %f" % (curr + change)
                yield self.write("CURR %f" % (curr + change))
                #print "output change by %f" % change
            else:
                if abs(curr) < RESOLUTION:
                    yield self.write("OUTP OFF")
        
        self.lastTime = time.time()
        self.inLoop = False
    
    def set_current(self, current = None):
        if current is not None:
            self.targetCurrent = min(current, CURRENT_LIMIT)
            self.targetCurrent = max(current, -CURRENT_LIMIT)
        return self.targetCurrent
        
    
        
    
        
        
class KepcoServer(GPIBManagedServer):
    name = 'Kepco BOP 20-20'
    deviceName = 'KEPCO BIT 4886 20-20  10/13/2011'
    deviceWrapper = KepcoWrapper

    @setting(10, 'Voltage', returns=['v[V]'])
    def voltage(self, c):
        ''' Returns measured voltage. '''
        returnValue(float( (yield self.selectedDevice(c).query("MEAS:VOLT?")) ))
    @setting(11, 'Current', returns=['v[A]'])
    def current(self, c):
        ''' Returns measured current. '''
        returnValue(float( (yield self.selectedDevice(c).query("MEAS:CURR?")) ))
        
    @setting(20, 'Set Voltage', voltage='v[V]', returns='v[V]')
    def set_voltage(self, c, voltage=None):
        ''' Sets the voltage limit and returns the voltage limit. If there is no argument, only returns the limit.\n
            Note that the hard limit on the power supply is just under 1 V, though it will let you set it higher. '''
        if voltage is not None:
            voltage = min(voltage, VOLT_LIMIT)
            yield self.selectedDevice(c).write("VOLT %f" % voltage['V'])
        returnValue(float( (yield self.selectedDevice(c).query("VOLT?")) ))

    @setting(21, 'Set Current', current='v[A]', returns='v[A]')
    def set_current(self, c, current=None):
        ''' Sets the target current and returns the target current. If there is no argument, only returns the target.\n
            Note that the hard limit on the power supply is just under 15 A, though it will let you set it higher. '''
        return self.selectedDevice(c).set_current(current)
    
    @setting(30, 'Output', on='b', returns='b')
    def output(self, c, on=None):
        ''' Sets the output state to ON (T) or OFF (F), and returns the current output state. If there is no argument, only returns current state. '''
        if on is not None:
            s = 'ON' if on else 'OFF'
            yield self.selectedDevice(c).write("OUTP %s" % s)
        returnValue(bool(int( (yield self.selectedDevice(c).query("OUTP?")) )))
        
    @setting(31, 'Shut Off')
    def shut_off(self, c):
        ''' Immediately turns off the power supply. Use in case of magnet quench (only)! '''
        dev = self.selectedDevice(c)
        dev.targetCurrent = 0 * A
        yield dev.write("OUTP OFF")
        yield dev.write("VOLT 1")   # set voltage to 1 so the magnet can drain at the max allowed rate
        yield dev.write("CURR 0")
        
        
        
__server__ = KepcoServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
