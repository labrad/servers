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
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.reactor import callLater
from twisted.internet.task import LoopingCall

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
    name = '%LABRADNODE% IBCL GPIB Bus'

    refreshInterval = 60
    timelist = [.00001, .00003, .0001, .0003, .001, .003, .01, .03,\
                .1, .3, 1, 3, 10, 30, 100, 300, 1000]
    refreshTimeout = 0.3

    def IBCLtimeoutIndex(self, time):
        found = False
        for ind, t in enumerate(self.timelist):
            if time <= t:
                index = ind+1
                found = True
                break
        if not found:
            index = 0   # this means no timeout is in effect
        return index
    
    def initServer(self):
        # start refreshing only after we have started serving
        # this ensures that we are added to the list of available
        # servers before we start sending messages
        self.devices = {}
        self.ctrls = {}
        self.keepRefreshing = True
        def startLater(self):
            self.refreshLoop = self.startRefreshLoop()
        callLater(0.1, startLater, self)

    @inlineCallbacks
    def stopServer(self):
        if hasattr(self, 'refreshLoop'):
            self.keepRefreshing = False
            yield self.refreshLoop

    def initContext(self, c):
        c['timeout'] = T.Value(0.3, 's')

    @inlineCallbacks
    def initController(self, name):
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
    
    @setting(0, 'Address', addr=['s'], returns=['s'])
    def address(self, c, addr=None):
        """Get or set the GPIB address."""
        if addr is not None:
            c['addr'] = addr
        return c['addr']

    @setting(1, 'Refresh Timeout', time=['v[s]'])
    def refresh_timeout(self, c, time=None):
        """Get or set the GPIB timeout used by this server for refreshing devices."""
        if time is not None:
            self.refreshTimeout = time
        return self.refreshTimeout
        
    @setting(2, 'Timeout', time=['v[s]'], returns=['v[s]'])
    def timeout(self, c, time=None):
        """Get or set the GPIB timeout.

        NOTES:
        Only the following timeouts are allowed:
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
        1000 s,
        infinite s.
        Function rounds up."""

        if time is not None:
            c['timeout'] = time
        return c['timeout']
    
    @setting(5, 'Controllers', returns=['*s: Controllers'])
    def controllers(self, c):
        """Request a list of available IBCL controllers."""
        returnValue(self.ctrls)

    @setting(20, 'List Devices', returns=['*s'])
    def list_devices(self, c):
        """Get a list of devices."""
        return sorted(self.devices.keys())

    @inlineCallbacks
    def startRefreshLoop(self):
        while self.keepRefreshing:# & 'IBCL' in self.client.servers:
            try:
                yield self.refresh_devices()
            except:
                import traceback
                print "An error occured while refreshing devices:"
                traceback.print_exc()
            if self.keepRefreshing:
                yield util.wakeupCall(self.refreshInterval)
    
    @inlineCallbacks
    def refresh_devices(self):
        """Refresh the device list.
        NOTES:
        This setting uses the timeout set for this context (0.3 s by default)"""
        
        # refresh controllers
        oldCont = self.ctrls
        yield self.client.refresh()
        self.ctrls = yield self.client.ibcl.controllers()
        newCont = set(self.ctrls) - set(oldCont)
        for cont in newCont:
            self.initController(cont)
            
        # look for devices at every possible address
        if not len(self.ctrls):
            print "There are no controllers connected."
        else:
            newdevices = {}
            for cont in self.ctrls:
                print cont + " scanning for devices..."
                for gpibaddr in range(0,32):
                    addr = cont + '::' + str(gpibaddr)
                    if addr not in self.devices.keys():     # ignores devices already connected (cannot disconnect)
                        result = yield self.writeGPIB(addr, self.refreshTimeout, '*IDN?')
                        if not result[15]:
                            idnstr = (yield self.readGPIB(addr, self.refreshTimeout))[0]
                            if idnstr is not '':
                                mfr, model = [s.strip() for s in idnstr.split(',')][:2]
                                newdevices[addr] = mfr + ' ' + model
                                print "%2d - %s" % (gpibaddr, mfr[0:10] + ' ' + model[0:10])
                            else:
                                newdevices[addr] = ''
                                print "%2d - something" % gpibaddr
                        else:
                            print "%2d - " % gpibaddr
                    else:
                        print "%2d - device already connected" % gpibaddr
            # tell the Device Manager about new additions
            for addr in newdevices.keys():
                self.devices[addr] = newdevices[addr]
                self.sendDeviceMessage('GPIB Device Connect', addr)
            
    def sendDeviceMessage(self, msg, addr):
        print msg + ': ' + addr
        self.client.manager.send_named_message(msg, (self.name, addr))
        
    @setting(3, 'Write', data=['s'], returns=[''])
    def write(self, c, data):
        """Send GPIB data"""
        if not ('addr' in c):
            raise Exception("No address selected!")
        if not ('timeout' in c):
            raise Exception("No timeout selected!")
        state = yield self.writeGPIB(c['addr'], c['timeout'], data, c.ID)

    @setting(4, 'Read', bytes=['w'], returns=['s'])
    def read(self, c, bytes=None):
        """Reads GPIB data"""
        if not ('addr' in c):
            raise Exception("No address selected!")
        if not ('timeout' in c):
            raise Exception("No timeout selected!")
        totalres = ""
##        if bytes is None or bytes == 0:
            # read until carriage return
        for block in range(bytes/10000):
            res, state = yield self.readGPIB(c['addr'], c['timeout'], 10000, c.ID)
            totalres += res
        if bytes%10000 > 0:
            res, state = yield self.readGPIB(c['addr'], c['timeout'], bytes%10000, c.ID)
            totalres += res
        returnValue(totalres)
        
    @inlineCallbacks
    def readGPIB(self, addr, timeout, bytes=1000, ctxt=(0,0)):
        cont, gpibaddr = addr.split('::')
        yield self.client.ibcl.select(cont, context=ctxt)   # select controller
        tmo = self.IBCLtimeoutIndex(timeout)
        res = yield self.client.ibcl.command('%X %X %X %X read' % (int(gpibaddr), self.buffer, bytes, tmo), timeout+0.1, context=ctxt)
        state = int(res[0][0],16)
        state = [(state & 2**b)>0 for b in range(16)]
        res = res[0][1]
        if '%' in res:
            for old, new in replacements:
                res = res.replace(old, new)
        returnValue((res, state))

    @inlineCallbacks
    def writeGPIB(self, addr, timeout, data, ctxt=(0,0)):
        cont, gpibaddr = addr.split('::')
        yield self.client.ibcl.select(cont, context=ctxt)   # select controller
        tmo = self.IBCLtimeoutIndex(timeout)
        res = yield self.client.ibcl.command('%X " %s" %X write' % (int(gpibaddr), data, tmo), timeout+0.1, context=ctxt)
        state = int(res[0][0], 16)
        state = [(state & 2**b)>0 for b in range(16)]
        returnValue(state)
    
__server__ = IBCLGPIBServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)    
