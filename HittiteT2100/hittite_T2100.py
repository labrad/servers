# Copyright (C) 2007  Yu Chen
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
name = Hittite T2100 Server
version = 1.0
description = Microwave function generator

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

class HittiteWrapper(GPIBDeviceWrapper):
	@inlineCallbacks
	def initialize(self):
		self.frequency = yield self.getFrequency()
		self.amplitude = yield self.getAmplitude()
		self.output = yield self.getOutput()
		self.status = yield self.getStatus()

	@inlineCallbacks
	def getOutput(self):
		self.output  = yield self.query('OUTP:STAT?')#.addCallback(bool)
		returnValue(self.output)
	 
	@inlineCallbacks 
	def getFrequency(self):
		self.frequency = yield self.query('SOUR:FREQ?')#.addCallback(float)
		returnValue(self.frequency)

	@inlineCallbacks
	def getAmplitude(self):
		self.amplitude = yield self.query('SOUR:POW:LEV:AMPL?')#.addCallback(float)
		returnValue(self.amplitude)

	@inlineCallbacks
	def getStatus(self):
		self.status = yield self.query('*STB?')#.addCallback(float)
		returnValue(self.status)
        
	@inlineCallbacks
	def setFrequency(self, f):
		f = f['Hz']
		if self.frequency != f:
			yield self.write('SOUR:FREQ:FIX %f' % f)
			self.frequency = f
	
	@inlineCallbacks
	def setAmplitude(self, a):
		a = a['dBm']
		if self.amplitude != a:
			yield self.write('SOUR:POW:LEV:IMM:AMPL %f' % a)
			self.amplitude = a

	@inlineCallbacks
	def setOutput(self, out):
		if self.output != out:
			yield self.write('OUTP:STAT %d' % int(out))
			self.output = out
			

class HittiteServer(GPIBManagedServer):
	"""ADD DOCUMENT STRING"""
	name = 'Hittite T2100 Server'
	deviceName = 'Hittite HMC-T2100'
	deviceWrapper = HittiteWrapper

	@setting(10, 'Frequency', f=['v[Hz]'], returns=['v[Hz]'])
	def frequency(self, c, f=None):
		"""Get or set the CW frequency."""
		dev = self.selectedDevice(c)
		if f is not None:
			yield dev.setFrequency(f)
		returnValue(dev.frequency)

	@setting(11, 'Amplitude', a=['v[dBm]'], returns=['v[dBm]'])
	def amplitude(self, c, a=None):
		"""Get or set the CW amplitude."""
		dev = self.selectedDevice(c)
		if a is not None:
			yield dev.setAmplitude(a)
		returnValue(dev.amplitude)

	@setting(12, 'Output', os=['b'], returns=['b'])
	def output_state(self, c, os=None):
		"""Get or set the output status."""
		dev = self.selectedDevice(c)
		if os is not None:
			yield dev.setOutput(os)
		returnValue(dev.output == 1)
        
	@setting(13, 'Status', returns=['i'])
	def status(self, c):
		"""Get the status byte."""
		dev = self.selectedDevice(c)
		byte = yield dev.status
		returnValue(int(byte))
        
__server__ = HittiteServer()

if __name__ == '__main__':
	from labrad import util
	util.runServer(__server__)
