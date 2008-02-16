#!c:\python25\python.exe

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

from labrad import types as T, util
from labrad.server import LabradServer, setting

from twisted.python import log
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from datetime import datetime, timedelta

MIN_TIME = .25 # shortest allowed pressurizing time
CHANNELS = ['ch1', 'ch2']

class HEPressurizer(LabradServer):
    """Control the valve to pressurize the LHe dewar during transfers."""
    name = 'He Pressurizing Server'

    config = dict(server='DR Serial Server', port='COM7', ID=None)

    @inlineCallbacks
    def initServer(self):
        self.connected = False
        self.pressurizing = False
        yield self.findValve()
        
    def serverConnected(self, data):
        ID, name = data
        if name == self.config['server']:
            self.findValve()
        
    def serverDisconnected(self, ID):
        if ID == self.config['ID']:
            self.connected = False

    @inlineCallbacks
    def findValve(self):
        if self.connected:
            return
        cxn = self.client
        yield cxn.refresh()
        server = self.config['server']
        port = self.config['port']
        if server not in cxn.servers:
            log.msg("'%s' not found." % server)
            return
        ser = cxn[server]
        self.config['ID'] = ser.ID
        log.msg('Connecting to %s...' % server)
        ports = yield ser.list_serial_ports()
        if port not in ports:
            raise Exception('Port %s not found on %s.' % (port, server))
        yield self.connectToValve(ser, port)
        log.msg('Server ready')


    @inlineCallbacks
    def connectToValve(self, ser, port):
        self.ser = ser
        log.msg('  Connecting to %s...' % port)
        res = yield ser.open(port)
        if res == port:
            self.ser.rts(False)
            log.msg('    OK')
            self.connected = True
        else:
            log.msg('    ERROR')
            raise Exception('Could not set up connection.')

    @inlineCallbacks
    def openValve(self, seconds):
        seconds = max(seconds, MIN_TIME)
        yield self.ser.rts(True)
        self.stopCall = reactor.callLater(seconds, self.closeValve)
        self.pressurizing = True

    @inlineCallbacks
    def closeValve(self):
        yield self.ser.rts(False)
        self.pressurizing = False

    def times(self, data):
        seconds = data.value
        delay = timedelta(seconds=seconds)
        now = datetime.now()
        newStop = now + delay
        return seconds, newStop

    def checkConnection(self):
        if not self.connected:
            raise Exception('Not connected to valve. '\
                            'Make sure %s is running.' % self.config['server'])
        
    @setting(0, 'Pressurize',
                data=[': Pressurize for 3 seconds',
                      'v[s]: Pressurize for specified time'],
                returns=['b: Indicates whether valve was already open'])
    def pressurize(self, c, data=T.Value(3.0,'s')):
        """Open the pressurization valve."""
        self.checkConnection()
        seconds, newStop = self.times(data)
        if self.pressurizing:
            if newStop > self.stopTime and self.stopCall.active():
                self.stopCall.reset(seconds)
                self.stopTime = newStop
            returnValue(True)
        else:
            self.stopTime = newStop
            yield self.openValve(seconds)
            returnValue(False)

    @setting(1, 'Stop',
                data=[': Close the valve immediately',
                      'v[s]: Close the valve after the specified delay'],
                returns=['b: Indicates whether the valve was still open'])
    def close_valve(self, c, data=T.Value(0.0,'s')):
        """Close the pressurization valve."""
        self.checkConnection()
        seconds, newStop = self.times(data)
        if self.pressurizing:
            if newStop < self.stopTime and self.stopCall.active():
                self.stopCall.reset(seconds)
                self.stopTime = newStop
            returnValue(True)
        else:
            returnValue(False)

    @setting(2, 'Time Left',
                data=[': Request the valve status'],
                returns=['v[s]: Time that the valve will remain open'])
    def time_left(self, c, data):
        """Get the time until the pressurization valve will close."""
        self.checkConnection()
        if self.pressurizing:
            timeLeft = self.stopTime - datetime.now()
            secondsLeft = timeLeft.seconds + timeLeft.microseconds/1e6
        else:
            secondsLeft = 0
        return T.Value(secondsLeft, 's')


__server__ = HEPressurizer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)    
