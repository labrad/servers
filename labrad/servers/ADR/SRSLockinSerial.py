# Copyright (C) 2013 Ted White
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
name = SRS lockin Serial
version = 1.0
description = Brooks adding serial communication

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
from labrad.devices import DeviceServer, DeviceWrapper
from labrad.gpib import GPIBManagedServer
from struct import unpack
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad import util
from labrad.units import V

__QUERY__ = """\
:FORM INT,32
:FORM:BORD NORM
:TRAC? TRACE%s"""

class SRSLockinWrapper(DeviceWrapper):
   
    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a SIM900."""
        print 'connecting to "%s" on port "%s"...' % (server.name, port)
        self.setTrace = []
        self.resetTrace = []
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(9600L)
        p.stopbits(1L)
        p.bytesize(8L)
        p.parity('N')
        p.read() # clear out the read buffer
        p.timeout(TIMEOUT)
        yield p.send()
        print 'done.'
        
    def packet(self):
        """Create a packet in our private context."""
        return self.server.packet(context=self.ctx)
    
    def shutdown(self):
        """Disconnect from the serial port when we shut down."""
        return self.packet().close().send()
    
    @inlineCallbacks
    def write(self, code, index = 0):
        """Write a data value to the SIM900."""
        p = self.packet()
        p.write(code)
        yield p.send()
        
        
    @inlineCallbacks
    def res(self, input):
        """Send a set command to the SIM900 and check
           the current output to see that it set"""
        p = self.packet()
        p.write(input)
        p.write("TERM LF\n")
        p.write("RVAL?\n")
        p.read_line()
        ans = yield p.send()
        output = ans.read_line
        returnValue(output)
    
    @inlineCallbacks
    def disconnect(self):
        """Send a set command to the SIM900 and check
           the current output to see that it set"""
        p = self.packet()
        p.write("xyz")
        yield p.send()
        
 
class SRSLockinServer(DeviceServer):
    deviceName = ['Stanford_Research_Systems SIM900']
    name = 'SRS lockin Serial'
    deviceWrapper = SRSLockinWrapper
    
    @inlineCallbacks
    def initServer(self):
        print 'loading config info...',
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print 'done.'
        yield DeviceServer.initServer(self)
    
    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.reg
        yield reg.cd(['', 'Servers', 'SRSLockin', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        for k in keys:
            p.get(k, key=k)
        ans = yield p.send()
        self.serialLinks = dict((k, ans[k]) for k in keys)
    
    @inlineCallbacks    
    def findDevices(self):
        """Find available devices from list stored in the registry."""
        devs = []
        for name, (serServer, port) in self.serialLinks.items():
            if serServer not in self.client.servers:
                continue
            server = self.client[serServer]
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s - %s' % (serServer, port)
            devs += [(devName, (server, port))]
        returnValue(devs)
         
    @setting(21, 'r', returns=['v[V] {Peak Amplitude}'])
    def r(self, c, data = "CONN 7, 'xyz'\n"):
        """Gets the current amplitude from the peak detector"""
        dev = self.selectedDevice(c)
        data = yield dev.res(data)
        yield dev.disconnect()
        data = float(data)*V
        returnValue(data)
        
    # @setting(22 , 'write','s', returns = 's')
    # def write(self, c, data):
        # """Gets the current amplitude from the peak detector"""
        # dev = self.selectedDevice(c)
        # yield dev.write("CONN 7, 'xyz'\n")
        yield dev.write("TERM LF\n")
        # data =  yield dev.query("RVAL?\n")
        # value = float(data)*V
        # yield dev.write("xyz")
        # print value
        # returnValue(value)
		
    @setting(25, 'auto sensitivity')
    def auto_sensitivity(self, c):
       pass   
    

TIMEOUT = 1
__server__ = SRSLockinServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
