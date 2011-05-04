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
name = DC Rack
version = 1.1
description = Control Fastbias and Preamp boards.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.types import Value
from labrad.devices import DeviceServer, DeviceWrapper
from labrad.server import LabradServer, setting
from labrad.errors import Error
from twisted.internet.defer import inlineCallbacks, returnValue

class NoConnectionError(Error):
    """You need to connect first."""
    code = 2


class DcRackWrapper(DeviceWrapper):

    preAmpState = []
    
    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a compressor device."""
        print 'connecting to "%s" on port "%s"...' % (server.name, port),
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(115200L)
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

    @inlineCallbacks
    def InitDACs(self):
        """Initialize the DACs."""
        yield self.write([196])
        returnValue(196L)
     
    @inlineCallbacks
    def selectCard(self, data):
        """Sends a select card command."""
        yield self.write([long(data&63)])
        returnValue(long(data&63))

    @inlineCallbacks
    def changeHighPassFilter(self, channel, data):
         ID = {'A': 192, 'B': 193, 'C': 194, 'D': 195}[channel]
        if isinstance(data, tuple):
            data = ((data[0] & 7) << 21) | \
                   ((data[1] & 7) << 18) | \
                   ((data[2] & 1) << 17) | \
                    (data[3] & 0xFFFF)
        else:
            data &= 0xFFFFFF
        l = [(data >> 18) & 0x3f | 0x80,
             (data >> 12) & 0x3f | 0x80,
             (data >>  6) & 0x3f | 0x80,
              data        & 0x3f | 0x80,
             ID]
        yield self.write(self.cmdToList(data, ID))
        returnValue(data)

    @inlineCallbacks
    def changeLowPassFilter(self, channel, data):
        """Sends a select card command.
        yield self.write([long(data&63)])
        returnValue(long(data&63))"""

    @inlineCallbacks
    def changePolarityself, channel, data):
        """Sends a select card command.
        yield self.write([long(data&63)])
        returnValue(long(data&63))"""

    @inlineCallbacks
    def changeDCOffset(self, channel, data):
        """Sends a select card command.
        yield self.write([long(data&63)])
        returnValue(long(data&63)) @inlineCallbacks"""

    def changeMonitor(self, command, settings, keys=None):

        if keys is None:
            keys = sorted(settings.keys())

        if command is None:
            returnValue(keys)

        if command not in settings:
            raise Error('Allowed commands: %s.' % ', '.join(keys))

        com = settings[command]
        d = self.write([com])
        return d.addCallback(lambda r: command)
        
        
    @inlineCallbacks
    def changeLEDs(self, data):
        """Sets LED status."""
        if isinstance(data, tuple):
            data = 224 + 4*data[0] + 2*data[1] + 1*data[2]
        else:
            data = 224 + (data & 7)
        yield self.write([data])
        returnValue(data & 7)

    @inlineCallbacks
    def identSelf(self, timeout=Value(1, 's')):
        """Sends an identification command."""
        p = self.packet()
        p.timeout()
        p.read()
        p.write([96L])
        p.timeout(timeout)
        p.read(1, key = 'ID')
        p.timeout()
        p.read(key = 'ID')
        try:
            res = yield p.send()
            returnValue(''.join(res['ID']))
        except:
            raise Exception('Ident error')

class DcRackServer(DeviceServer): 
    deviceName = 'DC Rack Server'
    name = 'DC Rack Server'
    deviceWrapper = DcRackWrapper
	
    @inlineCallbacks
    def initServer(self):
        print 'loading config info...',
        yield self.loadConfigInfo()
        print 'done.'
        yield DeviceServer.initServer(self)

    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.client.registry()
        yield reg.cd(['', 'Servers', 'DC Rack', 'Links'], True)
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
        for name, (server, port) in self.serialLinks.items():
            if server not in self.client.servers:
                continue
            server = self.client[server]
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s - %s' % (server, port)
            devs += [(name, (server, port))]
        returnValue(devs)

    
    @setting(20, 'Select Card', data='w', returns='w')
    def select_card(self, c, data):
        """Sends a select card command."""
        dev = self.selectedDevice(c)
        yield dev.selectCard(data)
        returnValue(long(data&63))

    @setting(70, 'Init DACs', returns='w')
    def Init_DACs(self, c):
        """Initialize the DACs."""
        dev = self.selectedDevice(c)
        init = yield dev.InitDACs()
        returnValue(init)

    @setting(60, 'Change High Pass Filter', data = 'w', returns='w')
    def change_high_pass_filter(self, c, data):
        dev = self.selectedDevice(c)
        yield dev.changeHighPassFilter(data)

    @setting(34, 'Change Low Pass Filter', data = 'w', returns='w')
    def change_low_pass_filter(self, c, data):
        dev = self.selectedDevice(c)
        yield dev.changeLowPassFilter(data)

    @setting(400, 'Change Polarity', data = 'w', returns='w')
    def change_polarity(self, c, data):
        dev = self.selectedDevice(c)
        yield dev.changePolarity(data)

    @setting(100, 'Change DC Offset', data = 'w', returns='w')
    def change_dc_offset(self, c, data):
        dev = self.selectedDevice(c)
        yield dev.changeDCOffset(data)

    @setting(130, 'change monitor', ID = 'w', command = 's', returns='s')
    def change_monitor(self, c, ID, command=None):
        dev = self.selectedDevice(c)
        settings = [{'A0': 80L, 'B0': 81L, 'C0': 82L, 'D0': 83L},
                    {'A1': 88L, 'B1': 89L, 'C1': 90L, 'D1': 91L},
                    {'trigA':  64L, 'trigB': 65L, 'trigC':  66L, 'trigD': 67L,
                     'foin1':  64L, 'foin2': 65L, 'foin3':  66L, 'foin4': 67L,
                     'dadata': 68L, 'done':  69L, 'strobe': 70L, 'clk': 71L,
                     'on1': 68L, 'on2':  69L, 'on3': 70L, 'on4': 71L},
                    {'FOoutA': 72L, 'FOoutB':  73L, 'FOoutC': 74L, 'FOoutD':  75L,
                     'Pbus0': 72L, 'clk':  73L, 'clockon': 74L, 'cardsel':  75L,
                     'dasyn':  76L, 'cardsel': 77L, 'Pbus0':  78L, 'Clockon': 79L
                     'clk1':  76L, 'clk2': 77L, 'clk3':  78L, 'clk4': 79L}][ID]
        return dev.changeMonitor(command, settings)
        
    @setting(336, 'LEDs',
                 data=['w: Lowest 3 bits: LED flags',
                       '(bbb): Status of BP LED, FP FOout flash, FP Reg. Load Flash'],
                 returns='w')
    def LEDs(self, c, data):
        """Sets LED status."""
        dev = self.selectedDevice(c)
        p = yield dev.changeLEDs(data)
        returnValue(p)


    @setting(893, 'Ident',
                 timeout=[': Use a read timeout of 1s',
                          'v[s]: Use this read timeout'],
                 returns='s')
    def ident(self, c):
        dev = self.selectedDevice(c)
        ident = dev.identSelf()
        returnValue(ident)


class preamp()
    def __init__():
        self.channels = [[[0,0,0,0]],[[0,0,0,0]],[[0,0,0,0]],[[0,0,0,0]]]

    def updateHP(ID, hp):
        self.channels[ID][0]=hp
        
    def updateLP(ID, lp):
        self.channels[ID][1]=lp
        
    def updatePol(ID, pol):
        self.channels[ID][2]=pol
        
    def updateOff(ID, off):
        self.channels[ID][3]=off
        

class monitor()
    def __init__():
        self.dBus0 = 'state'
        self.dBus1 = 'state'
        self.aBus0 = 'state'
        self.abus1 = 'state'

    def updateDBus0(newState):
        self.dBus0 = newState

    def updateDBus1(newState):
        self.dBus1 = newState

    def updateABus0(newState):
        self.aBus0 = newState

    def updateABus1(newState):
        self.aBus1 = newState

        
TIMEOUT = 1

__server__ = DcRackServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
