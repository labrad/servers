# Copyright (C) 2010  Michael Lenander
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
name = Heat Switch
version = 1.0
description = Heat switch for the ADR.

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

# registry (for info about where to connect)
# Servers -> CP2800 Compressor
# -> Serial Links = [(server, port),...]
# -> Logs -> <deviceName> -> YYYY -> MM -> DD ->

# data vault (for logging of numerical data)
# Logs -> CP2800 Compressor -> <deviceName> -> {YYYY} -> {MM} -> {DD} ->
#      -> Vince -> {YYYY} -> {MM} -> {DD} ->
#      -> Jules -> {YYYY} -> {MM} -> {DD} ->

class HeatSwitchDevice(DeviceWrapper):
    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a heat switch device."""
        print 'connecting to "%s" on port "%s"...' % (server.name, port),
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(2400)
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
        """Write a data value to the heat switch."""
        yield self.packet().write(code).send()

    def open(self):
        return self.write('CODEO')

    def close(self):
        return self.write('CODEC')

class HeatSwitchServer(DeviceServer):
    name = 'Heat Switch'
    deviceWrapper = HeatSwitchDevice

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
        p.cd(['', 'Servers', 'Heat Switch'], True)
        p.get('Serial Links', '*(ss)', key='links')
        ans = yield p.send()
        self.serialLinks = ans['links']

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
    
    @setting(100, 'Open', returns='')
    def open_heat_switch(self, c):
        """Opens the heat switch."""
        dev = self.selectedDevice(c)
        yield dev.open()

    @setting(200, 'Close', returns='')
    def close_heat_switch(self, c):
        """Closes the heat switch."""
        dev = self.selectedDevice(c)
        yield dev.close()


#####
# Create a server instance and run it

__server__ = HeatSwitchServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)

