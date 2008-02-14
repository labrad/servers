#!c:\Python25\python.exe

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
from twisted.internet.defer import inlineCallbacks, returnValue

from pyvisa import visa, vpp43

class GPIBBusServer(LabradServer):
    name = 'GPIB Bus'
    isLocal = True

    def initServer(self):
        self.devices = {}
        self.refreshDevices()
        
    def refreshDevices(self):
        for s in visa.get_instruments_list():
            if not s.startswith('GPIB'):
                print 'skipping:', s
                continue
            print 'checking:', s
            addr = int(s.split('::')[1])
            instr = visa.instrument(s, timeout=1)
            try:
                instr.clear()
                instr.write('*IDN?')
                idnstr = instr.read()
                mfr, model = idnstr.split(',')[:2]
            except:
                mfr, model = '<unknown>', '<unkown>'
            print '    mfr=%s, model=%s' % (mfr, model)
            self.devices[addr] = dict(instr=instr, mfr=mfr, model=model)
    
    def initContext(self, c):
        c['timeout'] = 1
        
    @setting(0, addr=['s', 'w'], returns=['w'])
    def address(self, c, addr=None):
        """Get or set the GPIB address."""
        if addr is not None:
            c['addr'] = int(addr)
        return c['addr']
        
    #@setting(1, data=['w'], returns=['w'])
    #def mode(self, c, data=None):
    #    """Get or set the GPIB read/write mode."""
    #    if data is not None:
    #        c['mode'] = mode
    #    return c['mode']

    @setting(2, time=['v[s]'], returns=['v[s]'])
    def timeout(self, c, time=None):
        """Get or set the GPIB timeout."""
        if time is not None:
            c['timeout'] = time
        return c['timeout'] 

    @setting(3, data=['s'], returns=['*b{status}'])
    def write(self, c, data):
        """Write a string to the GPIB bus."""
        instr = self.devices[c['addr']]['instr']
        instr.timeout = c['timeout']
        instr.write(data)
        status = vpp43.read_stb(instr.vi)
        return byteToBoolList(status)

    @setting(4, bytes=['w'], returns=['(s{data}, *b{status})'])
    def read(self, c, bytes=None):
        """Read from the GPIB bus."""
        instr = self.devices[c['addr']]['instr']
        instr.timeout = c['timeout']
        if bytes is None:
            ans = instr.read()
        else:
            ans = vpp43.read(instr.vi, bytes)
        status = vpp43.read_stb(instr.vi)
        return ans, byteToBoolList(status)

    @setting(20, bytes=['w'], returns=['*(w{GPIB ID}, s{device name})'])
    def list_devices(self, c, bytes=None):
        """Get a list of devices."""
        return [(addr, '%(mfr)s %(model)s' % dev)
                for addr, dev in sorted(self.devices.items())]


def byteToBoolList(byte):
    return [bool((byte >> n) & 1) for n in range(15, -1, -1)]

__server__ = GPIBBusServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
