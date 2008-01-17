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

from labrad import types as T
from labrad.server import setting
from labrad.gpib import GPIBDeviceServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

CHANNELS = 'T T0 A B AB C D CD ALL'.split()
ALL = CHANNELS.index('ALL')
MODES = 'TTL NIM ECL VAR'.split()

def findString(key, ls):
    if key is None:
        key = 0
    elif isinstance(key, str):
        key = ls.index(key)
    elif isinstance(key, (int, long)):
        if key < 0 or key >= len(ls):
            raise Exception('Out of range.')
    return key

def makeChannelCommand(cmd, channel, params, all_channels=[2,3,4,5,6,7]):
    if params:
        params = ',' + params
    if channel == ALL:
        channel = all_channels
    else:
        channel = [channel]
    cmds = ['%s %d%s' % (cmd, c, params) for c in channel]
    return ';'.join(cmds)

class DG535Server(GPIBDeviceServer):
    name = 'DG535'
    deviceName = 'SRS DG535'

    @inlineCallbacks
    def initServer(self):
        yield GPIBDeviceServer.initServer(self)
        self.defaultCtxtData.update(channel=2, anchor=1)

    @setting(11, 'Select Channel', chan=['s', 'w'], returns=['w'])
    def select_channel(self, c, chan=2):
        ch = c['channel'] = findString(chan, CHANNELS)
        return ch

    @setting(12, 'Select Delay Anchor', chan=['s', 'w'], returns=['w'])
    def select_delay_anchor(self, c, chan=1):
        ch = c['anchor'] = findString(data, CHANNELS)
        return ch

    def doCommand(self, c, cmd, params):
        dev = self.selectedDevice(c)
        chan = c['channel']
        cmd = makeChannelCommand(cmd, chan, params)
        return dev.write(cmd)

    @setting(20, 'Set Channel Delay', delay=['v[s]'], returns=['b'])
    def set_channel_delay(self, c, delay):
        params = '%d,%g' % (c['anchor'], delay)
        yield self.doCommand(c, 'DT', params)
        returnValue(True)

    @setting(30, 'Set High Impedance', data=['b'], returns=['b'])
    def set_high_impedance(self, c, data):
        params = str(int(data))
        yield self.doCommand(c, 'TZ', params)
        returnValue(True)

    @setting(31, 'Set Output Mode', mode=['s', 'w'], returns=['b'])
    def set_output_mode(self, c, mode=0):
        params = str(findString(data, MODES))
        yield self.doCommand(c, 'OM', params)
        returnValue(True)

    @setting(32, 'Set Output Amplitude', amp=['v[V]'], returns=['b'])
    def set_output_amplitude(self, c, amp):
        params = str(float(amp))
        yield self.doCommand(c, 'OA', params)
        returnValue(True)

    @setting(33, 'Set Output Offset', off=['v[V]'], returns=['b'])
    def set_output_offset(self, c, off):
        params = str(float(off))
        yield self.doCommand(c, 'OO', params)
        returnValue(True)

    @setting(34, 'Set Output Inversion', inv=['b'], returns=['b'])
    def set_output_inversion(self, c, inv):
        params = str(int(not inv))
        yield self.doCommand(c, 'OP', params)
        returnValue(True)

__server__ = DG535Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
