# Copyright (C) 2008  Matthew Neeley
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

from labrad.server import LabradServer, setting
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.reactor import callLater
from twisted.internet.task import LoopingCall

from pyvisa import visa, vpp43

"""
### BEGIN NODE INFO
[info]
name = SR830
version = 1.1
description = Gives access to GPIB devices via pyvisa.
instancename = %LABRADNODE% GPIB Bus

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

class GPIBBusServer(LabradServer):
    """Provides direct access to GPIB-enabled devices."""
    name = 'SR830'

    refreshInterval = 10
    defaultTimeout = 1.0

    def initServer(self):
        self.devices = {}
        # start refreshing only after we have started serving
        # this ensures that we are added to the list of available
        # servers before we start sending messages
        callLater(0.1, self.startRefreshing)

    def startRefreshing(self):
        """Start periodically refreshing the list of devices.

        The start call returns a deferred which we save for later.
        When the refresh loop is shutdown, we will wait for this
        deferred to fire to indicate that it has terminated.
        """
        self.refresher = LoopingCall(self.refreshDevices)
        self.refresherDone = self.refresher.start(self.refreshInterval, now=True)
        
    @inlineCallbacks
    def stopServer(self):
        """Kill the device refresh loop and wait for it to terminate."""
        if hasattr(self, 'refresher'):
            self.refresher.stop()
            yield self.refresherDone
        
    def refreshDevices(self):
        """Refresh the list of known devices on this bus.

        Currently supported are GPIB devices and GPIB over USB.
        """
        try:
            addresses = visa.get_instruments_list()
            additions = set(addresses) - set(self.devices.keys())
            deletions = set(self.devices.keys()) - set(addresses)
            for addr in additions:
                try:
                    if addr.startswith('GPIB'):
                        instName = addr
                    elif addr.startswith('USB'):
                        instName = addr + '::INSTR'
                    else:
                        continue
                    instr = visa.instrument(instName, timeout=1.0)
                    instr.clear()
                    self.devices[addr] = instr
                    self.sendDeviceMessage('GPIB Device Connect', addr)
                except Exception, e:
                    print 'Failed to add ' + addr + ':' + str(e)
            for addr in deletions:
                del self.devices[addr]
                self.sendDeviceMessage('GPIB Device Disconnect', addr)
        except Exception, e:
            print 'Problem while refreshing devices:', str(e)
            
    def sendDeviceMessage(self, msg, addr):
        print msg + ': ' + addr
        self.client.manager.send_named_message(msg, (self.name, addr))
            
    def initContext(self, c):
        c['timeout'] = self.defaultTimeout

    def getDevice(self, c):
        if c['addr'] not in self.devices:
            raise Exception('Could not find device ' + c['addr'])
        instr = self.devices[c['addr']]
        instr.timeout = c['timeout']
        return instr
        
    @setting(0, addr='s', returns='s')
    def address(self, c, addr=None):
        """Get or set the GPIB address for this context.

        To get the addresses of available devices,
        use the list_devices function.
        """
        if addr is not None:
            c['addr'] = addr
        return c['addr']

    @setting(2, time='v[s]', returns='v[s]')
    def timeout(self, c, time=None):
        """Get or set the GPIB timeout."""
        if time is not None:
            c['timeout'] = time
        return c['timeout'] 

    @setting(3, data='s', returns='')
    def write(self, c, data):
        """Write a string to the GPIB bus."""
        self.getDevice(c).write(data)

    @setting(4, bytes='w', returns='s')
    def read(self, c, bytes=None):
        """Read from the GPIB bus.

        If specified, reads only the given number of bytes.
        Otherwise, reads until the device stops sending.
        """
        instr = self.getDevice(c)
        if bytes is None:
            ans = instr.read()
        else:
            ans = vpp43.read(instr.vi, bytes)
        return ans

    @setting(5, data='s', returns='s')
    def query(self, c, data):
        """Make a GPIB query, a write followed by a read.

        This query is atomic.  No other communication to the
        device will occur while the query is in progress.
        """
        instr = self.getDevice(c)
        instr.write(data)
        ans = instr.read()
        return ans

    @setting(20, returns='*s')
    def list_devices(self, c):
        """Get a list of devices on this bus."""
        return sorted(self.devices.keys())

#SR830 settings		
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
        """If the argument is empty, e.g. reference(''), the reference source is queried.
        
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
        """If the argument is empty, e.g. frequency(''), the frequency is queried.

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
        """If the argument is empty, e.g. ExtRefSlope(''), the external reference slope is queried.

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
        """If the argument is empty, e.g. harmonic(''), the harmonic is queried.

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
        """If the argument is empty, e.g. sinoutamp(''), the amplitude of sin out is queried.

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

        Syntax: setauxout('i ')
        """
        instr = self.getDevice(c)
        instr.write('AUXV ' + data)
        returnValue('Auxilary ouput setting: ' + data) 		

    @setting(22, 'xyrt', data='s', returns='s')
    def xyrt(self, c, data):
        """Query the value of X (1), Y (2), R(3), or Theta (4)

        For example, xyrt('4')
        """
        instr = self.getDevice(c)
        instr.write('OUTP? ' + data)
        resp = yield instr.read()
        returnValue(resp)   			
		

__server__ = GPIBBusServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
