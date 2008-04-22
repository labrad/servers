#!c:\python25\python.exe

# Copyright (C) 2008  Isaac Storch, Markus Ansmann
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

from datetime import datetime

IBCL_Script_bindl = \
  [': bindl',                                # Use: <addr> <n> bindl
       'base @ rot rot',                     # Store current base
       'hex',                                # Switch to base hex
       '0 do',
           'dup c@',                         # Load byte
           'dup 20 <',                       # Check for less than ' '
           'if',
               '0',
               '<# # # 25 hold #> type',     # Display as %HEX if so
           'else',
               'dup 7E >',                   # Check for greater than '~'
               'if',
                   '0',
                   '<# # # 25 hold #> type', # Display as %HEX if so
               'else',
                   'dup 25 =',               # Check for '%'
                   'if dup emit endif',      # If so, display as '%%'
                   'emit',                   # Send
               'endif',
           'endif',
           '1+',                             # Increase address
       'loop',
       'drop',                               # Drop address
       'base !',                             # Restore previous base
   ';']

IBCL_Script_write = \
  [': write',         # Use: <addr> " <data>" <timeout> write
       'tmo',         # Set timeout
       'wrt',         # Write GPIB data
       'stat . drop', # Get GPIB status
       '" _" cmd',    # Untalk
       '0 gts',       # Go to standby
   ';']

IBCL_Script_read = \
  [': read',                            # Use: <addr> <buffer> <count> <timeout> read
       'tmo',                           # Set timeout
       'rot rot dup >r rot rot r> rot', # Make a copy of <buffer> for download
       'rd',                            # Do GPIB read
       'stat dup . cr',                 # Get GPIB status, duplicate and transfer
       '" ?" cmd',                      # Unlisten
       'sic',                           # Reset bus
       '0 gts',                         # Go to standby
       '0< if',                         # Error?
           'drop drop',                 # Remove byte count and <buffer>
       'else',
           'bindl',                     # Transfer data
       'endif',
   ';']

replacements = [('%%%02X' % i, chr(i)) for i in range(32)+range(127,256)] + [('%%','%')]

class IBCLGPIBServer(LabradServer):
    name = 'IBCL GPIB Bus'
    isLocal = True

    @inlineCallbacks
    def initServer(self):
        # select first controller
        name = (yield self.client.ibcl.controllers())[0]
        p = self.client.ibcl.packet()\
                            .select(name)\
                            .command('cold')
        for l in IBCL_Script_bindl: p.command(l)
        for l in IBCL_Script_write: p.command(l)
        for l in IBCL_Script_read:  p.command(l)
        p.command('decimal')\
         .command('here .', key='addr')\
         .command('10240 allot')\
         .command('hex')
        res = yield p.send()
        print (yield self.client.ibcl.debug())
        if 'addr' in res.settings:
            self.buffer = int(res['addr'][0][0])
        yield self.refresh_devices()

    def initContext(self, c):
        c['timeout'] = 10
        c['address'] = 6
    
    @setting(0, 'Address', addr=['s', 'w'], returns=['w'])
    def address(self, c, addr=None):
        """Get or set the GPIB address."""
        if addr is not None:
            c['address'] = int(addr)
        return c['address']
    
    @setting(1, 'Mode', data=['w'], returns=['w'])
    def mode(self, c, data=None):
        """Get or set the GPIB read/write mode.
        NOTES:
        Right now, setting the mode does nothing in this server."""
        if data is not None:
            c['mode'] = mode
        return c['mode']
        
    @setting(2, 'Timeout', time=['v[ms]','w'], returns=['v[s]'])
    def timeout(self, c, time=None):
        """Get or set the GPIB timeout.

        NOTES:
        Only the following timeouts are allowed:
        0 s,
        10 us,
        30 us,
        100 us,
        300 us,
        1 ms,
        3 ms,
        10 ms,
        30 ms,
        100 ms,
        300 ms,
        1 s,
        3 s,
        10 s,
        30 s,
        100 s,
        300 s,
        1000 s. 
        Function rounds up."""
        timelist = [0, .00001, .00003, .0001, .0003, .001, .003, .01, .03,\
                    .1, .3, 1, 3, 10, 30, 100, 300, 1000]
        if time is not None:
            for ind, t in enumerate(timelist):
                if time*1000 <= t:
                    c['timeout'] = ind
                    break
        return timelist[c['timeout']]

    @setting(3, 'Write', data=['s'], returns=['*b'])
    def write(self, c, data):
        """Send GPIB data"""
        if not ('address' in c):
            raise Exception("No address selected!")
        if not ('timeout' in c):
            raise Exception("No timeout selected!")
        res = yield self.writeGPIB(c['address'], c['timeout'], data)
        returnValue(res)

    @setting(4, 'Read', count=['w'], returns=['s*b'])
    def read(self, c, count=10000):
        """Reads GPIB data"""
        if count>10000:
            count=10000
        if not ('address' in c):
            raise Exception("No address selected!")
        if not ('timeout' in c):
            raise Exception("No timeout selected!")
        res = yield self.readGPIB(c['address'], c['timeout'], count)
        returnValue(res)
    
    @setting(5, 'Controllers', returns=['*s: Controllers'])
    def controllers(self, c):
        """Request a list of available IBCL controllers."""
        res = yield self.client.ibcl.controllers()
        returnValue(res)

    @setting(20, 'List Devices', bytes=['w'], returns=['*(w{GPIB ID}, s{device name})'])
    def list_devices(self, c, bytes=None):
        """Get a list of devices."""
        return self.devicelist
    
    @setting(30, 'Refresh Devices')
    def refresh_devices(self, c=None):
        """Refresh the device list.
        NOTES:
        This setting uses the timeout set for this context (0.3 s by default)"""
        self.devicelist = []
        print "Scanning for devices..."
        if c is None:
            tmo = 10    # 0.3 s
        else:
            tmo = c['timeout']
        for addr in range(0,32):
            result = yield self.writeGPIB(addr, tmo, '*IDN?')
            if not result[15]:
                idnstr = (yield self.readGPIB(addr, tmo))[0]
                if idnstr is not '':
                    mfr, model = idnstr.split(',')[:2]
                    self.devicelist.append((addr, mfr + ' ' + model))
                    print "%2d - %s" % (addr, mfr[0:10] + ' ' + model[0:10])
                else:    
                    print "%2d - " % addr
            else:
                print "%2d - " % addr

    @inlineCallbacks
    def readGPIB(self, addr, timeout, count=1000):
        res = yield self.client.ibcl.command('%X %X %X %X read' % (addr, self.buffer, count, timeout))
        state = int(res[0][0],16)
        state = [(state & 2**b)>0 for b in range(16)]
        res = res[0][1]
        if '%' in res:
            for old, new in replacements:
                res = res.replace(old, new)
        returnValue((res, state))

    @inlineCallbacks
    def writeGPIB(self, addr, timeout, data):
        res = yield self.client.ibcl.command('%X " %s" %X write' % (addr, data, timeout))
        state = int(res[0][0],16)
        state = [(state & 2**b)>0 for b in range(16)]
        returnValue(state)
    
__server__ = IBCLGPIBServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)    
