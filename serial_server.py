#!c:\python25\python.exe

# Copyright (C) 2007  Markus Ansmann
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

from labrad import types as T, util
from labrad.errors import Error
from labrad.server import LabradServer, setting

from twisted.python import log
from twisted.internet import defer, reactor, threads
from twisted.internet.defer import inlineCallbacks, returnValue

from serial import Serial
from serial.serialutil import SerialException

from time import sleep

class NoPortSelectedError(Error):
    """Please open a port first."""
    code = 1

class NoPortsAvailableError(Error):
    """No serial ports are available."""
    code = 3

class SerialServer(LabradServer):
    name = 'Serial Server'
    isLocal = True

    def initServer(self):
        self.SerialPorts = []
        print 'Searching for COM ports:'
        for a in range(1,20):
            COMexists = True
            try:
                ser = Serial('\\\\.\\COM%d' % a)
                ser.close()
            except SerialException, e:
                if e.message.find('cannot find') >= 0:
                    COMexists = False
            if COMexists:
                self.SerialPorts += ['COM%d' % a]
                print '  COM%d' %a
        if not len(self.SerialPorts):
            print '  none'


    def expireContext(self, c):
        if 'PortObject' in c:
            c['PortObject'].close()

    def getPort(self, c):
        try:
            return c['PortObject']
        except:
            raise NoPortSelectedError()


    @setting(1, 'List Serial Ports',
                returns=['*s: List of serial ports'])
    def list_serial_ports(self, c):
        """Retrieves a list of all serial ports.

        NOTES:
        This list contains all ports installed on the computer,
        including ones that are already in use by other programs."""
        return self.SerialPorts


    @setting(10, 'Open',
                 port=[': Open the first available port',
                       's: Port to open, e.g. COM4'],
                 returns=['s: Opened port'])
    def open(self, c, port=0):
        """Opens a serial port in the current context."""
        c['Timeout'] = 0
        if 'PortObject' in c:
            c['PortObject'].close()
            del c['PortObject']
        if port == 0:
            for i in range(len(self.SerialPorts)):
                try:
                    c['PortObject'] = Serial('\\\\.\\'+self.SerialPorts[i], timeout=0)
                    break
                except SerialException:
                    pass
            if 'PortObject' not in c:
                raise NoPortsAvailableError()
        else:
            try:
                c['PortObject'] = Serial('\\\\.\\'+port, timeout=0)
            except SerialException, e:
                if e.message.find('cannot find') >= 0:
                    raise Error(code=1, msg=e.message)
                else:
                    raise Error(code=2, msg=e.message)
        return c['PortObject'].portstr.replace('\\\\.\\','')


    @setting(11, 'Close', returns=[''])
    def close(self, c):
        """Closes the current serial port."""
        if 'PortObject' in c:
            c['PortObject'].close()
            del c['PortObject']


    @setting(20, 'Baudrate',
                 data=[': List baudrates',
                       'w: Set baudrate (0: query current)'],
                 returns=['w: Selected baudrate', '*w: Available baudrates'])
    def baudrate(self, c, data=None):
        """Sets the baudrate."""
        ser = self.getPort(c)
        brates = [long(x[1]) for x in ser.getSupportedBaudrates()]
        if data is None:
            return brates
        else:
            if data in brates:
                ser.setBaudrate(data)
            return long(ser.getBaudrate())


    @setting(21, 'Bytesize',
                 data=[': List bytesizes',
                       'w: Set bytesize (0: query current)'],
                 returns=['*w: Available bytesizes',
                          'w: Selected bytesize'])
    def bytesize(self, c, data=None):
        """Sets the bytesize."""
        ser = self.getPort(c)
        bsizes = [long(x[1]) for x in ser.getSupportedByteSizes()]
        if data is None:
            return bsizes
        else:
            if data in bsizes:
                ser.setByteSize(data)
            return long(ser.getByteSize())


    @setting(22, 'Parity',
                 data=[': List parities',
                       's: Set parity (empty: query current)'],
                 returns=['*s: Available parities',
                          's: Selected parity'])
    def parity(self, c, data=None):
        """Sets the parity."""
        ser = self.getPort(c)
        bsizes = [x[1] for x in ser.getSupportedParities()]
        if data is None:
            return bsizes
        else:
            data = data.upper()
            if data in bsizes:
                ser.setParity(data)
            return ser.getParity()


    @setting(23, 'Stopbits',
                 data=[': List stopbits',
                       'w: Set stopbits (0: query current)'],
                 returns=['*w: Available stopbits',
                          'w: Selected stopbits'])
    def stopbits(self, c, data=None):
        """Sets the number of stop bits."""
        ser = self.getPort(c)
        bsizes = [long(x[1]) for x in ser.getSupportedStopbits()]
        if data is None:
            return bsizes
        else:
            if data in bsizes:
                ser.setStopbits(data)
            return long(ser.getStopbits())


    @setting(25, 'Timeout',
                 data=[': Return immediately',
                       'v[s]: Timeout to use (max: 5min)'],
                 returns=['v[s]: Timeout being used (0 for immediate return)'])
    def timeout(self, c, data=T.Value(0,'s')):
        """Sets a timeout for read operations."""
        ser = self.getPort(c)
        c['Timeout'] = min(data.value, 300)
        return T.Value(c['Timeout'], 's')


    @setting(30, 'RTS', data=['b'], returns=['b'])
    def RTS(self, c, data):
        """Sets the state of the RTS line."""
        ser = self.getPort(c)
        ser.setRTS(int(data))
        return data


    @setting(31, 'DTR', data=['b'], returns=['b'])
    def DTR(self, c, data):
        """Sets the state of the DTR line."""
        ser = self.getPort(c)
        ser.setDTR(int(data))
        return data


    @setting(40, 'Write',
                 data=['s: Data to send',
                       '*w: Byte-data to send'],
                 returns=['w: Bytes sent'])
    def write(self, c, data):
        """Sends data over the port."""
        ser = self.getPort(c)
        if isinstance(data, list):
            data = ''.join(chr(x&255) for x in data)
        ser.write(data)
        return long(len(data))


    @setting(41, 'Write Line', data=['s: Data to send'],
                               returns=['w: Bytes sent'])
    def write_line(self, c, data):
        """Sends data over the port appending CR LF."""
        ser = self.getPort(c)
        ser.write(data + '\r\n')
        return long(len(data)+2)


    @inlineCallbacks
    def deferredRead(self, ser, timeout, count=1):
        killit = False
        def doRead(count):
            d = ''
            while not killit:
                d = ser.read(count)
                if d:
                    break
                sleep(0.05)
            return d
        data = threads.deferToThread(doRead, count)
        r = yield util.maybeTimeout(data, min(timeout, 300), '')
        killit = True

        if r == '':
            r = ser.read(count)

        returnValue(r)


    @inlineCallbacks
    def readSome(self, c, count=0):
        ser = self.getPort(c)

        if count == 0:
            returnValue(ser.read(10000))

        timeout = c['Timeout']
        if timeout == 0:
            returnValue(ser.read(count))

        recd = ''
        while len(recd) < count:
            r = ser.read(count)
            if r == '':
                r = yield self.deferredRead(ser, timeout, count=count)
                if r == '':
                    ser.close()
                    ser.open()
                    break
            recd += r
        returnValue(recd)


    @setting(50, 'Read', count=[': Read all bytes in buffer',
                                'w: Read this many bytes'],
                         returns=['s: Received data'])
    def read(self, c, count=0):
        """Read data from the port."""
        return self.readSome(c, count)


    @setting(51, 'Read as Words',
                 data=[': Read all bytes in buffer',
                       'w: Read this many bytes'],
                 returns=['*w: Received data'])
    def read_as_words(self, c, data=0):
        """Read data from the port."""
        ans = yield self.readSome(c, data)
        returnValue([long(ord(x)) for x in ans])


    @setting(52, 'Read Line',
                 data=[': Read until LF, ignoring CRs',
                       's: Other delimiter to use'],
                 returns=['s: Received data'])
    def read_line(self, c, data=''):
        """Read data from the port, up to but not including the specified delimiter."""
        ser = self.getPort(c)
        timeout = c['Timeout']

        if data:
            delim, skip = data, ''
        else:
            delim, skip = '\n', '\r'

        recd = ''
        while True:
            r = ser.read(1)
            if r == '' and timeout > 0:
                # only try a deferred read if there is a timeout
                r = yield self.deferredRead(ser, timeout)
            if r in ('', delim):
                break
            if r != skip:
                recd += r
        returnValue(recd)


__server__ = SerialServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
