# Copyright (C) 2010  Michael Lenander & Julian Kelly
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
name = RF Mux
version = 1.0.0
description = RF Mux for the DR lab

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad.devices import DeviceServer, DeviceWrapper
from labrad.server import setting, inlineCallbacks, returnValue

class RFMuxDevice(DeviceWrapper):
    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a RF Mux device."""
        print 'connecting to "%s" on port "%s"...' % (server.name, port),
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(9600)
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
    def write(self, code, index=0):
        """Write a data value to the RF Mux."""
        yield self.packet().write(code).send()

    def get_channel(self):
        self.write('?')
        read_chan = self.read()
        return ord(val) - ord('A') # queries received from RF Mux are in ASCII, channel 0 = 'A', channel 1 = 'B' etc

    def set_channel(self, channel):
        set_chan = chr(channel + ord('A'))
        return self.write('CODEC') # queries sent to RF Mux are in ASCII, channel 0 = 'A', channel 1 = 'B' etc

class RFMuxServer(DeviceServer):
    name = 'RF Mux'
    deviceWrapper = RFMuxDevice

    @inlineCallbacks
    def initServer(self):
        print 'loading config info...',
        yield self.loadConfigInfo()
        print 'done.'
        yield DeviceServer.initServer(self)

    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.client.registry
        p = reg.packet()
        p.cd(['', 'Servers', 'RF Mux'], True)
        p.get('Serial Links', '*(ss)', key='links')
        ans = yield p.send()
        self.serialLinks = ans['links']
        print ans['links']

    @inlineCallbacks
    def findDevices(self):
        """Find available devices from list stored in the registry."""
        devs = []
        for name, port in self.serialLinks:
            if name not in self.client.servers:
                continue
            server = self.client[name]
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s - %s' % (name, port)
            devs += [(devName, (server, port))]
        returnValue(devs)
    
    @setting(100, 'get_channel', returns='w')
    def get_channel(self, c):
        """Gets current RF Mux Channel."""
        dev = self.selectedDevice(c)
        yield dev.get_channel()

    @setting(200, 'set_channel', channel = 'w', returns='')
    def set_channel(self, c, channel):
        """Sets RF Mux channel."""
        dev = self.selectedDevice(c)
        yield dev.set_channel(channel)


TIMEOUT = 1 # serial read timeout

#####
# Create a server instance and run it

__server__ = RFMuxServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)

