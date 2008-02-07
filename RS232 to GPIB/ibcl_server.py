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

class IBCLServer(LabradServer):
    name = 'IBCL'

    Links = [{'Name':     'Governator GPIB-422CT',
              'server':   'governator_serial_server',
              'port':     'COM1',
              'settings': (19200, 7, 'E', 1)}]

    @inlineCallbacks
    def initServer(self):
        self.controllers = []
        yield self.findControllers()

    @inlineCallbacks
    def findControllers(self):
        cxn = self.client
        for S in self.Links:
            if S['server'] in cxn.servers:
                log.msg('%s:' % S['Name'])
                ser = cxn[S['server']]
                ports = yield ser.list_serial_ports()
                if S['port'] in ports:
                    yield self.connectController(ser, S)    
        log.msg('Server ready')

    @inlineCallbacks
    def connectController(self, ser, G):
        G['server'] = ser
        port = G['port']
        ctx  = G['context'] = ser.context()
        log.msg('  Connecting to %s...' % port)
        try:
            res = yield ser.open(port, context=ctx)
            ready = res==port
        except:
            ready = False
        if not ready:
            log.msg('    ERROR: Can''t open port')
            return
        log.msg('    Connected');
            
        # set up port parameters
        p = ser.packet(context=ctx)\
               .baudrate(G['settings'][0])\
               .bytesize(G['settings'][1])\
               .parity  (G['settings'][2])\
               .stopbits(G['settings'][3])\
               .timeout (T.Value(0, 's'))
        yield p.send()
        res = yield ser.read(context=ctx)
        while res:
            res = yield ser.read(context=ctx)
        yield ser

        # initialize IBCL
        log.msg('  Starting IBCL...')
        p = ser.packet(context=ctx)\
               .timeout(T.Value(1, 's'))\
               .write('ibcl\r')\
               .read(6L)
        res = yield p.send()
        if 'read' not in res.settings:
            log.msg('    ERROR 1: Can''t send data')
            return
        if res['read']=='\r\nok\r\n':
            log.msg('    Ready')
            self.controllers += [G]
            return
        if res['read']!='ibcl \r':
            if res['read']=='':
                log.msg('    ERROR 2: No response')
            else:
                log.msg('    ERROR 3: Invalid response: %s' % repr(res['read']))
            return
        res = yield ser.read(5L, context=ctx)
        if res!='\nok\r\n':
            log.msg('    ERROR 4: Invalid response: %s' % repr(res))
            return
        log.msg('    Already running')
        log.msg('  Resetting IBCL...')
        p = ser.packet(context=ctx)\
               .write('cold\r')\
               .read(11L)
        res = yield p.send()
        if 'read' not in res.settings:
            log.msg('    ERROR 5: "cold" command failed')
            return
        if res['read']=='cold \r\nok\r\n':
            log.msg('    Ready')
            self.controllers += [G]
        else:
            log.msg('    ERROR 6: "cold" command failed')
        

    @setting(1, 'Controllers', returns=['*s: Controllers'])
    def commands(self, c):
        """Request a list of available IBCL controllers."""
        return [C['Name'] for C in self.controllers]


    @setting(10, 'Select', name=['s'], returns=[])
    def select(self, c, name):
        """Select active controller"""
        c['ctrl']=None
        for l in self.controllers:
            if l['Name']==name:
                c['ctrl']=l
        if c['ctrl'] is None:
            raise Exception('Invalid controller name')

    @setting(20, 'Command', cmd=['s'], timeout=['v[s]'], returns=['*ss: response, status'])
    def command(self, c, cmd, timeout=T.Value(60,'s')):
        """Send command to selected controller"""
        if 'ctrl' not in c:
            raise Exception('No controller selected')
        p = c['ctrl']['server'].packet(context=c['ctrl']['context'])\
                               .timeout(timeout)\
                               .write('%s\r' % cmd)\
                               .read_line(key='echo')\
                               .read_line(key='status')
        res = yield p.send()
        status=res['status']
        ans=[res['echo'][len(cmd)+1:]]
        empties=5
        while ('ok' not in status) and ('? MSG #' not in status):
            ans.append(status)
            status=yield c['ctrl']['server'].read_line(context=c['ctrl']['context'])
            if status=='':
                empties-=1
                if empties==0:
                    raise Exception('Invalid response!')
        returnValue((ans, status))

__server__ = IBCLServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)    
