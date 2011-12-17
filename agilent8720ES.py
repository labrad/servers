# Copyright (C) 2011  Ted White
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
#

"""
### BEGIN NODE INFO
[info]
name = Agilent 8720ES Server
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
import numpy as np




class Agilent8720ES(GPIBManagedServer):
    name = 'Agilent 8720ES'
    deviceName = 'HEWLETT PACKARD 8720ES'
    
    
    @setting(345, 'Get Trace')
    def get_trace(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('FORM4')
        yield dev.write('SING')
        result = yield dev.query('OUTPDATA')
        data = parseData(result)
        returnValue(data)
    
    @setting(346, 'Set Start Freq MHz')
    def set_start_freq_mhz(self, c, start):
        dev = self.selectedDevice(c)
        startString = str(start)
        yield dev.write('STAR '+ startString + ' MHZ')
        
    @setting(347, 'Set Stop Freq MHz')
    def set_stop_freq_mhz(self, c, stop):
        dev = self.selectedDevice(c)
        stopString = str(stop)
        yield dev.write('STOP ' + stopString + ' MHZ')
        
    @setting(348, 'Get Maximum')
    def get_max_point(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('SING')
        yield dev.write('SEAMAX')
        result = yield dev.query('OUTPMARK')
        result = result.split(',')
        data = [float(result[0]), float(result[2])]
        returnValue(data)
        
        
    @setting(349, 'Set Sweep Mode')
    def set_sweep_mode(self, c, mode):
        dev = self.selectedDevice(c)
        yield dev.write(mode)
        
    @setting(351, 'Set Sweep Power')
    def set_sweep_power(self, c, power = 0):
        dev = self.selectedDevice(c)
        powerString = str(power)
        print 'POWE ' + powerString + ' DB'
        yield dev.write('POWE ' + powerString + ' DB')
    
    @setting(367, 'Num Points')
    def num_points(self, c, data):
        dev = self.selectedDevice(c)
        dataString = str(data)
        yield dev.write('POIN'+dataString)
    


    
def parseData(data):
    data = data.split('\n')
    for i in range(len(data)):
        stuff = data[i].split(',')
        num1 = float(stuff[0])
        num2 = float(stuff[1])
        num = (num1**2 + num2**2)
        num = 10*np.log10(num)
        data[i] = num
    return data    
    
__server__ = Agilent8720ES()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
