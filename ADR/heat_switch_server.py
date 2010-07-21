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
    

# compressor control protocol
STX = 0x02
ESC = 0x07
ADDR = 0x10
CR = ord('\r')
CMD_RSP = 0x80
RESP_LEN = 14 # 3 bytes SMDP header, 8 bytes data, 2 bytes checksum, CR
TIMEOUT = 1 # serial read timeout

# codes for compressor variables
HASHCODES = {
    # misc
    'CODE_SUM': 0x2B0D, # Firmware checksum
    'MEM_LOSS': 0x801A, # TRUE if nonvolatile memory was lost
    'CPU_TEMP': 0x3574, # CPU temperature (0.1 C)
    'BATT_OK': 0xA37A, # TRUE if clock OK
    'BATT_LOW': 0x0B8B, # TRUE if clock battery low
    'COMP_MINUTES': 0x454C, # Elapsed compressor minutes
    'MOTOR_CURR_A': 0x638B, # Compressor motor current draw, in Amps

    # temperatures
    'TEMP_TNTH_DEG': 0x0D8F, # temperatures (0.1 C)
    'TEMP_TNTH_DEG_MINS': 0x6E58, # minimum temps seen (0.1 C)
    'TEMP_TNTH_DEG_MAXES': 0x8A1C, # maximum temps seen (0.1 C)
    'TEMP_ERR_ANY': 0x6E2D, # TRUE if any temperature sensor has failed

    # pressures
    'PRES_TNTH_PSI': 0xAA50, # low/high side pressures (0.1 PSIA)
    'PRES_TNTH_PSI_MINS': 0x5E0B, # minimum pressures seen (0.1 PSIA)
    'PRES_TNTH_PSI_MAXES': 0x7A62, # maximum pressures seen (0.1 PSIA)
    'PRES_ERR_ANY': 0xF82B, # TRUE if any pressure sensor has failed
    'H_ALP': 0xBB94, # average low-side pressure (0.1 PSIA)
    'H_AHP': 0x7E90, # average high-side pressure (0.1 PSIA)
    'H_ADP': 0x319C, # average delta pressure (0.1 PSIA)
    'H_DPAC': 0x66FA, # 1st deriv. of high side pressure, "bounce" (0.1 PSIA)

    'CLR_TEMP_PRES_MMMARKERS': 0xD3DB, # reset pres/temp min/max markers

    # compressor control and status
    'EV_START_COMP_REM': 0xD501, # start compressor
    'EV_STOP_COMP_REM': 0xC598, # stop compressor
    'COMP_ON': 0x5F95, # TRUE if compressor is on
    'ERR_CODE_STATUS': 0x65A4, # non-zero value indicates an error code
    }

READABLE = [
    'CPU_TEMP',
    'TEMP_TNTH_DEG',
    'TEMP_TNTH_DEG_MINS',
    'TEMP_TNTH_DEG_MAXES',
    'PRES_TNTH_PSI',
    'PRES_TNTH_PSI_MINS',
    'PRES_TNTH_PSI_MAXES',
    'H_ALP',
    'H_AHP',
    'H_ADP',
    'COMP_ON',
    'COMP_MINUTES',
    'MOTOR_CURR_A',
    ]

WRITEABLE = [
    'EV_START_COMP_REM',
    'EV_STOP_COMP_REM',
    'CLR_TEMP_PRES_MMMARKERS',
    ]

#####
# SMDP functions (Sycon Multi-Drop Protocol)

def checksum(data):
    """Compute checksum for Sycon Multi Drop Protocol."""
    ck = sum(data) % 256
    cksum1 = (ck >> 4) + 0x30
    cksum2 = (ck & 0xF) + 0x30
    return [cksum1, cksum2]

def stuff(data):
    """Escape the data to be sent to compressor."""
    XLATE = {0x02: 0x30, 0x0D: 0x31, 0x07: 0x32}
    out = []
    for c in data:
        if c in XLATE:
            out.extend([ESC, XLATE[c]])
        else:
            out.append(c)
    return out

def unstuff(data):
    """Unescape data coming back from the compressor."""
    XLATE = {0x30: 0x02, 0x31: 0x0D, 0x32: 0x07}
    out = []
    escape = False
    for c in data:
        if escape:
            out.append(XLATE[c])
            escape = False
        elif c == ESC:
            escape == True
        else:
            out.append(c)
    return out

def pack(data):
    """Make a packet to send data to the compressor.
    
    We use the Sycon Multi Drop Protocol (see docs on skynet).
    """
    chk = checksum([ADDR, CMD_RSP] + data)
    pkt = [ADDR, CMD_RSP] + stuff(data)
    return [STX] + pkt + chk + [CR]

def unpack(response):
    """pull binary data out of SMDP response packet"""
    if isinstance(response, str):
        response = [ord(c) for c in response]
    if response[-1] == CR:
        response = response[:-1]
    rsp = response[2] & 0xF # response code (see SMDP docs)
    # drop 3 byte header (STX, ADDR, CMD_RSP) and 2 byte checksum
    data = unstuff(response[3:-2])
    return data

#####
# Data Dictionary for CP2800 Compressor
    
def read(key, index=0):
    """Make a packet to read a variable."""
    return pack([0x63] + toBytes(HASHCODES[key], count=2) + [index])

def write(key, value, index=0):
    """Make a packet to write a variable."""
    return pack([0x61] + toBytes(HASHCODES[key], count=2) + [index] + toBytes(value))

def getValue(resp):
    """Get an integer value from a response packet."""
    data = unpack(resp)
    return fromBytes(data[-4:])
    
def toBytes(n, count=4):
    """Turn an int into a list of bytes."""
    return [(n >> (8*i)) & 0xFF for i in reversed(range(count))]

def fromBytes(b, count=4):
    """Turn a list of bytes into an int."""
    return sum(d << (8*i) for d, i in zip(b, reversed(range(count))))


#####
# Create a server instance and run it

__server__ = HeatSwitchServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)

