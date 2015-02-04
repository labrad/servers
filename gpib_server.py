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
#
# CHANGELOG
#
# 2011 December 10 - Peter O'Malley & Jim Wenner
#
# Fixed bug where doesn't add devices if no SOCKETS connected.
#
# 2011 December 5 - Jim Wenner
#
# Added ability to read TCPIP (Ethernet) devices if configured to use
# sockets (i.e., fixed port address). To do this, added getSocketsList
# function and changed refresh_devices.
#
# 2011 December 3 - Jim Wenner
#
# Added ability to read TCPIP (Ethernet) devices. Must be configured
# using VXI-11 or LXI so that address ends in INSTR. Does not accept if
# configured to use sockets. To do this, changed refresh_devices.
#
# To be clear, the gpib system already supported ethernet devices just fine
# as long as they weren't using raw socket protocol. The changes that
# were made here and in the next few revisions are hacks to make socket
# connections work, and should be improved.

from labrad.server import LabradServer, setting
from twisted.internet.defer import inlineCallbacks
from twisted.internet.reactor import callLater
from labrad.errors import DeviceNotSelectedError
import labrad.units as units
import visa


"""
### BEGIN NODE INFO
[info]
name = GPIB Bus
version = 1.3.2-no-refresh
description = Gives access to GPIB devices via pyvisa.
instancename = %LABRADNODE% GPIB Bus

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""


class GPIBBusServer(LabradServer):
    """Provides direct access to GPIB-enabled devices."""
    name = '%LABRADNODE% GPIB Bus'

    refreshInterval = 10
    defaultTimeout = 1.0 * units.s

    def initServer(self):
        self.devices = {}
        # start refreshing only after we have started serving
        # this ensures that we are added to the list of available
        # servers before we start sending messages
        callLater(0.1, self.startRefreshing)

    def startRefreshing(self):
        """Start periodically refreshing the list of devices.

        The start call returns a deferred which we save for later.
        When the refresh loop is shutdown, we will wait for this
        deferred to fire to indicate that it has terminated.
        """
        # self.refresher = LoopingCall(self.refreshDevices)
        #self.refresherDone = self.refresher.start(self.refreshInterval, now=True)
        self.refreshDevices()

    @inlineCallbacks
    def stopServer(self):
        """Kill the device refresh loop and wait for it to terminate."""
        if hasattr(self, 'refresher'):
            self.refresher.stop()
            yield self.refresherDone

    def refreshDevices(self):
        """Refresh the list of known devices on this bus.

        Currently supported are GPIB devices and GPIB over USB.
        """
        try:
            rm = visa.ResourceManager()
            addresses = [str(x) for x in rm.list_resources()]
            additions = set(addresses) - set(self.devices.keys())
            deletions = set(self.devices.keys()) - set(addresses)
            for addr in additions:
                try:
                    if addr.startswith('GPIB'):
                        instName = addr
                    elif addr.startswith('TCPIP'):
                        instName = addr
                    elif addr.startswith('USB'):
                        instName = addr + '::INSTR'
                    else:
                        continue
                    instr = rm.get_instrument(instName)
                    instr.write_termination = ''
                    instr.clear()
                    if addr.endswith('SOCKET'):
                        instr.write_termination = '\n'
                    self.devices[addr] = instr
                    self.sendDeviceMessage('GPIB Device Connect', addr)
                except Exception, e:
                    print 'Failed to add ' + addr + ':' + str(e)
            for addr in deletions:
                del self.devices[addr]
                self.sendDeviceMessage('GPIB Device Disconnect', addr)
        except Exception, e:
            print 'Problem while refreshing devices:', str(e)

    def sendDeviceMessage(self, msg, addr):
        print msg + ': ' + addr
        self.client.manager.send_named_message(msg, (self.name, addr))

    def initContext(self, c):
        c['timeout'] = self.defaultTimeout

    def getDevice(self, c):
        if 'addr' not in c:
            raise DeviceNotSelectedError("No GPIB address selected")
        if c['addr'] not in self.devices:
            raise Exception('Could not find device ' + c['addr'])
        instr = self.devices[c['addr']]
        return instr

    @setting(0, addr='s', returns='s')
    def address(self, c, addr=None):
        """Get or set the GPIB address for this context.

        To get the addresses of available devices,
        use the list_devices function.
        """
        if addr is not None:
            c['addr'] = addr
        return c['addr']

    @setting(2, time='v[s]', returns='v[s]')
    def timeout(self, c, time=None):
        """Get or set the GPIB timeout."""
        if time is not None:
            c['timeout'] = time
        return c['timeout']

    @setting(3, data='s', returns='')
    def write(self, c, data):
        """Write a string to the GPIB bus."""
        self.getDevice(c).write(data)

    @setting(4, n_bytes='w', returns='s')
    def read(self, c, n_bytes=None):
        """Read from the GPIB bus.

        If specified, reads only the given number of bytes.
        Otherwise, reads until the device stops sending.
        """
        instr = self.getDevice(c)
        if n_bytes is None:
            ans = instr.read_raw()
        else:
            ans = instr.read_raw(n_bytes)
        return str(ans).strip()

    @setting(5, data='s', returns='s')
    def query(self, c, data):
        """Make a GPIB query, a write followed by a read.

        This query is atomic.  No other communication to the
        device will occur while the query is in progress.
        """
        instr = self.getDevice(c)
        instr.write(data)
        ans = instr.read_raw()
        return str(ans).strip()

    @setting(20, returns='*s')
    def list_devices(self, c):
        """Get a list of devices on this bus."""
        return sorted(self.devices.keys())

    @setting(21)
    def refresh_devices(self, c):
        """ manually refresh devices """
        self.refreshDevices()


__server__ = GPIBBusServer()

if __name__ == '__main__':
    from labrad import util

    util.runServer(__server__)
