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
#
# Written August 9, 2010 by Nate Earnest

"""
### BEGIN NODE INFO
[info]
name = Agilent 33120a generator
version = 1.0
description = Controls Agilent 33120a function generator

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO:b
"""

from labrad import types as T, errors
from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from struct import unpack
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.units import Unit, Value, V
import labrad.units as U

class AgilentFunctionGenerator(GPIBManagedServer):
    name = 'Agilent 33120a generator'
    deviceName = 'HEWLETT-PACKARD 33120A'
    
    @setting(11, 'clear')      
    def clear(self, c):
        """Clears status byte summary and event registers

        """

        dev = self.selectedDevice(c)
        dev.write('*CLS')
      
    @setting(12, 'set impedance', val='s', returns='')      
    def set_impedance(self, c, val = '50'):
        """Sets the loading impedance
        
        args: 
           val (str): The loading impedance
        """

        allowed = ['50', 'INF']
        if setting not in allowed:
            raise Exception('allowed settings are: %s' % allowed)
        dev = self.selectedDevice(c)
        dev.write('OUTP:LOAD {}'.format(val))

    @setting(13,'Set DC voltage', val='v[V]', returns='')
    def set_dc_voltage(self, c,val=0*V):
        """Puts generator into DC mode with given voltage.
        
        args: 
            val (value[V]): The DC Voltage to be set

        """
        if val< -5*U.V or val > 5*U.V:
            raise Exception(
                    'Signal Gnerator only puts out -5 to 5 volts in DC Voltage')
        dev = self.selectedDevice(c)
        dev.write('APPL:DC')
        dev.write('VOLT:OFFS {}'.format(val['V']))
    
    @setting(14, 'set AC voltage', val='v[V]', returns='')      
    def set_ac_voltage(self, c, val = '1*U.V'):
        """Puts generator into AC mode with given peak to peak voltage.
        
        args: 
            val (value[V]): The AC Voltage to be set
        """

        dev = self.selectedDevice(c)
        dev.write('APPL:SIN')
        dev.write('SOUR:VOLT {}'.format(val['V']))
    
    @setting(15, 'set frequency', val='v[Hz]', returns='')      
    def set_frequency(self, c, val = '100*U.Hz'):
        """Puts generator into AC mode with given frequency
        
        args: 
            val (value[Hz]): The frequency to be set
        """
        dev = self.selectedDevice(c)
        dev.write('APPL:SIN')
        dev.write('SOUR:FREQ {}'.format(val['Hz']))



__server__ = AgilentFunctionGenerator()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)



