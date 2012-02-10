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
version = 0.31
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

VOLT_LIMIT = 0.9 * V
CURRENT_LIMIT = 17.17 * A

class KepcoWrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        if int( (yield self.query("FUNC:MODE?")) ):
            yield self.write("FUNC:MODE VOLT")
        
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
            voltage = min(max(voltage, -VOLT_LIMIT), VOLT_LIMIT)
            yield self.selectedDevice(c).write("VOLT %f" % voltage['V'])
        returnValue(float( (yield self.selectedDevice(c).query("VOLT?")) ))

    @setting(21, 'Set Current', current='v[A]', returns='v[A]')
    def set_current(self, c, current=None):
        ''' Sets the target current and returns the target current. If there is no argument, only returns the target.\n
            Note that the hard limit on the power supply is just under 15 A, though it will let you set it higher. '''
        if current is not None:
            current = min(max(current, -CURRENT_LIMIT), CURRENT_LIMIT)
            yield self.selectedDevice(c).write("CURR %f" % current['A'])
        returnValue(float( (yield self.selectedDevice(c).query("CURR?")) ))
    
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
        dev.write("OUTP OFF")
        dev.write("FUNC:MODE CURR")
        dev.write("CURR 0")
        dev.write("VOLT 1")

    @setting(32, 'Voltage Mode')
    def voltage_mode(self, c):
        ''' Put back into voltage mode (e.g. after a shut off) '''
        dev = self.selectedDevice(c)
        yield dev.write("FUNC:MODE VOLT")
        
__server__ = KepcoServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
