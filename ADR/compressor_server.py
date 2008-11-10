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

from labrad.server import LabradServer, setting, inlineCallbacks, returnValue
from labrad.units import degC, K, psi, torr

# registry (for info about where to connect)
# Servers -> CP2800 Compressor
# -> Serial Link = server, port
# -> log -> YYYY -> MM -> DD ->

# data vault (for logging of numerical data)
# Logs -> CP2800 Compressor -> {YYYY} -> {MM} -> {DD} ->
#      -> Vince -> {YYYY} -> {MM} -> {DD} ->
#      -> Jules -> {YYYY} -> {MM} -> {DD} ->

class CompressorServer(LabradServer):
    name = 'CP2800 Compressor'

    @inlineCallbacks
    def initServer(self):
        print 'loading config info...',
        yield self.loadConfigInfo()
        print 'done.'
        self.serialConnected = False
        if self.serialName in self.client.servers:
            yield self.connectSerial()

    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.client.registry
        p = reg.packet()
        p.cd(['', 'Servers', 'CP2800 Compressor'], True)
        p.get('Serial Link', key='link')
        ans = yield p.send()
        self.serialName, self.serialPort = ans['link']

    @inlineCallbacks
    def connectSerial(self):
        """Connect to/disconnect from the serial port."""
        print 'connecting to "%s" on port "%s"...' % (self.serialName, self.serialPort),
        self.serialServer = self.client[self.serialName]
        p = self.serialServer.packet()
        p.open(self.serialPort)
        p.baudrate(115200)
        p.read()
        p.timeout(TIMEOUT)
        yield p.send()
        self.serialConnected = True
        print 'done.'
        

    def disconnectSerial(self):
        """Disconnect from the serial port."""

    @inlineCallbacks
    def serverConnected(self, ID, name):
        """Called when a server connects to LabRAD."""
        if name == self.serialName:
            yield self.connectSerial()

    @inlineCallbacks
    def serverDisconnected(self, ID, name):
        """Called when a server disconnect from LabRAD."""
        if name == self.serialName:
            self.serialConnected = False
    
    @setting(1, 'Start')
    def start_compressor(self, c):
        """Start the compressor."""
        yield self.serialServer.write(write('EV_START_COMP_REM', 1))

    @setting(2, 'Stop')
    def stop_compressor(self, c):
        """Stop the compressor."""
        yield self.serialServer.write(write('EV_STOP_COMP_REM', 1))

    @setting(3, 'Status', returns='b')
    def compresssor_status(self, c):
        """Get the on/off status of the compressor."""
        p = self.serialServer.packet()
        p.write(read('COMP_ON'))
        p.read_as_words(RESP_LEN, key='COMP_ON')
        ans = yield p.send()
        returnValue(bool(getValue(ans['COMP_ON'])))

    @setting(10, 'Temperatures', minmax='s',
             returns='v[K] {water in}, v[K] {water out}, v[K] {He}, v[K] {oil}')
    def temperatures(self, c, minmax='CURR'):
        """Get temperatures.

        If called with 'MIN' or 'MAX', will return the minimum or maximum
        recorded values of the temperatures, respectively.  These min and
        max values can be reset by calling 'Clear Markers'.
        """
        key = 'TEMP_TNTH_DEG'
        if minmax.upper() == 'MIN':
            key = 'TEMP_TNTH_DEG_MINS'
        elif minmax.upper() == 'MAX':
            key = 'TEMP_TNTH_DEG_MAXES'
        p = self.serialServer.packet()
        for i in range(4):
            p.write(read(key, i))
            p.read_as_words(RESP_LEN, key=i)
        ans = yield p.send()
        for i in range(4):
            print ans[i]
        returnValue(tuple(((getValue(ans[i])/10.0)*degC)[K] for i in range(4)))
    
    @setting(11, 'Pressures', minmax='s',
             returns='v[torr] {high side}, v[torr] {low side}')
    def pressures(self, c, minmax='CURR'):
        """Get pressures.

        If called with 'MIN' or 'MAX', will return the minimum or maximum
        recorded values of the pressures, respectively.  These min and
        max values can be reset by calling 'Clear Markers'.
        """
        key = 'PRES_TNTH_PSI'
        if minmax.upper() == 'MIN':
            key = 'PRES_TNTH_PSI_MINS'
        elif minmax.upper() == 'MAX':
            key = 'PRES_TNTH_PSI_MAXES'
        p = self.serialServer.packet()
        for i in range(2):
            p.write(read(key))
            p.read_as_words(RESP_LEN, key=i)
        ans = yield p.send()
        returnValue(tuple(((getValue(ans[i])/10.0)*psi)[torr] for i in range(2)))

    @setting(12, 'Clear Markers')
    def clear_markers(self, c):
        """Clear Min/Max temperature and pressure markers."""
        yield self.serialServer.write(write('CLR_TEMP_PRES_MMMARKERS', 1))

    

# compressor control protocol
STX = 0x02
ADDR = 0x10
CR = ord('\r')
CMD_RSP = 0x80
RESP_LEN = 17 # 3 bytes SMDP header, 11 bytes data, 2 bytes checksum, CR
TIMEOUT = 10 # serial read timeout

def checksum(data):
    """Compute checksum for Sycon Multi Drop Protocol."""
    ck = sum(data) % 256
    cksum1 = (ck >> 4) + 0x30
    cksum2 = (ck & 0xF) + 0x30
    return [cksum1, cksum2]

def pack(data):
    """Make a packet to send data to the compressor.
    
    We use the Sycon Multi Drop Protocol (see docs on skynet).
    """
    pkt = [ADDR, CMD_RSP] + data
    return [STX] + pkt + checksum(pkt) + [CR]

def unpack(response):
    """pull binary data out of SMDP response packet"""
    print response
    rsp = response[2] & 0xF # response code (see SMDP docs)
    data = response[3:-3]
    return data


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
        


__server__ = CompressorServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)

