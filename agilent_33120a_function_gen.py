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
### END NODE INFO
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
    
    @setting(11)
    def clear(self, c):
        """Clears status byte summary and event registers

        """
        dev = self.selectedDevice(c)
        dev.write('*CLS')

      
    @setting(12, val='s', returns='v[Ohm]')
    def load_impedance(self, c, val='50'):
        """Gets and sets the loading impedance
        
        Args: 
           val (str): The loading impedance.
                Allowed values are '50' or 'INF'
        """

        dev = self.selectedDevice(c)
        if val is not None:
            allowed = ['50', 'INF']
            if val not in allowed:
                raise Exception('allowed settings are: %s' % allowed)
            dev.write('OUTP:LOAD {}'.format(val))
        status = yield dev.query('OUTP:LOAD?')
        returnValue(float(status)*U.Ohm)


    @setting(13, val='v[V]', returns='v[V]')
    def dc_voltage(self, c, val=None):
        """Gets or sets DC offset voltage.
        
        Args: 
            val (value[V]): The DC Voltage to be set if None
                queries the DC Voltage
        Returns:
            (val): The DC offset
        """

        dev = self.selectedDevice(c)
        if val is not None:
            if val < -5*U.V or val > 5*U.V:
                raise Exception(
                        'Signal Generator only puts ' +
                        'out -5 to 5 volts in DC Voltage')

            dev.write('VOLT:OFFS {}'.format(val['V']))

        status = yield dev.query('APPL?')
        returnValue(self.parse_status_string(status)['offset'])


    @setting(14, val='v[V]', returns='v[V]')
    def ac_voltage(self, c, val=None):
        """Gets or sets AC mode peak to peak voltage.
        
        Args: 
            val (value[V]): The AC Voltage to be set,
            If None query the AC-Voltage.

        Returns:
            (val): The AC Voltage Amplitude
        """

        dev = self.selectedDevice(c)
        if val is not None:
            dev.write('SOUR:VOLT {}'.format(val['V']))
        status = yield dev.query('APPL?')
        returnValue (self.parse_status_string(status)['amplitude'])

    
    @setting(15, val='v[Hz]', returns='v[Hz]')
    def frequency(self, c, val=None):
        """Gets or sets AC mode frequency
        
        Args: 
            val (value[Hz]): The frequency to be set,
             if None query the frequency.

        Returns:
            (val):  The waveform frequency
        """

        dev = self.selectedDevice(c)
        if val is not None:
            dev.write('SOUR:FREQ {}'.format(val['Hz']))
        status = yield dev.query('APPL?')
        returnValue(self.parse_status_string(status)['frequency'])


    @setting(16, val='s', returns='s')
    def waveform(self, c, val=None):
        """Gets or sets waveform type.

        Args:
            val (str): The output waveform type allowed values are:
                'SINusoid','SQUare','TRIangle' (Max frequency .1 MHz),
                'RAMP','NOISe'
        Returns:
            (str):  The output waveform type
        """

        dev = self.selectedDevice(c)
        if val is not None:
            dev.write('FUNC:SHAP {}'.format(val))
        status = yield dev.query('APPL?')

        returnValue(self.parse_status_string(status)['waveform'])


    @setting(17)
    def output_off(self, c):
        """Sets output to be 'Off' by changing to DC mode and setting
            DC voltage to 0 V.

        Args:
            val (str): The output.
        Returns:
            (str):  The output.
        """

        dev = self.selectedDevice(c)
        dev.write('FUNC:SHAP DC')
        dev.write('VOLT:OFFS 0')


    def parse_status_string(self, status_string):
        """Parses the status string from Agilent33120A

        Args:
            val(str):  The string resulting from APPL? command

        Returns:
            (str):  The current waveform type
            (val):  The frequency of that waveform
            (val):  The amplitude of that waveform
            (val):  The dc offset for that waveform.
        """

        status_string = status_string[1:-1]
        waveform = status_string[:4].strip(' ')
        [frequency, amplitude, offset] = status_string[4:].split(',')
        status = {'waveform': waveform,
                  'frequency': float(frequency)*U.Hz,
                  'amplitude': float(amplitude)*U.V,
                  'offset': float(offset)*U.V}

        return status

__server__ = AgilentFunctionGenerator()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
