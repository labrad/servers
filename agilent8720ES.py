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
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from struct import unpack
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad import util
from numpy import array, transpose, linspace, hstack

class Agilent_8720ES_Wrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        yield self.write("ELED 0 NS")

class Agilent_8720ES_Server(GPIBManagedServer):
    name = 'Agilent 8720ES Server'
    deviceName = 'HEWLETT PACKARD 8720ES'
    deviceWrapper = Agilent_8720ES_Wrapper
    
    @setting(345, 'Get Trace')
    def get_trace(self, c):
        def parseData(data):
            data = data.split('\n')
            for i in range(len(data)):
                stuff = data[i].split(',')
                num1 = float(stuff[0])
                num2 = float(stuff[1])
                #num = (num1**2 + num2**2)
                #num = 10*np.log10(num)
                # num1 is real, num2 is imaginary
                # units is U (dimensionless... Vout/Vin)
                data[i] = [num1, num2]
            return data
        dev = self.selectedDevice(c)
        yield dev.write('FORM4') # Set the output format 
        yield dev.write('SING') # Perform a single sweep
        result = yield dev.query('OUTPDATA') # Get the data
        data = parseData(result)
        data = array(data)
        start_freq = yield self.start_frequency(c)
        stop_freq = yield self.stop_frequency(c)
        num_point = yield self.num_points(c)
        freqs = linspace(start_freq, stop_freq, num_point)
        data = hstack((transpose([freqs]),data))
        
        returnValue(data)
    
    @setting(346, 'Start Frequency', f=['v[MHz]'], returns=['v[MHz]'])
    def start_frequency(self, c, f=None):
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('STAR %.2f MHZ' % f)
        f = yield dev.query('STAR?').addCallback(float)
        f = T.Value(f, 'Hz')
        returnValue(f)
        
    @setting(347, 'Stop Frequency', f=['v[MHz]'], returns=['v[MHz]'])
    def stop_frequency(self, c, f=None):
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('STOP %.2f MHZ' % f)
        f = yield dev.query('STOP?').addCallback(float)
        f = T.Value(f, 'Hz')
        returnValue(f)
        
    @setting(348, 'Get Maximum')
    def get_max_point(self, c):
        dev = self.selectedDevice(c)
        yield dev.write('SING')
        yield dev.write('SEAMAX')
        result = yield dev.query('OUTPMARK')
        result = result.split(',')
        data = [float(result[0]), float(result[2])]
        returnValue(data)
        
        
    @setting(349, 'Sweep Mode', m=['s'], returns=['s'])
    def sweep_mode(self, c, m=None):
        dev = self.selectedDevice(c)
        modes = ['S11', 'S12', 'S21', 'S22']
        if m is not None:
            m = m.upper()
            if m not in modes:
                raise Exception("Invalid mode")
            yield dev.write(m)
        else:
            for s in modes:
                sbool = yield dev.query(s+'?').addCallback(int).addCallback(bool)
                if sbool:
                    m = s
        returnValue(m)
                
    @setting(351, 'Sweep Power', p=['v[dBm]'], returns=['v[dBm]'])
    def sweep_power(self, c, p=None):
        dev = self.selectedDevice(c)
        if p is not None:
            yield dev.write('POWE %.2f DB' % p)
        p = yield dev.query('POWE?').addCallback(float)
        p = T.Value(p, 'dBm')
        returnValue(p)
    
    @setting(367, 'Num Points', np=['v'], returns=['v'])
    def num_points(self, c, np=None):
        dev = self.selectedDevice(c)
        if np is not None:
            yield dev.write('POIN %d' % np)
        np = yield dev.query('POIN?').addCallback(float).addCallback(int)
        returnValue(np)
    
__server__ = Agilent_8720ES_Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
