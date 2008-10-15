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

class GPIBBusServer(LabradServer):
    name = '%LABRADNODE% GPIB Bus'

    refreshInterval = 10

    def initServer(self):
        self.devices = {}
        # start refreshing only after we have started serving
        # this ensures that we are added to the list of available
        # servers before we start sending messages
        callLater(0.1, self.startRefreshing)

    def startRefreshing(self):
        l = LoopingCall(self.refreshDevices)
        self.refresher = l, l.start(self.refreshInterval, now=True)

    @inlineCallbacks
    def stopServer(self):
        if hasattr(self, 'refresher'):
            self.refresher[0].stop()
            yield self.refresher[1]
        
    def refreshDevices(self):
        """Refresh the list of known devices on this bus."""
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
                    print 'failed to add ' + addr + ':' + str(e)
            for addr in deletions:
                del self.devices[addr]
                self.sendDeviceMessage('GPIB Device Disconnect', addr)
        except Exception, e:
            print 'problem while refreshing devices:', str(e)
            
    def sendDeviceMessage(self, msg, addr):
        print msg + ': ' + addr
        self.client.manager.send_named_message(msg, (self.name, addr))
            
    def initContext(self, c):
        c['timeout'] = 1.0

    def getDevice(self, c):
        if c['addr'] not in self.devices:
            raise Exception('Could not find device ' + c['addr'])
        instr = self.devices[c['addr']]
        instr.timeout = c['timeout']
        return instr
        
    @setting(0, addr=['s'], returns=['s'])
    def address(self, c, addr=None):
        """Get or set the GPIB address."""
        if addr is not None:
            c['addr'] = addr
        return c['addr']

    @setting(2, time=['v[s]'], returns=['v[s]'])
    def timeout(self, c, time=None):
        """Get or set the GPIB timeout."""
        if time is not None:
            c['timeout'] = time
        return c['timeout'] 

    @setting(3, data=['s'], returns=[''])
    def write(self, c, data):
        """Write a string to the GPIB bus."""
        self.getDevice(c).write(data)

    @setting(4, bytes=['w'], returns=['s'])
    def read(self, c, bytes=None):
        """Read from the GPIB bus."""
        instr = self.getDevice(c)
        if bytes is None:
            ans = instr.read()
        else:
            ans = vpp43.read(instr.vi, bytes)
        return ans

    @setting(20, returns=['*s'])
    def list_devices(self, c):
        """Get a list of devices on this bus."""
        return sorted(self.devices.keys())

__server__ = GPIBBusServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
