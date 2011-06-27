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
name = SR830
version = 2.0
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
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import inlineCallbacks, returnValue

class SR830(GPIBManagedServer):
    name = 'SR830'
    deviceName = 'Stanford_Research_Systems SR830'


    @setting(12, 'Phase', data='s', returns='s')
    def phase(self, c, data):
        """If the argument is empty, e.g. phase(''), the phase shift is queried.

        Otherwise, the phase will be set to the value of the argument.
        """
        if data == '':
            instr = self.getDevice(c)
            instr.write('PHAS?')
            resp = yield instr.read()
            returnValue(resp)    	
        else:
            instr = self.getDevice(c)
            instr.write('PHAS ' + data)
            returnValue('Reference phase set to ' + data + ' degrees.')
			
    @setting(13, 'Reference', data='s', returns='s')
    def reference(self, c, data):
        """
        If the argument is empty, e.g. reference(''), the reference source is queried.

        Otherwise, the reference source will be set to the value of the argument.

        0 = External, 1 = Internal
        """
        if data == '':
            instr = self.getDevice(c)
            instr.write('FMOD?')
            resp = yield instr.read()
            returnValue(resp)    	
        else:
            instr = self.getDevice(c)
            instr.write('FMOD ' + data)
            returnValue('Reference set to ' + data + '.')   

    @setting(14, 'Frequency', data='s', returns='s')
    def frequency(self, c, data):
        """
        If the argument is empty, e.g. frequency(''), the frequency is queried.

        Otherwise, the frequency will be set to the value of the argument.

        Set only in internal reference mode.
        """
        if data == '':
            instr = self.getDevice(c)
            instr.write('FREQ?')
            resp = yield instr.read()
            returnValue(resp)    	
        else:
            instr = self.getDevice(c)
            instr.write('FREQ ' + data)
            returnValue('Frequency set to ' + data + ' Hz.')	

    @setting(15, 'ExtRefSlope', data='s', returns='s')
    def extrefslope(self, c, data):
        """
        If the argument is empty, e.g. ExtRefSlope(''), the external reference slope is queried.

        Otherwise, the external reference slope will be set to the value of the argument.

        0 = Sine, 1 = TTL Rising, 2 = TTL Falling
        """
        if data == '':
            instr = self.getDevice(c)
            instr.write('RSLP?')
            resp = yield instr.read()
            returnValue(resp)    	
        else:
            instr = self.getDevice(c)
            instr.write('RSLP ' + data)
            returnValue('External reference slope set to ' + data + '.')			
			
    @setting(16, 'Harmonic', data='s', returns='s')
    def harmonic(self, c, data):
        """
        If the argument is empty, e.g. harmonic(''), the harmonic is queried. 

        Otherwise, the harmonic will be set to the value of the argument. 

        Harmonic can be set as high as 19999 but is capped at a frequency of 102kHz.
        """
        if data == '':
            instr = self.getDevice(c)
            instr.write('HARM?')
            resp = yield instr.read()
            returnValue(resp)    	
        else:
            instr = self.getDevice(c)
            instr.write('HARM ' + data)
            returnValue('Harmonic set to ' + data + '.')	

    @setting(17, 'SinOutAmp', data='s', returns='s')
    def sinoutamp(self, c, data):
        """
        If the argument is empty, e.g. sinoutamp(''), the amplitude of sin out is queried. 

        Otherwise, the amplitude will be set to the value of the argument. 

        Accepts values between .004 and 5.0 Vrms
        """
        if data == '':
            instr = self.getDevice(c)
            instr.write('SLVL?')
            resp = yield instr.read()
            returnValue(resp)    	
        else:
            instr = self.getDevice(c)
            instr.write('SLVL ' + data)
            returnValue('Sin output amplitude set to ' + data + ' Vrms.')		

    @setting(18, 'AuxInput', data='s', returns='s')
    def auxinput(self, c, data):
        """Query the value of Aux Input i (1,2,3,4)

        For example, auxinput('3')
        """
        instr = self.getDevice(c)
        instr.write('OAUX? ' + data)
        resp = yield instr.read()
        returnValue(resp)    	
		
    @setting(19, 'QueryAuxOut', data='s', returns='s')
    def queryauxout(self, c, data):
        """Query the value of Aux Output i (1,2,3,4)

        For example, queryauxout('3')
        """
        instr = self.getDevice(c)
        instr.write('AUXV? ' + data)
        resp = yield instr.read()
        returnValue(resp)   	
		
    @setting(21, 'SetAuxOut', data='s', returns='s')
    def setauxout(self, c, data):
        """setauxout('i, x') will set the value of Aux Output i (1,2,3,4) to x

        Where x is between -10.5 V to 10.5 V
        """
        instr = self.getDevice(c)
        instr.write('AUXV ' + data)
        returnValue('Auxilary ouput setting: ' + data) 		

    @setting(22, 'xyrt', data='s', returns='s')
    def xyrt(self, c, data):
        """Query the value of X (1), Y (2), R (3), or Theta (4)

        For example, xyrt('4')
        """
        instr = self.getDevice(c)
        instr.write('OUTP? ' + data)
        resp = yield instr.read()
        returnValue(resp)   	

__server__ = SR830()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
