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


# note: every time the communication with the arduino, it resets.
# this means it loses its memory of the state (open/closed).
# to avoid this, open serialwin32.py, and change
#   self._dtrState = win32file.RTS_CONTROL_ENSABLE
# to
#   self._dtrState = win32file.RTS_CONTROL_DISABLE
# (this was line 63 in my copy.)
# then delete the pyc and pyo files and restart the serial server.

# documentation below copied from the arduino sketch.

# ---PINOUT---
# Arduino  Heat Switch Box  purpose
# 2        1                interrupt to detect switch opening
# 3        3                interrupt to detect switch closing
# 4        2                open control pin
# 5        9                close control
# 6        4                4K - 1K touch detector
# 7        7                1K - 50mK touch
# 8        6                4K - 50mK touch
# GND      11               signal ground
# (before wiring, double check that the heat switch pin functions are correct)

# ---PROTOCOL---
# We communicate with the computer over serial.
# Commands end with \n, \r is ignored.
# Timeout = 1 second.

# Command    Response
# *IDN?      MARTINISGROUP,HEATSWITCH,[version]
# STATUS?    [0,1,2] for [unknown, open, closed]
# TOUCH? n   [0, 1] for [touch, no touch] for n=[1,2,3]->[4K-1K, 1K-50mK, 4k-50mK]
#            Returns E for n != [1,2,3]
# OPEN!      open the heat switch
# CLOSE!     close the heat switch



"""
### BEGIN NODE INFO
[info]
name = Heat Switch Arduino
version = 1.0
description = Heat switch for the ADR, Arduino style.

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
        p.baudrate(9600)
        p.read() # clear out the read buffer
        p.timeout(TIMEOUT)
        yield p.send()
        # now check to make sure we have a heat switch
        idn = yield self.query("*IDN?")
        #self.sketch_version = idn.split(',')[2]
        #print idn
        #idn = idn.split(',')
        #if idn[1] != 'HEATSWITCH':
        #    print "ERROR: Heat switch not responding to *IDN? correctly!"
        #    self.shutdown()
        
        #print 'heatswitch version %s' % idn[2]

    def packet(self):
        """Create a packet in our private context."""
        return self.server.packet(context=self.ctx)
    
    def shutdown(self):
        """Disconnect from the serial port when we shut down."""
        return self.packet().close().send()

    @inlineCallbacks
    def write(self, code):
        """Write a data value to the heat switch."""
        yield self.packet().write_line(code).send()
        
    @inlineCallbacks
    def query(self, code):
        ''' Write, then read. '''
        p = self.packet()
        p.write_line(code)
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

class HeatSwitchServer(DeviceServer):
    name = 'Heat Switch Arduino'
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
        yield dev.write('OPEN!')

    @setting(200, 'Close', returns='')
    def close_heat_switch(self, c):
        """Closes the heat switch."""
        dev = self.selectedDevice(c)
        yield dev.write('CLOSE!')
        
    @setting(300, 'Status', returns='i: 0=Unknown, 1=Open, 2=Closed')
    def status(self, c):
        ''' Get open/closed status of heat switch. '''
        dev = self.selectedDevice(c)
        ans = yield dev.query('STATUS?')
        returnValue(int(ans))
    
    @setting(400, 'Touch', which='i: 1=4K-1K, 2=1K-50mK, 3=4K-50mK', returns='b')
    def touch(self, c, which):
        ''' Check for touch between two stages. '''
        if which != 1 and which != 2 and which != 3:
            raise ValueError('Argument to heat-switch "touch" setting must be 1, 2 or 3.')
        dev = self.selectedDevice(c)
        ans = yield dev.query('TOUCH? %s' % which)
        returnValue(bool(int(ans)))
        
    @setting(500, 'Sketch Version', returns='i')
    def sketch_version(self, c):
        ''' Get version number of sketch on Arduino. '''
        dev = self.selectedDevice(c)
        ans = yield dev.query('*IDN?')
        returnValue(int(ans.split(',')[2]))


TIMEOUT = 1.0 # serial read timeout

#####
# Create a server instance and run it

__server__ = HeatSwitchServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)

