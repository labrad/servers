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
  [': write',         # Use: <addr> " <data>" write
       'wrt',         # Write GPIB data
       'stat . drop', # Get GPIB status
       '" _" cmd',    # Untalk
       'sic',         # Reset bus
       '0 gts',       # Go to standby
   ';']

IBCL_Script_read = \
  [': read',                            # Use: <addr> <buffer> <count> read
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
    name = 'IBCL GPIB'

    @setting(1, 'Controllers', returns=['*s: Controllers'])
    def controllers(self, c):
        """Request a list of available IBCL controllers."""
        res = yield self.client.ibcl.controllers()
        returnValue(res)

    @setting(10, 'Select', name=['s'], returns=[])
    def select(self, c, name):
        """Select active controller"""
        p = self.client.ibcl.packet(context=c.ID)\
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
        if 'addr' in res.settings:
            c['buffer'] = int(res['addr'][0][0])
        return

    @setting(20, 'Write', addr=['w'], data=['s'], returns=['*b'])
    def write(self, c, addr, data):
        """Send GPIB data"""
        res = yield self.client.ibcl.command('%X " %s" write' % (addr, data), context=c.ID)
        state = int(res[0][0],16)
        state = [(state & 2**b)>0 for b in range(16)]
        returnValue(state)

    @setting(30, 'Read', addr=['w'], count=['w'], returns=['s*b'])
    def read(self, c, addr, count=10000):
        """Reads GPIB data"""
        if count>10000:
            count=10000
        res = yield self.client.ibcl.command('%X %X %X read' % (addr, c['buffer'], count), context=c.ID)
        state = int(res[0][0],16)
        state = [(state & 2**b)>0 for b in range(16)]
        res = res[0][1]
        if '%' in res:
            for old, new in replacements:
                res = res.replace(old, new)
        returnValue((res, state))

__server__ = IBCLGPIBServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)    
