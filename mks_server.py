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

"""
### BEGIN NODE INFO
[info]
name = MKS Gauge Server
version = 2.0
description = 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

import labrad 

from labrad import types as T, util
from labrad.server import LabradServer, setting

from twisted.python import log
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor

from datetime import datetime

CHANNELS = ['ch1', 'ch2']


class MKSServer(LabradServer):
    name = 'MKS Gauge Server'
    
    @inlineCallbacks
    def initServer(self):
        cxn = yield self.client
        self.name = 'mks_server_2'
        self.fridge = self.fridgeAutoDetect()

        reg = cxn.registry
        reg.cd(['','Servers','MKS_Gauge_Server',self.fridge])
        gauge_list = reg.get('gauge_list')
        serial_server = yield reg.get('serial_server')
        yield reg.cd('gauges')
        gauges = []
        
        loopvar = yield reg.dir()
        for key in loopvar[1]:
            gaugeentry = yield reg.get(key)
            dictentry = {gaugeentry[0][0]:gaugeentry[0][1],gaugeentry[1][0]:gaugeentry[1][1],gaugeentry[2][0]:gaugeentry[2][1]}
            gauges.append(dictentry)
        self.gaugeServers = [{'server' : serial_server, 'ID':None, 'gauges':gauges}]
        lc = twisted.internet.task.loopingCall(self.update_readings)
        lc.start(1.0)
        self.gauges = []
        yield self.findGauges()

        
    def fridgeAutoDetect(self):
        cxn = self.client
        attributeList = cxn.__dict__
        if attributeList.has_key('node_vince'):
            myFridge = 'Vince'
            return myFridge
        elif attributeList.has_key('node_dr'):
            myFridge = 'Jules'
            return myFridge
        elif attributeList.has_key('node_trench'):
            myFridge = 'DryDR'
            return myFridge

    def serverConnected(self, ID, name):
        """Try to connect to gauges when a server connects."""
        self.findGauges()
        
    def serverDisconnected(self, ID, name):
        """Drop gauges from the list when a server disconnects."""
        for S in self.gaugeServers:
            if S['ID'] == ID:
                print "'%s' disconnected." % S['server']
                S['ID'] = None
                removals = [G for G in self.gauges if G['server'].ID == ID]
                for G in removals:
                    self.gauges.remove(G)
        
    @inlineCallbacks
    def findGauges(self):
        """Look for gauges and servers."""
        cxn = self.client
        yield cxn.refresh()
        log.msg('findGauges')
        log.msg(self.gaugeServers)
        for S in self.gaugeServers:
            if S['ID'] is not None:
                continue
            if S['server'] in cxn.servers:
                log.msg('Connecting to %s...' % S['server'])
                ser = cxn[S['server']]
                ports = yield ser.list_serial_ports()
                for G in S['gauges']:
                    if G['port'] in ports:
                        yield self.connectToGauge(ser, G)
                S['ID'] = ser.ID
        log.msg('Server ready')


    @inlineCallbacks
    def connectToGauge(self, ser, G):
        """Connect to a single gauge."""
        port = G['port']
        ctx = G['context'] = ser.context()
        log.msg('  Connecting to %s...' % port)
        try:
            res = yield ser.open(port, context=ctx)
            ready = G['ready'] = res==port
        except:
            ready = False
        if ready:
            # set up baudrate
            p = ser.packet(context=ctx)\
                   .baudrate(9600L)\
                   .timeout()
            yield p.send()
            res = yield ser.read(context=ctx)
            while res:
                res = yield ser.read(context=ctx)
            yield ser.timeout(T.Value(2, 's'), context=ctx)

            # check units
            p = ser.packet()\
                   .write_line('u').pause(T.Value(0.02, 's'))\
                   .read_line(key='units')
            res = yield p.send(context=ctx)
            if 'units' in res.settings:
                G['units'] = res['units']
            else:
                G['ready'] = False

            # create a packet to read the pressure
            p = ser.packet(context=ctx)\
                   .write_line('p').pause(T.Value(0.02, 's'))\
                   .read_line(key='pressure').pause(T.Value(0.02, 's'))
            G['packet'] = p

            G['server'] = ser
            G['readings'] = (T.Value(float('nan'), 'Torr'), T.Value(float('nan'), 'Torr'))

        if ready:
            self.gauges.append(G)
            log.msg('    OK')
        else:
            log.msg('    ERROR')
        

    @setting(2, 'Get Gauge List', returns=['*s: Gauge names'])
    def list_gauges(self, c):
        """Request a list of available gauges."""
        gauges = [G[ch] for G in self.gauges
                        for ch in CHANNELS if G[ch]]
        return gauges

    @inlineCallbacks
    def update_readings(self):
        for G in self.gauges:
            try:
                result = yield G['packet'].send()
            except Exception:
                continue
            if result:
                try:
                    (rdg1, rdg2) = result.pressure.split()
                except Exception:
                    (rdg1, rdg2) = ('Off', 'Off')
                try: data1 = float(rdg1) except Exception: data1 = float('NaN')
                try: data2 = float(rdg2) except Exception: data2 = float('NaN')
                if G[0] and math.isnan(data1): print 'gauge %s returns NaN (%s:ch1)' % (G[0], G['port'])
                if G[1] and math.isnan(data2): print 'gauge %s returns NaN (%s:ch2)' % (G[1], G['port'])
                G['reading'] = T.Value(data1, 'Torr'), T.Value(data2, 'Torr')
                
    @setting(1, 'Get Readings', returns=['*v[Torr]: Readings'])
    def get_readings(self, c):
        """Request current readings."""
        result = []
        for G in self.gauges:
            for ch in CHANNELS:
                if G[ch]:
                    readings += [G['reading'][ch]]
        return readings
    @setting(2, 'Get Named Readings', returns=['*(s, v[Torr])'])
    def get_named_readings(self, c):
        result = []
        for G in self.gauges:
            for ch in CHANNELS:
                if G[ch]:
                    readings += [(G[ch], G['reading'][ch])]
    
        packagedreadings = zip(gauge_list,readings)#@#
        returnValue(packagedreadings)#@#
        
__server__ = MKSServer()

if __name__ == '__main__':
    util.runServer(__server__)
